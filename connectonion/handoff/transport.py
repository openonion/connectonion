"""How a bundle and its replies reach the other side: mail first, then the agent inbox.

Mail is for discovery: the first handoff goes to a person, whose agent address is
not known yet. Once it is (the code carries the sender's, an acceptance carries the
recipient's, and each side saves the other as a contact), messages go to that agent's
inbox on the backend (`/api/v1/messages`, #2410) instead of through the mail service.
Both work while the other side is offline, and no Host has to be running. `deliver`
and `fetch` are the only two functions that know this.
"""

import json
import os
import re

from ..address import agent_email
from ..environment import global_config_dir

SUBJECT_PREFIX = "[co handoff] "


def contacts_file():
    return global_config_dir() / "handoff" / "contacts.json"


def contacts() -> dict:
    """name → {"mail": where a handoff to them is delivered, "agent": their 0x address once known}.

    Names only. Who may call this agent is the trust list (co trust list), which `meet` also updates.
    """
    path = contacts_file()
    book = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {name: entry if isinstance(entry, dict) else {"mail": entry} for name, entry in book.items()}


def _save(book: dict) -> None:
    contacts_file().parent.mkdir(parents=True, exist_ok=True)
    contacts_file().write_text(json.dumps(book, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_contact(name: str, address: str) -> str:
    mail = mail_address(address)
    book = contacts()
    book[name.lower()] = {"mail": mail, "agent": address.lower()} if "@" not in address else {"mail": mail}
    _save(book)
    return mail


def meet(mail: str, agent: str, inbox: bool = False, reason: str = None) -> str:
    """After a handoff is accepted, each side makes the other its agent's contact. Returns their name.

    `inbox` records that their co reads the agent inbox (they used a coh2 code), so later
    handoffs to them go there; a contact without it gets mail, which every version reads.

    `agent` joins this identity's trust contacts (co trust list). The name book learns that `mail`
    reaches them: a name already reached at `mail`, or already known as `agent`, keeps its name and
    gains the agent; anyone else is saved under the mailbox's name. `reason` (which handoff)
    goes into the record.
    """
    from ..network.trust.tools import promote_to_contact
    promote_to_contact(agent, global_config_dir(), reason)
    book = contacts()
    name = next((n for n, e in book.items() if e["mail"] == mail or e.get("agent") == agent), None)
    if name is None:
        name = mail.split("@")[0].lower()
        name = f"{name}-{agent[2:8]}" if name in book else name
        book[name] = {"mail": mail}
    book[name]["agent"] = agent
    if inbox:
        book[name]["inbox"] = True
    _save(book)
    return name


def mail_address(address: str) -> str:
    """An email stays as it is; a 0x agent address becomes that agent's mailbox."""
    if "@" in address:
        return address
    if re.fullmatch(r"0x[0-9a-fA-F]{64}", address):
        return agent_email(address.lower())
    raise ValueError(f"'{address}' is neither an email nor a full 0x agent address (0x + 64 hex)")


def my_address() -> str:
    """This agent's full 0x address: the selected identity, whose token reads the inbox (#2424 review)."""
    from ..project import project_identity
    return project_identity()["address"]


def resolve(who: str) -> str | None:
    """Recipient mailbox for a name, email or 0x address; None for an unknown name.

    Names come first: a peer met through its agent mailbox is named `0x` + 10 hex, like the mailbox."""
    entry = contacts().get(who.lower())
    if entry:
        return entry["mail"]
    if "@" in who or who.startswith("0x"):
        return mail_address(who)
    return None


def deliver(to: str, subject: str, body: str, idempotency_key: str, agent: str | None = None) -> dict:
    """Send to `agent`'s inbox when known (passed, or a contact that reads its inbox), else mail `to`.

    Returns send_email's result dict; an inbox delivery adds "via": "agent inbox"."""
    agent = agent or next((e["agent"] for e in contacts().values() if e["mail"] == to and e.get("inbox")), None)
    if agent:
        return _post_message(agent, json.dumps({"subject": subject, "message": body, "from": os.getenv("AGENT_EMAIL")}))
    return _send_mail(to, subject, body, idempotency_key)


def fetch(last: int = 200) -> list[dict]:
    """Recent mail and inbox messages that carry a handoff, newest first, in the mail's shape."""
    found = [m for m in _read_mail(last) + _read_messages()
             if m.get("subject", "").startswith(SUBJECT_PREFIX)]
    return sorted(found, key=lambda m: str(m.get("timestamp", "")), reverse=True)


def _send_mail(to: str, subject: str, body: str, idempotency_key: str) -> dict:
    from ..useful_tools.send_email import send_email
    return send_email(to, subject, body, idempotency_key=idempotency_key)


def _read_mail(last: int) -> list[dict]:
    from ..useful_tools.get_emails import get_emails
    return get_emails(last=last)


def _post_message(agent: str, body: str) -> dict:
    import requests
    from ..backend import backend_url
    from ..credentials import require_ambient_api_key
    response = requests.post(f"{backend_url()}/api/v1/messages", json={"to": agent, "body": body},
                             headers={"Authorization": f"Bearer {require_ambient_api_key()}"}, timeout=30)
    if not response.ok:
        return {"success": False, "error": f"agent inbox answered {response.status_code}: {response.text[:200]}"}
    return {"success": True, "message_id": f"agent-message-{response.json()['id']}",
            "from": os.getenv("AGENT_EMAIL"), "via": "agent inbox"}


def _read_messages() -> list[dict]:
    """This agent's inbox, as mail-shaped dicts. A backend without the inbox yet (404) has none."""
    import requests
    from ..backend import backend_url
    from ..credentials import require_ambient_api_key
    headers, rows = {"Authorization": f"Bearer {require_ambient_api_key()}"}, []
    while True:   # the backend pages oldest first, so read to the end for the newest
        response = requests.get(f"{backend_url()}/api/v1/messages", headers=headers, timeout=30,
                                params={"after": rows[-1]["id"] if rows else 0, "limit": PAGE})
        if response.status_code == 404:
            return []
        response.raise_for_status()
        page = response.json()["messages"]
        rows += page
        if len(page) < PAGE:
            break
    return [mail for mail in map(_as_mail, rows) if mail]


PAGE = 500


def _as_mail(message: dict) -> dict | None:
    """A handoff message as a mail-shaped dict; None for anything else another agent posted."""
    content = json.loads(message["body"])   # the backend takes only JSON objects
    if not isinstance(content, dict) or not isinstance(content.get("subject"), str):
        return None
    return {"id": f"agent-message-{message['id']}", "from": content.get("from") or message["from_address"],
            "subject": content["subject"], "message": content.get("message", ""), "timestamp": message["created_at"]}


def sent_status(to: str, subject: str) -> dict | None:
    """The mail service's own record of the sent message, or None if it has none."""
    from ..useful_tools.get_emails import get_sent
    return next((m for m in get_sent(last=50, to=to) if m.get("subject") == subject), None)

"""How a bundle and its replies reach the other side: mail first, then the agent inbox.

Mail is for discovery: the first handoff goes to a person, whose agent address is
not known yet. Once it is (the code carries the sender's, an acceptance carries the
recipient's, and each side saves the other as a contact), messages go to that agent's
inbox on the backend (`/api/v1/messages`, #2410) instead of through the mail service.
Both work while the other side is offline, and no Host has to be running. `deliver`
and `fetch` are the only two functions that know this.
"""

import html
import hashlib
import json
import os
import re

from ..address import agent_email
from ..environment import global_config_dir

SUBJECT_PREFIX = "[co handoff] "
MARKER = "BEGIN CO HANDOFF"   # in every handoff body: a first mail's subject reads like a person's, not like co


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


def meet(mail: str, agent: str, inbox: bool = False, reason: str = None, level: str = "handoffs") -> str:
    """After a handoff is accepted, each side admits the other at `level`: handoffs, which exchanges handoff
    messages and nothing else, unless a caller asks for more. Returns their name.

    `inbox` records that their co reads the agent inbox (they used a coh2 code), so later
    handoffs to them go there; a contact without it gets mail, which every version reads.

    `agent` joins this identity's trust contacts (co trust list). The name book learns that `mail`
    reaches them: a name already reached at `mail`, or already known as `agent`, keeps its name and
    gains the agent; anyone else is saved under the mailbox's name. `reason` (which handoff)
    goes into the record.
    """
    from ..network.trust.tools import admit_for_handoffs, promote_to_contact
    admit = admit_for_handoffs if level == "handoffs" else promote_to_contact
    admit(agent, global_config_dir(), reason)
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
    """A reply: to `agent`'s inbox when known (passed, or a contact that reads its inbox), else mail `to`.

    Returns send_email's result dict; an inbox delivery adds "via": "agent inbox"."""
    agent = agent or _inbox_agent(to)
    if agent:
        return _post_message(agent, json.dumps({"subject": subject, "message": body, "from": os.getenv("AGENT_EMAIL")}))
    return _send_mail(to, subject, body, idempotency_key)


def _inbox_agent(to: str) -> str | None:
    return next((e["agent"] for e in contacts().values() if e["mail"] == to and e.get("inbox")), None)


VIA = ("auto", "mcp", "gmail", "outlook", "agent")


def own_mailboxes() -> dict[str, str]:
    """{"gmail" | "outlook": address} for each mailbox of the person's own connected with send access."""
    from ..provider_credentials import resolve_provider_credentials
    found = {}
    for provider, channel, scope in (("google", "gmail", "gmail.send"), ("microsoft", "outlook", "Mail.Send")):
        record = resolve_provider_credentials(provider)
        if scope in record.scopes and (record.get("ACCESS_TOKEN") or record.get("REFRESH_TOKEN")):
            found[channel] = record.get("EMAIL") or ""
    return found


def own_mailbox() -> tuple[str, str] | None:
    """The first of them, Gmail before Outlook: where a handoff goes from unless --via names one."""
    return next(iter(own_mailboxes().items()), None)


def channel_for(via: str) -> str:
    """Which mailbox a new handoff goes out from: asked for, else the person's own, else the agent's (#2478)."""
    return via if via != "auto" else (own_mailbox() or ("agent", ""))[0]


def hand_over(to: str, mail: dict, idempotency_key: str, via: str = "auto") -> dict:
    """A new handoff: the person's mail through `via`, and a copy in their agent's inbox when they are a contact.

    "mcp" mails nothing: the coding agent sends `mail` with its own mail tool, from the person's mailbox.
    Returns {success, via, from, message_id, inbox, mailed, error}: success when either arrived."""
    agent = _inbox_agent(to)
    if agent:   # the subject prefix and hidden bundle are how co handoff inbox finds it there
        posted = _post_message(agent, json.dumps({"subject": SUBJECT_PREFIX + mail["subject"],
                                                  "message": mail.get("inbox_html", mail["html"]),
                                                  "from": os.getenv("AGENT_EMAIL")}))
        if not posted.get("success"):
            return posted
    channel = channel_for(via)
    sent = {"success": True, "via": "mcp"} if channel == "mcp" else _mail_from(channel, to, mail, idempotency_key)
    mailed = channel != "mcp" and bool(sent.get("success"))
    return {**sent, "inbox": bool(agent), "mailed": mailed, "success": bool(sent.get("success")) or bool(agent)}


def _mail_from(channel: str, to: str, mail: dict, idempotency_key: str) -> dict:
    if channel == "agent":
        return {**_send_mail(to, mail["subject"], mail["html"], idempotency_key), "via": "agent mailbox"}
    tool = _own_tool(channel)
    said = tool.send(to, mail["subject"], mail["text"], html=mail["html"])
    found = re.search(r"Message ID: (\S+)", said)
    return {"success": True, "via": channel, "from": own_mailboxes().get(channel, ""),
            "message_id": found.group(1) if found else ""}


def _own_tool(channel: str):
    if channel == "gmail":
        from ..useful_tools.gmail import Gmail
        return Gmail(emails_csv=None, contacts_csv=None)
    from ..useful_tools.outlook import Outlook
    return Outlook()


def fetch(last: int = 200) -> list[dict]:
    """Recent mail and inbox messages that carry a handoff, newest first, in the mail's shape."""
    found = [m for m in _read_mail(last) + _read_messages()
             if m.get("subject", "").startswith(SUBJECT_PREFIX) or MARKER in m.get("message", "")]
    return sorted(found, key=lambda m: str(m.get("timestamp", "")), reverse=True)


def mail_person(to: str, subject: str, body: str, idempotency_key: str) -> dict:
    """Mail a person directly (never their agent's inbox): the sender's own address, when a question waits on them.

    From their own mailbox when co has one (to itself, so it lands in their inbox, not spam), else the agent's."""
    own = own_mailbox()
    if not own:
        return _send_mail(to, subject, body, idempotency_key)
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    return _mail_from(own[0], to, {"subject": subject, "text": text, "html": body}, idempotency_key)


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


VIEWER = "https://o.openonion.ai/h/"


def new_drop_id() -> str:
    """Chosen here, not by the backend: the prompt that goes in the drop carries a code that names it."""
    import secrets
    return secrets.token_urlsafe(24)


def viewer_url(drop_id: str) -> str:
    """The page a person reads the handoff on, before installing anything (oo-frontend /h/<id>)."""
    return VIEWER + drop_id


def agent_url(drop_id: str) -> str:
    """The plain-text page the one line a person pastes tells their agent to read: the whole prompt."""
    return viewer_url(drop_id) + "/codex"


def page_bundle(code: dict) -> dict:
    """The handoff as its public page shows it, checked against the code: reading it claims nothing."""
    from .bundle import seal
    import requests
    from ..backend import backend_url
    response = requests.get(f"{backend_url()}/api/v1/drops/{code['drop']}/view", timeout=30)
    response.raise_for_status()
    bundle = response.json()["bundle"]
    if seal(bundle)["content_hash"] != code["hash"]:
        raise ValueError(f"the handoff {code['id']} on the server differs from what the sender approved")
    return bundle


def page_prompt(drop_id: str) -> str:
    """The whole prompt a handoff's page shows its recipient's agent (public, like the page)."""
    import requests
    from ..backend import backend_url
    response = requests.get(f"{backend_url()}/api/v1/drops/{drop_id}/view", timeout=30)
    response.raise_for_status()
    return response.json().get("prompt", "")


def drop(bundle: dict, code: list = (), context: str = "", drop_id: str = None, prompt: str = "", key: str = "") -> str:
    """Hold the handoff on the backend until the recipient accepts; returns the id their code carries.

    A first recipient has no agent address until they install co, so the agent inbox cannot hold it
    for them (#2459). With it go the code they cannot fetch (#2469) and the redacted session copy, so
    nothing waits on the sender's machine being online. Drops expire after 30 days. `key` is the code's
    secret: only its hash goes to the server, which then gives the whole drop to its holder alone (#2496)."""
    body = {"bundle": bundle, "code": list(code), "context": context, "prompt": prompt}
    return _put_drop(json.dumps(body, ensure_ascii=False), drop_id or new_drop_id(),
                     hashlib.sha256(key.encode()).hexdigest() if key else None)


def pickup(code: dict) -> dict:
    """{bundle, code, context} for `code`: refused unless the bundle is exactly what the sender approved
    and each patch matches the digest the approved bundle records."""
    from .bundle import seal
    from .sessions import patch_digest
    held = _get_drop(code["drop"], code["secret"])
    if held is None:   # withdrawn, expired, or sent by co 1.9.2b26 or earlier, whose copy is not served
        return {"gone": True}
    if not held:       # another agent read it first and claimed it (oo-api#267)
        return {"taken": True}
    body = json.loads(held)
    if seal(body["bundle"])["content_hash"] != code["hash"]:
        raise ValueError(f"the handoff {code['id']} on the server differs from what the sender approved")
    for entry, patch in zip(body["bundle"].get("code") or [], body.get("code") or []):
        if patch and patch_digest(patch)["sha256"] != (entry.get("patch") or {}).get("sha256"):
            raise ValueError(f"the code for {code['id']} on the server differs from what the sender approved")
    return {"bundle": body["bundle"], "code": body.get("code") or [], "context": body.get("context", "")}


def _put_drop(body: str, drop_id: str, key_hash: str | None) -> str:
    import requests
    from ..backend import backend_url
    from ..credentials import require_ambient_api_key
    response = requests.post(f"{backend_url()}/api/v1/drops", json={"id": drop_id, "body": body, "key_hash": key_hash},
                             headers={"Authorization": f"Bearer {require_ambient_api_key()}"}, timeout=30)
    response.raise_for_status()
    return response.json()["id"]


def _delete_drop(drop_id: str) -> None:
    import requests
    from ..backend import backend_url
    from ..credentials import require_ambient_api_key
    response = requests.delete(f"{backend_url()}/api/v1/drops/{drop_id}",
                               headers={"Authorization": f"Bearer {require_ambient_api_key()}"}, timeout=30)
    response.raise_for_status()


def withdraw(page: str) -> None:
    """Take a handoff's page down, and its pickup with it: only the agent that dropped it can (#2492)."""
    _delete_drop(page.rstrip("/").rsplit("/", 1)[1])


def _get_drop(drop_id: str, key: str) -> str | None:
    import requests
    from ..backend import backend_url
    from ..credentials import require_ambient_api_key
    response = requests.get(f"{backend_url()}/api/v1/drops/{drop_id}", timeout=30,
                            headers={"Authorization": f"Bearer {require_ambient_api_key()}", "X-Drop-Key": key})
    if response.status_code == 409:   # already accepted by another agent: "" says so
        return ""
    if response.status_code == 404:   # gone: None says so
        return None
    response.raise_for_status()
    return response.json()["body"]


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
            "sender": message["from_address"],   # who the backend says posted it; "from" is the poster's own word
            "subject": content["subject"], "message": content.get("message", ""), "timestamp": message["created_at"]}


def sent_status(to: str, subject: str) -> dict | None:
    """The mail service's own record of the sent message, or None if it has none."""
    from ..useful_tools.get_emails import get_sent
    return next((m for m in get_sent(last=50, to=to) if m.get("subject") == subject), None)

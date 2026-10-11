"""How a bundle reaches the recipient: today, their agent mailbox.

Every co identity has a mail address, delivery works while the recipient is
offline, and no Host has to be running. `deliver` and `fetch` are the only two
functions that know this; a direct agent-to-agent route (`co host`) replaces
them later without touching drafting, preview or opening.
"""

import json
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


def meet(mail: str, agent: str) -> str:
    """After a handoff is accepted, each side makes the other its agent's contact. Returns their name.

    `agent` joins this identity's trust contacts (co trust list). The name book learns that `mail`
    reaches them: a name already reached at `mail`, or already known as `agent`, keeps its name and
    gains the agent; anyone else is saved under the mailbox's name.
    """
    from ..network.trust.tools import promote_to_contact
    promote_to_contact(agent, global_config_dir())
    book = contacts()
    name = next((n for n, e in book.items() if e["mail"] == mail or e.get("agent") == agent), None)
    if name is None:
        name = mail.split("@")[0].lower()
        name = f"{name}-{agent[2:8]}" if name in book else name
        book[name] = {"mail": mail}
    book[name]["agent"] = agent
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
    """This agent's full 0x address (the global identity in ~/.co)."""
    from ..address import load
    return load(global_config_dir())["address"]


def resolve(who: str) -> str | None:
    """Recipient mailbox for a name, email or 0x address; None for an unknown name."""
    if "@" in who or who.startswith("0x"):
        return mail_address(who)
    entry = contacts().get(who.lower())
    return entry["mail"] if entry else None


def deliver(to: str, subject: str, body: str, idempotency_key: str) -> dict:
    """Send through the agent mailbox. Returns send_email's result dict."""
    from ..useful_tools.send_email import send_email
    return send_email(to, subject, body, idempotency_key=idempotency_key)


def fetch(last: int = 200) -> list[dict]:
    """Recent mail that carries a handoff, newest first."""
    from ..useful_tools.get_emails import get_emails
    return [m for m in get_emails(last=last) if m.get("subject", "").startswith(SUBJECT_PREFIX)]


def sent_status(to: str, subject: str) -> dict | None:
    """The mail service's own record of the sent message, or None if it has none."""
    from ..useful_tools.get_emails import get_sent
    return next((m for m in get_sent(last=50, to=to) if m.get("subject") == subject), None)

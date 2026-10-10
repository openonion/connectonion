"""How a bundle reaches the recipient: today, their agent mailbox.

Every co identity has a mail address, delivery works while the recipient is
offline, and no Host has to be running. `deliver` and `fetch` are the only two
functions that know this; a direct agent-to-agent route (`co host`) replaces
them later without touching drafting, preview or opening.
"""

import json
import re

from ..environment import global_config_dir

AGENT_MAIL_DOMAIN = "mail.openonion.ai"
SUBJECT_PREFIX = "[co handoff] "


def contacts_file():
    return global_config_dir() / "handoff" / "contacts.json"


def contacts() -> dict:
    path = contacts_file()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def add_contact(name: str, address: str) -> str:
    mail = mail_address(address)
    book = contacts()
    book[name.lower()] = mail
    contacts_file().parent.mkdir(parents=True, exist_ok=True)
    contacts_file().write_text(json.dumps(book, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return mail


def mail_address(address: str) -> str:
    """An email stays as it is; a 0x agent address becomes that agent's mailbox."""
    if "@" in address:
        return address
    if re.fullmatch(r"0x[0-9a-fA-F]{64}", address):
        return f"{address[:10].lower()}@{AGENT_MAIL_DOMAIN}"
    raise ValueError(f"'{address}' is neither an email nor a full 0x agent address (0x + 64 hex)")


def resolve(who: str) -> str | None:
    """Recipient mailbox for a name, email or 0x address; None for an unknown name."""
    if "@" in who or who.startswith("0x"):
        return mail_address(who)
    return contacts().get(who.lower())


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

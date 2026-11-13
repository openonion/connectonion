"""
Purpose: The names the owner gave WhatsApp numbers, and turning a phone number or one of those names into the chat id a send needs (#2964)
LLM-Note:
  Dependencies: imports from [json, re, pathlib, inbox/store.py] and lazily [phonenumbers] for --country | imported by [inbox/whatsapp.py, cli/commands/whatsapp_commands.py] | tested by [tests/unit/test_whatsapp_contacts.py]
  Data flow: contacts add → add_contact() → contacts.json | send "<name>" or "+61…" → resolve_chat() → (jid, phone) | the listener's name_of() → saved_name()
  State/Effects: one JSON file, <inbox>/whatsapp/contacts.json, beside the session and the log | local only: nothing here talks to WhatsApp
  Integration: keyed by the user half of the JID, so `61412345678@s.whatsapp.net` and a record whose sender is `61412345678:12@…` match | `phone` is kept only for a contact added by number: a send to it asks the listener to check the number first, because a number is not yet a WhatsApp id
  Errors: a local number with no --country, a name already given to another number, and a name nobody has are ValueError with the next step in the sentence

Why a file of names and not WhatsApp's own contacts.  A linked device cannot
add to the phone's address book, and the names whatsmeow syncs are whatever
the person typed into their own profile, or nothing for someone who has never
written to this number. The owner's name for a new client is the one that
should show in `chats` and `log`, and it must exist before the first message.
"""

import json
import re
from pathlib import Path
from typing import Optional

from .store import default_home

CONTACTS_FILE = "contacts.json"
USER_SERVER = "s.whatsapp.net"
# Digits with the punctuation people write numbers with: "+61 412 345 678",
# "(02) 9876-5432". Anything else is a name.
_PHONE_LIKE = re.compile(r"\+?[\d\s().-]+")


def contacts_path() -> Path:
    return default_home("whatsapp") / CONTACTS_FILE


def read_contacts(path: Optional[Path] = None) -> dict:
    path = path or contacts_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, contacts: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(path.name + ".partial")
    staged.write_text(json.dumps(contacts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    staged.replace(path)


def _user_of(jid: str) -> str:
    return str(jid or "").split("@", 1)[0].split(":", 1)[0]


def is_phone(text: str) -> bool:
    return bool(_PHONE_LIKE.fullmatch(text.strip()))


def phone_digits(text: str, country: Optional[str] = None) -> str:
    """A phone number as WhatsApp's user part: country code and number, digits only.

    `--country AU` reads a local number the way that country dials it, so
    0412 345 678 becomes 61412345678. Without it a number has to carry its
    country code already: a leading 0 is refused, because 0412345678 sent as
    is names a different, or no, account and the answer would look like
    "not on WhatsApp".
    """
    raw = text.strip()
    if country:
        return _national(raw, country)
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw.startswith("00"):
        digits = digits[2:]
    elif raw.startswith("0"):
        raise ValueError(f"{text} is a local number; say which country with --country AU (or the "
                         f"person's country), or write it with the country code: +61…")
    if not 7 <= len(digits) <= 15:
        raise ValueError(f"{text} is not a phone number: expected the country code and number, "
                         "e.g. +61412345678")
    return digits


# --country is the one thing here that needs a library: every other path takes
# a number that already carries its country code.
PHONENUMBERS_MISSING = ("--country needs the phone number library, which comes with the WhatsApp extra. "
                        "Run: pip install 'connectonion[whatsapp]'  (with uv: uv pip install "
                        "'connectonion[whatsapp]'), or write the number with its country code: +61…")


def _national(raw: str, country: str) -> str:
    try:
        import phonenumbers
    except ImportError:
        raise ValueError(PHONENUMBERS_MISSING) from None

    try:
        parsed = phonenumbers.parse(raw, country.upper())
    except phonenumbers.NumberParseException as exc:
        raise ValueError(f"{raw} is not a phone number in {country.upper()}: {exc}") from None
    if not phonenumbers.is_possible_number(parsed):
        raise ValueError(f"{raw} is not a possible phone number in {country.upper()}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164).lstrip("+")


def find(contacts: dict, which: str) -> Optional[str]:
    """The key of the contact `which` names: its name (any case), its JID, or its number."""
    wanted = which.strip()
    for key, contact in contacts.items():
        if contact["name"].casefold() == wanted.casefold() or contact["jid"] == wanted:
            return key
    if "@" in wanted:
        return _user_of(wanted) if _user_of(wanted) in contacts else None
    if is_phone(wanted):
        digits = "".join(ch for ch in wanted if ch.isdigit())
        return digits if digits in contacts else None
    return None


def add_contact(target: str, name: str, note: str = "", country: Optional[str] = None,
                path: Optional[Path] = None) -> dict:
    """Save `name` for a JID or a phone number. Replaces the name a number already had."""
    path = path or contacts_path()
    name = name.strip()
    if not name:
        raise ValueError("a contact needs a name: --name \"Alex Example\"")
    if "@" in target:
        jid, phone = target.strip(), ""
    else:
        phone = phone_digits(target, country)
        jid = f"{phone}@{USER_SERVER}"
    contacts = read_contacts(path)
    key = _user_of(jid)
    taken = find(contacts, name)
    if taken is not None and taken != key:
        raise ValueError(f"{name!r} already names {contacts[taken]['jid']}. Pick another name, or "
                         f"first: co whatsapp contacts rm {name!r}")
    contacts[key] = {"name": name, "jid": jid, "phone": phone, "note": note}
    _write(path, contacts)
    return contacts[key]


def remove_contact(which: str, path: Optional[Path] = None) -> Optional[dict]:
    path = path or contacts_path()
    contacts = read_contacts(path)
    key = find(contacts, which)
    if key is None:
        return None
    removed = contacts.pop(key)
    _write(path, contacts)
    return removed


def resolve_chat(target: str, path: Optional[Path] = None) -> tuple:
    """(chat id, phone to check) for what `send` was given.

    A JID goes as it is. A saved name goes to that contact's JID. A phone
    number goes to `<digits>@s.whatsapp.net`, with the digits handed on so the
    listener can ask WhatsApp whether the number has an account before
    anything is sent to it; the same for a contact saved by number.
    """
    contacts = read_contacts(path)
    key = find(contacts, target)
    if key is not None:
        return contacts[key]["jid"], contacts[key].get("phone", "")
    if "@" in target:
        return target, ""
    if is_phone(target):
        digits = phone_digits(target)
        return f"{digits}@{USER_SERVER}", digits
    raise ValueError(f"no contact named {target!r}. Next: co whatsapp contacts ls")


def saved_name(users: list, path: Optional[Path] = None) -> str:
    """The owner's name for whichever of these ids (a number, its LID) has one."""
    contacts = read_contacts(path)
    for user in users:
        if user in contacts:
            return contacts[user]["name"]
    return ""

"""
Purpose: `co whatsapp lookup` and `co whatsapp contacts add|ls|rm` — check a new person's number and save them under a name before anything is sent to them (#2964)
LLM-Note:
  Dependencies: imports from [json, sys, inbox/whatsapp_contacts.py, cli/commands/listen_commands.py (_configured, errors), command_tips] | imported by [cli/main.py (the whatsapp group)] | tested by [tests/unit/test_whatsapp_contacts.py]
  Data flow: lookup → phone_digits() for each number → WhatsApp.lookup() through the listener's outbox → one JSON object per number on stdout | contacts add/rm → contacts.json | contacts ls → one line per contact
  State/Effects: lookup asks WhatsApp's servers and sends nothing to the person | contacts touch only <inbox>/whatsapp/contacts.json
  Integration: exit 0 every number is on WhatsApp, 4 at least one is not, 2 a number that is not a number, 1 the listener could not answer, 3 the listener cannot start
  Errors: a refusal is one sentence on stderr ending in the next command
"""

import json
import sys
from typing import List, Optional

from ...inbox.whatsapp_contacts import add_contact, phone_digits, read_contacts, remove_contact
from .command_tips import print_tip
from .listen_commands import _configured, _refused, errors

EXIT_NOT_ON_WHATSAPP = 4


def _digits_or_exit(phones: List[str], country: Optional[str]) -> List[str]:
    try:
        return [phone_digits(phone, country) for phone in phones]
    except ValueError as exc:
        errors.print(str(exc), style="red")
        sys.exit(2)


def handle_lookup(phones: List[str], country: Optional[str] = None) -> None:
    """One JSON line per number; exit 4 when any of them has no WhatsApp account."""
    digits = _digits_or_exit(phones, country)
    p = _configured("whatsapp", sends=True)
    try:
        results = p.lookup(digits)
    except RuntimeError as exc:
        _refused("whatsapp", exc)
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    absent = [r["phone"] for r in results if not r["on_whatsapp"]]
    if absent:
        errors.print(f"not on WhatsApp: {', '.join(absent)}. Nothing was sent to anyone.", style="yellow")
        sys.exit(EXIT_NOT_ON_WHATSAPP)
    print_tip(f'Next: co whatsapp contacts add {results[0]["jid"]} --name "<their name>"')


def handle_contacts_add(target: str, name: str, note: str = "", country: Optional[str] = None) -> None:
    try:
        contact = add_contact(target, name, note=note, country=country)
    except ValueError as exc:
        errors.print(str(exc), style="red")
        sys.exit(2)
    print(f"{contact['jid']}\t{contact['name']}")
    print_tip(f'Next: co whatsapp send "{contact["name"]}" "<text>"')


def handle_contacts_ls() -> None:
    contacts = read_contacts()
    if not contacts:
        errors.print("no saved contacts.", style="dim")
        print_tip('Next: co whatsapp contacts add +61412345678 --name "Alex Example"')
        return
    for contact in sorted(contacts.values(), key=lambda c: c["name"].casefold()):
        print(f"{contact['jid']}\t{contact['name']}\t{contact.get('note', '')}")


def handle_contacts_rm(which: str) -> None:
    removed = remove_contact(which)
    if removed is None:
        errors.print(f"no saved contact {which!r}. Next: co whatsapp contacts ls", style="red")
        sys.exit(1)
    print(f"{removed['jid']}\t{removed['name']}")

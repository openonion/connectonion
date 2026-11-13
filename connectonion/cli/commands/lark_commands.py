"""
Purpose: `co lark lookup | groups | contacts` (and the same under `co feishu`) — find the person or group to send to
LLM-Note:
  Dependencies: imports from [sys, listen_commands (_configured, _refused, errors), command_tips] | imported by [cli/main.py via _people_verbs()] | tested by [tests/unit/test_lark_finds_people.py]
  Data flow: lookup → Feishu.lookup() → POST /contact/v3/users/batch_get_id → the union id on stdout | groups → Feishu.groups() → GET /im/v1/chats → "chat_id<TAB>name" lines | contacts add → Feishu.person() (a phone is looked up once) → contacts.json in the inbox directory | contacts ls/rm → contacts.json
  State/Effects: lookup and groups are read-only API calls (each counts against the tenant's monthly quota) | contacts writes only contacts.json beside the inbox
  Integration: `co lark send <name>` reads the same contacts.json through Feishu.resolve() | ids printed here are what send, log --chat and reply take
  Errors: a missing scope prints the scope and the link that grants it (via _refused) and exits 1 | nobody found exits 1 with what to check | an unknown contact name exits 1 naming `contacts ls`
"""

import sys

from .command_tips import print_tip
from .listen_commands import _configured, _refused, errors


def handle_lookup(name: str, who: str) -> None:
    """Print the union id of the person with this email or phone number."""
    p = _configured(name)
    try:
        found = p.person(who)
    except Exception as exc:
        _refused(name, exc)
    print(found)
    print_tip(f'Next: co {name} send {found} "Hello"  or  co {name} contacts add <name> {who}')


def handle_groups(name: str) -> None:
    """The groups the bot is in, one "chat_id<TAB>name" line each."""
    p = _configured(name)
    try:
        groups = p.groups()
    except Exception as exc:
        _refused(name, exc)
    if not groups:
        errors.print(f"the bot is in no groups. Add it to one in {p.brand}, then run this again.", style="dim")
        return
    for group in groups:
        external = "\texternal" if group.get("external") else ""
        print(f"{group['chat_id']}\t{group.get('name') or '(no name)'}{external}")
    print_tip(f'Next: co {name} send "<name or chat_id>" "Hello"  or  co {name} log --chat <chat_id> -n 1')


def handle_contacts_add(name: str, contact: str, who: str) -> None:
    """Save a name for a person or chat, so `send <name>` reaches them."""
    p = _configured(name)
    try:
        # An email is kept as typed: Lark sends to one directly, so saving it
        # needs no lookup and no contact scope. A phone is looked up now, once.
        target = who if "@" in who else p.person(who)
    except Exception as exc:
        _refused(name, exc)
    contacts = p.contacts()
    contacts[contact] = target
    p.save_contacts(contacts)
    print(f"{contact}\t{target}")
    print_tip(f'Next: co {name} send "{contact}" "Hello"')


def handle_contacts_ls(name: str) -> None:
    """Every saved contact, one "name<TAB>id" line each."""
    from ...inbox import provider

    contacts = provider(name).contacts()
    if not contacts:
        errors.print("no contacts saved yet.", style="dim")
        print_tip(f"Next: co {name} contacts add <name> <email or +phone>")
        return
    for contact, target in sorted(contacts.items(), key=lambda item: item[0].casefold()):
        print(f"{contact}\t{target}")


def handle_contacts_rm(name: str, contact: str) -> None:
    """Forget a saved name. The person on Lark is not touched."""
    from ...inbox import provider

    p = provider(name)
    contacts = p.contacts()
    if contact not in contacts:
        errors.print(f"no contact named {contact!r}. Next: co {name} contacts ls", style="red")
        sys.exit(1)
    del contacts[contact]
    p.save_contacts(contacts)
    print(contact)

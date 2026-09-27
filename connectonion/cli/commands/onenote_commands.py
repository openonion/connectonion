"""
Purpose: `co onenote` — list, read and create OneNote pages from the terminal (#1887)
LLM-Note:
  Dependencies: imports from [sys, rich, useful_tools/onenote.OneNote, command_tips.print_tip] | imported by [cli/main.py] | tested by [tests/unit/test_onenote.py]
  Data flow: each handler builds OneNote() (refuses without Notes.ReadWrite.All, naming co auth microsoft) → calls one tool method → prints its text → names the next command
  State/Effects: create writes one new page; the other verbs only read
  Errors: ValueError and credential errors print as one red line plus the command to run, exit 1
"""

import sys
from typing import Optional

from rich.console import Console

from .command_tips import print_tip

errors = Console(stderr=True)


def _onenote():
    from ...useful_tools.onenote import OneNote
    return OneNote()


def _run(call, next_command: str) -> None:
    from ...provider_credentials import ProviderCredentialError
    try:
        print(call(_onenote()))
    except (ValueError, ProviderCredentialError) as exc:
        text = str(exc).strip()
        errors.print(text if "co " in text else f"{text} Next: co onenote ls", style="red", markup=False)
        sys.exit(1)
    print_tip(next_command)


def handle_onenote_ls() -> None:
    _run(lambda n: n.list_notebooks(), "Next: co onenote pages \"<section>\"")


def handle_onenote_pages(section: str, limit: int = 20) -> None:
    _run(lambda n: n.list_pages(section, max_results=limit), "Next: co onenote read <page id>")


def handle_onenote_read(page_id: str) -> None:
    _run(lambda n: n.read_page(page_id), "Next: co onenote ls")


def handle_onenote_create(section: str, title: str, text: Optional[str] = None) -> None:
    body = text if text is not None else ("" if sys.stdin.isatty() else sys.stdin.read())
    _run(lambda n: n.create_page(section, title, body), f"Next: co onenote pages \"{section}\"")

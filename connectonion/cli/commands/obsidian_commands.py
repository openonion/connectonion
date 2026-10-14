"""
Purpose: Show Obsidian's registered vaults from the terminal, without importing notes
LLM-Note:
  Dependencies: imports from [json, typer, rich.markup, cli/style.py, command_tips.py, useful_tools/obsidian.py] | imported lazily by [cli/main.py]
  Data flow: explicit --json → discover_vaults() → human rows or one JSON value → one Next line
  State/Effects: stdout/stderr only; no selected-vault state or row listing cache
  Errors: ObsidianError → cause and Next on stderr, exit 1; ValueError → same format, exit 2
"""

import json
from functools import wraps

import typer
from rich.markup import escape

from .. import style
from ...useful_tools import obsidian as api
from .command_tips import mark_next_step_named, print_tip, selected_tip


def _reported(handler):
    """The cause and one recovery command, with no partial stdout or traceback."""
    @wraps(handler)
    def run(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except (api.ObsidianError, ValueError) as error:
            out = style.console(stderr=True)
            out.print(f"{style.error('✗')} {escape(str(error))}")
            out.print(style.next_line(selected_tip(getattr(error, "next_step", api.HELP))))
            mark_next_step_named()
            raise typer.Exit(1 if isinstance(error, api.ObsidianError) else 2) from None
    return run


def _emit_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _tip(command: str, as_json: bool) -> None:
    """JSON keeps stdout parseable; its Next line goes to stderr, as Linear's does."""
    if not as_json:
        print_tip(f"Next: {command}")
        return
    style.console(stderr=True).print(style.next_line(selected_tip(command)))
    mark_next_step_named()


def _render_vaults(vaults: list[dict]) -> None:
    lines = [f"{style.count(len(vaults))} registered Obsidian vaults"]
    for vault in vaults:
        available = style.ok("available") if vault["available"] else style.warn("unavailable")
        opened = "open" if vault["open"] else "not open"
        lines.append(f"{escape(vault['name'])}  {style.path(vault['path'])}  {available}  {opened}")
    out = style.console()
    for line in lines:
        out.print(line)


@_reported
def handle_obsidian_vaults(*, json_output: bool = False) -> None:
    """List registered vaults without importing them or reading any notes."""
    vaults = api.discover_vaults()
    if json_output:
        _emit_json(vaults)
    else:
        _render_vaults(vaults)
    # notes belongs to -3; this names the workflow without registering it here.
    _tip('co obsidian vaults --json', json_output)

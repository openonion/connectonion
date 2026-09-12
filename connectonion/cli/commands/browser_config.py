"""
Purpose: `co browser config` — which browser engine this machine uses by default
LLM-Note:
  Dependencies: imports from [sys, environment.py, env_file.py, useful_tools/browser_tools/engine.py] | imported by [cli/main.py via the browser command group] | tested by [tests/unit/test_browser_default_engine.py]
  Data flow: no argument → read CO_BROWSER_ENGINE from the selected env file and say where it came from | an argument → normalize it, say what it costs, upsert_env into the selected file
  State/Effects: writes one name to the selected env file; starts no browser and charges nothing
  Integration: the setting is read by engine.effective_mode(), which a `--engine` flag still overrides in both directions | `co env` shows the value and whether the shell overrides it, which is where a wrong engine gets diagnosed
  Errors: a name that is not an engine exits 2 and lists the ones that are

Why the env file and not a browser config file: a small setting a command reads
belongs where every other small setting lives, so `co env` can answer "what does
this machine hold and where did it come from" for this one too — which is the
question someone debugging a wrong engine asks first. `.co/host.yaml` is for the
Host, which is long-running and has structure; a single name is not structure.
"""

import sys

from ...environment import display_path, process_environment, selected_env_file
from ...env_file import upsert_env
from ...useful_tools.browser_tools.engine import (
    ACCEPTED_MODES,
    AUTO,
    ENGINE_SETTING,
    SYSTEM,
    WTF,
    configured_mode,
    normalize_mode,
)

WHAT_EACH_ONE_IS = {
    AUTO: "system Chrome, and never a paid session unless one is asked for",
    SYSTEM: "the installed system Chrome, always free",
    WTF: "the WTF Browser, which is paid — every session it starts is billed",
}


def handle_browser_config(engine: str | None = None) -> int:
    """Show the default engine, or set it."""
    path = selected_env_file()

    if engine is None:
        current = configured_mode()
        if current is None:
            print(f"No default engine configured, so browser commands use "
                  f"{WHAT_EACH_ONE_IS[AUTO]}.")
        else:
            inherited = process_environment()
            source = ("your shell, which wins over the file"
                      if ENGINE_SETTING in inherited else display_path(path))
            print(f"Default engine: {current} — {WHAT_EACH_ONE_IS[current]}")
            print(f"Set in {source}.")
        print(f"Next: co browser config {WTF}")
        return 0

    try:
        chosen = normalize_mode(engine)
    except ValueError:
        print(f"{engine!r} is not an engine. Choose one of: "
              f"{', '.join(ACCEPTED_MODES)}", file=sys.stderr)
        print(f"Next: co browser config", file=sys.stderr)
        return 2

    if str(engine).strip().lower() != chosen:
        # `onion` is the old spelling and still works. Said once, here, rather
        # than left to be discovered from a mismatch between what was typed
        # and what `config` prints back.
        print(f"`{engine}` is now spelled `{chosen}`; saving `{chosen}`.")

    upsert_env(path, {ENGINE_SETTING: chosen})
    print(f"✓ Default engine: {chosen} — {WHAT_EACH_ONE_IS[chosen]}")
    print(f"  Saved to {display_path(path)}.")
    if chosen == WTF:
        # Named before it costs anything, not after. `--engine system` is the
        # way out that needs no file edited.
        print("  Every browser command now starts a paid session. "
              "Use --engine system for one that does not.")
    print(f"Next: co browser status")
    return 0

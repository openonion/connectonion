"""
Purpose: Main package entry point exposing public API for ConnectOnion framework
LLM-Note:
  Dependencies: imports from [core/, logger.py, llm_do.py, transcribe.py, prompts.py, debug/, useful_tools/, network/, address.py] | imported by [user code, tests/, examples/] | no direct tests (integration tests import from here)
  Data flow: loads the designated global keys.env (inherited process values win as whole provider records) → exports all public API symbols → user imports `from connectonion import Agent, llm_do, ...`
  State/Effects: loads global env at import time; CLI --env-file explicitly replaces the selected source before commands run
  Integration: exposes complete public API: Agent, LLM, Logger, create_tool_from_function, llm_do, transcribe, xray, event decorators, built-in tools, networking functions | __all__ defines explicit public exports
  Performance: .env loading happens at first package import
  Errors: none (import errors bubble from submodules)
ConnectOnion - A simple agent framework with behavior tracking.
"""

# Single source, in a module the CLI can import on its own — see _version.py.
# Auto-load .env files for the entire framework
import os as _os
import sys as _sys
from pathlib import Path as _Path
from types import ModuleType as _ModuleType

from ._version import __version__
from .environment import load_environment as _load_environment

# Console-script and `python -m` startup let Typer select the file first. This
# avoids reading a broken global file before a valid --env-file can be parsed.
# Ordinary SDK imports keep the documented eager global initialization.
_cli_startup = (_Path(_sys.argv[0]).stem in {"co", "co-script"} or
                (_sys.argv[0] == "-m" and
                 "connectonion.cli.main" in getattr(_sys, "orig_argv", ())))
if not _cli_startup:
    _load_environment()

# The public names are resolved on first use, not on import (PEP 562).
#
# These used to be plain `from .core import Agent` lines, which meant importing
# anything from this package imported all of it: the model SDKs, Gmail's Google
# credentials, the TUI and the whole network stack. `import connectonion.cli.main`
# runs this file first — Python offers no way around that — so `co --version`
# paid 3.4s to print six characters, and every `co` call paid it again.
#
# Only the lookup moves. `from connectonion import Agent` still works, still
# returns the same object, and the second read is a plain global: __getattr__
# writes what it resolved into globals(), so it runs once per name.
# Every subpackage the eager imports used to bind onto this package as a side
# effect. `tui` and `useful_plugins` are re-exported by nobody, which is exactly
# why they are listed: removing a name that used to resolve is not something a
# startup-time change should do quietly. Naming one here does not import it.
# Every submodule that resolved as an attribute before the package went lazy.
# The eager imports set these as a side effect; nothing does now, so each one
# has to be named. #632 named most of them and missed console, derive and
# useful_events_handlers -- each measured, one interpreter per attribute,
# because accessing any one of them imports the others and hides the gap.
_SUBMODULES = ("address", "console", "core", "debug", "derive", "logger",
               "network", "prompts", "tui", "useful_events_handlers",
               "useful_plugins", "useful_tools", "plugins")

_FROM = {
    **{name: ".core" for name in (
        "Agent", "LLM", "create_tool_from_function",
        "on_agent_ready", "after_user_input", "before_iteration", "after_iteration",
        "before_llm", "after_llm", "before_each_tool", "before_tools",
        "after_each_tool", "after_tools", "on_error", "on_complete", "on_stop_signal",
    )},
    "Logger": ".logger",
    # Both of these name a module *and* the function inside it. The eager
    # `from .llm_do import llm_do` bound the function over the module, and code
    # calls `connectonion.llm_do(...)` — so the function is what this must return.
    "llm_do": ".llm_do",
    "transcribe": ".transcribe",
    "load_system_prompt": ".prompts",
    **{name: ".debug" for name in ("xray", "auto_debug_exception", "replay", "xray_replay")},
    **{name: ".plugins" for name in ("CodexPlugin", "ClaudeCodePlugin", "PermissionMode")},
    **{name: ".useful_tools" for name in (
        "send_email", "get_emails", "mark_read", "mark_unread", "send_telegram",
        "create_sms_pairing", "get_sms_pairing", "pairing_confirmation_code", "confirm_sms_pairing",
        "get_sms", "wait_for_sms", "acknowledge_sms", "delete_sms",
        "list_sms_devices", "revoke_sms_device",
        "Memory", "Gmail", "GDrive", "YouTube", "Synology", "GoogleCalendar", "Outlook",
        "MicrosoftCalendar", "WebFetch", "Shell", "bash", "codex", "ClaudeCode",
        "youcom_search", "youcom_contents", "youcom_research",
        "claude_code",
        "DiffWriter",
        "MODE_NORMAL", "MODE_AUTO", "MODE_PLAN",
        "pick", "yes_no", "autocomplete", "TodoList", "SlashCommand",
        # Claude Code-style file tools
        "read_file", "edit", "multi_edit", "glob", "grep", "write",
    )},
    **{name: ".network" for name in (
        "connect", "RemoteAgent", "Response", "ExecResult", "PermissionModeError",
        "host", "create_app",
        "IO", "relay", "announce", "HTTPRequest", "HTTPResponse", "HTTPRoute",
        "HTTPRouter",
    )},
}


def __getattr__(name):
    from importlib import import_module

    if name in _SUBMODULES:
        # `from .core import Agent` also set `connectonion.core`, and code reads it.
        value = import_module(f".{name}", __name__)
    elif name in _FROM:
        value = getattr(import_module(_FROM[name], __name__), name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    globals()[name] = value
    return value


def __dir__():
    return sorted(set(__all__) | set(_SUBMODULES) | set(globals()))


class _Package(_ModuleType):
    """Keeps `llm_do` and `transcribe` meaning the function, not the module.

    Each of those names belongs to both a module and the function inside it.
    Importing `connectonion.llm_do` — which docs/README.md tells people to do,
    and which web_fetch.py and gmail.py do internally — makes the import system
    bind the *module* onto this package, shadowing the function. Then
    `connectonion.llm_do(...)` raises "'module' object is not callable".

    The eager version won that race by accident: `__init__` ran before anything
    else could import the submodule, and its last act was to rebind the name to
    the function. Lazy resolution gives up that ordering, so the tie is settled
    here instead — where it does not depend on who imported what first.

    Overriding __getattribute__ rather than __getattr__ is the point: by the
    time this matters the attribute *exists*, so __getattr__ would never run.
    """

    _SHADOWED = frozenset({"llm_do", "transcribe"})

    def __getattribute__(self, name):
        value = _ModuleType.__getattribute__(self, name)
        if name in _Package._SHADOWED and isinstance(value, _ModuleType):
            return getattr(value, name)
        return value


__all__ = [
    # Core
    "Agent",
    "LLM",
    "Logger",
    "create_tool_from_function",
    "llm_do",
    "transcribe",
    "load_system_prompt",
    "xray",
    "replay",
    "xray_replay",
    "auto_debug_exception",
    "CodexPlugin",
    "ClaudeCodePlugin",
    "PermissionMode",
    # Email tools
    "send_email",
    "get_emails",
    "mark_read",
    "mark_unread",
    "create_sms_pairing",
    "get_sms_pairing",
    "pairing_confirmation_code",
    "confirm_sms_pairing",
    "get_sms",
    "wait_for_sms",
    "acknowledge_sms",
    "delete_sms",
    "list_sms_devices",
    "revoke_sms_device",
    "send_telegram",
    # Class-based tools
    "Memory",
    "Gmail",
    "GDrive",
    "YouTube",
    "Synology",
    "GoogleCalendar",
    "Outlook",
    "MicrosoftCalendar",
    "WebFetch",
    "Shell",
    "bash",
    "codex",
    "ClaudeCode",
    "claude_code",
    "DiffWriter",
    "MODE_NORMAL",
    "MODE_AUTO",
    "MODE_PLAN",
    # TUI helpers
    "pick",
    "yes_no",
    "autocomplete",
    # Task management
    "TodoList",
    "SlashCommand",
    # Claude Code-style file tools
    "read_file",
    "edit",
    "multi_edit",
    "glob",
    "grep",
    "write",
    # Networking
    "connect",
    "RemoteAgent",
    "Response",
    "ExecResult",
    "PermissionModeError",
    "host",
    "create_app",
    "IO",
    "relay",
    "announce",
    "HTTPRequest",
    "HTTPResponse",
    "HTTPRoute",
    "HTTPRouter",
    "address",
    # Event decorators
    "on_agent_ready",
    "after_user_input",
    "before_iteration",
    "after_iteration",
    "before_llm",
    "after_llm",
    "before_each_tool",
    "before_tools",
    "after_each_tool",
    "after_tools",
    "on_error",
    "on_complete",
    "on_stop_signal",
]

# The module's last act: everything above must exist before the class changes.
_sys.modules[__name__].__class__ = _Package

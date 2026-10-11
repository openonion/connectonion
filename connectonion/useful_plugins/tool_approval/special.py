"""
Purpose: Name the three kinds of action that need the owner's own authorization (#2408)
LLM-Note:
  Dependencies: imports from [./policy.py (evaluate_auto_approve, _classify_single_command, _classify_git, _redirect_verdict), ./bash_parser.py (_extract_subcommands), project.py (project_root), shlex, pathlib] | imported by [approval.py check_approval, network/host/http_router.py exec_handler] | tested by [tests/unit/test_special_classes.py]
  Data flow: special_class(tool_name, args, root, tool) → reads the effect class policy.py already assigns, segment by segment for shell → returns {"class", "kind", "reason"} or None
  State/Effects: pure classification, no I/O
  Integration: exposes special_class(), needs_the_owner(), SPECIAL_KINDS
  Errors: none raised; an unparseable command is not special here (policy.py still asks for it)

Everything an agent does is recorded and judged from context, except three
classes the owner decided need their own say (#2408, 2026-10-11):

  1. credentials, authority and money
  2. irreversible deletes and overwrites
  3. acting as the owner in the owner's own accounts

This module only names them. Code decides the class, never the model, so a
model cannot argue an action out of it. It reuses the effect classes policy.py
already assigns, so there is one classifier, not two that drift apart.
"""

import shlex
from pathlib import Path

from ...project import project_root
from .bash_parser import _extract_subcommands
from .policy import _classify_git, _classify_single_command, _redirect_targets, _redirect_verdict, evaluate_auto_approve

SPECIAL_KINDS = {
    "credentials": 1, "authority": 1, "money": 1,
    "irreversible": 2,
    "as_owner": 3,
}

# policy.py's effect class -> our kind
_EFFECT_KIND = {
    "credentials": "credentials",
    "authorization_control": "authority",
    "payment": "money",
    "deletion": "irreversible",
}
# Tool names policy.py files under external_effect that are really money.
_MONEY_TOOLS = {"transfer", "pay", "create_payment"}
# Methods of the owner's own mail accounts that send as the owner.
_OWNER_MAIL_CLASSES = {"Gmail", "Outlook"}
_OWNER_MAIL_METHODS = {"send", "reply", "forward", "send_draft"}
# `co` paths with a meaning policy.py does not separate. Matched as a prefix
# of the non-flag words after `co`. `co email` is the agent's own mailbox,
# so it is not here: only mail sent as the owner is class 3.
_CO_PATHS = {
    ("gmail", "send"): "as_owner",
    ("gmail", "reply"): "as_owner",
    ("gmail", "draft", "send"): "as_owner",
    ("outlook", "send"): "as_owner",
    ("outlook", "reply"): "as_owner",
    ("server", "new"): "money",
    ("server", "destroy"): "irreversible",
}
_SHELL_TOOLS = {"bash", "shell", "run", "run_in_dir", "run_background"}


def _found(kind: str, reason: str) -> dict:
    return {"class": SPECIAL_KINDS[kind], "kind": kind, "reason": reason}


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return []


def _co_path_kind(words: list[str]) -> str | None:
    if not words or Path(words[0]).name != "co":
        return None
    path = tuple(word for word in words[1:] if not word.startswith("-"))
    for prefix, kind in _CO_PATHS.items():
        if path[:len(prefix)] == prefix:
            return kind
    return None


def _from_effect(verdict: dict) -> dict | None:
    kind = _EFFECT_KIND.get(verdict.get("effect_class"))
    return _found(kind, verdict.get("reason", kind)) if kind else None


def _segment_class(segment: str, root: Path) -> dict | None:
    words = _words(segment)
    kind = _co_path_kind(words)
    if kind:
        return _found(kind, f"`{segment}`")
    # policy.py files every `git push` under publication before it reads git's
    # flags, so a force push would look like any other push. Ask git first.
    if words and Path(words[0]).name == "git":
        verdict = _from_effect(_classify_git(words) or {})
        if verdict:
            return verdict
    return _from_effect(_classify_single_command(segment, root))


def _shell_class(command: str, root: Path | None) -> dict | None:
    """Every segment is checked on its own.

    policy.py reports a chain by its first `ask`, so in
    `python job.py && co transfer 5 0x…` the transfer hides behind the script.
    Here the most serious segment decides.
    """
    try:
        segments = [full for _, full in _extract_subcommands(command)]
        targets = _redirect_targets(command)
    except Exception:
        return None
    found = [_from_effect(_redirect_verdict(targets, root) or {})] if targets else []
    for segment in segments:
        found.append(_segment_class(segment, root))
    found = [item for item in found if item]
    return min(found, key=lambda item: item["class"]) if found else None


def special_class(tool_name: str, args: dict, root: Path | None = None, tool=None) -> dict | None:
    """Which of the three special classes this call is in, or None.

    `tool` is the registered tool object when the caller has it; it is how a
    `send` method of the owner's Gmail is told apart from any other `send`.
    """
    name = str(tool_name).lower()
    args = args or {}
    root = (root or project_root()).resolve()
    owner = getattr(getattr(tool, "_bound_instance", None), "__class__", None)
    if owner is not None and owner.__name__ in _OWNER_MAIL_CLASSES and name in _OWNER_MAIL_METHODS:
        return _found("as_owner", f"{owner.__name__}.{name} sends as the owner")
    if name in _MONEY_TOOLS:
        return _found("money", f"{name} moves money")
    if name in _SHELL_TOOLS:
        return _shell_class(str(args.get("command", "")), root)
    return _from_effect(evaluate_auto_approve(name, args, root))


_CLASS_WORDS = {
    1: "touches credentials, authority or money",
    2: "deletes or overwrites something that cannot be brought back",
    3: "acts as the owner in the owner's own accounts",
}


def needs_the_owner(special: dict) -> str:
    """What a caller who may not do this is told."""
    return (f"needs the owner: this {_CLASS_WORDS[special['class']]} "
            f"({special['reason']}). Ask the owner to run it from their own terminal.")

"""Deterministic authorization policy for the Default approval profile.

The policy answers one narrow question before the interactive approval hook:
may this exact tool call run without asking a person?  It does not persist
approvals.  Human session grants remain in ``session['permissions']``.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.events import before_each_tool
from ...project import project_root
from .approval import _is_control_file
from .bash_parser import _extract_subcommands

if TYPE_CHECKING:
    from ...core.agent import Agent


POLICY_ID = "connectonion.auto-approve"
POLICY_VERSION = 1
PROFILE_VERSION = 1

DEFAULT_PROFILE = "default"
SAFE_PROFILE = "safe"
FULL_ACCESS_PROFILE = "full_access"

PROFILE_ALIASES = {
    "default": DEFAULT_PROFILE,
    "auto": DEFAULT_PROFILE,
    "auto_approve": DEFAULT_PROFILE,
    "accept_edits": DEFAULT_PROFILE,
    "safe": SAFE_PROFILE,
    "manual": SAFE_PROFILE,
    "full_access": FULL_ACCESS_PROFILE,
    "full-access": FULL_ACCESS_PROFILE,
    "ulw": FULL_ACCESS_PROFILE,
    "yolo": FULL_ACCESS_PROFILE,
}

READ_TOOLS = {
    "read", "read_file", "glob", "grep", "search", "list", "ls",
    "list_files", "get_file_info", "task_output", "get_emails", "get_events",
    "screenshot", "load_guide",
}
WORKFLOW_TOOLS = {"task", "ask_user", "skill", "enter_plan_mode", "exit_plan_and_implement", "write_plan"}
WORKSPACE_EDIT_TOOLS = {"write", "edit", "multi_edit"}
DELETE_TOOLS = {"delete", "remove", "unlink", "rmdir", "delete_file"}
EXTERNAL_EFFECT_TOOLS = {
    "send_email", "post", "publish", "deploy", "transfer", "pay",
    "create_payment", "delete_event", "send_message",
}

_FOCUSED_COMMANDS = {
    "pytest", "ruff", "mypy", "pyright", "eslint", "tsc", "vitest",
    "jest", "cargo", "go", "make",
}
_PACKAGE_RUNNERS = {"npm", "pnpm", "yarn", "bun"}
_DESTRUCTIVE_COMMANDS = {
    "rm", "rmdir", "shred", "truncate", "del", "erase", "format",
}
_EXTERNAL_COMMANDS = {
    "curl", "wget", "ssh", "scp", "rsync", "mail", "sendmail",
}
_SENSITIVE_COMMANDS = {
    "env", "printenv", "security", "keychain", "gcloud", "aws", "az",
}


def decision(
    effect: str, verdict: str, reason: str, scope: str, *, requires_human: bool = False
) -> dict:
    """Return the versioned decision shape exposed to logs and clients."""
    return {
        "decision": verdict,
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "source": "built-in",
        "reason": reason,
        "effect_class": effect,
        "scope": scope,
        "requires_human": requires_human,
    }


def canonical_profile(value: object) -> str | None:
    """Map current and forward-compatible wire aliases to a stable profile."""
    if not isinstance(value, str):
        return None
    return PROFILE_ALIASES.get(value.strip().lower().replace(" ", "_"))


def _profile(profile_id: str, source: str) -> dict:
    return {"id": profile_id, "version": PROFILE_VERSION, "source": source}


def advertised_profile_state(
    session: dict | None, *, new_session: bool, allow_full_access: bool
) -> dict:
    """Build the authenticated, versioned profile capability sent on CONNECTED.

    Browser-provided session fields are never authority. Callers must derive
    ``new_session`` from Host storage, never from a client marker.
    """
    stored = (session or {}).get("approval_profile")
    profile_id = None
    if isinstance(stored, dict) and stored.get("version") == PROFILE_VERSION:
        profile_id = canonical_profile(stored.get("id"))
    if new_session:
        profile_id = DEFAULT_PROFILE
    elif profile_id is None:
        raw_mode = (session or {}).get("mode")
        legacy = canonical_profile(raw_mode)
        profile_id = (
            legacy
            if raw_mode not in (None, "default") and legacy is not None
            else SAFE_PROFILE
        )
    if profile_id == FULL_ACCESS_PROFILE and not allow_full_access:
        profile_id = SAFE_PROFILE

    available = [
        {
            "id": SAFE_PROFILE,
            "name": "Safe",
            "description": "Read normally; ask before unresolved effects.",
        },
        {
            "id": DEFAULT_PROFILE,
            "name": "Default",
            "description": "Automatically allow low-risk workspace work; ask or deny otherwise.",
            "recommended": True,
        },
    ]
    if allow_full_access:
        available.append({
            "id": FULL_ACCESS_PROFILE,
            "name": "Full access",
            "description": "Bypass per-action approval within the Host-defined bound.",
            "dangerous": True,
            "bound": "host-configured",
        })
    return {
        "schemaVersion": PROFILE_VERSION,
        "currentModeId": profile_id,
        "availableModes": available,
        "policy": {"id": POLICY_ID, "version": POLICY_VERSION},
    }


def ensure_approval_profile(agent: "Agent") -> str:
    """Restore a versioned profile, conservatively migrating older sessions.

    Only sessions explicitly marked as new receive Default/Auto Approve.  An
    old session containing the historical ``mode: default`` (or no mode at
    all) migrates to Safe, so an upgrade cannot silently add authority.
    """
    session = agent.current_session
    stored = session.get("approval_profile")
    if (isinstance(stored, dict) and stored.get("version") == PROFILE_VERSION
            and canonical_profile(stored.get("id"))):
        profile_id = canonical_profile(stored["id"])
        stored["id"] = profile_id
        return profile_id

    raw_mode = session.get("mode")
    legacy_alias = canonical_profile(raw_mode)
    if session.pop("_new_session", False):
        profile_id = DEFAULT_PROFILE
        source = "new-session-default"
    elif raw_mode not in (None, "default") and legacy_alias is not None:
        profile_id = legacy_alias
        source = "legacy-alias-migration"
    else:
        profile_id = SAFE_PROFILE
        source = "legacy-session-migration"

    session["approval_profile"] = _profile(profile_id, source)
    session["mode"] = profile_id
    return profile_id


def set_approval_profile(agent: "Agent", profile_id: str, source: str = "user") -> str:
    """Persist a canonical profile while retaining old wire aliases."""
    canonical = canonical_profile(profile_id)
    if canonical is None:
        raise ValueError(f"Unknown approval profile: {profile_id}")
    agent.current_session["approval_profile"] = _profile(canonical, source)
    agent.current_session["mode"] = "ulw" if canonical == FULL_ACCESS_PROFILE else canonical
    return canonical


def _workspace_path(args: dict) -> Path | None:
    raw = next((args.get(key) for key in ("file_path", "path", "target", "filename")
                if args.get(key)), None)
    if raw is None:
        return None
    return Path(str(raw)).expanduser().resolve(strict=False)


def _inside_workspace(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _command_words(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except (TypeError, ValueError):
        return []


def _classify_single_command(command: str) -> dict:
    words = _command_words(command)
    if not words:
        return decision("command", "ask", "command could not be parsed safely", "call", requires_human=True)

    lowered = [word.lower() for word in words]
    first = Path(words[0]).name.lower()
    if first in _DESTRUCTIVE_COMMANDS:
        return decision("deletion", "deny", "destructive command requires an explicit safer workflow", "call")
    if any(token in lowered for token in ("publish", "deploy", "release", "push")):
        return decision("publication", "ask", "publishing and deployment require human approval", "call", requires_human=True)
    if first in _EXTERNAL_COMMANDS:
        return decision("external_network", "ask", "external network access requires human approval", "call", requires_human=True)
    if first in _SENSITIVE_COMMANDS or any(
        ".env" in token or "credential" in token or "secret" in token
        for token in lowered
    ):
        return decision("credentials", "deny", "credential access is never auto-approved", "call")

    focused = first in _FOCUSED_COMMANDS
    focused = focused or (first in {"python", "python3"} and words[1:3] == ["-m", "pytest"])
    focused = focused or (first == "uv" and len(words) > 2 and words[1] == "run"
                          and Path(words[2]).name in _FOCUSED_COMMANDS)
    if first in _PACKAGE_RUNNERS:
        focused = any(token in lowered[1:4] for token in ("test", "lint", "build", "check", "typecheck"))
    if first == "cargo":
        focused = len(words) > 1 and words[1] in {"test", "check", "clippy", "build"}
    if first == "go":
        focused = len(words) > 1 and words[1] == "test"

    if focused:
        return decision("verification", "allow", "focused test, lint, or build command", "workspace")
    return decision("command", "ask", "command is outside the focused verification allowlist", "call")


def _classify_command(command: str) -> dict:
    """All parts of a shell chain must independently qualify for auto approval."""
    try:
        subcommands = _extract_subcommands(command)
    except Exception:
        return decision("command", "ask", "command could not be parsed safely", "call", requires_human=True)

    results = [_classify_single_command(full) for _, full in subcommands]
    denied = next((item for item in results if item["decision"] == "deny"), None)
    if denied:
        return denied
    asked = next((item for item in results if item["decision"] == "ask"), None)
    if asked:
        return asked
    return decision(
        "verification", "allow",
        f"focused verification chain ({len(results)} command{'s' if len(results) != 1 else ''})",
        "workspace",
    )


def evaluate_auto_approve(tool_name: str, args: dict, root: Path | None = None) -> dict:
    """Classify one exact tool call without model judgment or side effects."""
    root = (root or project_root()).resolve()
    name = str(tool_name).lower()

    if name in READ_TOOLS:
        path = _workspace_path(args)
        if path is not None and not _inside_workspace(path, root):
            return decision("read_outside_workspace", "ask", "reading outside the workspace requires approval", "call", requires_human=True)
        return decision("read", "allow", "read-only workspace operation", "workspace")

    if name in WORKFLOW_TOOLS:
        return decision("workflow", "allow", "built-in planning or user-interaction workflow", "session")

    if name in WORKSPACE_EDIT_TOOLS:
        path = _workspace_path(args)
        if path is None:
            return decision("workspace_edit", "ask", "edit target is missing or ambiguous", "call", requires_human=True)
        if _is_control_file(str(path)):
            return decision("authorization_control", "deny", "agents cannot rewrite authorization control files", "call")
        if not _inside_workspace(path, root):
            return decision("write_outside_workspace", "deny", "writes outside the workspace are not auto-approved", "call")
        return decision("workspace_edit", "allow", "reversible edit inside the workspace", "workspace")

    if name in DELETE_TOOLS:
        return decision("deletion", "deny", "deletion is never auto-approved", "call")
    if name in EXTERNAL_EFFECT_TOOLS:
        return decision("external_effect", "ask", "external side effects require human approval", "call", requires_human=True)
    if name in {"bash", "shell", "run", "run_in_dir", "run_background"}:
        return _classify_command(str(args.get("command", "")))
    if name == "kill_task":
        return decision("task_control", "ask", "stopping a running task requires approval", "call", requires_human=True)
    return decision("unknown", "ask", "unknown tools never run silently", "call", requires_human=True)


@before_each_tool
def apply_auto_approve_policy(agent: "Agent") -> None:
    """Attach a transient decision before the existing human approval hook."""
    pending = agent.current_session.get("pending_tool")
    if not pending:
        return

    profile_id = ensure_approval_profile(agent)
    if profile_id == FULL_ACCESS_PROFILE:
        requester = agent.current_session.get("requester")
        if requester and requester.get("level") != "admin":
            set_approval_profile(agent, SAFE_PROFILE, source="host-boundary")
            pending["approval_policy"] = decision(
                "authority", "ask", "only the local or Host admin operator can select Full access", "call",
                requires_human=True,
            )
            _record_decision(agent, pending)
            return
        pending["approval_policy"] = decision(
            "unbounded", "allow", "Full access was explicitly selected", "host"
        )
        _record_decision(agent, pending)
        return
    if profile_id == SAFE_PROFILE:
        pending["approval_policy"] = decision(
            "manual", "ask", "Safe profile requires manual approval", "call", requires_human=True
        )
        _record_decision(agent, pending)
        return

    try:
        result = evaluate_auto_approve(pending["name"], pending.get("arguments") or {})
    except Exception as exc:  # Policy failure is authority failure, never a bypass.
        verdict = "ask" if agent.io else "deny"
        result = decision(
            "policy_failure", verdict,
            f"authorization policy failed closed ({type(exc).__name__})", "call",
            requires_human=verdict == "ask",
        )
    if result["decision"] == "ask" and not agent.io:
        result = {**result, "decision": "deny", "reason": result["reason"] + "; no approval channel is available"}
    pending["approval_policy"] = result
    _record_decision(agent, pending)


def _record_decision(agent: "Agent", pending: dict) -> None:
    """Attach the decision to the existing tool trace for durable auditing."""
    tool_id = pending.get("id")
    for entry in reversed(agent.current_session.get("trace", [])):
        if entry.get("type") == "tool_call" and (not tool_id or entry.get("id") == tool_id):
            entry["approval_policy"] = dict(pending["approval_policy"])
            return


__all__ = [
    "DEFAULT_PROFILE", "FULL_ACCESS_PROFILE", "POLICY_ID", "POLICY_VERSION",
    "PROFILE_VERSION", "SAFE_PROFILE", "apply_auto_approve_policy",
    "advertised_profile_state", "canonical_profile", "ensure_approval_profile",
    "evaluate_auto_approve", "set_approval_profile",
]

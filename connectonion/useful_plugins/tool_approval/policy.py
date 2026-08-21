"""Deterministic, fail-closed policy for the OIP ``:workspace`` profile.

The Host owns the selected permission profile.  This module never persists a
client-supplied profile or grants Full access; it only classifies one pending
tool call after the Host has selected ``:workspace`` for an operator.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    legacy_permission_profile_id,
)
from ...core.events import before_each_tool
from ...project import project_root
from .bash_parser import _extract_subcommands

if TYPE_CHECKING:
    from ...core.agent import Agent


POLICY_ID = "connectonion.workspace-auto-approve"
POLICY_VERSION = 1

# Compatibility exports for integrations built against the 1.6.11 draft.
DEFAULT_PROFILE = WORKSPACE_PERMISSION_PROFILE
SAFE_PROFILE = READ_ONLY_PERMISSION_PROFILE
FULL_ACCESS_PROFILE = DANGER_FULL_ACCESS_PERMISSION_PROFILE

READ_TOOLS = {
    "read", "read_file", "glob", "grep", "search", "list", "ls",
    "list_files", "get_file_info", "task_output", "get_emails", "get_events",
    "screenshot", "load_guide",
}
WORKFLOW_TOOLS = {
    "task", "ask_user", "skill", "enter_plan_mode", "exit_plan_and_implement",
    "write_plan",
}
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
_DESTRUCTIVE_COMMANDS = {"rm", "rmdir", "shred", "truncate", "del", "erase", "format"}
_EXTERNAL_COMMANDS = {"curl", "wget", "ssh", "scp", "rsync", "mail", "sendmail"}
_SENSITIVE_COMMANDS = {
    "env", "printenv", "security", "keychain", "gcloud", "aws", "az",
}


def decision(
    effect: str, verdict: str, reason: str, scope: str, *, requires_human: bool = False
) -> dict:
    """Return the versioned, UI-safe decision recorded on a pending tool."""
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
    """Read current and legacy profile spellings without granting authority."""
    try:
        return legacy_permission_profile_id(value)
    except ValueError:
        return None


def ensure_approval_profile(agent: "Agent") -> str:
    """Canonicalize the already-authorized Host profile, failing closed."""
    profile = canonical_profile(agent.current_session.get("mode"))
    if profile is None:
        profile = READ_ONLY_PERMISSION_PROFILE
    agent.current_session["mode"] = profile
    return profile


def set_approval_profile(agent: "Agent", profile_id: str, source: str = "user") -> str:
    """Compatibility setter; Host transactions remain the remote authority."""
    del source
    profile = canonical_profile(profile_id)
    if profile is None:
        raise ValueError(f"Unknown approval profile: {profile_id}")
    agent.current_session["mode"] = profile
    return profile


def advertised_profile_state(
    session: dict | None, *, new_session: bool, allow_full_access: bool
) -> dict:
    """Compatibility view; production CONNECT uses ``HostPermissionPolicy``."""
    del new_session
    profile = canonical_profile((session or {}).get("mode")) or READ_ONLY_PERMISSION_PROFILE
    available = [
        {"id": READ_ONLY_PERMISSION_PROFILE, "name": "Read only"},
        {"id": WORKSPACE_PERMISSION_PROFILE, "name": "Auto", "recommended": True},
    ]
    if allow_full_access:
        available.append({
            "id": DANGER_FULL_ACCESS_PERMISSION_PROFILE,
            "name": "Full access",
            "dangerous": True,
            "bound": "host-configured",
        })
    if profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE and not allow_full_access:
        profile = READ_ONLY_PERMISSION_PROFILE
    return {
        "schemaVersion": POLICY_VERSION,
        "currentModeId": profile,
        "availableModes": available,
        "policy": {"id": POLICY_ID, "version": POLICY_VERSION},
    }


def _workspace_path(args: dict) -> Path | None:
    raw = next(
        (args.get(key) for key in ("file_path", "path", "target", "filename") if args.get(key)),
        None,
    )
    return Path(str(raw)).expanduser().resolve(strict=False) if raw is not None else None


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
        ".env" in token or "credential" in token or "secret" in token for token in lowered
    ):
        return decision("credentials", "deny", "credential access is never auto-approved", "call")

    focused = first in _FOCUSED_COMMANDS
    focused = focused or (first in {"python", "python3"} and words[1:3] == ["-m", "pytest"])
    focused = focused or (first == "uv" and len(words) > 2 and words[1] == "run" and Path(words[2]).name in _FOCUSED_COMMANDS)
    if first in _PACKAGE_RUNNERS:
        focused = any(token in lowered[1:4] for token in ("test", "lint", "build", "check", "typecheck"))
    if first == "cargo":
        focused = len(words) > 1 and words[1] in {"test", "check", "clippy", "build"}
    if first == "go":
        focused = len(words) > 1 and words[1] == "test"
    if focused:
        return decision("verification", "allow", "focused test, lint, or build command", "workspace")
    return decision("command", "ask", "command is outside the focused verification allowlist", "call", requires_human=True)


def _classify_command(command: str) -> dict:
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
    return decision("verification", "allow", f"focused verification chain ({len(results)} command{'s' if len(results) != 1 else ''})", "workspace")


def evaluate_auto_approve(tool_name: str, args: dict, root: Path | None = None) -> dict:
    """Classify one exact Auto-profile tool call without side effects."""
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
        from .approval import _is_control_file
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


def _operator(agent: "Agent") -> bool:
    requester = agent.current_session.get("requester")
    return not requester or requester.get("level") == "admin"


def workspace_policy_for_pending(agent: "Agent", pending: dict) -> dict | None:
    """Return an Auto decision only for an authorized Workspace session."""
    if ensure_approval_profile(agent) != WORKSPACE_PERMISSION_PROFILE or not _operator(agent):
        return None
    try:
        result = evaluate_auto_approve(pending["name"], pending.get("arguments") or {})
    except Exception as exc:
        result = decision(
            "policy_failure",
            "ask" if agent.io else "deny",
            f"authorization policy failed closed ({type(exc).__name__})",
            "call",
            requires_human=bool(agent.io),
        )
    if not agent.io and result["decision"] == "ask":
        result = decision(
            result["effect_class"],
            "deny",
            f"{result['reason']}; no approval channel is available",
            result["scope"],
        )
    pending["approval_policy"] = result
    record_approval_policy(agent, pending)
    return result


@before_each_tool
def apply_auto_approve_policy(agent: "Agent") -> None:
    """Attach a durable semantic decision before the human approval hook."""
    pending = agent.current_session.get("pending_tool")
    if pending:
        workspace_policy_for_pending(agent, pending)


def record_approval_policy(agent: "Agent", pending: dict) -> None:
    """Attach the decision to the matching trace entry for audit and replay."""
    result = pending.get("approval_policy")
    if not isinstance(result, dict):
        return
    tool_id = pending.get("id")
    for entry in reversed(agent.current_session.get("trace", [])):
        if entry.get("type") == "tool_call" and (not tool_id or entry.get("id") == tool_id):
            entry["approval_policy"] = dict(result)
            return

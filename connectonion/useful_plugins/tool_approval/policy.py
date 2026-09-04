"""Deterministic, fail-closed policy for canonical Auto mode.

The Host owns the selected permission profile.  This module never persists a
client-supplied mode or grants Full access; it only classifies one pending
tool call after the Host has selected ``auto``.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.events import before_each_tool
from ...core.mode import AUTO, FULL_ACCESS, READ_ONLY, mode_id, mode_of, set_mode
from ...project import project_root
from .bash_parser import _extract_subcommands, check_bash_chain_permitted

if TYPE_CHECKING:
    from ...core.agent import Agent


POLICY_ID = "connectonion.auto"
POLICY_VERSION = 1
MANAGED_DELEGATION_TOOLS = frozenset({"codex", "claude_code"})
MANAGED_DELEGATION_REASON = "managed delegation owns inner approval"

READ_TOOLS = {
    "read", "read_file", "glob", "grep", "search", "list", "ls",
    "list_files", "get_file_info", "task_output", "get_emails", "get_events",
    "screenshot", "load_guide",
}
WORKFLOW_TOOLS = {"task", "ask_user", "skill", "todo_list"}
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


def canonical_mode(value: object) -> str | None:
    """Read one exact public mode without granting authority."""
    try:
        return mode_id(value)
    except ValueError:
        return None


def managed_delegation_permission() -> dict:
    """Build the exact co ai grant consumed by the Auto classifier."""
    return {
        "allowed": True,
        "source": "safe",
        "reason": MANAGED_DELEGATION_REASON,
        "expires": {"type": "never"},
    }


def _has_managed_delegation_grant(session: dict, tool_name: object) -> bool:
    """Recognize only the runtime grant injected by co ai for native adapters."""
    name = str(tool_name)
    if name not in MANAGED_DELEGATION_TOOLS:
        return False
    permissions = session.get("permissions")
    return (
        isinstance(permissions, dict)
        and permissions.get(name) == managed_delegation_permission()
    )


def ensure_approval_mode(agent: "Agent") -> str:
    """Canonicalize stored state through the one writer."""

    canonical = mode_of(agent.current_session)
    if canonical == FULL_ACCESS:
        return canonical
    set_mode(agent.current_session, canonical)
    return canonical


def set_approval_mode(agent: "Agent", mode: str, source: str = "user") -> str:
    """Set Read only or Auto; Host transactions remain remote authority."""
    del source
    canonical = mode_id(mode)
    if canonical not in {READ_ONLY, AUTO}:
        raise ValueError(f"Mode is not owned by Auto policy: {canonical}")
    return set_mode(agent.current_session, canonical)


def advertised_mode_state(
    session: dict | None, *, new_session: bool, allow_full_access: bool
) -> dict:
    """Return the exact public state advertised by compatibility callers."""
    del new_session
    current = mode_of(session or {})
    available = [
        {"id": READ_ONLY, "name": "Read only"},
        {"id": AUTO, "name": "Auto", "recommended": True},
    ]
    if allow_full_access:
        available.append({
            "id": FULL_ACCESS,
            "name": "Full access",
            "dangerous": True,
            "bound": "host-configured",
        })
    if current == FULL_ACCESS and not allow_full_access:
        current = AUTO
    return {
        "schemaVersion": POLICY_VERSION,
        "currentModeId": current,
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


def workspace_policy_for_pending(agent: "Agent", pending: dict) -> dict | None:
    """Return a deterministic decision for any ordinary Auto session."""
    if ensure_approval_mode(agent) != AUTO:
        return None
    try:
        if _has_managed_delegation_grant(agent.current_session, pending.get("name")):
            result = decision(
                "managed_delegation",
                "allow",
                MANAGED_DELEGATION_REASON,
                "session",
            )
        else:
            result = evaluate_auto_approve(
                pending["name"], pending.get("arguments") or {}
            )
    except Exception as exc:
        result = decision(
            "policy_failure",
            "ask" if agent.io else "deny",
            f"authorization policy failed closed ({type(exc).__name__})",
            "call",
            requires_human=bool(agent.io),
        )
    if not agent.io and result["decision"] == "ask":
        configured = _headless_configured_command(agent, pending, result)
        if configured is not None:
            result = configured
        else:
            result = decision(
                result["effect_class"],
                "deny",
                f"{result['reason']}; no approval channel is available",
                result["scope"],
            )
    pending["approval_policy"] = result
    record_approval_policy(agent, pending)
    return result


def _headless_configured_command(
    agent: "Agent", pending: dict, result: dict
) -> dict | None:
    """Honor an operator's standing command grant without weakening Auto.

    Only ordinary commands reach this path. Publication, deployment, network,
    credential, deletion, and unknown effects keep their stronger verdict even
    when a broad legacy pattern such as ``Bash(co *)`` happens to match.
    """
    if result.get("effect_class") != "command" or pending.get("name") != "bash":
        return None
    permissions = agent.current_session.get("permissions")
    if not isinstance(permissions, dict):
        return None
    configured = {
        pattern: permission
        for pattern, permission in permissions.items()
        if isinstance(permission, dict) and permission.get("source") == "config"
    }
    # The shipped historical Bash(co *) grant is broader than its "safe CLI"
    # description. Preserve the unattended browser/status compatibility users
    # relied on without silently authorizing email, account, server, or payment
    # commands. Operators can still name a narrower command explicitly.
    broad_co = configured.pop("Bash(co *)", None)
    if broad_co is not None:
        subcommands = _extract_subcommands(
            str((pending.get("arguments") or {}).get("command", ""))
        )
        if subcommands and all(
            full == "co status" or full.startswith("co browser ")
            for _, full in subcommands
        ):
            configured["Bash(co *)"] = broad_co
    try:
        permitted, _, _ = check_bash_chain_permitted(
            str((pending.get("arguments") or {}).get("command", "")), configured
        )
    except Exception:
        return None
    if not permitted:
        return None
    return decision(
        "configured_command",
        "allow",
        "operator-configured command allowlist",
        "call",
    )


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

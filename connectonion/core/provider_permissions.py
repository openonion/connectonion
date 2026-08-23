"""Bounded provider-native permission catalogs for OIP Work Rooms."""

from __future__ import annotations

from typing import Any

from .mode import AUTO, FULL_ACCESS, READ_ONLY


_OPTION_DEFINITIONS = {
    "codex": (
        {"id": "codex:read-only", "nativeProfileId": ":read-only", "reviewer": "user", "label": "Read Only", "description": "Codex can inspect the workspace but cannot change it.", "ceiling": 0, "risk": "standard"},
        {"id": "codex:workspace-ask", "nativeProfileId": ":workspace", "reviewer": "user", "label": "Ask for approval", "description": "Codex can work in the workspace and asks before protected actions.", "ceiling": 1, "risk": "standard"},
        {"id": "codex:workspace-auto", "nativeProfileId": ":workspace", "reviewer": "auto", "label": "Approve for me", "description": "Codex automatically reviews actions inside the workspace boundary.", "ceiling": 1, "risk": "standard"},
        {"id": "codex:full-access", "nativeProfileId": ":danger-full-access", "reviewer": "auto", "label": "Full Access", "description": "Codex can act outside the workspace boundary for the next provider turn.", "ceiling": 2, "risk": "elevated"},
    ),
    "claude_code": (
        {"id": "claude:plan", "nativeProfileId": "plan", "reviewer": "user", "label": "Plan", "description": "Claude Code can inspect and plan without applying changes.", "ceiling": 0, "risk": "standard"},
        {"id": "claude:default", "nativeProfileId": "default", "reviewer": "user", "label": "Default", "description": "Claude Code asks before actions that need permission.", "ceiling": 1, "risk": "standard"},
        {"id": "claude:accept-edits", "nativeProfileId": "acceptEdits", "reviewer": "provider", "label": "Accept edits", "description": "Claude Code may apply workspace edits while retaining its native checks.", "ceiling": 1, "risk": "standard"},
        {"id": "claude:auto", "nativeProfileId": "auto", "reviewer": "auto", "label": "Auto", "description": "Claude Code automatically handles permitted workspace actions.", "ceiling": 1, "risk": "standard"},
        {"id": "claude:bypass-permissions", "nativeProfileId": "bypassPermissions", "reviewer": "auto", "label": "Bypass permissions", "description": "Claude Code bypasses native permission prompts for the next provider turn.", "ceiling": 2, "risk": "elevated"},
    ),
}
_DEFAULT_OPTIONS = {
    "codex": {READ_ONLY: "codex:read-only", AUTO: "codex:workspace-ask", FULL_ACCESS: "codex:full-access"},
    "claude_code": {READ_ONLY: "claude:plan", AUTO: "claude:accept-edits", FULL_ACCESS: "claude:auto"},
}
_CEILING = {READ_ONLY: 0, AUTO: 1, FULL_ACCESS: 2}
_CEILING_LABEL = {READ_ONLY: "Read Only", AUTO: "Auto", FULL_ACCESS: "Full Access"}


def default_provider_permission_option(provider: str, host_mode: str) -> str:
    try:
        return _DEFAULT_OPTIONS[provider][host_mode]
    except KeyError as exc:
        raise ValueError("unsupported provider permission boundary") from exc


def provider_permission_state(
    provider: str,
    active_option_id: str,
    host_mode: str,
    *,
    state_revision: int | None = None,
) -> dict[str, Any]:
    definitions = _OPTION_DEFINITIONS.get(provider)
    if definitions is None or host_mode not in _CEILING:
        raise ValueError("unsupported provider permission boundary")
    if active_option_id not in {option["id"] for option in definitions}:
        raise ValueError("unknown provider permission option")
    ceiling = _CEILING[host_mode]
    options = []
    for definition in definitions:
        option = {key: value for key, value in definition.items() if key != "ceiling"}
        option["selectable"] = definition["ceiling"] <= ceiling
        if not option["selectable"]:
            option["disabledReason"] = f"Host permission ceiling is {_CEILING_LABEL[host_mode]}."
        options.append(option)
    state: dict[str, Any] = {
        "provider": provider,
        "activeOptionId": active_option_id,
        "options": options,
        "appliesTo": "subsequent_turn",
    }
    if state_revision is not None:
        if isinstance(state_revision, bool) or not isinstance(state_revision, int) or state_revision < 1:
            raise ValueError("provider permission state requires a positive revision")
        state["effectiveRevision"] = state_revision
    return state


def provider_permission_option(provider: str, option_id: str, host_mode: str) -> dict[str, Any]:
    state = provider_permission_state(provider, option_id, host_mode)
    selected = next(option for option in state["options"] if option["id"] == option_id)
    if not selected["selectable"]:
        raise ValueError(selected["disabledReason"])
    return selected


def selected_provider_permission_option(session: object, workroom_id: object) -> str | None:
    if not isinstance(session, dict) or not isinstance(workroom_id, str):
        return None
    selected = session.get("_provider_permission_options")
    option = selected.get(workroom_id) if isinstance(selected, dict) else None
    return option if isinstance(option, str) else None


def reconcile_provider_permission_events(session: dict[str, Any], host_mode: str) -> None:
    """Narrow every latest Work Room snapshot after its outer Host ceiling changes."""
    trace = session.get("trace")
    if not isinstance(trace, list):
        return
    latest_by_workroom: dict[str, dict[str, Any]] = {}
    for event in trace:
        if (
            isinstance(event, dict)
            and event.get("type") == "provider_invocation"
            and event.get("provider") in _OPTION_DEFINITIONS
            and isinstance(event.get("invocationId"), str)
            and isinstance(event.get("stateRevision"), int)
            and not isinstance(event.get("stateRevision"), bool)
        ):
            workroom_id = event.get("workroomId") or event["invocationId"]
            if isinstance(workroom_id, str):
                latest_by_workroom[workroom_id] = event
    stored = session.setdefault("_provider_permission_options", {})
    if not isinstance(stored, dict):
        stored = {}
        session["_provider_permission_options"] = stored
    for workroom_id, source in latest_by_workroom.items():
        provider = source["provider"]
        selected = stored.get(workroom_id)
        if not isinstance(selected, str):
            selected = default_provider_permission_option(provider, host_mode)
        try:
            provider_permission_option(provider, selected, host_mode)
        except ValueError:
            selected = default_provider_permission_option(provider, host_mode)
        stored[workroom_id] = selected
        revision = source["stateRevision"]
        expected = provider_permission_state(
            provider,
            selected,
            host_mode,
            state_revision=revision,
        )
        if source.get("providerPermission") == expected:
            continue
        updated = dict(source)
        updated["stateRevision"] = revision + 1
        updated["providerPermission"] = provider_permission_state(
            provider,
            selected,
            host_mode,
            state_revision=revision + 1,
        )
        trace.append(updated)


__all__ = [
    "default_provider_permission_option",
    "provider_permission_option",
    "provider_permission_state",
    "reconcile_provider_permission_events",
    "selected_provider_permission_option",
]

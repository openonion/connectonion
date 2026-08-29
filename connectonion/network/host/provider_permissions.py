"""Provider-owned Work Room permission profiles and durable transactions.

Outer COAI mode remains the Host ceiling.  This module exposes the narrower
provider-native choices permitted inside that ceiling, then commits a choice
only for the authenticated owner's subsequent provider work.  Browser state is
never authority: every write is bound to the latest durable state revision.
"""

from __future__ import annotations

import copy
from typing import Any

from ...core.mode import mode_of
from ...core.provider_permissions import (
    provider_permission_state,
    selected_provider_permission_option,
)
from .session import SessionStorage, session_owner

_SUPPORTED_PROVIDERS = frozenset({"codex", "claude_code"})
_SESSION_ACTOR_LEVELS = frozenset({"contact", "whitelist", "admin"})


class ProviderPermissionError(RuntimeError):
    """A safe, stable rejection for one provider permission transaction."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def commit_provider_permission(
    storage: SessionStorage,
    session_id: str,
    requester_address: object,
    invocation_id: object,
    observed_revision: object,
    option_id: object,
    *,
    request_id: object,
    confirm_risk: object,
) -> dict[str, Any]:
    """Commit an acknowledged provider option for subsequent native work."""
    for value in (session_id, invocation_id, option_id, request_id):
        if not _valid_id(value):
            raise ProviderPermissionError("invalid_request", "Provider permission request is invalid.")
    if isinstance(observed_revision, bool) or not isinstance(observed_revision, int) or observed_revision < 1:
        raise ProviderPermissionError("invalid_revision", "Provider state revision is invalid.")
    result: dict[str, Any] = {}

    def commit(current):
        nonlocal result
        if current is None or session_owner(current) != requester_address:
            raise ProviderPermissionError("not_owner", "The Work Room is not owned by this requester.")
        session = copy.deepcopy(current.session or {})
        requester = session.get("requester")
        if (
            not isinstance(requester, dict)
            or requester.get("address") != requester_address
            or requester.get("level") not in _SESSION_ACTOR_LEVELS
        ):
            # ``operator_required`` is retained as the wire code for rolling
            # React compatibility. Provider profiles are session execution
            # controls, not Host control-plane settings: an invited contact may
            # change its own Work Room within the already-authoritative outer
            # ceiling, while a forged/missing requester still fails closed.
            raise ProviderPermissionError(
                "operator_required",
                "Only the authenticated session owner can change provider permissions.",
            )
        source = _latest_invocation(session, invocation_id)
        if not source:
            raise ProviderPermissionError("not_found", "The provider Work Room is unavailable.")
        if source.get("stateRevision") != observed_revision:
            raise ProviderPermissionError("stale_revision", "The provider state changed; refresh before trying again.")
        provider = source.get("provider")
        host_mode = mode_of(session)
        try:
            state = provider_permission_state(provider, option_id, host_mode)
        except ValueError as exc:
            raise ProviderPermissionError("unsupported_option", "This provider option is unavailable.") from exc
        selected = next(option for option in state["options"] if option["id"] == option_id)
        if not selected["selectable"]:
            raise ProviderPermissionError("ceiling_denied", selected["disabledReason"])
        if selected["risk"] == "elevated" and confirm_risk is not True:
            raise ProviderPermissionError("confirmation_required", "Confirm the provider Full Access risk separately.")
        revision = observed_revision + 1
        state = provider_permission_state(
            provider,
            option_id,
            host_mode,
            state_revision=revision,
        )
        workroom_id = source.get("workroomId") or invocation_id
        choices = session.setdefault("_provider_permission_options", {})
        if not isinstance(choices, dict):
            choices = {}
            session["_provider_permission_options"] = choices
        choices[workroom_id] = option_id
        event = copy.deepcopy(source)
        event["stateRevision"] = revision
        event["providerPermission"] = state
        session.setdefault("trace", []).append(event)
        result = {
            "invocationId": invocation_id,
            "stateRevision": revision,
            "providerPermission": state,
            "event": event,
        }
        return current.model_copy(update={"session": session})

    storage.atomic_update(session_id, commit)
    return result


def _latest_invocation(session: dict[str, Any], invocation_id: str) -> dict[str, Any]:
    trace = session.get("trace")
    candidates = [
        event for event in trace or []
        if isinstance(event, dict)
        and event.get("type") == "provider_invocation"
        and event.get("invocationId") == invocation_id
        and event.get("provider") in _SUPPORTED_PROVIDERS
        and isinstance(event.get("stateRevision"), int)
        and not isinstance(event.get("stateRevision"), bool)
    ]
    return max(candidates, key=lambda event: event["stateRevision"], default={})


def _valid_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 512
        and value.isascii()
        and all(character.isalnum() or character in "._:-" for character in value)
    )


__all__ = [
    "ProviderPermissionError",
    "commit_provider_permission",
    "provider_permission_state",
    "selected_provider_permission_option",
]

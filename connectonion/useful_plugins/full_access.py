"""Bounded Full access permission plugin.

Full access controls approval only. It never synthesizes a prompt, calls
``agent.input(...)``, extends its own grant, or decides whether an objective is
complete. Each completed user-driven Agent turn consumes one unit of the
canonical ``turns_left`` budget and expiry returns to Auto.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.events import after_user_input, on_complete
from ..core.mode import (
    AUTO,
    FULL_ACCESS,
    consume_full_access_turn,
    full_access_turns_left,
    mode_of,
    set_mode,
)

if TYPE_CHECKING:
    from ..core.agent import Agent


FULL_ACCESS_DEFAULT_TURNS = 100


def _log(agent: "Agent", message: str) -> None:
    if hasattr(agent, "logger") and agent.logger:
        agent.logger.print(message)


def _positive_turn_count(value: object, *, default: int | None = None) -> int:
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Full access turns must be a positive integer")
    return value


def handle_full_access_mode_change(
    agent: "Agent", turns: int | None = None
) -> None:
    """Select bounded Full access using the canonical state writer."""

    budget = _positive_turn_count(turns, default=FULL_ACCESS_DEFAULT_TURNS)
    if agent.current_session is None:
        agent._full_access_turns = budget
        agent._full_access_needs_activation = True
        return

    old_mode = mode_of(agent.current_session)
    set_mode(agent.current_session, FULL_ACCESS, turns_left=budget)
    if agent.io:
        agent.io.send({
            "type": "mode_changed",
            "mode": FULL_ACCESS,
            "turns_left": budget,
            "triggered_by": "user",
        })
    _log(agent, f"[cyan]Permission mode changed: {old_mode} → {FULL_ACCESS} ({budget} turns)[/cyan]")


def enable_full_access(agent: "Agent", turns: int | None = None) -> None:
    """Configure bounded Full access before or during a session."""

    budget = _positive_turn_count(turns, default=FULL_ACCESS_DEFAULT_TURNS)
    agent._full_access_turns = budget
    agent._full_access_needs_activation = True
    if agent.current_session is not None:
        handle_full_access_mode_change(agent, budget)
        agent._full_access_needs_activation = False


def offer_full_access(agent: "Agent", turns: int | None = None) -> None:
    """Advertise a Host ceiling without changing a fresh session from Auto."""

    budget = _positive_turn_count(turns, default=FULL_ACCESS_DEFAULT_TURNS)
    agent._full_access_turns = budget
    agent._full_access_needs_activation = False


@after_user_input
def activate_configured_full_access(agent: "Agent") -> None:
    """Activate an explicitly configured grant before the first model call."""

    budget = getattr(agent, "_full_access_turns", None)
    if budget is None or not getattr(agent, "_full_access_needs_activation", False):
        return
    handle_full_access_mode_change(agent, budget)
    agent._full_access_needs_activation = False


@on_complete
def consume_configured_full_access_turn(agent: "Agent") -> None:
    """Consume this completed user turn without starting another one."""

    if mode_of(agent.current_session) != FULL_ACCESS:
        return
    previous = full_access_turns_left(agent.current_session)
    resulting_mode = consume_full_access_turn(agent.current_session)
    remaining = full_access_turns_left(agent.current_session)
    if agent.io:
        if resulting_mode == AUTO:
            agent.io.send({
                "type": "mode_changed",
                "mode": AUTO,
                "turns_left": None,
                "triggered_by": "full_access_expired",
            })
        else:
            agent.io.send({
                "type": "mode_budget_changed",
                "mode": FULL_ACCESS,
                "turns_left": remaining,
                "previous_turns_left": previous,
            })
    if resulting_mode == AUTO:
        _log(agent, "[cyan]Full access expired → auto[/cyan]")


full_access = [
    activate_configured_full_access,
    consume_configured_full_access_turn,
]
__all__ = [
    "FULL_ACCESS_DEFAULT_TURNS",
    "activate_configured_full_access",
    "consume_configured_full_access_turn",
    "enable_full_access",
    "full_access",
    "handle_full_access_mode_change",
    "offer_full_access",
]

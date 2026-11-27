"""Build detached provider input from canonical ConnectOnion messages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Kept on the session for the chat UI and watch recovery. A strict Chat
# Completions API rejects them as unknown message fields.
_SESSION_ONLY_KEYS = frozenset({"id", "internal", "watch_event", "watch_events"})


def messages_for_provider(
    messages: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Copy messages without ConnectOnion's session-only keys."""

    return [
        {key: value for key, value in message.items() if key not in _SESSION_ONLY_KEYS}
        for message in messages
    ]

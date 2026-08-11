"""Build detached provider input from canonical ConnectOnion messages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def messages_for_provider(
    messages: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Copy messages without ConnectOnion's top-level domain identity."""

    return [
        {key: value for key, value in message.items() if key != "id"}
        for message in messages
    ]

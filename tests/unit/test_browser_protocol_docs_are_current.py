"""Authoritative browser docs describe the shipped OIP-only architecture."""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUTHORITATIVE_TEXTS = (
    REPO / "connectonion" / "cli" / "co_ai" / "main.py",
    REPO / "docs" / "cli" / "ai.md",
    REPO / "docs" / "network" / "websocket-protocol.md",
)


@pytest.mark.parametrize("document", AUTHORITATIVE_TEXTS, ids=lambda path: path.name)
def test_the_browser_protocol_owner_is_current(document):
    text = document.read_text(encoding="utf-8")

    assert "OIP" in text
    assert "/ws" in text
    assert "/acp" not in text.lower()

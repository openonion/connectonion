"""The browser migration is complete; authoritative docs must not move it back to the future."""

from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
AUTHORITATIVE_DOCS = (
    REPO / "docs" / "cli" / "ai.md",
    REPO / "docs" / "network" / "acp-websocket.md",
    REPO / "docs" / "network" / "websocket-protocol.md",
)
STALE_MIGRATION_CLAIMS = (
    "current O Chat release still connects through",
    "current O Chat release still\nuses `/ws`",
    "future React/O Chat native-ACP client",
    "until its React client migration is complete",
    "before the React/O Chat migration",
)


@pytest.mark.parametrize("document", AUTHORITATIVE_DOCS, ids=lambda path: path.name)
def test_the_browser_protocol_owner_is_current(document):
    text = document.read_text(encoding="utf-8")

    assert "@connectonion/react" in text
    assert "`/acp`" in text
    for stale_claim in STALE_MIGRATION_CLAIMS:
        assert stale_claim not in text, (
            f"{document.relative_to(REPO)} describes the completed native ACP "
            f"browser migration as future work: {stale_claim!r}"
        )

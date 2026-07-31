"""Every guide the agent is offered must exist.

index.md is the menu the agent reads to decide what to load_guide(). A row
pointing at a file that was never written is not a gap in the docs — it is a
tool call the agent will make and that will fail, every time, for as long as the
row is there.

This test is the point of the fix. Correcting today's eleven without it just
resets the clock until the next guide is listed before it is written.
"""

import re
from pathlib import Path

import pytest

GUIDES = Path(__file__).resolve().parents[2] / "connectonion/cli/co_ai/prompts/connectonion"


def _listed():
    rows = re.findall(r"^\|\s*`([a-z0-9][a-z0-9_/-]*)`\s*\|", (GUIDES / "index.md").read_text(), re.M)
    return sorted(set(rows))


def _on_disk():
    return sorted(str(p.relative_to(GUIDES).with_suffix("")) for p in GUIDES.rglob("*.md"))


def test_every_listed_guide_exists():
    missing = [g for g in _listed() if g not in _on_disk()]

    assert not missing, (
        "index.md offers guides with no file behind them, so load_guide() fails "
        f"on each: {missing}"
    )


def test_the_menu_is_not_empty():
    """A guard on the guard: a regex that stopped matching would make the test
    above pass by finding nothing to check."""
    assert len(_listed()) > 40


@pytest.mark.parametrize("guide", _listed())
def test_each_guide_has_content(guide):
    """An empty file satisfies "the file exists" while still wasting the call."""
    path = GUIDES / f"{guide}.md"
    if not path.exists():
        pytest.skip("covered by test_every_listed_guide_exists")

    assert len(path.read_text().strip()) > 80, f"{guide}.md is a stub"

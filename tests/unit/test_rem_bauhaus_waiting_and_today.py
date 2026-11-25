"""Tests for Bauhaus Waiting on You two-screen flow, Today flipper strip, and owner_record fallback."""

from datetime import datetime, timezone
from pathlib import Path

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import owner_record, render


def _build_invented_notebook(root: Path) -> None:
    prepare(root)
    book = Notebook(root)
    book.write(
        "people/owner-casey.md",
        "# Casey Lin\n\n## Facts\n"
        "- How we know them: This is the owner's page.\n"
        "- Email: casey@example.test\n\n"
        "## Open threads\n"
        "- You owe Mara a pilot review: \"Please send the pilot review notes before Friday.\" [1]\n\n"
        "## Sources\n"
        "1. outlook:msg-pilot-1\n",
    )
    book.write(
        "people/mara-ostrowski.md",
        "# Mara Ostrowski\n\n## Facts\n"
        "- Organisation: Fernhill Labs\n"
        "- Email: mara@fernhill.test\n\n"
        "## Open threads\n"
        "- You owe Mara a pilot review: \"Please send the pilot review notes before Friday.\" [1]\n"
        "- Mara asked you to confirm the contract dates: \"Could we lock in Tuesday at 2pm for signing?\" [2]\n\n"
        "## Sources\n"
        "1. outlook:msg-pilot-1\n"
        "2. outlook:msg-contract-2\n",
    )
    book.write(
        "orgs/fernhill-labs.md",
        "# Fernhill Labs\n\n## Facts\n"
        "- Domain: fernhill.test\n\n"
        "## Open threads\n"
        "- You owe Mara a pilot review: \"Please send the pilot review notes before Friday.\" [1]\n"
        "- Fernhill owes you the revised invoice.\n\n"
        "## Sources\n"
        "1. outlook:msg-pilot-1\n",
    )


def test_owner_record_falls_back_when_map_json_is_absent(tmp_path):
    """Synced notebooks without .state/map.json still resolve REM.owner so owner never appears as counterparty."""
    root = tmp_path / "rem"
    _build_invented_notebook(root)
    assert not (root / ".state" / "map.json").exists()
    assert owner_record(root) == "people/owner-casey.md"


def test_owner_record_falls_back_by_owner_email_when_marker_absent(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    book = Notebook(root)
    book.write(
        "people/devon-park.md",
        "# Devon Park\n\n## Facts\n- Email: devon@example.test\n",
    )
    monkeypatch.setattr("connectonion.rem.store_messages.owner_addresses", lambda _root: ["devon@example.test"])
    assert owner_record(root) == "people/devon-park.md"


def test_bauhaus_waiting_two_screen_and_today_strip_in_template(tmp_path):
    """Rendered snapshot carries self-healed owner and Bauhaus two-screen Waiting + Today flipper hooks."""
    root = tmp_path / "rem"
    _build_invented_notebook(root)
    html = render(root, live=False)
    assert '"owner": "people/owner-casey.md"' in html
    assert "function bauRenderDetail(" in html
    assert "function dedupOpenEntries(" in html
    assert "function bauTodayStrip(" in html
    assert ".deck:has(.qcard ~ .qcard)::before" not in html

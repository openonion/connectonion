"""Opt-in synthetic native acceptance, never the operator's session history.

This is deliberately not a mocked-Skill success test. An isolation/preflight
failure fails acceptance; do not convert it to a skip or enable broader tools.
"""

from datetime import datetime, timezone

import pytest

from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.service import approve_sources, run_sync
from tests.unit.test_wiki_source import rollout

pytestmark = [pytest.mark.real_api, pytest.mark.provider_cli]


def test_native_wiki_successive_updates_and_noop(tmp_path, monkeypatch):
    root, sources = tmp_path / "wiki", tmp_path / "sources"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sources)
    monkeypatch.setattr("connectonion.wiki.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    prepare(root)
    approve_sources(root)
    path = sources / "rollout-synthetic.jsonl"
    messages = [("user", "For Project Aurora we choose Markdown, not SQLite, because portability matters.")]
    rollout(path, messages)
    first = run_sync(root)
    assert first["outcome"] == "completed", first
    text = "\n".join(Notebook(root).read(record) for record in Notebook(root).list())
    assert "Aurora" in text and "Markdown" in text
    assert "portab" in text.lower()

    messages.append(("user", "Correction: Aurora prioritizes inspectability over portability; keep Markdown."
                     " The proposed SQLite alternative was not adopted."))
    rollout(path, messages)
    second = run_sync(root)
    assert second["outcome"] == "completed", second
    text = "\n".join(Notebook(root).read(record) for record in Notebook(root).list())
    assert "inspectab" in text.lower()
    unchanged = run_sync(root)
    assert unchanged["outcome"] == "no_change"
    assert unchanged["runner_attempts"] == 0

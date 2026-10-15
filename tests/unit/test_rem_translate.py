"""A page read in another language: made once by co ai, cached by the page's hash,
made again when the page changes, and never written over the page."""

import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import translate as tr
from connectonion.rem.config import prepare
from connectonion.rem.files import RemError

PAGE = "# Alice Chen\n\n## Facts\n- Role: founder [1]\n\n## Sources\n- [1] gmail:abc — intro mail\n"
CHINESE = "# Alice Chen\n\n## Facts\n- Role: 创始人 [1]\n\n## Sources\n- [1] gmail:abc — 介绍邮件\n"


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    prepare(tmp_path)
    (tmp_path / "people" / "alice-chen.md").write_text(PAGE)
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", ""))
    return tmp_path


def model(answer, calls):
    def run(workspace, prompt, config, stage):
        calls.append({"page": (workspace / "page.md").read_text(), "prompt": prompt, "stage": stage})
        (workspace / "translation.md").write_text(answer)
        return {"outcome": "natural"}
    return run


def test_a_translation_is_made_once_and_then_read_from_the_cache(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    assert tr.translate(notebook, "people/alice-chen.md", "zh") == CHINESE
    assert tr.translate(notebook, "people/alice-chen.md", "zh") == CHINESE
    assert len(calls) == 1 and calls[0]["page"] == PAGE and "`zh`" in calls[0]["prompt"]
    assert "a quote stays in its original language" in calls[0]["prompt"]
    assert (notebook / "people" / "alice-chen.md").read_text() == PAGE
    saved = notebook / ".state" / "translations" / "zh" / "people" / "alice-chen.md"
    assert saved.read_text().startswith("<!-- co rem translation of people/alice-chen.md sha256:")
    assert tr.cached_languages(notebook, "people/alice-chen.md") == {"zh": CHINESE}


def test_a_changed_page_makes_its_translation_stale_and_it_is_made_again(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    tr.translate(notebook, "people/alice-chen.md", "zh")
    (notebook / "people" / "alice-chen.md").write_text(PAGE.replace("founder", "CEO"))
    assert tr.cached(notebook, "people/alice-chen.md", "zh") is None
    assert tr.cached_languages(notebook, "people/alice-chen.md") == {}
    tr.translate(notebook, "people/alice-chen.md", "zh")
    assert len(calls) == 2 and "CEO" in calls[1]["page"]


def test_a_translation_that_breaks_headings_or_sources_is_not_cached(notebook, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE.replace("## Facts", "## 事实"), []))
    with pytest.raises(RemError, match="headings"):
        tr.translate(notebook, "people/alice-chen.md", "zh")
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE.replace(" [1]\n\n", "\n\n"), []))
    with pytest.raises(RemError, match="source ids"):
        tr.translate(notebook, "people/alice-chen.md", "zh")
    assert tr.cached(notebook, "people/alice-chen.md", "zh") is None


def test_a_translated_marker_is_refused_because_the_reader_would_misread_it(notebook, monkeypatch):
    """Codex turned `Nothing open as of 2026-09-29` into Chinese and the reader
    showed a closed conversation as an open thread (live check, 2026-10-15)."""
    page = PAGE + "\n## Open threads\nNothing open as of 2026-09-29; the role was filled [1].\n"
    (notebook / "people" / "alice-chen.md").write_text(page)
    translated = CHINESE + "\n## Open threads\n截至 2026-09-29，没有待处理事项 [1]。\n"
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(translated, []))
    with pytest.raises(RemError, match="Nothing open as of"):
        tr.translate(notebook, "people/alice-chen.md", "zh")
    kept = CHINESE + "\n## Open threads\nNothing open as of 2026-09-29；职位已招满 [1]。\n"
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(kept, []))
    assert tr.translate(notebook, "people/alice-chen.md", "zh") == kept


def test_the_investigation_stamp_is_never_sent_and_comes_back_as_written(notebook, monkeypatch):
    """Codex translated the stamp's label, and the reader lost the page's status."""
    stamp = "Investigation: mapped 2026-10-10 · investigated 2026-10-10 (outlook)"
    (notebook / "people" / "alice-chen.md").write_text(PAGE + "\n" + stamp + "\n")
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    assert tr.translate(notebook, "people/alice-chen.md", "zh") == CHINESE + "\n" + stamp + "\n"
    assert "Investigation:" not in calls[0]["page"]


def test_a_runner_that_cannot_run_is_named_before_any_model_call(notebook, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("Codex is not signed in", "codex login"))
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a: pytest.fail("model called"))
    with pytest.raises(RemError, match="codex login"):
        tr.translate(notebook, "people/alice-chen.md", "zh")


def test_a_language_is_a_tag_not_a_path(notebook):
    for bad in ("../people", "zh/../../x", "", "中文"):
        with pytest.raises(RemError, match="language"):
            tr.translation_path(notebook, "people/alice-chen.md", bad)


def test_the_snapshot_carries_only_current_translations(notebook, monkeypatch):
    from connectonion.rem.reader import snapshot
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, []))
    tr.translate(notebook, "people/alice-chen.md", "zh")
    record = next(r for r in snapshot(notebook)["records"] if r["path"] == "people/alice-chen.md")
    assert record["translations"] == {"zh": CHINESE} and record["text"] == PAGE


def test_cli_translate_prints_the_translation(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "--json", "translate",
                                      "people/alice-chen.md", "--to", "zh"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"] == CHINESE
    bad = CliRunner().invoke(app, ["rem", "--root", str(notebook), "--json", "translate",
                                   "people/alice-chen.md", "--to", "../x"])
    assert bad.exit_code != 0 and "language" in bad.output
    assert len(calls) == 1

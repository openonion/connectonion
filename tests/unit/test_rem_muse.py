"""Deepening one page reuses the runner and preserves its cited originals."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import muse as feature, runner
from connectonion.rem.config import prepare, read_config
from connectonion.rem.files import Notebook, RemError, state_path, write_json


RECORD = "people/avery-lin.md"
PAGE = '# Avery Lin\n\nThey said “Keep the original words”. [1]\n\n## Sources\n- [1] gmail:aaaaaaaaaaaa\n'


@pytest.fixture
def notebook(tmp_path):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.write(RECORD, PAGE)
    return book


@pytest.mark.parametrize("stage", ["enrich", "muse"])
def test_command_resolves_page_and_prints_report(notebook, monkeypatch, stage):
    calls = []
    monkeypatch.setattr(feature, stage, lambda root, record, **kw: calls.append((root, record, kw)) or {
        "changed": [record], "page_chars": [15030, 16210], "report": "A lead worth following"})
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "fixture"})
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook.root), stage, "avery-lin"])
    assert result.exit_code == 0, result.output
    assert calls[0][:2] == (notebook.root, RECORD)
    assert callable(calls[0][2]["stage_progress"])
    assert "A lead worth following" in result.stdout and "15,030 -> 16,210" in result.stdout
    assert f"show {RECORD}" in result.stdout


@pytest.mark.parametrize("stage", ["enrich", "muse"])
def test_unknown_page_uses_resolver_error(notebook, stage):
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook.root), stage, "missing"])
    assert result.exit_code == 1
    assert "No page matches that name, email or path" in result.output


@pytest.mark.parametrize("harness,expected", [("codex", {"input_tokens": 7, "output_tokens": 2}),
                                               ("claude-code", {"input_tokens": 28, "output_tokens": 14})])
def test_muse_turns_resume_one_thread_and_count_usage(notebook, monkeypatch, harness, expected):
    calls, progress = [], []

    def run(workdir, prompt, config, stage, **kw):
        calls.append((workdir, prompt, kw))
        assert next(workdir.glob("muse-*/candidate.md")).read_text() == PAGE
        return {"result": "No insight", "session_id": "first-thread" if len(calls) == 1 else "same-thread",
                "usage": {"input_tokens": len(calls), "output_tokens": 2}}

    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(runner, "promote_with_repairs", lambda *a, **kw: pytest.fail("unchanged page reviewed"))
    config = {**read_config(notebook.root), "runner": harness}
    result = runner.run_stage(notebook, [{"role": "page", "record": RECORD, "text": PAGE}],
                              config, stage="muse", turns=feature.MUSE_TURNS,
                              stage_progress=progress.append)
    assert len(calls) == 7
    assert "Now do Turn 1 only." in calls[0][1]
    assert calls[0][1].index("Now do Turn 1 only.") < calls[0][1].index("</co_rem_task>")
    assert [call[1] for call in calls[1:]] == list(feature.MUSE_TURNS[1:])
    assert all(call[0] == calls[0][0] for call in calls)
    assert [call[2] for call in calls[1:]] == [{"session": "first-thread"}] * 6
    assert progress == [f"turn {n} of 7" for n in range(1, 8)]
    assert result["usage"] == expected
    assert result["changed"] == []


def test_missing_session_cannot_resume(notebook, monkeypatch):
    monkeypatch.setattr(runner, "run_task", lambda *a, **kw: {"result": "questions", "usage": {"input_tokens": 9}})
    with pytest.raises(runner.RunFailed, match="session_id") as caught:
        runner.run_stage(notebook, [{"role": "page", "record": RECORD, "text": PAGE}],
                         read_config(notebook.root), stage="muse", turns=feature.MUSE_TURNS)
    assert caught.value.usage == {"input_tokens": 9}
    assert notebook.read(RECORD) == PAGE


def test_run_task_resumes_delegate(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(runner.subprocess, "run", lambda argv, **kw: calls.append(argv) or
                        SimpleNamespace(returncode=0, stdout=json.dumps({"outcome": "natural"}), stderr=""))
    prepare(tmp_path)
    runner.run_task(tmp_path, "next turn", read_config(tmp_path), "muse", session="abc")
    argv = calls[0]
    assert argv[argv.index("--resume") + 1] == "abc"


@pytest.mark.parametrize("stage", ["enrich", "muse"])
def test_stage_instructions_compose_core_and_page_kind(stage):
    text = runner.instructions(stage, page_kind="person")
    assert ("# Enrich one page" if stage == "enrich" else "# Muse on one page") in text
    directory = runner.useful_skills_dir()
    for name in ("rem-investigate", "rem-page-person"):
        body = (directory / name / "SKILL.md").read_text()
        assert re.sub(r"(?m)^Why these rules: .*\n+", "", body) in text
    assert (directory / "rem-investigate-person/SKILL.md").read_text() not in text
    assert (directory / "rem-correspondent/SKILL.md").read_text() not in text


@pytest.mark.parametrize("loss", ["quote", "source", "none"])
def test_muse_restores_lost_quotes_and_sources(notebook, loss):
    updated = PAGE + "\nAn insight.\n"
    if loss == "quote":
        updated = updated.replace("“Keep the original words”", "A paraphrase")
    if loss == "source":
        updated = updated.replace("- [1] gmail:aaaaaaaaaaaa", "- [1] gmail:bbbbbbbbbbbb")

    def fake(book, items, config, **kw):
        assert kw["stage"] == "muse" and kw["turns"] == feature.MUSE_TURNS
        book.write(RECORD, updated)
        return {"changed": [RECORD], "report": "An insight"}

    result = feature.muse(notebook.root, RECORD, runner=fake)
    assert notebook.read(RECORD) == (updated if loss == "none" else PAGE)
    assert bool(result["restored"]) == (loss != "none")
    assert result["changed"] == ([RECORD] if loss == "none" else [])
    assert result["page_chars"] == [len(PAGE), len(notebook.read(RECORD))]
    assert result["turns"] == 7


def test_enrich_keeps_and_replaces_its_ledger(notebook, monkeypatch):
    gathered = [{"source": f"gmail:{n * 12}", "text": f"Original {n}", "timestamp": "2026-10-01"}
                for n in ("a", "b")]
    seen = {}

    def gather(title, handles, **kw):
        assert title == "Avery Lin" and "Avery Lin" in handles
        assert kw["days"] == 3650 and kw["clients"] == {} and kw["attachments_dir"] is None
        assert kw["archive_root"] == notebook.root and kw["record"] == RECORD
        assert "live mail is not searched" in kw["mail_skipped"]
        return gathered, ["Saved mail read"]

    def fake(book, items, config, **kw):
        assert kw["stage"] == "enrich"
        assert items[0]["role"] == "page" and items[1]["role"] == "coverage"
        ledger = next(item for item in items if item["role"] == "evidence-index")
        assert ledger["sources"] == [item["source"] for item in gathered]
        assert "2 reachable sources" in ledger["text"] and "1" in ledger["text"]
        assert "gmail:bbbbbbbbbbbb" in ledger["text"]
        seen["index"] = Path(ledger["file"])
        assert seen["index"].is_file()
        assert seen["index"].read_text() not in ledger["text"]
        assert "one line per evidence file" in ledger["text"]
        assert "### <source id>" in ledger["text"]
        return {"changed": [], "report": "Open lead"}

    monkeypatch.setattr(feature, "gather", gather)
    result = feature.enrich(notebook.root, RECORD, runner=fake)
    assert result["items"] == 2 and result["report"] == "Open lead"
    assert seen["index"] == notebook.root / ".state/enrich/avery-lin" / feature.INDEX
    assert seen["index"].is_file()
    stale = seen["index"].parent / "stale.md"
    stale.write_text("Previous run")
    feature.enrich(notebook.root, RECORD, runner=fake)
    assert seen["index"].is_file() and not stale.exists()


@pytest.mark.parametrize("has_ledger", [True, False])
def test_muse_includes_ledger_and_archive_paths(notebook, has_ledger):
    index = feature.ledger_dir(notebook.root, RECORD) / feature.INDEX
    if has_ledger:
        index.parent.mkdir(parents=True)
        index.write_text("Saved ledger")

    def fake(book, items, config, **kw):
        ledger = items[1]
        assert ledger["role"] == "evidence-index" and ledger["source"] == "investigation:evidence"
        assert ledger["timestamp"]
        assert str(notebook.root / ".state/mail/messages") in ledger["text"]
        assert str(notebook.root / ".state/attachments") in ledger["text"]
        assert (str(index) in ledger["text"]) == has_ledger
        assert ("No enrich ledger exists for this page yet." in ledger["text"]) == (not has_ledger)
        if has_ledger:
            assert "A source the page does not cite yet" in ledger["text"]
        return {}

    feature.muse(notebook.root, RECORD, runner=fake)


@pytest.mark.parametrize("command", ["enrich", "muse"])
def test_refuses_missing_or_unsupported_pages(notebook, command):
    function = getattr(feature, command)
    with pytest.raises(RemError, match="does not exist"):
        function(notebook.root, "people/missing.md", runner=lambda *a, **kw: None)
    notebook.write("notes/notes.md", "# Notes")
    with pytest.raises(RemError, match="people/.*projects/.*orgs/"):
        function(notebook.root, "notes/notes.md", runner=lambda *a, **kw: None)


@pytest.mark.parametrize("stage", ["enrich", "muse"])
def test_changed_candidate_is_reviewed_once_after_all_turns(notebook, monkeypatch, stage):
    calls, reviews = [], []

    def run(workdir, prompt, config, phase, **kw):
        calls.append(prompt)
        candidate = next(workdir.glob(f"{stage}-*/candidate.md"))
        candidate.write_text(PAGE + "\nNew insight.\n")
        return {"result": "Findings", "session_id": "thread", "usage": {"output_tokens": 1}}

    def promote(book, record, candidate, original, *args, **kw):
        assert len(calls) == (7 if stage == "muse" else 1)
        assert kw["investigation"] is True
        reviews.append(record)
        book.write(record, candidate.read_text())

    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(runner, "promote_with_repairs", promote)
    result = runner.run_stage(notebook, [{"role": "page", "record": RECORD, "text": PAGE}],
                              read_config(notebook.root), stage=stage,
                              turns=feature.MUSE_TURNS if stage == "muse" else ())
    assert reviews == [RECORD] and result["changed"] == [RECORD]


@pytest.mark.parametrize("harness,failure_usage,expected", [
    ("codex", {"input_tokens": 45}, 45), ("codex", None, 25),
    ("codex", {}, 25), ("claude-code", {"input_tokens": 45}, 80),
    ("claude-code", None, 35), ("claude-code", {}, 35)])
def test_failed_later_turn_reports_all_usage_without_promotion(notebook, monkeypatch, harness, failure_usage, expected):
    calls = []

    def run(*args, **kw):
        calls.append(kw)
        if len(calls) == 3:
            raise runner.RunFailed("delegate failed", failure_usage)
        return {"result": "Questions", "session_id": "thread", "usage": {"input_tokens": 10 if len(calls) == 1 else 25}}

    monkeypatch.setattr(runner, "run_task", run)
    with pytest.raises(runner.RunFailed, match="delegate failed") as caught:
        runner.run_stage(notebook, [{"role": "page", "record": RECORD, "text": PAGE}],
                         {**read_config(notebook.root), "runner": harness}, stage="muse", turns=feature.MUSE_TURNS)
    assert caught.value.usage == {"input_tokens": expected}
    assert notebook.read(RECORD) == PAGE


def test_muse_reads_latest_completed_reports_for_this_page(notebook):
    for n, (phase, record, outcome, report) in enumerate([
            ("enrich", RECORD, "completed", "Old lead"),
            ("enrich", RECORD, "completed", "Newest lead"),
            ("muse", RECORD, "completed", "Open question"),
            ("enrich", RECORD, "failed", "Failed lead"),
            ("muse", "people/another.md", "completed", "Other person's question")], 1):
        write_json(state_path(notebook.root, f"runs/run_{n:032x}.json"), {
            "phase": phase, "record": record, "outcome": outcome, "report": report,
            "started_at": f"2026-10-{n:02d}T00:00:00+00:00"})

    def fake(book, items, config, **kw):
        prior = next(item for item in items if item["role"] == "prior-runs")
        assert "Open leads from enrich\nNewest lead" in prior["text"]
        assert "Questions the last muse run left\nOpen question" in prior["text"]
        assert all(text not in prior["text"] for text in ("Old lead", "Failed lead", "Other person's"))
        return {"report": "No insight"}

    feature.muse(notebook.root, RECORD, runner=fake)


def test_muse_preserves_quotes_when_markdown_link_markup_changes(notebook):
    before = PAGE.replace("original", "[original](https://example.com)")
    notebook.write(RECORD, before)

    def fake(book, items, config, **kw):
        book.write(RECORD, PAGE)
        return {"report": "Same quote"}

    result = feature.muse(notebook.root, RECORD, runner=fake)
    assert result["restored"] == "" and notebook.read(RECORD) == PAGE


def test_enrich_keeps_evidence_when_runner_refuses(notebook, monkeypatch):
    monkeypatch.setattr(feature, "gather", lambda *a, **kw: ([], []))
    directories = []

    def fake(book, items, config, **kw):
        directories.append(Path(next(item["file"] for item in items if item["role"] == "evidence-index")).parent)
        raise runner.RunFailed("review rejected")

    with pytest.raises(runner.RunFailed, match="review rejected"):
        feature.enrich(notebook.root, RECORD, runner=fake)
    assert (directories[0] / feature.INDEX).is_file()


def test_cited_originals_skip_gathered_ids_and_keep_private_context(notebook, monkeypatch):
    calls = []

    def context(root, records, **kw):
        calls.append(kw)
        return {source: {"time": "2026-10-01", "sender": "avery@example.com", "excerpt": "Original"}
                for source in ("gmail:aaaaaaaaaaaa", "gmail:bbbbbbbbbbbb")}

    monkeypatch.setattr(feature, "cited_context", context)
    items = feature._cited_originals(notebook.root, PAGE, {"gmail:aaaaaaaaaaaa"})
    assert calls == [{"private": True}]
    assert items == [{"role": "cited-original", "source": "gmail:bbbbbbbbbbbb", "timestamp": "2026-10-01",
                      "speaker": "avery@example.com", "subject": "", "text": "Original"}]


@pytest.mark.parametrize("stage", ["enrich", "muse"])
def test_skill_is_checked_before_reading_sources(notebook, monkeypatch, stage):
    def check(root, requested):
        assert root == notebook.root and requested == stage
        raise RemError("Skill unavailable")

    monkeypatch.setattr(runner, "check_skill", check)
    monkeypatch.setattr(feature, "gather", lambda *a, **kw: pytest.fail("gather before skill check"))
    monkeypatch.setattr(feature, "cited_context", lambda *a, **kw: pytest.fail("read before skill check"))
    with pytest.raises(RemError, match="Skill unavailable"):
        getattr(feature, stage)(notebook.root, RECORD)


def test_project_handles_use_mapped_paths_instead_of_aliases(notebook):
    from connectonion.rem.investigate import page_handles

    notebook.stub_project("projects/atlas.md", "Atlas", ["/work/atlas"])
    title, handles = page_handles(notebook, "projects/atlas.md", ["explicit@example.com"])
    assert title == "Atlas" and handles == ["explicit@example.com", "/work/atlas", "Atlas"]

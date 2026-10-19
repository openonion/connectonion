"""Deepening one page reuses the runner and preserves its cited originals."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import muse as feature, page_review, project_claim_review, runner
from connectonion.rem.config import prepare, read_config
from connectonion.rem.files import Notebook, RemError, state_path, write_json
from connectonion.rem.investigate import GITHUB_SOURCE


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
    assert result["turn_replies"] == ["No insight"] * 7


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


@pytest.mark.parametrize("stage", ["enrich", "muse"])
@pytest.mark.parametrize("loss", ["quote", "source", "none"])
def test_deepening_restores_lost_quotes_and_sources(notebook, monkeypatch, loss, stage):
    monkeypatch.setattr(feature, "gather", lambda *a, **kw: ([], []))
    updated = PAGE + "\nAn insight.\n"
    if loss == "quote":
        updated = updated.replace("“Keep the original words”", "A paraphrase")
    if loss == "source":
        updated = updated.replace("- [1] gmail:aaaaaaaaaaaa", "- [1] gmail:bbbbbbbbbbbb")

    def fake(book, items, config, **kw):
        assert kw["stage"] == stage
        if stage == "muse":
            assert kw["turns"] == feature.MUSE_TURNS
        book.write(RECORD, updated)
        return {"changed": [RECORD], "report": "An insight"}

    result = getattr(feature, stage)(notebook.root, RECORD, runner=fake)
    assert notebook.read(RECORD) == (updated if loss == "none" else PAGE)
    assert bool(result["restored"]) == (loss != "none")
    assert result["changed"] == ([RECORD] if loss == "none" else [])
    assert result["page_chars"] == [len(PAGE), len(notebook.read(RECORD))]
    if stage == "muse":
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
        originals = next(item for item in items if item["role"] == "original_evidence")
        assert json.loads(Path(originals["file"]).read_text()) == gathered
        assert Path(originals["file"]).name == "items.json"
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
        write_json(index.parent / "items.json", [{"source": "github:owner/repo#42", "text": "Issue"}])

    def fake(book, items, config, **kw):
        ledger = items[1]
        assert ledger["role"] == "evidence-index" and ledger["source"] == "investigation:evidence"
        assert ledger["timestamp"]
        assert str(notebook.root / ".state/mail/messages") in ledger["text"]
        assert str(notebook.root / ".state/attachments") in ledger["text"]
        assert (str(index) in ledger["text"]) == has_ledger
        assert ("No enrich ledger exists for this page yet." in ledger["text"]) == (not has_ledger)
        if has_ledger:
            assert ledger["file"] == str(index)
            assert ledger["sources"] == ["github:owner/repo#42"]
            assert "Uncited source ids" in ledger["text"]
            originals = items[2]
            assert originals["role"] == "original_evidence"
            assert originals["source"] == "investigation:original-evidence"
            assert originals["timestamp"]
            assert originals["file"] == str(index.parent / "items.json")
        else:
            assert not any(item["role"] == "original_evidence" for item in items)
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


@pytest.mark.parametrize("stage", ["enrich", "muse"])
def test_muse_reads_latest_completed_reports_for_this_page(notebook, monkeypatch, stage):
    monkeypatch.setattr(feature, "gather", lambda *a, **kw: ([], []))
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

    getattr(feature, stage)(notebook.root, RECORD, runner=fake)


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


def test_cited_attachment_without_time_or_sender_is_still_an_original(notebook, monkeypatch):
    monkeypatch.setattr(feature, "cited_context", lambda root, records, **kw: {
        "attachment:aaaaaaaaaaaa": {"excerpt": "Invoice INV-7", "truncated": False}})
    assert feature._cited_originals(notebook.root, PAGE) == [
        {"role": "cited-original", "source": "attachment:aaaaaaaaaaaa", "timestamp": "", "speaker": "",
         "subject": "", "text": "Invoice INV-7"}]


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


@pytest.fixture
def project(notebook, monkeypatch):
    record = "projects/atlas.md"
    checkout = notebook.root / "checkout"
    checkout.mkdir()
    notebook.stub_project(record, "Atlas", [str(checkout)])
    rows = [{"source": f"codex:atlas:{n}", "timestamp": "2026-10-01", "cwd": str(checkout),
             "text": f"Owner input {n}"} for n in (1, 2)]
    messages = state_path(notebook.root, "projects/atlas/messages.jsonl")
    messages.parent.mkdir(parents=True)
    messages.write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(feature, "gather", lambda *a, **kw: (
        [{"role": "user", **rows[0]}], ["Saved mail read"]))
    monkeypatch.setattr(feature.shutil, "which", lambda command: "/mock/gh")
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        assert kw == {"capture_output": True, "text": True, "timeout": 120}
        if argv[0] == "gh":
            if argv[1] == "search":
                return SimpleNamespace(returncode=0, stdout="[]", stderr="")
            assert argv[2:9] == ["list", "-R", "owner/atlas", "--state", "all", "--limit", "400"]
            assert argv[9:] == ["--json", "number,title,body,author,createdAt,state,url,comments"]
            number = 41 if argv[1] == "issue" else 42
            output = json.dumps([{
                "number": number, "title": f"Discussion {number}", "body": "Original body " + "x" * 7_000,
                "author": {"login": "owner"}, "createdAt": "2026-10-02T00:00:00Z", "state": "OPEN",
                "url": f"https://github.com/owner/atlas/issues/{number}",
                "comments": [{"author": {"login": "reviewer"}, "createdAt": "2026-10-03T00:00:00Z",
                              "body": "Comment retained for review"}]}])
        elif argv[3:] == ["remote", "get-url", "origin"]:
            output = "git@github.com:owner/atlas.git\n"
        else:
            assert argv[-2:] == ["--", "."]
            if "--first-parent" in argv:
                assert argv[3:-2] == ["log", "origin/HEAD", "--first-parent", "--reverse",
                                      "--date=short", "--format=%h %ad %s"]
                output = "abc123 2026-10-02 Ship atlas\n"
            else:
                assert argv[3:-2] == ["log", "origin/HEAD", "--date=short", "--format=%h %ad %an %s"]
                output = "abc123 2026-10-02 Owner Ship atlas\n"
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(feature.subprocess, "run", run)
    return SimpleNamespace(book=notebook, record=record, checkout=checkout, calls=calls)


def test_project_enrich_retains_all_originals_and_review_can_open_them(project):
    book, record = project.book, project.record
    stages = []

    def review(book, items, config, **kw):
        stages.append(kw["stage"])
        if kw["stage"] == "enrich":
            assert [item["role"] for item in items[:4]] == ["page", "coverage", "timeline", "evidence-index"]
            assert items[2]["source"] == "investigation:timeline"
            assert "## 2026-10 — 1 commits, 1 pull requests, 1 issues" in items[2]["text"]
            assert "github:owner/atlas#42 PR open: Discussion 42" in items[2]["text"]
            assert "commit abc123: Ship atlas" in items[2]["text"]
        ledger = next(item for item in items if item["role"] == "evidence-index")
        originals = next(item for item in items if item["role"] == "original_evidence")
        gathered = json.loads(Path(originals["file"]).read_text())
        assert [item["source"] for item in gathered] == [
            "codex:atlas:1", "codex:atlas:2", "github:owner/atlas#41", "github:owner/atlas#42",
            f"git-log:{project.checkout}"]
        assert ledger["sources"] == [item["source"] for item in gathered[:-1]]
        assert gathered[0]["speaker"] == "owner" and gathered[0]["project"] == str(project.checkout)
        assert "Ship atlas" in gathered[-1]["text"]
        assert len(gathered[2]["text"]) > 7_000
        for item in gathered[2:4]:
            assert GITHUB_SOURCE.fullmatch(item["source"])
            assert "--- comment by reviewer at 2026-10-03T00:00:00Z" in item["text"]
            assert "Comment retained for review" in item["text"]
            assert page_review._identifiable(item["source"], known=page_review._known_sources([ledger]),
                                             record=record, original=book.read(record), old_sources=set(),
                                             items=[ledger], pages=[])
        assert "4 reachable sources" in ledger["text"]
        material = runner.readable_material([ledger, originals])
        assert str(Path(originals["file"])) in material and "Original body" not in material
        candidate = "# Atlas\n\nA discussion. [1]\n\n## Sources\n- [1] github:owner/atlas#42\n"
        project_claim_review.retain_cited_originals(book, candidate, items)
        packet, missing = project_claim_review.packet(book, candidate, record, items)
        assert missing == [] and packet["sources"][0]["source_id"] == "github:owner/atlas#42"
        assert "Original body" in packet["sources"][0]["context"]["excerpt"]
        assert "Comment retained for review" in packet["sources"][0]["context"]["excerpt"]
        assert packet["sources"][0]["context"]["truncated"] is False
        return {}

    result = feature.enrich(book.root, record, runner=review)
    assert result["items"] == 5
    assert "github owner/atlas: 1 issues, 1 pull requests" in result["coverage"]
    assert "mapped sessions: 2 owner messages" in result["coverage"]
    feature.muse(book.root, record, runner=review)
    assert stages == ["enrich", "muse"]


def test_timeline_walks_months_oldest_first_and_lists_discussions_before_commits():
    rows = [
        {"date": "2025-04-01", "kind": "issue", "line": "github:acme/lantern#14 issue open: Next step"},
        {"date": "2025-03-01", "kind": "commit", "line": "commit 1a2b3c4: Start Lantern"},
        {"date": "2025-03-04", "kind": "pr", "line": "github:acme/lantern#12 PR merged: Ship Lantern"},
        {"date": "2025-03-05", "kind": "issue", "line": "github:acme/lantern#13 issue closed: Pick a name"}]
    text = feature._timeline_text(rows)
    assert text.index("## 2025-03 — 1 commits, 1 pull requests, 1 issues") < text.index("## 2025-04")
    assert text.index("#12 PR merged") < text.index("#13 issue closed") < text.index("commit 1a2b3c4")
    assert "## 2025-04 — 0 commits, 0 pull requests, 1 issues" in text
    assert "`git:<full sha>`" in text and "`git -C <path> show`" in text


def test_timeline_cap_reduces_examples_without_hiding_months():
    rows = [{"date": f"2025-{month:02d}-01", "kind": "commit", "line": f"commit {n:07x}: " + "x" * 900}
            for month in range(1, 13) for n in range(41)]
    text = feature._timeline_text(rows)
    assert len(text) <= 60_000
    assert len(re.findall(r"^## 2025-\d\d — 41 commits, 0 pull requests, 0 issues$", text, re.M)) == 12
    assert len(re.findall(r"^- ", text, re.M)) == 12 * 5


def test_timeline_lists_every_line_while_the_history_fits():
    rows = [{"date": "2025-03-01", "kind": "pr", "line": f"github:acme/lantern#{n} PR merged: Step {n}"}
            for n in range(40)]
    assert len(re.findall(r"^- ", feature._timeline_text(rows), re.M)) == 40


def test_history_keeps_own_repository_items_and_others_that_name_the_project(monkeypatch):
    monkeypatch.setattr(feature, "_github_checkouts", lambda page: [("/x", "acme/lantern")])
    item = lambda source, subject: {"source": source, "subject": subject, "kind": "pr", "state": "MERGED",
                                    "timestamp": "2025-03-01T00:00:00Z"}
    rows = feature._history_rows("# Lantern\n", [item("github:acme/lantern#1", "Fix README"),
                                                 item("github:acme/core#9", "lantern: send a task"),
                                                 item("github:acme/core#10", "Unrelated release")], "Lantern")
    assert [row["line"].split()[0] for row in rows] == ["github:acme/lantern#1", "github:acme/core#9"]


def test_timeline_caps_even_one_long_subject_per_month():
    rows = [{"date": f"2025-{month:02d}-01", "kind": "commit", "line": "commit 1a2b3c4: " + "x" * 10_000}
            for month in range(1, 13)]
    text = feature._timeline_text(rows)
    assert len(text) <= 60_000
    assert len(re.findall(r"^## 2025-\d\d — 1 commits, 0 pull requests, 0 issues$", text, re.M)) == 12
    assert len(re.findall(r"^- 2025-\d\d-01 commit 1a2b3c4:", text, re.M)) == 12


def test_history_reads_each_mapped_directory_and_falls_back_to_head(tmp_path, monkeypatch):
    checkout = tmp_path / "lantern"
    checkout.mkdir()
    calls = []

    def run(argv, **kw):
        calls.append(list(argv))
        assert argv[:4] == ["git", "-C", str(checkout), "log"]
        assert argv[5:] == ["--first-parent", "--reverse", "--date=short", "--format=%h %ad %s", "--", "."]
        return SimpleNamespace(returncode=1 if argv[4] == "origin/HEAD" else 0,
                               stdout="1a2b3c4 2025-03-05 Start Lantern\n", stderr="")

    monkeypatch.setattr(feature.subprocess, "run", run)
    monkeypatch.setattr(feature, "_github_checkouts", lambda page: [])
    rows = feature._history_rows(f"# Lantern\n\n## Paths\n- {checkout}\n", [])
    assert rows == [{"date": "2025-03-05", "kind": "commit", "line": "commit 1a2b3c4: Start Lantern"}]
    assert [call[4] for call in calls] == ["origin/HEAD", "HEAD"]


@pytest.mark.parametrize("failed_kind", ["issue", "pr"])
def test_failed_github_read_is_covered_and_enrich_runs(project, monkeypatch, failed_kind):
    run = feature.subprocess.run

    def fail(argv, **kw):
        if argv[:2] == ["gh", failed_kind]:
            return SimpleNamespace(returncode=1, stdout="", stderr="Not logged in " + "x" * 300)
        return run(argv, **kw)

    monkeypatch.setattr(feature.subprocess, "run", fail)
    seen = []
    result = feature.enrich(project.book.root, project.record,
                            runner=lambda book, items, config, **kw: seen.extend(items) or {})
    assert "github owner/atlas: not read (" + ("Not logged in " + "x" * 300)[:200] + ")" in result["coverage"]
    assert result["items"] == 3
    ledger = next(item for item in seen if item["role"] == "evidence-index")
    assert not any(source.startswith("github:") for source in ledger["sources"])


@pytest.mark.parametrize("remote", ["https://github.com/owner/atlas.git", "ssh://git@github.com/owner/atlas.git",
                                   "git@github.com:owner/atlas", "https://github.com/owner/atlas/"])
def test_github_repositories_are_deduplicated(project, monkeypatch, remote):
    run = feature.subprocess.run

    def origin(argv, **kw):
        if argv[0] == "git":
            return SimpleNamespace(returncode=0, stdout=remote, stderr="")
        return run(argv, **kw)

    second = project.book.root / "worktree"
    second.mkdir()
    page = project.book.read(project.record).replace(str(project.checkout), f"{project.checkout}\n- {second}")
    monkeypatch.setattr(feature.subprocess, "run", origin)
    items, coverage = feature._github_items(page)
    assert len(items) == 2 and len(coverage) == 1
    assert len([call for call in project.calls if call[0] == "gh"]) == 2


def test_git_log_falls_back_to_head(project, monkeypatch):
    run = feature.subprocess.run

    def log(argv, **kw):
        if argv[3:5] == ["log", "origin/HEAD"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="Unknown revision")
        if argv[3:5] == ["log", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="Fallback history", stderr="")
        return run(argv, **kw)

    monkeypatch.setattr(feature.subprocess, "run", log)
    assert feature._git_log_items(project.book.read(project.record))[0]["text"] == "Fallback history"


def test_github_item_preserves_long_discussion_up_to_40000_characters():
    item = feature._github_item("owner/atlas", {
        "number": 99, "author": None, "title": "Deleted author", "url": "url",
        "state": "OPEN", "createdAt": "date", "body": "x" * 50_000}, "issue")
    assert len(item["text"]) == 40_000 and item["speaker"] == ""


def test_missing_gh_is_covered_and_enrich_runs(project, monkeypatch):
    monkeypatch.setattr(feature.shutil, "which", lambda command: None)
    result = feature.enrich(project.book.root, project.record, runner=lambda *a, **kw: {})
    assert "github owner/atlas: not read (gh is not installed)" in result["coverage"]
    assert result["items"] == 3
    assert not any(call[0] == "gh" for call in project.calls)


def test_muse_counts_only_insight_verdicts_in_study_turns(notebook):
    replies = ["verdict: insight", "verdict: insight", "verdict: no insight", "verdict: **Insight**",
               "Verdict: open", "VERDICT: insight", "verdict: insight"]
    result = feature.muse(notebook.root, RECORD, runner=lambda *a, **kw: {"turn_replies": replies})
    assert result["insights"] == 3


@pytest.mark.parametrize("stage", ["enrich", "muse"])
@pytest.mark.parametrize("harness", ["codex", "claude-code"])
def test_audit_repairs_resume_last_thread_and_charge_only_their_usage(notebook, monkeypatch, stage, harness):
    calls, promotions = [], []
    turns = feature.MUSE_TURNS if stage == "muse" else ()
    initial = len(turns) or 1

    def run(workdir, prompt, config, phase, **kw):
        calls.append(kw)
        next(workdir.glob(f"{stage}-*/candidate.md")).write_text(PAGE + "\nNew finding.\n")
        n = len(calls)
        usage = {"input_tokens": 100 * n, "cached_input_tokens": 80 * n, "output_tokens": n}
        return {"result": "verdict: insight", "session_id": f"thread-{n}", "usage": usage}

    def promote(book, record, candidate, original, items, directory, usage, **kw):
        promotions.append(usage)
        if len(promotions) <= 2:
            write_json(directory / "review.json", {"errors": ["Quote is not in its cited source: 1"]})
            raise runner.RunFailed("Candidate rejected", usage)
        book.write(record, candidate.read_text())

    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(runner, "_promote_candidate", promote)
    result = runner.run_stage(notebook, [{"role": "page", "record": RECORD, "text": PAGE}],
                              {**read_config(notebook.root), "runner": harness}, stage=stage, turns=turns)
    assert calls[-2:] == [{"session": f"thread-{initial}"}] * 2
    expected = 200 if harness == "codex" else 100 * (initial + 1 + initial + 2)
    assert result["repairs"] == 2 and result["repair_usage"]["input_tokens"] == expected
    total = (initial + 2) * 100 if harness == "codex" else sum(100 * n for n in range(1, initial + 3))
    assert result["usage"]["input_tokens"] == total
    metrics = json.loads(next((notebook.root / ".state").rglob("result.json")).read_text())
    assert metrics["repairs"] == 2 and metrics["repair_usage"] == result["repair_usage"]
    if turns:
        assert len(result["turn_replies"]) == 7


def test_failed_resumed_repair_charges_delta_and_keeps_metrics(notebook, monkeypatch):
    calls = []

    def run(workdir, *a, **kw):
        calls.append(kw)
        if len(calls) == 2:
            raise runner.RunFailed("repair stopped", {"input_tokens": 150})
        next(workdir.glob("enrich-*/candidate.md")).write_text(PAGE + "\nNew finding.\n")
        return {"session_id": "thread", "usage": {"input_tokens": 100}}

    def reject(*args, **kw):
        write_json(args[5] / "review.json", {"errors": ["Quote is not in its cited source: 1"]})
        raise runner.RunFailed("Candidate rejected", args[6])

    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(runner, "_promote_candidate", reject)
    with pytest.raises(runner.RunFailed, match="repair stopped") as caught:
        runner.run_stage(notebook, [{"role": "page", "record": RECORD, "text": PAGE}],
                         {**read_config(notebook.root), "runner": "codex"}, stage="enrich")
    assert caught.value.usage == {"input_tokens": 150}
    metrics = json.loads(next((notebook.root / ".state").rglob("result.json")).read_text())
    assert metrics["repairs"] == 1 and metrics["repair_usage"] == {"input_tokens": 50}


def test_github_owner_search_reaches_other_repos_and_keeps_richer_duplicates(monkeypatch):
    monkeypatch.setattr(feature, "_github_checkouts", lambda page: [("/work/atlas", "avery/monorepo"),
                                                                 ("/work/other", "avery/other")])
    monkeypatch.setattr(feature.shutil, "which", lambda command: "/mock/gh")
    calls = []

    def row(repo, number):
        return {"repository": {"nameWithOwner": repo}, "number": number, "title": "Atlas finding",
                "createdAt": "2026-10-01T00:00:00Z", "state": "OPEN", "url": "https://example.com/issue",
                "body": "Original", "author": {"login": "avery"}}

    def run(argv, **kw):
        calls.append(argv)
        if argv[1] == "search":
            history = argv[3] == "Atlas in:title"
            order = ["--sort", "created", "--order", "asc"] if history else []
            assert argv[3:] == ["Atlas in:title" if history else "Atlas", "--owner", "avery", *order,
                                "--limit", "300" if history else "100", "--json",
                                "number,title,body,author,createdAt,state,url,repository"]
            rows = [row("avery/monorepo", 1), row("avery/sibling", 9)] if argv[2] == "issues" else []
            if history and argv[2] == "prs":
                rows = [dict(row("avery/sibling", 10), state="MERGED")]
        else:
            rows = [dict(row("avery/monorepo", 1), comments=[
                {"createdAt": "2026-10-02", "body": "Full comment", "author": {"login": "avery"}}])]
            if argv[1] != "issue" or argv[4] != "avery/monorepo":
                rows = []
        return SimpleNamespace(returncode=0, stdout=json.dumps(rows), stderr="")

    monkeypatch.setattr(feature.subprocess, "run", run)
    items, coverage = feature._github_items("# Atlas", "Atlas")
    assert [item["source"] for item in items] == ["github:avery/monorepo#1", "github:avery/sibling#9",
                                                 "github:avery/sibling#10"]
    assert "Full comment" in items[0]["text"]
    assert 'github search avery "Atlas": 2 issues, 0 pull requests' in coverage
    assert [item["kind"] for item in items] == ["issue", "issue", "pr"]
    assert items[-1]["state"] == "MERGED"
    assert len([argv for argv in calls if argv[1] == "search"]) == 4
    calls.clear()
    feature._github_items("# Ax", "Ax")
    assert not any(argv[1] == "search" for argv in calls)


def test_failed_github_search_records_coverage(project, monkeypatch):
    run = feature.subprocess.run

    def fail(argv, **kw):
        if argv[:2] == ["gh", "search"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="Not signed in")
        return run(argv, **kw)

    monkeypatch.setattr(feature.subprocess, "run", fail)
    items, coverage = feature._github_items(project.book.read(project.record), "Atlas")
    assert len(items) == 2
    assert 'github search owner "Atlas": not read (Not signed in)' in coverage


@pytest.mark.parametrize('stage', ['enrich', 'muse'])
@pytest.mark.parametrize('repair', [True, False])
def test_carried_losses_are_repaired_or_restored_after_two_repairs(notebook, monkeypatch, stage, repair):
    # Isolate retention from page shape and source audits; promotion still runs its transformations.
    monkeypatch.setattr(page_review, 'validate', lambda *a, **kw: [])
    monkeypatch.setattr(page_review, 'misquoted', lambda *a, **kw: [])
    monkeypatch.setattr(runner, 'AUDIT', SimpleNamespace(get=lambda: False))
    directory = notebook.root / 'review'
    directory.mkdir()
    candidate = directory / 'candidate.md'
    candidate.write_text(PAGE.replace('“Keep the original words”', 'A paraphrase')
                         .replace('gmail:aaaaaaaaaaaa', 'gmail:bbbbbbbbbbbb'))
    calls = []

    def run(workdir, prompt, config, phase):
        calls.append(prompt)
        assert phase == stage
        assert 'Dropped quote the page had: “Keep the original words”' in prompt
        assert 'Dropped source id the page had: gmail:aaaaaaaaaaaa' in prompt
        assert 'Put each named quote and source back where it was, unchanged, unless an original contradicts it.' in prompt
        if repair:
            candidate.write_text(PAGE + '\nA new finding.\n')
        return {}

    args = (notebook, RECORD, candidate, PAGE, [{'source': 'gmail:bbbbbbbbbbbb'}], directory, {})
    kwargs = dict(workdir=notebook.root, config={}, stage=stage, run=run)
    if repair:
        runner.promote_with_repairs(*args, **kwargs)
        assert len(calls) == 1
        assert page_review.dropped(PAGE, notebook.read(RECORD)) == []
    else:
        runner.promote_with_repairs(*args, **kwargs)
        assert len(calls) == 2
        assert 'They said A paraphrase. [1]' in notebook.read(RECORD)
        assert page_review.dropped(PAGE, notebook.read(RECORD)) == []
        review = json.loads((directory / 'review.json').read_text())
        assert review['accepted'] and review['restored_lines'] == 1

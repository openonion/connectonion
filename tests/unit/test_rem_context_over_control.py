"""Investigation can use local tools and leaves a source trail after the turn."""

import json
import hashlib
import subprocess

import pytest

from connectonion.rem import investigate as inv
from connectonion.rem import runner as rem_runner
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook


@pytest.mark.parametrize("stage", ["init", "investigate"])
@pytest.mark.parametrize("harness,flag,value", [
    ("codex", "--sandbox", "danger-full-access"),
    ("claude-code", "--permission-mode", "bypassPermissions"),
])
def test_investigation_stages_authorize_shell_tools(stage, harness, flag, value):
    config = default_config()
    config["runner"] = harness
    flags = rem_runner.harness_flags(config, stage)
    assert flags[flags.index(flag) + 1] == value


def test_completed_task_record_keeps_source_id_path_and_timestamp(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    source = {"role": "project-file", "source": "file:/work/reader/README.md",
              "file": "/work/reader/README.md", "timestamp": "2026-10-01T09:00:00Z",
              "captured_at": "2026-10-03T09:00:00Z", "text": "Reader design"}
    monkeypatch.setattr(rem_runner, "run_task", lambda *args: {"result": "Inspected README.md at /work/reader",
                                                               "usage": None})
    rem_runner.run_stage(Notebook(root), [source], default_config(), stage="init")
    record = json.loads(next((root / ".state/tasks").glob("init-*/result.json")).read_text())
    assert record["evidence"] == [{key: source[key] for key in
                                   ("source", "file", "timestamp", "captured_at")}]
    assert "Inspected README.md" in record["report"]


def test_project_turn_supplies_live_repo_and_keeps_original_provenance(tmp_path, monkeypatch):
    repo = tmp_path / "reader"
    repo.mkdir()
    (repo / "README.md").write_text("# Reader\nLocal source of truth.\n")
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_project("projects/reader.md", "Reader", [str(repo)])
    mail = {"role": "user", "source": "codex:session:1", "project": str(repo),
            "timestamp": "2026-10-01T09:00:00Z", "text": "Inspect the Reader repository."}
    monkeypatch.setattr(inv, "gather", lambda *args, **kwargs: ([mail], ["codex: 1 related input"]))
    seen = []
    result = inv.investigate(root, "projects/reader.md", "Reader", ["Reader"], days=7,
                             clients={}, subscriptions={},
                             runner=lambda notebook, items, config, stage: seen.extend(items) or
                             {"changed": [], "report": "Inspected README.md", "usage": None})
    paths = next(item for item in seen if item["role"] == "project-repositories")
    assert paths["paths"] == [str(repo)] and "git log" in paths["text"]
    assert {item["source"] for item in result["evidence"]} >= {
        "codex:session:1", "investigation:project-repositories"}
    assert next(item for item in result["evidence"] if item["source"] == "codex:session:1")[
        "timestamp"] == mail["timestamp"]


def test_project_paths_cannot_be_cited_as_file_evidence(tmp_path):
    from connectonion.rem.page_review import validate

    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_project("projects/reader.md", "Reader", [str(tmp_path / "reader")])
    original = notebook.read("projects/reader.md")
    candidate = original.replace("## Sources\n", "## Sources\n- [1] investigation:project-repositories — 2026-10-03\n")
    candidate = candidate.replace("## What it is\n", "## What it is\n- A reader [1].\n")
    errors = validate("projects/reader.md", candidate, original, [
        {"role": "project-repositories", "source": "investigation:project-repositories",
         "paths": [str(tmp_path / "reader")]}
    ])
    assert any("Project paths are reading leads" in error for error in errors)


def test_live_file_citation_is_hash_pinned_and_openable_after_file_changes(tmp_path, monkeypatch):
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem import project_claim_review

    repo = tmp_path / "reader"
    repo.mkdir()
    file = repo / "feature.md"
    file.write_text("Verified feature design.\n")
    source = f"file:{file}@{hashlib.sha256(file.read_bytes()).hexdigest()}"
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    record = "projects/reader.md"
    notebook.stub_project(record, "Reader", [str(repo)])

    def write_candidate(workdir, prompt, config, stage):
        candidate = next(path for path in workdir.glob("investigate-*")
                         if not (path / "result.json").exists()) / "candidate.md"
        page = notebook.read(record).replace("- Unknown — not investigated yet", "- Unknown")
        page = page.replace("## What it is\n- Unknown", "## What it is\n- Verified feature design [1]")
        page = page.replace("- (none yet)", f"- [1] {source} — 2026-10-03")
        assert "Verified feature design [1]" in page
        candidate.write_text(page)
        return {"result": f"Inspected {file}", "usage": None}

    monkeypatch.setattr(rem_runner, "run_task", write_candidate)

    def audited(notebook, candidate, *_args, **_kwargs):
        material, missing = project_claim_review.packet(notebook, candidate)
        assert missing == []
        assert material['sources'][0]['context']['excerpt'] == 'Verified feature design.'
        return {'verdict': 'pass', 'findings': []}, {}

    monkeypatch.setattr(project_claim_review, 'review', audited)
    result = rem_runner.run_stage(notebook, [{"role": "page", "record": record,
                                              "source": "investigation:page", "text": notebook.read(record)}],
                                  default_config(), stage="investigate")
    assert result["changed"] == [record]
    file.write_text("Changed after the investigation.\n")
    context = cited_context(root, [{"text": notebook.read(record)}])[source]
    assert context["excerpt"] == "Verified feature design."
    assert context["captured_at"] and context["time"]
    assert "SHA-256" in context["input_scope"]
    rem_runner.run_stage(notebook, [{"role": "page", "record": record,
                                     "source": "investigation:page", "text": notebook.read(record)}],
                         default_config(), stage="investigate")


def test_historical_git_file_outside_prepared_snapshots_is_openable(tmp_path, monkeypatch):
    from connectonion.rem.reader_model import cited_context

    repo = tmp_path / "reader"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    file = repo / "feature.md"
    file.write_text("Original feature design.\n")
    subprocess.run(["git", "-C", str(repo), "add", "feature.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org",
                    "commit", "-qm", "Add feature"], check=True)
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    file.write_text("New working tree design.\n")
    source = f"git:{repo}:{commit}:feature.md"
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    record = "projects/reader.md"
    notebook.stub_project(record, "Reader", [str(repo)])

    def write_candidate(workdir, prompt, config, stage):
        candidate = next(path for path in workdir.glob("investigate-*")
                         if not (path / "result.json").exists()) / "candidate.md"
        page = notebook.read(record).replace("- Unknown — not investigated yet", "- Unknown")
        page = page.replace("## What it is\n- Unknown", "## What it is\n- Original feature design [1]")
        candidate.write_text(page.replace("- (none yet)", f"- [1] {source} — 2026-10-03"))
        return {"result": f"Inspected {source}", "usage": None}

    monkeypatch.setattr(rem_runner, "run_task", write_candidate)
    rem_runner.run_stage(notebook, [{"role": "page", "record": record,
                                     "source": "investigation:page", "text": notebook.read(record)}],
                         default_config(), stage="investigate")
    context = cited_context(root, [{"text": notebook.read(record)}])[source]
    assert context["excerpt"] == "Original feature design."
    assert context["time"] and context["captured_at"] and commit[:12] in context["input_scope"]
    assert context["origin"] == source


def test_scheduled_run_record_keeps_page_evidence_and_inspection_report(tmp_path, monkeypatch):
    from connectonion.rem import daily

    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_person("people/ada.md", "Ada", ["ada@example.org"], email="ada@example.org")
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [{"path": "people/ada.md"}])
    monkeypatch.setattr(daily, "_clients", lambda sources: {})
    evidence = [{"source": "outlook:message-1", "file": "/mail/archive/2026-10.md",
                 "timestamp": "2026-10-01T09:00:00Z"}]
    result = daily.run_daily(root, scheduled=True,
                             maintain=lambda root, scheduled: {"outcome": "no_change"},
                             investigate_one=lambda *args, **kwargs: {
                                 "changed": [], "usage": None, "evidence": evidence,
                                 "report": "Inspected /mail/archive/2026-10.md"})
    record = json.loads(next((root / ".state/runs").glob("run_*.json")).read_text())
    assert result["outcome"] == "completed"
    assert record["pages"][0]["evidence"] == evidence
    assert "Inspected /mail/archive/2026-10.md" in record["pages"][0]["report"]
    from connectonion.rem.reader import snapshot
    assert snapshot(root)["logs"][0]["pages"][0]["evidence"] == evidence


def test_manual_run_record_keeps_page_evidence_and_inspection_report(tmp_path):
    from connectonion.cli.commands.rem_commands import _logged

    root = tmp_path / "rem"
    prepare(root)
    evidence = [{"source": "file:/work/reader/README.md", "file": "/work/reader/README.md",
                 "timestamp": "2026-10-01T09:00:00Z"}]
    _logged(root, "projects/reader.md", "investigate",
            lambda update: {"changed": [], "items": 1, "usage": None,
                            "evidence": evidence, "report": "Inspected /work/reader/README.md"},
            quiet=True)
    record = json.loads(next((root / ".state/runs").glob("run_*.json")).read_text())
    assert record["evidence"] == evidence
    assert record["report"] == "Inspected /work/reader/README.md"
    from connectonion.rem.reader import snapshot
    assert snapshot(root)["logs"][0]["report"] == record["report"]

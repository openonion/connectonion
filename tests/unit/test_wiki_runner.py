"""Wiki sends tasks to the COAI CLI; harness internals belong to COAI."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.wiki.config import default_config, prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.runner import RunFailed, run_stage
from connectonion.wiki.extract import run_extract


@pytest.fixture
def notebook(tmp_path):
    root = tmp_path / "wiki"
    prepare(root)
    nb = Notebook(root)
    nb.write("notes/old.md", "# Existing\nKeep this.")
    return nb


@pytest.fixture
def delegate(monkeypatch):
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        if argv[-1].startswith('/wiki-investigate'):
            import re
            path = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
            path.write_text((Path(kw['cwd']) / 'notes/old.md').read_text())
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "outcome": "natural", "result": "done", "usage": {"input_tokens": 13}}), stderr="")

    monkeypatch.setattr("connectonion.wiki.runner.shutil.which", lambda name: "/opt/bin/co")
    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", run)
    return calls


@pytest.mark.parametrize("stage", ["maintain", "investigate", "abstract", "init"])
@pytest.mark.parametrize("harness", ["codex", "coai", "claude-code"])
def test_every_stage_uses_same_cli_and_explicit_harness(notebook, delegate, stage, harness):
    config = default_config()
    config.update(runner=harness, model="default")
    item = {"role": "page", "record": "notes/old.md", "text": "x" * 300000}
    result = run_stage(notebook, [item], config, stage=stage)
    argv, options = delegate[0]
    assert argv[:5] == ["/opt/bin/co", "ai", "--json", "--harness",
                        "ours" if harness == "coai" else harness]
    assert argv[-1].startswith(f"/wiki-{stage} ")
    assert len(argv[-1]) < 8000  # Large material must not go through argv.
    if stage in ("investigate", "maintain"):
        assert Path(options["cwd"]).name == "notebook"
        assert Path(options["cwd"]) != notebook.root
    else:
        assert options["cwd"] == str(notebook.root)
    seconds = config["limits"]["timeout_seconds"]
    assert options["timeout"] == seconds + (0 if harness == "coai" else 15)
    if harness != "coai":
        assert argv[argv.index("--timeout") + 1] == str(seconds)
    material = next((notebook.root / ".state/tasks").glob("*/material.json"))
    assert json.loads(material.read_text()) == [item]
    assert result["usage"] == {"input_tokens": 13}
    assert result["changed"] == []


def test_changes_include_deleted_and_partial_files(notebook, monkeypatch, delegate):
    def fail(argv, **kw):
        notebook.delete("notes/old.md")
        notebook.write("notes/new.md", "# New\nOnly partly finished.")
        return SimpleNamespace(returncode=1, stdout=json.dumps({
            "outcome": "error", "error": "model unavailable",
            "usage": {"input_tokens": 7}}), stderr="")

    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", fail)
    with pytest.raises(RunFailed) as caught:
        run_stage(notebook, [], default_config())
    assert caught.value.changed == ["notes/new.md", "notes/old.md"]
    assert caught.value.usage == {"input_tokens": 7}


def test_timeout_reports_partial_changes(notebook, monkeypatch, delegate):
    def timeout(argv, **kw):
        notebook.write("notes/new.md", "# Partial")
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", timeout)
    with pytest.raises(RunFailed, match="timed out") as caught:
        run_stage(notebook, [], default_config())
    assert caught.value.changed == ["notes/new.md"]


@pytest.mark.parametrize("payload", ['[]', '42', '{}', '{"outcome":"natural","usage":"oops"}'])
def test_invalid_envelope_fails(notebook, monkeypatch, delegate, payload):
    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run",
                        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=payload, stderr=""))
    with pytest.raises(RunFailed):
        run_stage(notebook, [], default_config())


def test_extract_reads_written_notes_not_status_text(monkeypatch, delegate):
    def extract(argv, **kw):
        directory = Path(kw["cwd"])
        assert argv[-1].startswith("/wiki-extract ")
        assert "--harness" in argv
        assert json.loads((directory / "material.json").read_text())[0]["text"] == "source"
        (directory / "notes.md").write_text("## People\n- Alice agreed [mail:1]")
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "outcome": "natural", "result": "I wrote the notes", "usage": {"input_tokens": 9}}), stderr="")

    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", extract)
    result = run_extract([{"text": "source", "source": "gmail:1"}], default_config(), "gmail")
    assert result == {"notes": "## People\n- Alice agreed [mail:1]", "usage": {"input_tokens": 9}}


def test_extract_without_output_fails_and_preserves_usage(delegate):
    with pytest.raises(RunFailed, match="notes") as caught:
        run_extract([], default_config())
    assert caught.value.usage == {"input_tokens": 13}


def test_coai_cache_metadata_does_not_break_usage_accounting(notebook, monkeypatch, delegate):
    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", lambda *a, **kw:
        SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
            "outcome": "natural", "usage": {"input_tokens": 5, "cache_metadata_status": "measured"}})))
    result = run_stage(notebook, [], default_config())
    assert result["usage"] == {"input_tokens": 5}


def test_skill_composition_keeps_source_and_page_definition(notebook, delegate):
    run_stage(notebook, [], default_config(), kind="codex")
    text = next((notebook.root / ".state/tasks").glob("*/instructions.md")).read_text()
    assert "wiki-source-codex" in text and "# A person's page" in text
    assert "wiki_write" not in text and "wiki_people" not in text

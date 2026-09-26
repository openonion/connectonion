"""Wiki sends tasks to the COAI CLI; harness internals belong to COAI."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.wiki.config import default_config, prepare
from connectonion.wiki.extract import run_extract
from connectonion.wiki.files import Notebook
from connectonion.wiki.runner import RunFailed, run_stage


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
            path.write_text((Path(kw['cwd']).parent.parent / 'notes/old.md').read_text())
        if argv[-1].startswith('/wiki-maintain'):
            workspace = Path(kw['cwd'])
            directory = max(workspace.glob('maintain-*'), key=lambda path: path.stat().st_mtime_ns)
            items = json.loads((directory / 'material.json').read_text())
            sources = sorted({item['source'] for item in items if item.get('source')})
            (directory / 'completion.json').write_text(json.dumps({
                'status': 'no_change', 'sources': sources, 'reason': 'No durable new fact.'}))
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "outcome": "natural", "result": "done", "usage": {"input_tokens": 13}}), stderr="")

    monkeypatch.setattr("connectonion.wiki.runner.co_command", lambda: ["/opt/bin/co"])
    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", run)
    return calls


def test_model_runs_use_the_running_installation_not_the_first_co_on_path(notebook, monkeypatch):
    """`venv/bin/co wiki ...` from a non-activated venv, with an older co earlier
    on PATH, sent every model turn to that older `co ai` (seen on 1.8.8b7)."""
    import sys
    calls = []
    monkeypatch.setattr("shutil.which", lambda name: "/elsewhere/bin/co")
    monkeypatch.setattr(sys, "executable", "/work/venv/bin/python")
    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", lambda argv, **kw: calls.append(argv) or
                        SimpleNamespace(returncode=0, stdout='{"outcome": "natural"}', stderr=""))
    run_stage(notebook, [], default_config())
    assert calls[0][:5] == ["/work/venv/bin/python", "-m", "connectonion.cli.main", "ai", "--json"]


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
    assert options["cwd"] == str(notebook.root / ".state/tasks")
    seconds = config["limits"]["timeout_seconds"]
    assert options["timeout"] == seconds + (0 if harness == "coai" else 15)
    if harness != "coai":
        assert argv[argv.index("--timeout") + 1] == str(seconds)
    # Every stage, not only investigation, reads untrusted source text. Codex
    # may use its sandboxed shell for local file operations, never the network.
    if harness == "claude-code":
        assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    else:
        assert "--permission-mode" not in argv
    if harness == "codex":
        assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    else:
        assert "--sandbox" not in argv
    material = next((notebook.root / ".state/tasks").glob("*/material.json"))
    assert json.loads(material.read_text()) == [item]
    assert result["usage"] == {"input_tokens": 13}
    assert result["changed"] == []


def test_claude_wiki_does_not_inherit_an_api_billing_key(notebook, delegate, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-test-key")
    config = default_config()
    config["runner"] = "claude-code"
    run_stage(notebook, [], config)
    assert "ANTHROPIC_API_KEY" not in delegate[0][1]["env"]
    assert delegate[0][1]["cwd"] == str(notebook.root / ".state/tasks")


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


def test_abstract_writes_disposable_copy_then_promotes(notebook, monkeypatch, delegate):
    def write_decision(argv, **kw):
        workspace = Path(kw["cwd"])
        working = next(workspace.glob("abstract-*/notebook"))
        assert working != notebook.root
        Notebook(working).write("decisions/example.md", "# Why use Markdown\n\n## Why\nReadable pages.\n")
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "outcome": "natural", "result": "done", "usage": {"input_tokens": 2}}), stderr="")

    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", write_decision)
    result = run_stage(notebook, [], default_config(), stage="abstract")
    assert result["changed"] == ["decisions/example.md"]
    assert notebook.read("decisions/example.md").startswith("# Why use Markdown")


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


def test_extract_reads_written_notes_not_status_text(tmp_path, monkeypatch, delegate):
    def extract(argv, **kw):
        import re
        root = tmp_path / "wiki"
        assert Path(kw["cwd"]) == root / ".state/tasks"
        directory = Path(re.search(r"Write the complete extraction notes to (.+?);", argv[-1])[1]).parent
        assert directory.parent == root / ".state/tasks"
        assert argv[-1].startswith("/wiki-extract ")
        assert "--harness" in argv
        assert json.loads((directory / "material.json").read_text())[0]["text"] == "source"
        (directory / "notes.md").write_text("## People\n- Alice agreed [mail:1]")
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "outcome": "natural", "result": "I wrote the notes", "usage": {"input_tokens": 9}}), stderr="")

    monkeypatch.setattr("connectonion.wiki.runner.subprocess.run", extract)
    result = run_extract([{"text": "source", "source": "gmail:1"}], default_config(), "gmail",
                         root=tmp_path / "wiki")
    assert result == {"notes": "## People\n- Alice agreed [mail:1]", "usage": {"input_tokens": 9}}


def test_extract_without_output_fails_and_preserves_usage(tmp_path, delegate):
    with pytest.raises(RunFailed, match="notes") as caught:
        run_extract([], default_config(), root=tmp_path / "wiki")
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


@pytest.mark.parametrize("scenario,accepted", [
    ("refused_without_receipt", False),
    ("wrong_source_receipt", False),
    ("blocked_receipt", False),
    ("missing_material", False),
    ("reviewed_no_change", True),
    ("local_page_update", True),
])
def test_offline_maintenance_benchmark(notebook, monkeypatch, scenario, accepted):
    """Fixed local-file cases distinguish a completed turn from completed work."""
    source = "codex:synthetic:1"

    def simulated_agent(argv, **kw):
        prompt = argv[-1]
        task = next(Path(kw['cwd']).glob('maintain-*'))
        assert 'no shell' not in prompt
        assert 'local file reads and writes' in prompt
        assert 'do not run commands, browse or search' not in prompt
        material_path = task / 'material-readable.json'
        if scenario == 'missing_material':
            material_path.unlink()
        else:
            material = json.loads(material_path.read_text())
            assert material[0]['source'] == source
        if scenario == 'local_page_update':
            page = task / 'notebook/notes/old.md'
            page.write_text(page.read_text() + '\n\nA durable update.\n')
        elif scenario not in ('refused_without_receipt', 'missing_material'):
            status = 'blocked' if scenario == 'blocked_receipt' else 'no_change'
            sources = ['wrong:source'] if scenario == 'wrong_source_receipt' else [source]
            (task / 'completion.json').write_text(json.dumps({
                'status': status, 'sources': sources, 'reason': 'Reviewed; no durable change.'}))
        return SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({
            'outcome': 'natural', 'result': 'done', 'usage': {'input_tokens': 23}}))

    monkeypatch.setattr('connectonion.wiki.runner.subprocess.run', simulated_agent)
    item = {'role': 'user', 'source': source, 'text': 'Synthetic maintenance input.'}
    if accepted:
        result = run_stage(notebook, [item], default_config())
        assert bool(result['changed']) == (scenario == 'local_page_update')
    else:
        with pytest.raises(RunFailed, match='no accepted changes') as caught:
            run_stage(notebook, [item], default_config())
        assert caught.value.usage == {'input_tokens': 23}
        assert 'A durable update' not in notebook.read('notes/old.md')


def test_rejected_maintenance_page_cannot_be_disguised_as_no_change(notebook, monkeypatch):
    notebook.stub_person('people/alice.md', 'Alice', [])
    original = notebook.read('people/alice.md')

    def simulated_agent(argv, **kw):
        task = next(Path(kw['cwd']).glob('maintain-*'))
        page = task / 'notebook/people/alice.md'
        page.write_text('# Alice\n\n## Who they are\n- Unsourced claim. [1]\n')
        (task / 'completion.json').write_text(json.dumps({
            'status': 'no_change', 'sources': ['codex:synthetic:2'],
            'reason': 'Nothing changed.'}))
        return SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({
            'outcome': 'natural', 'result': 'done', 'usage': {'input_tokens': 17}}))

    monkeypatch.setattr('connectonion.wiki.runner.subprocess.run', simulated_agent)
    with pytest.raises(RunFailed, match='only rejected pages'):
        run_stage(notebook, [{'role': 'user', 'source': 'codex:synthetic:2',
                              'text': 'Synthetic update.'}], default_config())
    assert notebook.read('people/alice.md') == original


def test_one_bad_page_does_not_hold_back_the_rest_of_a_maintenance_batch(tmp_path):
    """A real batch touched three pages, one lacked its overview diagram, and the
    whole batch was refused -- with the cursor held, so every scheduled run
    retried the same refusal and upkeep stopped."""
    from connectonion.wiki.config import prepare
    from connectonion.wiki.files import Notebook
    from connectonion.wiki.runner import _promote_maintenance
    root, work = tmp_path / "wiki", tmp_path / "work"
    prepare(root)
    prepare(work)
    notebook, working = Notebook(root), Notebook(work)
    for record, name in (("people/good.md", "Good"), ("people/bad.md", "Bad")):
        notebook.stub_person(record, name, [])
        working.stub_person(record, name, [])
    before = {r: notebook.read(r) for r in notebook.list()}
    items = [{"role": "user", "source": "codex:abc:1", "text": "x", "timestamp": "2026-09-24T00:00:00+00:00"}]
    good = before["people/good.md"].replace("## Who they are\n- Unknown — not investigated yet",
                                             "## Who they are\n- Ships the agent. [1]").replace(
        "## Sources\n- (none yet)", "## Sources\n- [1] `codex:abc:1`, 2026-09-24.")
    bad = before["people/bad.md"].replace("## Who they are\n- Unknown — not investigated yet",
                                           "## Who they are\n- Invented. [1]").replace(
        "## Sources\n- (none yet)", "## Sources\n- [1] Outlook message 39.")
    working.write("people/good.md", good)
    working.write("people/bad.md", bad)
    directory = tmp_path / "task"
    directory.mkdir()
    refusals = _promote_maintenance(notebook, working, before, items, directory, None, False)
    assert notebook.read("people/good.md") == good                      # written
    assert notebook.read("people/bad.md") == before["people/bad.md"]     # kept as it was
    assert [r["record"] for r in refusals] == ["people/bad.md"]
    assert (directory / "refused" / "people/bad.md").read_text() == bad  # the model's work is kept

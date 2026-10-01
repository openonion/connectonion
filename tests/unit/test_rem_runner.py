"""co rem sends tasks to the COAI CLI; harness internals belong to COAI."""

import json
import os
import time
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.rem.config import default_config, prepare
from connectonion.rem.extract import run_extract
from connectonion.rem.files import Notebook
from connectonion.rem.runner import RunFailed, _project_window_notice, run_stage, task_prompt


@pytest.fixture
def notebook(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    nb.write("notes/old.md", "# Existing\nKeep this.")
    return nb


@pytest.fixture
def delegate(monkeypatch):
    calls = []

    def run(argv, **kw):
        # What the model was handed, read while it runs: a finished task keeps
        # no copy of the material (#1958).
        tasks = [p for p in Path(kw['cwd']).glob('*/material.json')]
        newest = max(tasks, key=lambda path: path.stat().st_mtime_ns) if tasks else None
        kw = {**kw, 'material': json.loads(newest.read_text()) if newest else None}
        calls.append((argv, kw))
        if argv[-1].startswith('/rem-investigate'):
            import re
            path = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
            path.write_text((Path(kw['cwd']).parent.parent / 'notes/old.md').read_text())
        if argv[-1].startswith('/rem-maintain'):
            workspace = Path(kw['cwd'])
            directory = max(workspace.glob('maintain-*'), key=lambda path: path.stat().st_mtime_ns)
            items = json.loads((directory / 'material.json').read_text())
            sources = sorted({item['source'] for item in items if item.get('source')})
            (directory / 'completion.json').write_text(json.dumps({
                'status': 'no_change', 'sources': sources, 'reason': 'No durable new fact.'}))
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "outcome": "natural", "result": "done", "usage": {"input_tokens": 13}}), stderr="")

    monkeypatch.setattr("connectonion.rem.runner.co_command", lambda: ["/opt/bin/co"])
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", run)
    return calls


def test_model_runs_use_the_running_installation_not_the_first_co_on_path(notebook, monkeypatch):
    """`venv/bin/co rem ...` from a non-activated venv, with an older co earlier
    on PATH, sent every model turn to that older `co ai` (seen on 1.8.8b7)."""
    import sys
    calls = []
    monkeypatch.setattr("shutil.which", lambda name: "/elsewhere/bin/co")
    monkeypatch.setattr(sys, "executable", "/work/venv/bin/python")
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", lambda argv, **kw: calls.append(argv) or
                        SimpleNamespace(returncode=0, stdout='{"outcome": "natural"}', stderr=""))
    run_stage(notebook, [], default_config())
    assert calls[0][:5] == ["/work/venv/bin/python", "-m", "connectonion.cli.main", "ai", "--json"]


def test_project_investigation_bounds_local_file_search(notebook, monkeypatch):
    notebook.stub_project('projects/reader.md', 'Reader', ['/work/reader'])
    prompts = []

    def stop_after_capture(argv, **kwargs):
        prompts.append(argv[-1])
        raise OSError('synthetic stop')

    monkeypatch.setattr('connectonion.rem.runner.subprocess.run', stop_after_capture)
    with pytest.raises(RunFailed):
        run_stage(notebook, [{'role': 'page', 'record': 'projects/reader.md',
                              'text': notebook.read('projects/reader.md'),
                              'source': 'investigation:page'}], default_config(), stage='investigate')
    assert 'at most twelve relevant text files' in prompts[0]
    assert 'stop using tools and return a brief coverage summary' in prompts[0]


def test_quick_investigation_reads_complete_bounded_material_once(tmp_path):
    items = [{'role': 'quick-first-pass', 'source': 'investigation:quick-scope',
              'text': 'Only use the gathered items.'},
             {'role': 'page', 'record': 'people/me.md', 'text': 'A' * 200}]
    prompt = task_prompt(tmp_path, items, 'investigate')
    assert f'at {tmp_path / "material.json"}' in prompt
    assert 'once' in prompt
    assert 'continued_text' not in prompt
    assert json.loads((tmp_path / 'material.json').read_text()) == items
    assert (tmp_path / 'material.md').exists()


def test_project_page_keeps_zero_session_window_separate_from_old_files():
    page = ('# Reader\n\n## Uncertainties\n- Unknown\n\n## Sources\n'
            '- [1] project-file — observed today\n\nInvestigation: mapped today')
    items = [{'role': 'coverage', 'source': 'investigation:coverage',
              'text': 'codex: 10 messages in window, 0 related to subject, 0 read\n'
                      'claude-code: 101 messages in window, 0 related to subject, 0 read\n'
                      'Requested investigation window: 5 days ending 2026-09-26'}]
    result = _project_window_notice(page, items)
    assert 'No related Codex and Claude Code messages were found in the requested 5-day window' in result
    assert '- [2] investigation:coverage' in result
    assert _project_window_notice(result, items) == result


def test_investigation_does_not_claim_another_concurrent_page_change(notebook, monkeypatch):
    first = 'people/first.md'
    other = 'people/other.md'
    notebook.stub_person(first, 'First', ['first@example.org'], email='first@example.org')
    notebook.stub_person(other, 'Other', ['other@example.org'], email='other@example.org')

    def run_model(*args, **kwargs):
        notebook.write(other, notebook.read(other) + '\nConcurrent edit.\n')
        return {'usage': None, 'result': 'complete'}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        book.write(record, original + '\nInvestigated.\n')

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    result = run_stage(notebook, [{'role': 'page', 'record': first,
                                   'text': notebook.read(first),
                                   'source': 'investigation:page'}], default_config(), stage='investigate')
    assert result['changed'] == [first]
    assert 'Concurrent edit.' in notebook.read(other)


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
    assert argv[-1].startswith(f"/rem-{stage} ")
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
    assert options["material"] == [item]
    assert not list((notebook.root / ".state/tasks").glob("*/material.json")), "no private copy is left"
    assert list((notebook.root / ".state/tasks").glob("*/result.json"))
    assert result["usage"] == {"input_tokens": 13}
    assert result["changed"] == []


def test_claude_rem_does_not_inherit_an_api_billing_key(notebook, delegate, monkeypatch):
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

    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", fail)
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

    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", write_decision)
    result = run_stage(notebook, [], default_config(), stage="abstract")
    assert result["changed"] == ["decisions/example.md"]
    assert notebook.read("decisions/example.md").startswith("# Why use Markdown")


def test_timeout_reports_partial_changes(notebook, monkeypatch, delegate):
    def timeout(argv, **kw):
        notebook.write("notes/new.md", "# Partial")
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", timeout)
    with pytest.raises(RunFailed, match="timed out") as caught:
        run_stage(notebook, [], default_config())
    assert caught.value.changed == ["notes/new.md"]


@pytest.mark.parametrize("payload", ['[]', '42', '{}', '{"outcome":"natural","usage":"oops"}'])
def test_invalid_envelope_fails(notebook, monkeypatch, delegate, payload):
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run",
                        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=payload, stderr=""))
    with pytest.raises(RunFailed):
        run_stage(notebook, [], default_config())


def test_extract_reads_written_notes_not_status_text(tmp_path, monkeypatch, delegate):
    def extract(argv, **kw):
        import re
        root = tmp_path / "rem"
        assert Path(kw["cwd"]) == root / ".state/tasks"
        directory = Path(re.search(r"Write the complete extraction notes to (.+?);", argv[-1])[1]).parent
        assert directory.parent == root / ".state/tasks"
        assert argv[-1].startswith("/rem-extract ")
        assert "--harness" in argv
        assert json.loads((directory / "material.json").read_text())[0]["text"] == "source"
        (directory / "notes.md").write_text("## People\n- Alice agreed [mail:1]")
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "outcome": "natural", "result": "I wrote the notes", "usage": {"input_tokens": 9}}), stderr="")

    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", extract)
    result = run_extract([{"text": "source", "source": "gmail:1"}], default_config(), "gmail",
                         root=tmp_path / "rem")
    assert result["notes"] == "## People\n- Alice agreed [mail:1]" and result["usage"] == {"input_tokens": 9}
    assert result["instructions_chars"] > 0   # #1959: every stage reports its instruction size


def test_extract_without_output_fails_and_preserves_usage(tmp_path, delegate):
    with pytest.raises(RunFailed, match="notes") as caught:
        run_extract([], default_config(), root=tmp_path / "rem")
    assert caught.value.usage == {"input_tokens": 13}


def test_coai_cache_metadata_does_not_break_usage_accounting(notebook, monkeypatch, delegate):
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", lambda *a, **kw:
        SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
            "outcome": "natural", "usage": {"input_tokens": 5, "cache_metadata_status": "measured"}})))
    result = run_stage(notebook, [], default_config())
    assert result["usage"] == {"input_tokens": 5}


def test_skill_composition_keeps_source_and_page_definition(notebook, delegate):
    run_stage(notebook, [], default_config(), kind="codex")
    text = next((notebook.root / ".state/tasks").glob("*/instructions.md")).read_text()
    assert "rem-source-codex" in text and "# A person's page" in text
    assert "rem_write" not in text and "rem_people" not in text


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
        material_path = task / 'material.md'
        if scenario == 'missing_material':
            material_path.unlink()
        else:
            assert f'### {source}' in material_path.read_text()
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

    monkeypatch.setattr('connectonion.rem.runner.subprocess.run', simulated_agent)
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

    monkeypatch.setattr('connectonion.rem.runner.subprocess.run', simulated_agent)
    with pytest.raises(RunFailed, match='only rejected pages'):
        run_stage(notebook, [{'role': 'user', 'source': 'codex:synthetic:2',
                              'text': 'Synthetic update.'}], default_config())
    assert notebook.read('people/alice.md') == original


def test_one_bad_page_does_not_hold_back_the_rest_of_a_maintenance_batch(tmp_path):
    """A real batch touched three pages, one lacked its overview diagram, and the
    whole batch was refused -- with the cursor held, so every scheduled run
    retried the same refusal and upkeep stopped."""
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.runner import _promote_maintenance
    root, work = tmp_path / "rem", tmp_path / "work"
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


def test_a_small_maintenance_prompt_carries_its_instructions_and_material(tmp_path):
    """Reading them from files cost ten of nineteen turns on a real pass, each
    re-sending the whole context. Small enough, they travel in the prompt."""
    from connectonion.rem.runner import INLINE_LIMIT, task_prompt
    items = [{"role": "user", "source": "codex:abc:1", "text": "shipped the reader", "timestamp": "2026-09-24"}]
    prompt = task_prompt(tmp_path, items, "maintain", "codex")
    assert "<material>" in prompt and "shipped the reader" in prompt and "<instructions>" in prompt
    assert "Read all source material" not in prompt
    assert (tmp_path / "material.json").is_file() and (tmp_path / "instructions.md").is_file()   # still audited
    big = [{"role": "user", "source": "codex:abc:2", "text": "x" * INLINE_LIMIT, "timestamp": "2026-09-24"}]
    assert "Read all source material" in task_prompt(tmp_path, big, "maintain", "codex")        # too big: files
    assert "<material>" in task_prompt(tmp_path, items, "investigate", "codex")                # investigate too


def test_what_fits_is_counted_in_bytes_the_way_argv_is_capped(tmp_path):
    """Linux caps one argument at 128 KiB; a Chinese character is three bytes,
    so 60k characters of Chinese mail is 180 KB and could not be sent."""
    from connectonion.rem.runner import task_prompt
    chinese = [{"role": "user", "source": "gmail:a:1", "text": "中" * 60_000}]
    assert "<material>" not in task_prompt(tmp_path, chinese, "extract", "gmail")
    english = [{"role": "user", "source": "gmail:a:1", "text": "x" * 60_000}]
    assert "<material>" in task_prompt(tmp_path, english, "extract", "gmail")


def test_an_investigation_that_fits_is_given_its_material(tmp_path):
    from connectonion.rem.runner import task_prompt
    items = [{"role": "page", "record": "people/mia.md", "source": "investigation:page", "text": "# Mia\n"},
             {"role": "digest", "source": "gmail:m:1", "text": "Mia leads the data platform team."}]
    prompt = task_prompt(tmp_path, items, "investigate")
    assert "<material>" in prompt and "Mia leads the data platform team." in prompt


def test_material_too_big_to_give_is_plain_text_to_read(tmp_path):
    """The fallback cut every string into 64-character pieces; a real extraction
    then spent 22 turns and 1.2M tokens writing Python to glue them back and
    printing 8,000 characters a turn."""
    from connectonion.rem.runner import task_prompt
    body = "Hi Alex,\n" + "The pilot covers three suppliers and runs six weeks. " * 3000
    items = [{"role": "user", "source": "gmail:m:1", "date": "2026-09-01", "from": "Mia <m@h.example>", "text": body}]
    prompt = task_prompt(tmp_path, items, "extract", "gmail")
    readable = (tmp_path / "material.md").read_text()
    assert "continued_text" not in readable and "continued_text" not in prompt
    assert "### gmail:m:1" in readable and "from: Mia <m@h.example>" in readable
    assert "The pilot covers three suppliers" in readable
    assert max(map(len, readable.splitlines())) <= 400
    assert str(tmp_path / "material.md") in prompt
    assert json.loads((tmp_path / "material.json").read_text()) == items          # exact text kept


def test_investigation_digests_in_pieces_that_travel_in_the_prompt(tmp_path):
    """15 pieces of 150k characters never fit the prompt, so each was read from
    files: about 1M input tokens a piece on the owner's notebook."""
    from connectonion.rem.config import default_config
    from connectonion.rem.investigate import digest_in_chunks
    from connectonion.rem.runner import task_prompt
    seen = []

    def extractor(chunk, settings, kind):
        seen.append("<material>" in task_prompt(tmp_path, chunk, "extract", kind))
        return {"notes": "kept", "usage": None}

    config = default_config()
    config["limits"]["extract_chars_per_batch"] = 150_000
    items = [{"role": "user", "source": f"gmail:m:{n}", "timestamp": "2026-09-01T00:00:00Z", "text": "word " * 8000}
             for n in range(12)]
    digest_in_chunks(items, config, extractor)
    assert seen and all(seen)


def _hold_lock(root, seconds):
    """A scheduled sync holding the notebook for `seconds`, in another thread."""
    import threading
    from connectonion.rem.files import maintenance_lock
    held = threading.Event()

    def hold():
        with maintenance_lock(root):
            held.set()
            time.sleep(seconds)
    thread = threading.Thread(target=hold)
    thread.start()
    held.wait()
    return thread


def test_a_finished_investigation_waits_for_a_sync_instead_of_losing_its_page(tmp_path, monkeypatch):
    """05:00 on 2026-09-28: a project investigation had written its page when the
    scheduled sync took the lock, and the page was dropped with 'co rem is busy'."""
    from connectonion.rem import runner
    monkeypatch.setattr(runner, "PROMOTE_WAIT_SECONDS", 5)
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia", ["mia@h.example"], email="mia@h.example")
    original = notebook.read("people/mia.md")
    candidate = tmp_path / "candidate.md"
    candidate.write_text(original.replace("## Who they are\n- Unknown — not investigated yet",
                                          "## Who they are\n- Leads the data team. [1]")
                         .replace("- (none yet)", "- [1] gmail:m:1")
                         .replace("- Unknown — not investigated yet", "- Unknown"))
    thread = _hold_lock(tmp_path, 1.0)
    runner._promote_candidate(notebook, "people/mia.md", candidate, original,
                              [{"source": "gmail:m:1"}], tmp_path, None)
    thread.join()
    assert "Leads the data team." in notebook.read("people/mia.md")


def test_a_sync_that_outlasts_the_wait_leaves_the_page_where_it_can_be_found(tmp_path, monkeypatch):
    from connectonion.rem import runner
    from connectonion.rem.runner import RunFailed
    monkeypatch.setattr(runner, "PROMOTE_WAIT_SECONDS", 0.5)
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia", ["mia@h.example"], email="mia@h.example")
    original = notebook.read("people/mia.md")
    candidate = tmp_path / "candidate.md"
    candidate.write_text(original)
    thread = _hold_lock(tmp_path, 2.0)
    with pytest.raises(RunFailed) as error:
        runner._promote_candidate(notebook, "people/mia.md", candidate, original, [], tmp_path, None)
    thread.join()
    assert str(candidate) in str(error.value) and candidate.is_file()


def test_finished_tasks_lose_their_private_copies_and_running_ones_are_left_alone(tmp_path):
    """#1958: 98 task folders held 75 MB of the owner's mail. A folder is scrubbed
    once its run wrote result.json; a run still working keeps its material."""
    from connectonion.rem.runner import scrub_finished_tasks

    done, running = tmp_path / "maintain-a", tmp_path / "investigate-b"
    for folder in (done, running):
        (folder / "notebook/people").mkdir(parents=True)
        (folder / "material.json").write_text("[]")
        (folder / "material.md").write_text("mail")
        (folder / "notebook/people/x.md").write_text("# X")
    (done / "result.json").write_text("{}")
    (done / "candidate.md").write_text("# X")

    scrub_finished_tasks(tmp_path)

    assert sorted(p.name for p in done.iterdir()) == ["candidate.md", "result.json"]
    assert (running / "material.json").is_file() and (running / "notebook/people/x.md").is_file()


# ------------------------------------------------ #1974: private copies, one env


def test_task_files_are_owner_only_even_those_the_model_writes(notebook, monkeypatch):
    """.state/tasks held full mail bodies as 0644 files inside a 0700 folder."""
    import os
    import stat
    seen = {}

    def run(argv, **kw):
        folder = max(Path(kw['cwd']).glob('abstract-*'), key=lambda path: path.stat().st_mtime_ns)
        (folder / 'written-by-model.md').write_text('x')
        seen.update({path.name: stat.S_IMODE(path.stat().st_mode) for path in folder.iterdir() if path.is_file()})
        return SimpleNamespace(returncode=0, stdout=json.dumps({"outcome": "natural", "result": "done",
                                                                "usage": None}), stderr="")
    monkeypatch.setattr("connectonion.rem.runner.co_command", lambda: ["/opt/bin/co"])
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", run)
    before = os.umask(0o022)
    try:
        run_stage(notebook, [], default_config(), stage="abstract")
        assert os.umask(0o022) == 0o022  # restored
    finally:
        os.umask(before)
    assert seen and all(mode == 0o600 for mode in seen.values()), seen


def test_an_interrupted_task_loses_its_copies_too(notebook, monkeypatch):
    def run(argv, **kw):
        raise KeyboardInterrupt
    monkeypatch.setattr("connectonion.rem.runner.co_command", lambda: ["/opt/bin/co"])
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", run)
    with pytest.raises(KeyboardInterrupt):
        run_stage(notebook, [{"source": "gmail:1", "text": "private"}], default_config(), stage="abstract")
    folder = next((notebook.root / ".state" / "tasks").iterdir())
    assert not (folder / "material.json").exists() and not (folder / "notebook").exists()


def test_a_folder_a_killed_run_left_is_scrubbed_once_it_is_old(tmp_path):
    import os
    import stat
    from connectonion.rem.runner import ABANDONED_TASK_SECONDS, scrub_finished_tasks
    killed, working = tmp_path / "investigate-k", tmp_path / "investigate-w"
    for folder in (killed, working):
        folder.mkdir()
        (folder / "material.json").write_text("[]")
        (folder / "instructions.md").write_text("skill")
        (folder / "instructions.md").chmod(0o644)
    old = time.time() - ABANDONED_TASK_SECONDS - 60
    os.utime(killed, (old, old))
    scrub_finished_tasks(tmp_path)
    assert sorted(p.name for p in killed.iterdir()) == ["instructions.md"]
    assert stat.S_IMODE((killed / "instructions.md").stat().st_mode) == 0o600
    assert (working / "material.json").is_file()


def test_the_model_s_co_ai_gets_an_absolute_pythonpath(notebook, delegate, monkeypatch, tmp_path):
    """PYTHONPATH=. resolved against .state/tasks imported an older connectonion."""
    # Its own cwd: in a parallel run another test's chdir made "." resolve to a
    # second entry beside the checkout, and an equality check failed at random.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", ".")
    run_stage(notebook, [], default_config(), stage="abstract")
    parts = delegate[0][1]["env"]["PYTHONPATH"].split(os.pathsep)
    assert str(tmp_path.resolve()) in parts and all(Path(part).is_absolute() for part in parts)


def test_check_skill_fails_in_seconds_with_the_cause(tmp_path, monkeypatch):
    from connectonion.rem import runner
    from connectonion.rem.files import RemError
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        return SimpleNamespace(returncode=3, stdout="", stderr="")
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", run)
    with pytest.raises(RemError, match="rem-investigate"):
        runner.check_skill(tmp_path, "investigate")
    assert calls[0][1]["cwd"] == str(tmp_path / ".state" / "tasks")
    assert calls[0][1]["timeout"] <= 60


def test_maintenance_adds_to_a_page_it_was_not_asked_to_finish(tmp_path):
    """#2014: the placeholder rule for a page's own investigation refused every
    one-page maintenance turn on a never-investigated page (290k tokens, 0 pages)."""
    from connectonion.rem import runner
    from connectonion.rem.runner import RunFailed
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia", ["mia@h.example"], email="mia@h.example")
    original = notebook.read("people/mia.md")
    one_line = (original.replace("## Who they are\n- Unknown — not investigated yet",
                                 "## Who they are\n- Leads the data team. [1]", 1)
                .replace("- (none yet)", "- [1] gmail:m:1"))
    candidate = tmp_path / "candidate.md"

    candidate.write_text(one_line)
    with pytest.raises(RunFailed, match="not investigated yet"):
        runner._promote_candidate(notebook, "people/mia.md", candidate, original, [{"source": "gmail:m:1"}],
                                  tmp_path, None)
    candidate.write_text(one_line)
    runner._promote_candidate(notebook, "people/mia.md", candidate, original, [{"source": "gmail:m:1"}],
                              tmp_path, None, investigation=False)
    assert "Leads the data team." in notebook.read("people/mia.md")


def test_a_turn_that_writes_no_candidate_gets_one_more_turn(notebook, monkeypatch):
    """Real first runs lost 1-5 pages a run this way: the model decided the
    candidate path, inside its writable root, was not writable and stopped."""
    import re as regex
    record = 'people/first.md'
    notebook.stub_person(record, 'First', ['first@example.org'], email='first@example.org')
    prompts, promoted = [], []

    def run_model(workdir, prompt, config, stage):
        prompts.append(prompt)
        if len(prompts) == 2:
            path = regex.search(r'(/\S+/candidate\.md)', prompt).group(1)
            Path(path).write_text('# First\n')
        return {'usage': {'input_tokens': 10, 'output_tokens': 1}, 'result': 'done'}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        promoted.append((candidate.is_file(), usage))

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    run_stage(notebook, [{'role': 'page', 'record': record, 'text': notebook.read(record),
                          'source': 'investigation:page'}], default_config(), stage='investigate')
    assert len(prompts) == 2 and 'writable' in prompts[1]
    assert promoted == [(True, {'input_tokens': 20, 'output_tokens': 2})]


def test_a_turn_may_ask_for_mail_searches_and_gets_one_more_turn_with_their_results(notebook, monkeypatch):
    """The model has no network (its sandbox is the defence against mail that
    carries instructions); it names searches, our code runs them read-only,
    and the results come back as cited material for one more turn."""
    import json as jsonlib
    import re as regex
    record = 'people/first.md'
    notebook.stub_person(record, 'First', ['first@example.org'], email='first@example.org')
    prompts, asked, promoted = [], [], []
    found = [{'role': 'other', 'speaker': 'Second <second@example.org>', 'text': 'First runs the lab.',
              'timestamp': '2025-08-06', 'subject': 'Intro', 'source': 'outlook:abc123abc123'}]

    def search(queries):
        asked.append(queries)
        return found

    def run_model(workdir, prompt, config, stage):
        prompts.append(prompt)
        candidate = Path(regex.search(r'(/\S+/candidate\.md)', prompt).group(1))
        candidate.write_text('# First\n')
        if len(prompts) == 1:
            (candidate.parent / 'search-requests.json').write_text(jsonlib.dumps(['First lab', 'from:x@y.z']))
        return {'usage': {'input_tokens': 10}, 'result': 'done'}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        promoted.append([item['source'] for item in items])

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    run_stage(notebook, [{'role': 'page', 'record': record, 'text': notebook.read(record),
                          'source': 'investigation:page'}], default_config(), stage='investigate', search=search)
    assert asked == [['First lab', 'from:x@y.z']]
    assert len(prompts) == 2 and 'search-results.md' in prompts[1] and 'search-requests.json' in prompts[0]
    assert 'outlook:abc123abc123' in promoted[0]

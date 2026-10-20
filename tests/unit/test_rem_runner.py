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
from connectonion.rem import runner
from connectonion.rem.runner import RunFailed, run_claim_task, run_stage, task_prompt


@pytest.mark.parametrize('stage', ['muse', 'enrich', 'investigate'])
def test_only_muse_runs_independent_insight_critic_before_promotion(notebook, monkeypatch, stage):
    import re
    from connectonion.rem import insight_critic
    record = 'people/avery-lin.md'
    notebook.stub_person(record, 'Avery Lin')
    calls, progress = [], []
    bullet = '- Changed: Avery now pays for Lantern testing. [1][2]'

    def run(workdir, prompt, config, phase, **options):
        next(workdir.glob(f'{stage}-*/candidate.md')).write_text(f'# Avery Lin\n\n## Insight\n{bullet}\n')
        return {'session_id': 'avery-thread', 'usage': {'input_tokens': 10}}

    def judge(book, page, before, candidate, items, config, directory, independent_run):
        calls.append('critic')
        assert page == record and independent_run is runner.run_claim_task
        assert candidate.read_text().endswith(bullet + '\n')
        candidate.write_text('# Avery Lin\n\n## Insight\n')
        return {'bullets': [{'bullet': bullet, 'verdict': 'weak', 'reason': 'One message.'}],
                'usage': {'input_tokens': 3}}

    def promote(book, page, candidate, *args, **options):
        calls.append('promote')
        assert (bullet not in candidate.read_text()) == (stage == 'muse')
        book.write(page, candidate.read_text())

    monkeypatch.setattr(runner, 'run_task', run)
    monkeypatch.setattr(insight_critic, 'judge', judge)
    monkeypatch.setattr(runner, 'promote_with_repairs', promote)
    result = run_stage(notebook, [{'role': 'page', 'record': record}], default_config(),
                       stage=stage, turns=('first', 'second'), stage_progress=progress.append)
    assert calls == (['critic', 'promote'] if stage == 'muse' else ['promote'])
    assert ('insight critic' in progress) == (stage == 'muse')
    assert result['usage'] == {'input_tokens': 13 if stage == 'muse' else 10}
    if stage == 'muse':
        assert result['insights_proposed'] == 1 and result['insights_kept'] == 0
        assert result['insights_rejected'] == [{'bullet': bullet, 'verdict': 'weak', 'reason': 'One message.'}]
    else:
        assert 'insights_kept' not in result


@pytest.mark.parametrize('critic_fails', [False, True, 'invalid-root', 'invalid-json'])
def test_muse_repairs_cannot_reintroduce_rejected_insights(notebook, monkeypatch, critic_fails):
    from connectonion.rem.files import write_json
    record, bullet = 'people/avery-lin.md', '- Now: Avery received the Lantern deck. [1]'
    notebook.stub_person(record, 'Avery Lin')
    turns, critics, promotions = [], [], []

    def run(workdir, prompt, config, stage, **options):
        turns.append(prompt)
        next(workdir.glob('muse-*/candidate.md')).write_text(f'# Avery Lin\n\n## Insight\n{bullet}\n')
        return {'session_id': 'avery-thread', 'usage': {'input_tokens': len(turns) * 10}}

    def critic(*args):
        critics.append(args)
        if critic_fails and len(critics) == 2:
            if critic_fails is True:
                raise RunFailed('Critic failed', {'input_tokens': 3})
            return {'result': '[]' if critic_fails == 'invalid-root' else '{invalid', 'usage': {'input_tokens': 3}}
        return {'result': json.dumps({'bullets': [{'bullet': bullet, 'verdict': 'weak',
                    'reason': 'One message.', 'open_thread': ''}]}), 'usage': {'input_tokens': 3}}

    def promote(book, page, candidate, original, items, directory, usage, **options):
        promotions.append(candidate.read_text())
        assert bullet not in candidate.read_text()
        if len(promotions) == 1:
            write_json(directory / 'review.json', {'errors': ['Cited-claim audit did not pass']})
            raise RunFailed('Candidate rejected', usage)
        book.write(page, candidate.read_text())
        return {}

    monkeypatch.setattr(runner, 'run_task', run)
    monkeypatch.setattr(runner, 'run_claim_task', critic)
    monkeypatch.setattr(runner, '_promote_candidate', promote)
    if critic_fails:
        with pytest.raises(RunFailed, match='Critic failed|Insight critic returned') as error:
            run_stage(notebook, [{'role': 'page', 'record': record}], default_config(), stage='muse')
        assert error.value.usage == {'input_tokens': 26}
    else:
        result = run_stage(notebook, [{'role': 'page', 'record': record}], default_config(), stage='muse')
        assert result['insights_proposed'] == 1 and result['insights_kept'] == 0
        assert result['insights_rejected'] == [{'bullet': bullet, 'verdict': 'weak', 'reason': 'One message.'}]
        assert result['usage'] == {'input_tokens': 26}
        assert bullet not in notebook.read(record)
        logged = json.loads(next((notebook.root / '.state/tasks').glob('*/result.json')).read_text())
        assert logged['insights_rejected'] == result['insights_rejected']
    assert len(turns) == len(critics) == 2


def test_repaired_good_insight_is_not_also_reported_rejected(notebook, tmp_path, monkeypatch):
    record, bullet = 'people/avery-lin.md', '- Changed: Avery now pays for Lantern testing. [1][2]'
    notebook.stub_person(record, 'Avery Lin')
    original = notebook.read(record)
    candidate = tmp_path / 'candidate.md'
    text = f'# Avery Lin\n\n## Insight\n{bullet}\n'
    result = {}
    verdicts = iter(['weak', 'good'])
    monkeypatch.setattr(runner, 'run_claim_task', lambda *args: {'result': json.dumps({'bullets': [
        {'bullet': bullet, 'verdict': next(verdicts), 'reason': 'Invented review.', 'open_thread': ''}]})})
    for _ in range(2):
        candidate.write_text(text)
        runner._review_insights(notebook, record, original, candidate, [], {}, tmp_path, result, None)
    assert result['insights_proposed'] == result['insights_kept'] == 1
    assert result['insights_rejected'] == [] and bullet in candidate.read_text()


def test_independent_critic_uses_its_own_read_only_output_schema(tmp_path, monkeypatch):
    import importlib
    from connectonion.rem.insight_critic import CRITIC_SCHEMA
    codex = importlib.import_module('connectonion.useful_tools.codex')
    monkeypatch.setattr(codex, '_base_command', lambda: ['codex', 'app-server'])

    def completed(command, **options):
        assert json.loads(Path(command[command.index('--output-schema') + 1]).read_text()) == CRITIC_SCHEMA
        assert command[command.index('--sandbox') + 1] == 'read-only'
        assert '--ephemeral' in command and '--resume' not in command
        assert options['input'] == 'INDEPENDENT_PACKET' and 'INDEPENDENT_PACKET' not in command
        Path(command[command.index('-o') + 1]).write_text('{"bullets": []}')
        return SimpleNamespace(returncode=0, stdout=json.dumps({'type': 'turn.completed',
                               'usage': {'input_tokens': 3}}), stderr='')

    monkeypatch.setattr(runner.subprocess, 'run', completed)
    result = run_claim_task(tmp_path, 'INDEPENDENT_PACKET', default_config(), 'insight-critic')
    assert result['result'] == '{"bullets": []}' and result['usage']['input_tokens'] == 3


@pytest.mark.parametrize('timeouts', [1, 2])
@pytest.mark.parametrize('message', ['co ai timed out after 1200s', 'turn timed out after 1200s'])
def test_stage_retries_a_timeout_once_and_counts_failed_usage(notebook, monkeypatch, timeouts, message):
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) <= timeouts:
            raise RunFailed(message, {'input_tokens': 3})
        return {'usage': {'input_tokens': 10}, 'result': 'done'}

    monkeypatch.setattr(runner, 'run_task', run)
    if timeouts == 1:
        result = run_stage(notebook, [], default_config(), stage='abstract')
        assert result['usage'] == {'input_tokens': 13}
    else:
        with pytest.raises(RunFailed, match='timed out') as caught:
            run_stage(notebook, [], default_config(), stage='abstract')
        assert caught.value.usage == {'input_tokens': 6}
    assert len(calls) == 2 and calls[0] == calls[1]
    metrics = json.loads(next((notebook.root / '.state/tasks').glob('*/result.json')).read_text())
    assert metrics['timeouts_retried'] == 1
    assert metrics['usage'] == {'input_tokens': 13 if timeouts == 1 else 6}
    assert metrics['status'] == ('execution_finished' if timeouts == 1 else 'failed')


def test_stage_does_not_retry_other_failures(notebook, monkeypatch):
    calls = []

    def run(*args):
        calls.append(args)
        raise RunFailed('provider at capacity', {'input_tokens': 3})

    monkeypatch.setattr(runner, 'run_task', run)
    with pytest.raises(RunFailed, match='at capacity'):
        run_stage(notebook, [], default_config(), stage='abstract')
    assert len(calls) == 1


@pytest.mark.parametrize('harness,expected', [('codex', 33), ('claude-code', 63)])
def test_timeout_retry_resumes_same_thread_and_usage_survives_later_turns(notebook, monkeypatch, harness, expected):
    record = 'people/avery-lin.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    calls = []

    def run(workdir, prompt, config, stage, **options):
        calls.append((prompt, options))
        if len(calls) == 2:
            raise RunFailed('turn timed out after 1200s', {'input_tokens': 3})
        usage = 10 if len(calls) == 1 else 20 if len(calls) == 3 else 30
        return {'session_id': 'avery-thread', 'usage': {'input_tokens': usage}}

    monkeypatch.setattr(runner, 'run_task', run)
    result = run_stage(notebook, [{'role': 'page', 'record': record}],
                       {**default_config(), 'runner': harness}, stage='enrich', turns=('first', 'second', 'third'))
    assert calls[1] == calls[2] == ('second', {'session': 'avery-thread'})
    assert result['usage'] == {'input_tokens': expected}


def test_later_timeouts_without_usage_keep_prior_retry_usage(notebook, monkeypatch):
    record = 'people/avery-lin.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    calls = []

    def run(*args, **options):
        calls.append(options)
        if len(calls) == 2:
            return {'session_id': 'avery-thread', 'usage': {'input_tokens': 10}}
        raise RunFailed('turn timed out after 1200s', {'input_tokens': 3} if len(calls) == 1 else None)

    monkeypatch.setattr(runner, 'run_task', run)
    with pytest.raises(RunFailed, match='timed out') as caught:
        run_stage(notebook, [{'role': 'page', 'record': record}], default_config(),
                  stage='enrich', turns=('first', 'second'))
    assert len(calls) == 4
    assert caught.value.usage == {'input_tokens': 13}


@pytest.mark.parametrize('fails_twice', [False, True])
@pytest.mark.parametrize('followup', ['one_more', 'search'])
def test_followup_retries_timeout_and_counts_all_attempts(notebook, monkeypatch, fails_twice, followup):
    record = 'people/avery-lin.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    calls = []

    def run(workdir, prompt, config, stage):
        calls.append(prompt)
        if len(calls) == 2 or len(calls) == 3 and fails_twice:
            raise RunFailed('co ai timed out after 1200s', {'input_tokens': 3})
        if len(calls) == 3 or followup == 'search':
            next(workdir.glob('investigate-*/candidate.md')).write_text('# Avery Lin\n')
        if followup == 'search':
            next(workdir.glob('investigate-*')).joinpath('search-requests.json').write_text('["Avery Lin"]')
        return {'usage': {'input_tokens': 10}}

    monkeypatch.setattr(runner, 'run_task', run)
    monkeypatch.setattr(runner, '_promote_candidate', lambda *a, **kw: None)
    options = {'search': lambda queries: []} if followup == 'search' else {}
    if fails_twice:
        with pytest.raises(RunFailed, match='timed out') as caught:
            run_stage(notebook, [{'role': 'page', 'record': record}], default_config(), stage='investigate', **options)
        assert caught.value.usage == {'input_tokens': 16}
    else:
        result = run_stage(notebook, [{'role': 'page', 'record': record}], default_config(), stage='investigate', **options)
        assert result['usage'] == {'input_tokens': 23}
    assert len(calls) == 3 and calls[1] == calls[2]
    metrics = json.loads(next((notebook.root / '.state/tasks').glob('*/result.json')).read_text())
    assert metrics['usage'] == {'input_tokens': 16 if fails_twice else 23}
    assert metrics['timeouts_retried'] == 1


@pytest.mark.parametrize('fails_twice', [False, True])
def test_resumed_repair_retries_timeout_and_counts_failed_usage(notebook, monkeypatch, fails_twice):
    from connectonion.rem.files import write_json
    record = 'people/avery-lin.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    calls, reviews = [], []

    def run(workdir, prompt, config, stage, **options):
        calls.append(options)
        if len(calls) == 2 or len(calls) == 3 and fails_twice:
            raise RunFailed('turn timed out after 1200s', {'input_tokens': 150})
        next(workdir.glob('enrich-*/candidate.md')).write_text('# Avery Lin\n')
        return {'session_id': 'avery-thread', 'usage': {'input_tokens': 100 if len(calls) == 1 else 200}}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        reviews.append(usage)
        if len(reviews) == 1:
            write_json(directory / 'review.json', {'errors': ['Missing section: Insight']})
            raise RunFailed('Candidate rejected', usage)

    monkeypatch.setattr(runner, 'run_task', run)
    monkeypatch.setattr(runner, '_promote_candidate', promote)
    if fails_twice:
        with pytest.raises(RunFailed, match='timed out') as caught:
            run_stage(notebook, [{'role': 'page', 'record': record}], default_config(), stage='enrich')
        assert caught.value.usage == {'input_tokens': 300}
    else:
        result = run_stage(notebook, [{'role': 'page', 'record': record}], default_config(), stage='enrich')
        assert result['usage'] == {'input_tokens': 350}
        assert result['repair_usage'] == {'input_tokens': 250}
    assert calls == [{}, {'session': 'avery-thread'}, {'session': 'avery-thread'}]
    metrics = json.loads(next((notebook.root / '.state/tasks').glob('*/result.json')).read_text())
    assert metrics['timeouts_retried'] == 1


def test_review_and_audit_progress_separate_one_repair_from_model_turns(notebook, monkeypatch):
    import re
    from connectonion.rem import page_review, project_claim_review
    record = 'people/avery-lin.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    progress, calls, reviews = [], [], []

    def run(workdir, prompt, config, stage, **options):
        calls.append(options)
        Path(re.search(r'(/\S+/candidate\.md)', prompt)[1]).write_text('# Avery Lin\n\nA finding.\n')
        return {'session_id': 'avery-thread', 'usage': {'input_tokens': len(calls) * 10}}

    def review(*args, **options):
        reviews.append(options)
        return ({'verdict': 'fail' if len(reviews) == 1 else 'pass',
                 'findings': [{'claim': 'A finding.'}] if len(reviews) == 1 else []}, {})

    monkeypatch.setattr(runner, 'run_task', run)
    monkeypatch.setattr(page_review, 'validate', lambda *a, **kw: [])
    monkeypatch.setattr(project_claim_review, 'review', review)
    monkeypatch.setattr(project_claim_review, 'retain_cited_originals', lambda *a: None)
    result = run_stage(notebook, [{'role': 'page', 'record': record}], default_config(),
                       stage='enrich', turns=('first',), stage_progress=progress.append)
    assert result['repairs'] == 1
    assert progress == ['turn 1 of 1', 'reviewing', 'claim audit', 'repair 1', 'reviewing', 'claim audit']
    assert calls == [{}, {'session': 'avery-thread'}]


@pytest.mark.parametrize(('stage', 'repairs'), [('enrich', 1), ('muse', 1), ('investigate', 2)])
def test_stage_stops_repairs_at_its_limit_before_last_resort(notebook, monkeypatch, stage, repairs):
    from connectonion.rem.files import write_json
    record = 'people/avery.md'
    notebook.stub_person(record, 'Avery')
    calls, promotions = [], []

    def run(workdir, prompt, config, phase):
        calls.append(prompt)
        next(workdir.glob(f'{stage}-*/candidate.md')).write_text('# Avery\nA new finding.\n')
        return {'usage': {'input_tokens': 1}}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        promotions.append(options.get('last_resort', False))
        if not options.get('last_resort'):
            write_json(directory / 'review.json', {'errors': ['Cited-claim audit did not pass']})
            raise RunFailed('Candidate rejected', usage)
        book.write(record, candidate.read_text())

    monkeypatch.setattr(runner, 'run_task', run)
    monkeypatch.setattr(runner, '_promote_candidate', promote)
    result = run_stage(notebook, [{'role': 'page', 'record': record}], default_config(), stage=stage)
    assert result['repairs'] == repairs
    assert len(calls) == 1 + repairs
    assert promotions == [False] * (1 + repairs) + [True]


def test_model_access_probes_without_sources(tmp_path, monkeypatch):
    from connectonion.rem import runner as rem_runner
    prompts = []
    monkeypatch.setattr(rem_runner, "run_task", lambda workspace, prompt, config, stage:
                        prompts.append((workspace, prompt, stage)) or {"outcome": "natural"})
    assert rem_runner.model_access(tmp_path, {"runner": "claude-code"}) == ("", "")
    assert prompts[0][0].is_dir()
    assert "Do not use tools or read files" in prompts[0][1]
    assert prompts[0][2] == "abstract"
    assert rem_runner.model_denial(RunFailed("provider 403 permission_denied"))
    assert not rem_runner.model_denial(RunFailed("transient timeout"))


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
            path = Path(re.search(r'page is the file (.+?candidate.md)', argv[-1])[1])
            path.write_text((Path(kw['cwd']).parent.parent / 'notes/old.md').read_text())
        if argv[-1].startswith('/rem-maintain'):
            workspace = Path(kw['cwd'])
            directory = max(workspace.glob('maintain-*'), key=lambda path: path.stat().st_mtime_ns)
            items = json.loads((directory / 'material.json').read_text())
            sources = sorted({item['source'] for item in items if item.get('source')})
            (directory / 'completion.json').write_text(json.dumps({
                'status': 'no_change', 'sources': sources, 'reason': 'No durable new fact.'}))
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "outcome": "natural", "result": "done. NO CHANGE", "usage": {"input_tokens": 13}}), stderr="")

    monkeypatch.setattr("connectonion.rem.runner.co_command", lambda: ["/opt/bin/co"])
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", run)
    return calls


def test_run_task_drops_null_bytes_from_prompt(tmp_path, delegate):
    result = runner.run_task(tmp_path, "Continue\0 investigating\0.", default_config(), "investigate")
    argv = delegate[0][0]
    assert all("\0" not in argument for argument in argv)
    assert argv[-1] == "Continue investigating."
    assert result["outcome"] == "natural"


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


def test_project_investigation_authorizes_live_repo_search(notebook, monkeypatch):
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
    assert 'Start from the current line' in prompts[0]
    assert 'git log' in prompts[0] and 'git show' in prompts[0]
    assert 'alone is not an insight. Each is about the project' in prompts[0]
    assert 'None: `- Unknown`.' in prompts[0]
    assert 'local mail archives and project repositories' in prompts[0]
    assert 'stop using tools and return a brief coverage summary' in prompts[0]
    assert 'investigation:coverage, investigation:project-scope' in prompts[0]
    assert 'reading guides, never citable originals' in prompts[0]
    assert 'nearby checkouts outside those Paths cannot be retained' in prompts[0]
    assert 'earlier rounds read sources this turn does not hold' in prompts[0]
    assert 'write bare Unknown, not a no-pending-work summary' in prompts[0]


def test_a_person_page_near_the_limit_is_told_its_size_before_the_turn(notebook, monkeypatch):
    """#2041: Corin Marsh's 18,730-character page learnt about the 20,000 limit
    only from the review, after a 643k-token turn."""
    record = 'people/corin.md'
    notebook.stub_person(record, 'Corin', ['corin@example.org'], email='corin@example.org')
    notebook.write(record, notebook.read(record) + '\n' + 'x' * 18_000 + '\n')
    prompts = []

    def stop_after_capture(argv, **kwargs):
        prompts.append(argv[-1])
        raise OSError('synthetic stop')

    monkeypatch.setattr('connectonion.rem.runner.subprocess.run', stop_after_capture)
    with pytest.raises(RunFailed):
        run_stage(notebook, [{'role': 'page', 'record': record, 'text': notebook.read(record),
                              'source': 'investigation:page'}], default_config(), stage='investigate')
    size = len(notebook.read(record))
    assert f'The page is {size:,} characters; it must end under 20,000' in prompts[0]
    assert 'fold the oldest History' in prompts[0]


def test_quick_investigation_reads_complete_bounded_material_once(tmp_path):
    items = [{'role': 'quick-first-pass', 'source': 'investigation:quick-scope',
              'text': 'Only use the gathered items.'},
             {'role': 'page', 'record': 'people/me.md', 'text': 'A' * 200}]
    prompt = task_prompt(tmp_path, items, 'investigate')
    assert f'at {tmp_path / "material.json"}' in prompt
    assert 'Search the evidence index' in prompt
    assert 'continued_text' not in prompt
    assert json.loads((tmp_path / 'material.json').read_text()) == items
    assert (tmp_path / 'material.md').exists()


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
    investigating = stage in ("init", "investigate")
    if harness == "claude-code":
        assert argv[argv.index("--permission-mode") + 1] == (
            "bypassPermissions" if investigating else "acceptEdits")
    else:
        assert "--permission-mode" not in argv
    if harness == "codex":
        assert argv[argv.index("--speed") + 1] == "fast"
        assert argv[argv.index("--sandbox") + 1] == (
            "danger-full-access" if investigating else "workspace-write")
    else:
        assert "--speed" not in argv
        assert "--sandbox" not in argv
    assert options["material"] == [item]
    assert not list((notebook.root / ".state/tasks").glob("*/material.json")), "no private copy is left"
    metrics = json.loads(next((notebook.root / ".state/tasks").glob("*/result.json")).read_text())
    assert (metrics["harness"], metrics["model"], metrics["speed"]) == (harness, "default", "fast")
    assert result["usage"] == {"input_tokens": 13}
    assert result["changed"] == []


def test_codex_standard_speed_reaches_cli_and_task_metrics(notebook, delegate):
    config = {**default_config(), "speed": "standard"}
    run_stage(notebook, [], config)
    argv = delegate[0][0]
    assert argv[argv.index("--speed") + 1] == "standard"
    metrics = json.loads(next((notebook.root / ".state/tasks").glob("*/result.json")).read_text())
    assert metrics["speed"] == "standard"


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
        "## Sources\n- (none yet)", "## Sources\n- [1] codex:abc:1, 2026-09-24.")
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


def test_a_maintenance_batch_that_guts_a_page_keeps_the_old_one(tmp_path):
    """projects/connectonion went 14,356 -> 4,132 characters in one accepted
    maintenance turn (2026-10-13): nothing it dropped was invalid, only gone."""
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.runner import _promote_maintenance
    root, work = tmp_path / "rem", tmp_path / "work"
    prepare(root)
    prepare(work)
    notebook, working = Notebook(root), Notebook(work)
    notebook.stub_person("people/briar.md", "Briar", [])
    lines = "\n".join(f"- Briar settled point {n} of the lease, in writing, with the agent. [{n}]" for n in range(1, 13))
    sources = "\n".join(f"- [{n}] codex:abc:{n} — 2026-09-24" for n in range(1, 13))
    full = notebook.read("people/briar.md").replace("## Who they are\n- Unknown — not investigated yet",
                                                   f"## Who they are\n{lines}").replace(
        "## Sources\n- (none yet)", f"## Sources\n{sources}")
    notebook.write("people/briar.md", full)
    gutted = full.replace(lines, lines.split("\n")[0]).replace(sources, sources.split("\n")[0])
    working.write("people/briar.md", gutted)
    items = [{"role": "user", "source": f"codex:abc:{n}", "text": "x", "timestamp": "2026-09-24T00:00:00+00:00"}
             for n in range(1, 13)]
    directory = tmp_path / "task"
    directory.mkdir()
    refusals = _promote_maintenance(notebook, working, {"people/briar.md": full}, items, directory, None, False)
    assert notebook.read("people/briar.md") == full
    assert any("kept the old page" in error for error in refusals[0]["errors"])


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


def test_native_skill_is_expanded_once_with_page_rules(tmp_path):
    """The REM prompt used to send the core Skill once as a slash command and
    again inside its composed instructions, doubling it in Codex (#1972)."""
    from connectonion.cli.co_ai.harness import expand_skill
    from connectonion.rem.runner import task_prompt

    items = [{"role": "page", "record": "people/mia.md", "text": "# Mia\n"}]
    prompt = task_prompt(tmp_path, items, "investigate")
    expanded = expand_skill(prompt)
    assert expanded.count("# Investigate one subject") == 1
    assert expanded.count("# Investigating a person") == 1
    assert expanded.count("# A person's page") == 1
    big = [{**items[0], "text": "x" * 110_000}]
    fallback = task_prompt(tmp_path, big, "investigate")
    assert "Read the additional source and page instructions" in fallback
    assert "# Investigate one subject" not in (tmp_path / "additional-instructions.md").read_text()
    assert expand_skill(fallback).count("# Investigate one subject") == 1


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


def test_a_promoted_person_page_has_newest_first_history(notebook, tmp_path):
    record = 'people/avery.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    original = notebook.read(record)
    older = '- 2026-09-01: introduction — agreed to a call. [1]'
    newer = '- 2026-10-01: proposal — declined. [2]'
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(original.replace('## History\n- Unknown — not investigated yet',
                                          f'## History\n{older}\n{newer}')
                         .replace('- (none yet)', '- [1] gmail:m:1\n- [2] gmail:m:2')
                         .replace('- Unknown — not investigated yet', '- Unknown'))
    runner._promote_candidate(notebook, record, candidate, original,
                              [{'source': 'gmail:m:1'}, {'source': 'gmail:m:2'}], tmp_path, None)
    page = notebook.read(record)
    assert f'## History\n{newer}\n{older}\n' in page
    assert json.loads((tmp_path / 'review.json').read_text())['accepted']


@pytest.mark.parametrize('promotion', ['candidate', 'maintenance'])
def test_person_promotion_repairs_owner_pronouns(notebook, tmp_path, promotion):
    record = 'people/avery.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    original = notebook.read(record)
    line = 'The user said he would send the deck [1].'
    repaired = 'The user said the user would send the deck [1].'
    text = (original.replace('## Who they are\n- Unknown — not investigated yet',
                             '## Who they are\n- ' + line)
            .replace('- (none yet)', '- [1] gmail:avery-deck')
            .replace('- Unknown — not investigated yet', '- Unknown'))
    items = [{'source': 'gmail:avery-deck', 'role': 'user',
              'speaker': 'user@example.com', 'text': 'I will send the deck.'}]
    if promotion == 'candidate':
        candidate = tmp_path / 'candidate.md'
        candidate.write_text(text)
        runner._promote_candidate(notebook, record, candidate, original, items, tmp_path, None)
        review = json.loads((tmp_path / 'review.json').read_text())
        assert review['accepted']
        assert review['owner_pronouns_replaced'] == 1
    else:
        before = {r: notebook.read(r) for r in notebook.list()}
        working = Notebook(tmp_path / 'working')
        for r, page in before.items():
            working.write(r, page)
        working.write(record, text)
        assert runner._promote_maintenance(notebook, working, before, items, tmp_path, None, False) == []
        review = json.loads((tmp_path / 'review.json').read_text())
        assert record in review['accepted']
        assert review['repairs'][record]['owner_pronouns_replaced'] == 1
    assert repaired in notebook.read(record)
    assert line not in notebook.read(record)


@pytest.mark.parametrize('stage', ['enrich', 'muse'])
@pytest.mark.parametrize('collision', [False, True])
@pytest.mark.parametrize('sender,excerpt,tied', [
    ('MARA@EXAMPLE.COM', 'Mara asked', True),
    ('mara.chen@example.net', 'Mara asked', False),
    ('mara.chen@example.net', 'Mara Ostrowski asked', True),
    ('', 'Mara Ostrowski asked', True),
    ('', 'Mara asked', False),
])
def test_deepening_replaces_owner_first_name_only_with_cited_ties(
        notebook, tmp_path, monkeypatch, stage, collision, sender, excerpt, tied):
    """2026-10-21: a shared first name needs its cited sender or full name, never a page-title guess."""
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem import project_claim_review, reader_model
    owner, record = 'people/mara.md', 'people/avery.md'
    notebook.stub_person(owner, 'Mara Ostrowski', ['mara@example.com'], email='mara@example.com')
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    if collision:
        notebook.stub_person('people/mara-chen.md', 'Mara Chen', ['mara.chen@example.net'], email='mara.chen@example.net')
    write_json(state_path(notebook.root, 'map.json'), {'owner': {'record': owner, 'addresses': ['MARA@EXAMPLE.COM']}})
    original = notebook.read(record)
    short = '- Now: Avery Lin reviewed the Lantern interface. [1]'
    long = '- Now: Avery Lin reviewed the smaller Lantern interface. [1]'
    line = "- Changed: Mara asked Avery Lin for Mara Ostrowski's deck [1]."
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(original.replace('## Insight\n- Unknown — not investigated yet',
                                          f'## Insight\n{short}\n{long}\n{line}')
                         .replace('- (none yet)', '- [1] gmail:mara-deck')
                         .replace('- Unknown — not investigated yet', '- Unknown'))
    monkeypatch.setattr(project_claim_review, 'review', lambda *a, **kw: ({'verdict': 'pass', 'findings': []}, {}))
    private_reads = []
    def context(root, records, *, private=False):
        assert root == notebook.root
        if private:
            private_reads.append(records[0]['text'])
        return {'gmail:mara-deck': {'sender': sender, 'excerpt': excerpt}}
    monkeypatch.setattr(reader_model, 'cited_context', context)
    runner.promote_with_repairs(notebook, record, candidate, original, [{'source': 'gmail:mara-deck'}],
                                tmp_path, {}, workdir=tmp_path, config={}, stage=stage)
    page = notebook.read(record)
    first = 'The user' if tied else 'Mara'
    assert f"- Changed: {first} asked Avery Lin for the user's deck [1]." in page
    assert long in page and short not in page
    assert private_reads and all(line in text for text in private_reads)


def test_owner_ties_use_only_each_lines_numbered_originals(notebook, monkeypatch):
    """2026-10-21: another line's owner citation and the Sources caption cannot lend a tie."""
    from connectonion.rem import reader_model
    lines = ['Mara asked [7].', 'Mara asked [2].', 'Mara asked [3].', 'Mara asked [2][7].',
             'Mara asked without citations.', 'Mara asked [4].', 'Mara asked [1].']
    text = ('# Avery Lin\n\n' + '\n'.join(lines) + '\n\n## Sources\n'
            '- [7] gmail:owner\n- [2] gmail:correspondent — Mara Ostrowski\n'
            '- [3] gmail:mention\n- [4] gmail:unavailable\n')
    monkeypatch.setattr(reader_model, 'cited_context', lambda *a, **kw: {
        'gmail:owner': {'sender': 'mara@example.com', 'excerpt': 'Mara asked'},
        'gmail:correspondent': {'sender': 'mara.chen@example.net', 'excerpt': 'Mara asked'},
        'gmail:mention': {'excerpt': 'Mara Ostrowski asked'},
    })
    tied = runner._owner_tied_lines(notebook, text, {'addresses': ['MARA@EXAMPLE.COM']},
                                    ['Mara Ostrowski', 'Mara'])
    assert tied.intersection(lines) == {lines[0], lines[2], lines[3]}


def test_a_restored_carried_line_also_replaces_the_owner_name(notebook, tmp_path, monkeypatch):
    """2026-10-21: last-resort evidence restoration must not reintroduce the owner's name."""
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem import reader_model
    owner, record = 'people/mara.md', 'people/avery.md'
    notebook.stub_person(owner, 'Mara Ostrowski', ['mara@example.com'], email='mara@example.com')
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    write_json(state_path(notebook.root, 'map.json'), {'owner': {'record': owner, 'addresses': ['mara@example.com']}})
    monkeypatch.setattr(reader_model, 'cited_context', lambda *a, **kw: {
        'gmail:mara-deck': {'sender': 'mara@example.com', 'excerpt': 'Mara asked'}})
    original = (notebook.read(record).replace('## Insight\n- Unknown — not investigated yet',
                                             '## Insight\n- Changed: Mara handed Avery Lin the deck. [1]')
                .replace('- (none yet)', '- [1] gmail:mara-deck')
                .replace('- Unknown — not investigated yet', '- Unknown'))
    notebook.write(record, original)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(original.replace('- Changed: Mara handed Avery Lin the deck. [1]',
                                          '- Now: Avery Lin reviewed the Lantern interface. [2]')
                         .replace('- [1] gmail:mara-deck', '- [2] github:acme/lantern#12'))
    runner._promote_candidate(notebook, record, candidate, original,
                              [{'source': 'gmail:mara-deck'}, {'source': 'github:acme/lantern#12'}],
                              tmp_path, None, carried=original, last_resort=True)
    page = notebook.read(record)
    assert '- Changed: The user handed Avery Lin the deck.' in page
    assert 'gmail:mara-deck' in page and 'github:acme/lantern#12' in page


def test_upkeep_puts_back_a_quote_the_turn_dropped(notebook, tmp_path):
    """2026-10-20 upkeep A/B: one-page upkeep dropped 1-2 of a page's quotes per run, with no repair turn."""
    record = 'people/avery.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    quoted = '- Avery asked: “Could you send the deck by Friday?” (2026-10-01) [1]'
    page = (notebook.read(record).replace('## Who they are\n- Unknown — not investigated yet',
                                          '## Who they are\n' + quoted)
            .replace('- (none yet)', '- [1] gmail:avery-deck — 2026-10-01')
            .replace('- Unknown — not investigated yet', '- Unknown'))
    notebook.write(record, page)
    items = [{'source': 'gmail:avery-deck', 'role': 'other', 'speaker': 'Avery <avery@example.com>',
              'text': 'Could you send the deck by Friday?'}]
    before = {r: notebook.read(r) for r in notebook.list()}
    working = Notebook(tmp_path / 'working')
    for r, text in before.items():
        working.write(r, text)
    working.write(record, page.replace(quoted, '- Avery asked for the deck by Friday [1].'))
    assert runner._promote_maintenance(notebook, working, before, items, tmp_path, None, False) == []
    assert '“Could you send the deck by Friday?”' in notebook.read(record)
    assert json.loads((tmp_path / 'review.json').read_text())['repairs'][record]['restored_lines'] == 1


def test_a_finished_people_page_waits_for_backfill_before_its_claim_audit(tmp_path, monkeypatch):
    """2026-10-16: first-run backfill made the audit's zero-wait lock lose paid-for pages."""
    from connectonion.rem import page_review, project_claim_review
    monkeypatch.setattr(runner, "PROMOTE_WAIT_SECONDS", 5)
    monkeypatch.setattr(project_claim_review, "review", lambda *args, **kwargs:
                        ({"verdict": "pass"}, {"input_tokens": 0}))
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia", ["mia@h.example"], email="mia@h.example")
    original = notebook.read("people/mia.md")
    candidate = tmp_path / "candidate.md"
    candidate.write_text(original.replace("## Who they are\n- Unknown — not investigated yet",
                                          "## Who they are\n- Leads the data team. [1]")
                         .replace("- (none yet)", "- [1] gmail:m:1")
                         .replace("- Unknown — not investigated yet", "- Unknown"))
    threads, check_quotes = [], page_review.misquoted

    def before_audit(*args):
        errors = check_quotes(*args)
        threads.append(_hold_lock(tmp_path, 1.0))
        return errors

    monkeypatch.setattr(page_review, "misquoted", before_audit)
    audit_usage = runner._promote_candidate(notebook, "people/mia.md", candidate, original,
                                           [{"source": "gmail:m:1"}], tmp_path, {"input_tokens": 123},
                                           claim_config=default_config())
    threads[0].join()
    assert "Leads the data team." in notebook.read("people/mia.md")
    assert audit_usage == {"input_tokens": 0}
    assert json.loads((tmp_path / "review.json").read_text())["factual_quality"] == "bounded citation audit passed"


@pytest.mark.parametrize('stage', ['enrich', 'muse', 'investigate', 'maintain'])
def test_runner_claim_audit_carries_only_additive_stages(notebook, monkeypatch, tmp_path, stage):
    from connectonion.rem import project_claim_review
    record = 'projects/atlas.md'
    notebook.stub_project(record, 'Atlas')
    original = notebook.read(record)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(original.replace('- Unknown — not investigated yet', '- Unknown')
                         .replace('## What it is\n- Unknown', '## What it is\nA local demo. [1]')
                         .replace('- (none yet)', '- [1] codex:invented — 2026-10-01'))
    seen = []

    def review(*args, **kwargs):
        seen.append(kwargs['carried'])
        return {'verdict': 'fail' if len(seen) == 1 else 'pass',
                'findings': [{'claim': 'A local demo.', 'issue': 'Unsupported'}]}, {}

    monkeypatch.setattr(project_claim_review, 'review', review)
    items = [{'source': 'codex:invented', 'text': 'A local demo.'}]
    result = {}
    runner.promote_with_repairs(notebook, record, candidate, original, items, tmp_path, result,
        workdir=tmp_path, config={}, stage=stage, run=lambda *args: {})
    assert seen == [original if stage in ('enrich', 'muse', 'maintain') else ''] * 2
    assert result['repairs'] == 1


@pytest.mark.parametrize('stage', ['enrich', 'muse'])
def test_runner_restores_dropped_line_after_one_unsuccessful_repair(notebook, tmp_path, stage):
    from connectonion.rem.page_review import dropped
    record = 'people/avery.md'
    notebook.stub_person(record, 'Avery')
    lost = '- Profile says “Small tools travel far” and “Keep the interface quiet”. [56][57]\n'
    original = notebook.read(record).replace('- Unknown — not investigated yet', '- Unknown')
    original = original.replace('## Who they are\n- Unknown', '## Who they are\n' + lost.rstrip())
    original = original.replace('- (none yet)', '- [56] https://profile.example.test\n'
                                '- [57] https://work.example.test')
    notebook.write(record, original)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(original.replace(lost, '- Builds small research tools. [1]\n')
                         .replace('- [56] https://profile.example.test\n- [57] https://work.example.test',
                                  '- [1] codex:invented'))
    prompts = []

    def run(workdir, prompt, config, stage):
        prompts.append(prompt)
        return {'usage': {'input_tokens': 1}, 'result': 'done'}

    result = {}
    runner.promote_with_repairs(notebook, record, candidate, original,
        [{'source': 'codex:invented', 'text': 'Builds small research tools.'}], tmp_path, result,
        workdir=tmp_path, config={}, stage=stage, run=run, repairs=runner.DEEPEN_REPAIRS)
    saved = notebook.read(record)
    assert result['repairs'] == len(prompts) == 1
    assert all('Dropped quote the page had:' in prompt
               and 'Dropped source id the page had: https://profile.example.test' in prompt
               for prompt in prompts)
    assert 'Builds small research tools. [1]' in saved
    assert lost.replace('[56][57]', '[2][3]') in saved
    assert dropped(original, saved) == []
    review = json.loads((tmp_path / 'review.json').read_text())
    assert review['accepted'] and review['restored_lines'] == 1


def test_a_fact_whose_only_citation_is_dropped_loses_that_part_instead_of_failing_the_page(tmp_path):
    """1.9.2b3 trial: Maren's Role cited a project file outside her material; the
    unresolved [7] was dropped, the half it supported was left uncited, and the
    whole page was refused for "Fact without a citation: Role"."""
    from connectonion.rem import runner
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia", ["mia@h.example"], email="mia@h.example")
    original = notebook.read("people/mia.md")
    candidate = tmp_path / "candidate.md"
    candidate.write_text(original.replace("## Who they are\n- Unknown — not investigated yet",
                                          "## Who they are\n- Leads the data team. [1]")
                         .replace("- Role: Unknown", "- Role: Data lead [1]; tax customer (project record) [7]")
                         .replace("- (none yet)", "- [1] gmail:m:1\n- [7] project-file:/elsewhere/PEOPLE.md@abc")
                         .replace("- Unknown — not investigated yet", "- Unknown"))
    runner._promote_candidate(notebook, "people/mia.md", candidate, original,
                              [{"source": "gmail:m:1"}], tmp_path, None)
    page = notebook.read("people/mia.md")
    assert "- Role: Data lead [1]\n" in page and "tax customer" not in page


@pytest.mark.parametrize("audited", [False, True])
def test_a_sync_that_outlasts_the_wait_leaves_the_page_where_it_can_be_found(tmp_path, monkeypatch, audited):
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
    usage = {"input_tokens": 123}
    with pytest.raises(RunFailed) as error:
        runner._promote_candidate(notebook, "people/mia.md", candidate, original, [], tmp_path, usage,
                                  claim_config=default_config() if audited else None)
    thread.join()
    assert str(candidate) in str(error.value) and candidate.is_file()
    assert f"; the finished page is kept at {candidate}" in str(error.value)
    assert error.value.usage == usage


def test_finished_tasks_lose_their_private_copies_and_running_ones_are_left_alone(tmp_path):
    """#1958: 98 task folders held 75 MB of the owner's mail. A folder is scrubbed
    after its result is old enough; a run still finishing keeps its material."""
    from connectonion.rem.runner import FINISHED_TASK_GRACE_SECONDS, scrub_finished_tasks

    done, running = tmp_path / "maintain-a", tmp_path / "investigate-b"
    for folder in (done, running):
        (folder / "notebook/people").mkdir(parents=True)
        (folder / "material.json").write_text("[]")
        (folder / "material.md").write_text("mail")
        (folder / "notebook/people/x.md").write_text("# X")
    (done / "result.json").write_text("{}")
    (done / "candidate.md").write_text("# X")

    scrub_finished_tasks(tmp_path)
    assert (done / "material.json").is_file()
    old = time.time() - FINISHED_TASK_GRACE_SECONDS - 1
    os.utime(done / "result.json", (old, old))
    scrub_finished_tasks(tmp_path)

    assert sorted(p.name for p in done.iterdir()) == ["candidate.md", "result.json"]
    assert (running / "material.json").is_file() and (running / "notebook/people/x.md").is_file()


# ------------------------------------------------ #1974: private copies, one env


def test_finished_tasks_are_scrubbed_once_per_process(tmp_path, monkeypatch):
    calls = []
    scrub = runner.scrub_task

    def scrubbing(folder):
        calls.append(folder)
        scrub(folder)

    monkeypatch.setattr(runner, 'scrub_task', scrubbing)
    old = time.time() - runner.FINISHED_TASK_GRACE_SECONDS - 1
    for name in ('investigate-a', 'investigate-b'):
        folder = tmp_path / name
        folder.mkdir()
        result = folder / 'result.json'
        result.write_text('{}')
        os.utime(result, (old, old))
        with runner._TASK_CLEANUP_LOCK:
            runner.scrub_finished_tasks(tmp_path)
            runner.scrub_finished_tasks(tmp_path)
    assert calls == [tmp_path / 'investigate-a', tmp_path / 'investigate-b']


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


def test_overlapping_runner_tasks_keep_private_mask_until_both_finish(notebook, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    together = threading.Barrier(2, timeout=5)
    observed = []

    def run(argv, **kw):
        observed.append(os.umask(0o077))
        together.wait()
        if threading.current_thread().name.endswith("_0"):
            time.sleep(0.05)
            observed.append(os.umask(0o077))
        return SimpleNamespace(returncode=0, stdout='{"outcome":"natural"}', stderr="")

    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", run)
    original = os.umask(0o022)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run_stage, notebook, [], default_config(), stage="abstract") for _ in range(2)]
            for future in futures:
                future.result()
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(original)
    assert observed == [0o077] * 3


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
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia", ["mia@h.example"], email="mia@h.example")
    original = notebook.read("people/mia.md")
    one_line = (original.replace("## Who they are\n- Unknown — not investigated yet",
                                 "## Who they are\n- Leads the data team. [1]", 1)
                .replace("- (none yet)", "- [1] gmail:m:1"))
    candidate = tmp_path / "candidate.md"

    candidate.write_text(one_line)
    runner._promote_candidate(notebook, "people/mia.md", candidate, original, [{"source": "gmail:m:1"}],
                              tmp_path, None, investigation=False)
    page = notebook.read("people/mia.md")
    assert "Leads the data team." in page and "## Insight\n- Unknown — not investigated yet" in page


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


def test_history_only_refusal_gets_one_repair_turn_with_usage_counted(notebook, monkeypatch):
    """A ten-line History on a real first run was rejected after the model turn."""
    import re as regex
    from connectonion.rem.files import write_json

    record = 'people/first.md'
    notebook.stub_person(record, 'First', ['first@example.org'], email='first@example.org')
    prompts, promotions = [], []

    def run_model(workdir, prompt, config, stage):
        prompts.append(prompt)
        candidate = Path(regex.search(r'(/\S+/candidate\.md)', prompt).group(1))
        candidate.write_text('# First\n## History\n- 2026: first milestone\n')
        return {'usage': {'input_tokens': 10, 'output_tokens': 1}, 'result': 'done'}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        promotions.append(usage)
        if len(promotions) == 1:
            write_json(directory / 'review.json', {'accepted': False,
                        'errors': ['History has 10 lines (was 0); keep at most 8 dated milestones']})
            raise RunFailed('Candidate rejected', usage)
        book.write(record, candidate.read_text())

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    result = run_stage(notebook, [{'role': 'page', 'record': record,
                                   'text': notebook.read(record), 'source': 'investigation:page'}],
                       default_config(), stage='investigate')
    assert len(prompts) == 2 and 'at most sixteen dated History lines' in prompts[1]
    assert promotions[1] == result['usage'] == {'input_tokens': 20, 'output_tokens': 2}


def test_failed_history_repair_counts_both_model_turns(notebook, monkeypatch):
    import re as regex
    from connectonion.rem.files import write_json

    record = 'people/first.md'
    notebook.stub_person(record, 'First', ['first@example.org'], email='first@example.org')
    calls = []

    def run_model(workdir, prompt, config, stage):
        calls.append(prompt)
        if len(calls) == 2:
            raise RunFailed('repair unavailable', {'input_tokens': 3})
        Path(regex.search(r'(/\S+/candidate\.md)', prompt).group(1)).write_text('# First\n')
        return {'usage': {'input_tokens': 10}, 'result': 'done'}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        write_json(directory / 'review.json', {'accepted': False,
                   'errors': ['History has 10 lines (was 0); keep at most 8 dated milestones']})
        raise RunFailed('Candidate rejected', usage)

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    with pytest.raises(RunFailed, match='repair unavailable') as caught:
        run_stage(notebook, [{'role': 'page', 'record': record,
                              'text': notebook.read(record), 'source': 'investigation:page'}],
                  default_config(), stage='investigate')
    assert len(calls) == 2
    assert caught.value.usage == {'input_tokens': 13}


@pytest.mark.parametrize(('failure', 'repair_hint'), [
    ('Cited local file needs its current SHA-256 and a mapped path: file:/missing',
     'Replace invented `git:` or `file:` citations'),
    ('Cited-claim audit did not pass; see claim-review.json', 'Fix every audit finding'),
])
def test_project_refusal_gets_one_source_based_repair(notebook, monkeypatch, failure, repair_hint):
    import re
    from connectonion.rem.files import write_json

    record = 'projects/example.md'
    notebook.stub_project(record, 'Example', [])
    prompts, promotions = [], []

    def run_model(workdir, prompt, config, stage):
        prompts.append(prompt)
        candidate = Path(re.search(r'(/\S+/candidate\.md)', prompt).group(1))
        candidate.write_text('# Example\n' + ('Corrected' if len(prompts) == 2 else 'Bad file citation'))
        return {'usage': {'input_tokens': 10 if len(prompts) == 1 else 5}, 'result': 'done'}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        promotions.append(usage)
        if len(promotions) == 1:
            write_json(directory / 'review.json', {'accepted': False, 'errors': [failure]})
            if failure.startswith('Cited-claim'):
                write_json(directory / 'claim-review.json', {'verdict': 'fail', 'findings': []})
            raise RunFailed('Bad file citation', usage)
        book.write(record, candidate.read_text())

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    result = run_stage(notebook, [{'role': 'page', 'record': record,
                                   'text': notebook.read(record), 'source': 'investigation:page'}],
                       default_config(), stage='investigate')
    assert len(prompts) == 2 and repair_hint in prompts[1]
    assert 'material.md' in prompts[1]
    assert 'exact Sessions, First seen, and Last seen lines' in prompts[1]
    assert 'Read the original mapped page at ' in prompts[1]
    assert '/projects/example.md' in prompts[1]
    if failure.startswith('Cited local'):
        assert 'mapped Paths' in prompts[1]
    else:
        assert 'claim-review.json' in prompts[1]
    assert promotions == [{'input_tokens': 10}, {'input_tokens': 15}]
    assert result['usage'] == {'input_tokens': 15}
    assert 'Corrected' in notebook.read(record)


def test_project_claim_audit_can_surface_new_findings_on_a_second_repair(notebook, monkeypatch):
    import re
    from connectonion.rem.files import write_json

    record = 'projects/example.md'
    notebook.stub_project(record, 'Example', [])
    prompts, promotions = [], []

    def run_model(workdir, prompt, config, stage):
        prompts.append(prompt)
        candidate = Path(re.search(r'(/\S+/candidate\.md)', prompt).group(1))
        candidate.write_text('# Example\nCandidate ' + str(len(prompts)))
        return {'usage': {'input_tokens': 10}, 'result': 'done'}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        promotions.append(usage['input_tokens'])
        if len(promotions) < 3:
            write_json(directory / 'review.json', {'accepted': False,
                'errors': ['Cited-claim audit did not pass; see claim-review.json']})
            write_json(directory / 'claim-review.json', {'verdict': 'fail',
                'findings': [{'claim': f'False claim {len(promotions)}',
                              'issue': 'A different adjacent claim needs correction'}]})
            raise RunFailed('Claim audit failed', {'input_tokens': usage['input_tokens'] + 2})
        write_json(directory / 'claim-review.json', {'verdict': 'pass', 'findings': []})
        book.write(record, candidate.read_text())

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    result = run_stage(notebook, [{'role': 'page', 'record': record,
                                   'text': notebook.read(record), 'source': 'investigation:page'}],
                       default_config(), stage='investigate')
    assert len(prompts) == 3 and all('Fix every audit finding' in prompt for prompt in prompts[1:])
    assert all('exact Sessions, First seen, and Last seen lines' in prompt for prompt in prompts[1:])
    assert promotions == [10, 22, 34]
    assert result['usage'] == {'input_tokens': 34}
    assert result['refuted_claims'] == ['False claim 1', 'False claim 2']
    assert 'Candidate 3' in notebook.read(record)


@pytest.mark.parametrize('repaired', [True, False])
def test_mistyped_skill_citation_repairs_the_finding_once_instead_of_losing_it(notebook, monkeypatch, repaired):
    import re
    record = 'skills/catalog/editor.md'
    notebook.stub_skill(record, 'editor', '/source/SKILL.md')
    original = notebook.read(record)
    source = 'skill-session:claude-code:21836ac9-0d71-4a16-b9e5:2026-10-01T13:01:48.392Z'
    mistyped = source.replace('b9e5', '9b5e')
    claim = 'The reported English check skipped the full language pass. [1]'
    base = original.replace('Unknown — not investigated yet', 'Unknown')
    base = base.replace('## Insight\nUnknown', '## Insight\n- ' + claim)
    base = base.replace('## Current status\nUnknown — not verified; no run evidence reviewed',
                        '## Current status\n' + claim)
    prompts = []

    def run_model(workdir, prompt, config, stage):
        prompts.append(prompt)
        candidate = Path(re.search(r'(/\S+/candidate\.md)', prompt).group(1))
        citation = source if repaired and len(prompts) == 2 else mistyped
        candidate.write_text(base.replace('- Skill metadata: /source/SKILL.md', '- [1] ' + citation))
        return {'usage': {'input_tokens': 10}, 'result': 'done'}

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    items = [{'role': 'page', 'record': record, 'text': original, 'source': 'investigation:page'},
             {'role': 'evidence-index', 'sources': [source + ':part-1'], 'text': 'Reported partial check.'}]
    if repaired:
        result = run_stage(notebook, items, default_config(), stage='investigate')
        assert claim in notebook.read(record) and source in notebook.read(record)
        assert result['usage'] == {'input_tokens': 20}
        assert len(prompts) == 2
    else:
        # Two repairs, then the finding goes with its line; with nothing cited left, the page is refused.
        with pytest.raises(RunFailed, match='no numbered evidence references') as caught:
            run_stage(notebook, items, default_config(), stage='investigate')
        assert notebook.read(record) == original
        assert caught.value.usage == {'input_tokens': 30}
        assert len(prompts) == 1 + runner.MAX_REPAIRS
    assert 'copy the exact source ids' in prompts[1]


def test_a_turn_may_ask_for_mail_searches_and_gets_one_more_turn_with_their_results(notebook, monkeypatch):
    """The model has no network (its sandbox is the defence against mail that
    carries instructions); it names searches, our code runs them read-only,
    and the results come back as cited material for one more turn."""
    import json as jsonlib
    import re as regex
    from connectonion.rem.config import set_config
    set_config(notebook.root, ['schedule.timezone', 'Australia/Sydney'])
    record = 'people/first.md'
    notebook.stub_person(record, 'First', ['first@example.org'], email='first@example.org')
    prompts, asked, promoted = [], [], []
    found = [{'role': 'other', 'speaker': 'Second <second@example.org>', 'text': 'First runs the lab.',
              'timestamp': '2026-08-27T21:30:00Z', 'subject': 'Intro', 'source': 'outlook:abc123abc123'}]

    def search(queries):
        asked.append(queries)
        return found

    def run_model(workdir, prompt, config, stage):
        prompts.append(prompt)
        candidate = Path(regex.search(r'(/\S+/candidate\.md)', prompt).group(1))
        candidate.write_text('# First\n')
        if len(prompts) == 1:
            (candidate.parent / 'search-requests.json').write_text(jsonlib.dumps(['First lab', 'from:x@y.z']))
        else:
            assert 'Date: 2026-08-27T21:30:00Z (2026-08-28 07:30 Australia/Sydney)' in (
                candidate.parent / 'search-results.md').read_text()
        return {'usage': {'input_tokens': 10}, 'result': 'done'}

    def promote(book, record, candidate, original, items, directory, usage, **options):
        promoted.append([item['source'] for item in items])
        assert items[-1]['local_time'] == '2026-08-28 07:30 Australia/Sydney'

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    run_stage(notebook, [{'role': 'page', 'record': record, 'text': notebook.read(record),
                          'source': 'investigation:page'}], default_config(), stage='investigate', search=search)
    assert asked == [['First lab', 'from:x@y.z']]
    assert len(prompts) == 2 and 'search-results.md' in prompts[1] and 'search-requests.json' in prompts[0]
    assert all(prompt.endswith('</co_rem_task>') for prompt in prompts)
    assert 'outlook:abc123abc123' in promoted[0]
    assert 'local_time' not in found[0]


def test_quick_first_pass_never_offers_or_runs_extra_mail_search(notebook, monkeypatch):
    """The live quick prompt contradicted its own sample-only instruction."""
    import re
    record = 'people/first.md'
    notebook.stub_person(record, 'First', ['first@example.org'], email='first@example.org')
    prompts, asked = [], []

    def run_model(workdir, prompt, config, stage):
        prompts.append(prompt)
        candidate = Path(re.search(r'(/\S+/candidate\.md)', prompt).group(1))
        candidate.write_text('# First\n')
        (candidate.parent / 'search-requests.json').write_text('["extra mail"]')
        return {'usage': {'input_tokens': 10}, 'result': 'done'}

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', lambda *a, **kw: None)
    run_stage(notebook, [
        {'role': 'page', 'record': record, 'text': notebook.read(record), 'source': 'investigation:page'},
        {'role': 'quick-first-pass', 'source': 'investigation:quick-scope', 'text': 'Use only the sample.'},
    ], default_config(), stage='investigate', search=lambda queries: asked.append(queries) or [])
    assert len(prompts) == 1 and not asked
    assert 'Optional runner-mediated mail search' not in prompts[0]
    assert prompts[0].endswith('</co_rem_task>')


def test_a_project_still_refused_for_one_citation_after_its_repairs_drops_those_lines(notebook, monkeypatch):
    """3 of 4 project refusals on a real 1.9.1a2 init were one untraceable
    citation each, after two repair turns; the page was lost whole."""
    import re
    from connectonion.rem.files import write_json

    record = 'projects/example.md'
    notebook.stub_project(record, 'Example', [])
    modes = []

    def run_model(workdir, prompt, config, stage):
        Path(re.search(r'(/\S+/candidate\.md)', prompt).group(1)).write_text('# Example\nStill one bad citation')
        return {'usage': {'input_tokens': 1}, 'result': 'done'}

    def promote(book, record, candidate, original, items, directory, usage, last_resort=False, **options):
        modes.append(last_resort)
        if not last_resort:
            write_json(directory / 'review.json', {'accepted': False,
                       'errors': ['Citation has no identifiable source: 13']})
            raise RunFailed('Candidate rejected', usage)
        book.write(record, candidate.read_text())

    monkeypatch.setattr('connectonion.rem.runner.run_task', run_model)
    monkeypatch.setattr('connectonion.rem.runner._promote_candidate', promote)
    result = run_stage(notebook, [{'role': 'page', 'record': record,
                                   'text': notebook.read(record), 'source': 'investigation:page'}],
                       default_config(), stage='investigate')
    assert modes == [False, False, False, True]  # two repairs, then the lines go, not the page
    assert result['changed'] == [record]


def test_a_run_names_the_codex_threads_that_ran_it(notebook, monkeypatch):
    """The 1.9.2b3 audit could match only about 102 of 331 runs to their Codex
    threads, by timestamps; the run record carried no thread id."""
    monkeypatch.setattr("connectonion.rem.runner.subprocess.run", lambda argv, **kw: SimpleNamespace(
        returncode=0, stdout='{"outcome": "natural", "session_id": "01a12370-thread"}', stderr=""))
    assert run_stage(notebook, [], default_config())["threads"] == ["01a12370-thread"]


def test_material_carries_local_times_without_changing_the_sources(notebook, delegate):
    from zoneinfo import ZoneInfo
    from connectonion.rem.config import set_config
    from connectonion.rem.source import local_time, with_local_times
    zone = ZoneInfo("Australia/Sydney")
    stamp = "2026-08-27T21:30:00Z"
    items = [{"source": "outlook:reply", "timestamp": stamp, "text": "Reply sent."},
             {"source": "undated", "text": "No date."},
             {"source": "non-iso", "timestamp": "yesterday", "text": "No exact time."},
             {"source": "date-only", "timestamp": "2026-08-27", "text": "No exact time."}]
    shown = with_local_times(items, zone)
    assert local_time(stamp, zone) == "2026-08-28 07:30 Australia/Sydney"
    assert list(shown[0]) == ["source", "timestamp", "local_time", "text"]
    assert shown[1:] == items[1:] and all(copy is not item for copy, item in zip(shown, items))
    assert all("local_time" not in item for item in items)
    assert "timestamp: " + stamp + "\nlocal_time: 2026-08-28 07:30 Australia/Sydney" in runner.readable_material(shown)
    set_config(notebook.root, ["schedule.timezone", "Australia/Sydney"])
    run_stage(notebook, items, default_config())
    assert delegate[0][1]["material"] == shown


def test_every_page_turn_is_told_what_day_it_is_in_the_notebooks_timezone(notebook, delegate):
    """Corin's page kept 13 and 14 October events as open threads on the 15th:
    no turn was told the date."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from connectonion.rem.config import set_config
    set_config(notebook.root, ["schedule.timezone", "Australia/Sydney"])
    today = datetime.now(ZoneInfo("Australia/Sydney")).date().isoformat()
    note = runner.today_note(notebook.root)
    assert f"Today is {today} (Australia/Sydney)" in note and "never an open thread" in note
    assert "local_time" in note
    run_stage(notebook, [{"role": "page", "record": "notes/old.md", "text": "x"}], default_config(), stage="maintain")
    argv, options = delegate[0]
    handed = argv[-1] + "".join(path.read_text() for path in Path(options["cwd"]).rglob("*.md")
                                if path.is_file())
    assert f"Today is {today}" in handed


def test_a_maintenance_turn_cannot_give_a_person_a_relay_or_a_stranger_s_address(tmp_path):
    """Corin's Luma relay became his Email (contacts audit E2); a one-page sync turn is
    held to the same contact rule as an investigation."""
    from connectonion.rem.runner import _promote_maintenance
    root, work = tmp_path / "rem", tmp_path / "work"
    prepare(root)
    prepare(work)
    notebook, working = Notebook(root), Notebook(work)
    notebook.stub_person("people/corin.md", "Corin Marsh", ["corin.marsh@example.com"], email="corin.marsh@example.com")
    before = notebook.read("people/corin.md")
    after = before.replace("- Email: corin.marsh@example.com",
                           "- Email: corin.marsh@example.com; usr-abc@user.luma-mail.com; fenwick@estate.example")
    working.write("people/corin.md", after)
    directory = tmp_path / "task"
    directory.mkdir()
    refusals = _promote_maintenance(notebook, working, {"people/corin.md": before}, [], directory, None, False)
    saved = notebook.read("people/corin.md")
    assert not refusals
    assert json.loads((directory / "review.json").read_text())["accepted"] == ["people/corin.md"]
    assert "corin.marsh@example.com" in saved and "luma-mail" not in saved and "fenwick@" not in saved


def test_a_refuted_first_contact_is_replaced_with_the_extracted_date_on_last_resort(notebook, tmp_path):
    """2026-10-20: dropping an audited contact date must restore the extracted row."""
    from connectonion.rem import facts
    from connectonion.rem.files import write_json

    record = 'people/avery.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    original = notebook.read(record)
    claim = 'First contact: 2025-08-26 (earliest mail found) [2]'
    extracted = {'field': 'First contact', 'value': '2026-08-11', 'qualifier': 'earliest mail found',
                 'source': 'gmail:avery-first', 'date': '2026-08-11'}
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(original.replace('## Who they are\n- Unknown — not investigated yet',
                                          '## Who they are\n- Avery Lin leads the pilot. [1]')
                         .replace('- First contact: Unknown', '- ' + claim)
                         .replace('- (none yet)', '- [1] gmail:avery-latest\n- [2] gmail:avery-cc')
                         .replace('- Unknown — not investigated yet', '- Unknown'))
    write_json(tmp_path / 'claim-review.json', {'verdict': 'fail', 'findings': [
        {'claim': claim, 'issue': 'Avery was only cc’d on this mail; it was not direct contact.'}]})
    items = [{'source': 'gmail:avery-latest'}, {'source': 'gmail:avery-cc'},
             {'role': 'facts', 'facts': [extracted]}]

    runner._promote_candidate(notebook, record, candidate, original, items, tmp_path, None, last_resort=True)

    page = notebook.read(record)
    assert facts.parse(page, record)['First contact'] == [
        {'value': '2026-08-11', 'qualifier': 'earliest mail found', 'citations': ['2']}]
    assert '- [2] gmail:avery-first — 2026-08-11\n' in page
    assert '2025-08-26' not in page and '- First contact: Unknown' not in page
    review = json.loads((tmp_path / 'review.json').read_text())
    assert review['accepted']
    assert {'field': 'First contact', 'source': 'gmail:avery-first'} in review['facts_restored']


def test_a_page_whose_audit_emptied_its_lead_is_not_promoted():
    """Corin Marsh (2026-10-15) was kept with no lead: the audit refuted a claim in
    each sentence. `_lead` is what the last resort checks before keeping a page."""
    from connectonion.rem.runner import _lead
    assert _lead("# Corin Marsh\n\n\n## Facts\n- Email: x\n") == ""
    assert _lead("# Corin Marsh\n\nCorin is a co-founder [1]. Last contact: 2026-10-15.\n\n## Facts\n") \
        .startswith("Corin is a co-founder")


def test_a_lead_that_lost_who_they_are_opens_with_their_cited_role():
    """Greta and Petra (2026-10-15): an audit finding about a missing citation
    took the lead's first sentence, and Petra's page opened on an HR ticket."""
    from connectonion.rem.runner import _keep_identity
    facts = ("## Facts\n- Company: [UNSW Founders](../orgs/unsw.md) [4]\n- Role: Events Coordinator [4]\n\n"
             "## Insight\n- Unknown\n")
    before = "# Greta Holloway\n\nGreta is the user's main MCIC contact [1]. The user owes her a card [5].\n\n" + facts
    after = "# Greta Holloway\n\nThe user owes her a card [5].\n\n" + facts
    kept = _keep_identity("people/greta.md", before, after)
    assert kept.startswith("# Greta Holloway\n\nGreta Holloway is Events Coordinator at "
                           "[UNSW Founders](../orgs/unsw.md) [4]. The user owes her a card [5].\n\n## Facts")
    assert _keep_identity("people/greta.md", before, before) == before
    emptied = _keep_identity("people/greta.md", before, "# Greta Holloway\n\n\n" + facts)
    assert emptied.startswith("# Greta Holloway\n\nGreta Holloway is Events Coordinator") and "\n\n## Facts" in emptied



@pytest.mark.parametrize('footer, carried', [('investigated 2026-10-08 (outlook)', True), ('not investigated yet', False)])
def test_an_update_of_an_investigated_page_carries_the_page_it_replaces(notebook, monkeypatch, tmp_path, footer, carried):
    """2026-10-20: 15 people-page updates on real mail lost 22 quotes and 40-70 sources."""
    from connectonion.rem import project_claim_review
    record = 'people/avery.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    original = notebook.read(record).replace('not investigated yet', footer)
    notebook.write(record, original)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(original.replace('- Unknown — not investigated yet', '- Unknown')
                         .replace('## Who they are\n- Unknown', '## Who they are\nAvery tests pilots. [1]')
                         .replace('- (none yet)', '- [1] gmail:invented — 2026-10-01'))
    seen = []

    def review(*args, **kwargs):
        seen.append(kwargs['carried'])
        return {'verdict': 'pass', 'findings': []}, {}

    monkeypatch.setattr(project_claim_review, 'review', review)
    runner.promote_with_repairs(notebook, record, candidate, original, [{'source': 'gmail:invented', 'text': 'x'}],
                                tmp_path, {}, workdir=tmp_path, config={}, stage='investigate', run=lambda *a: {})
    assert seen == [original if carried else '']

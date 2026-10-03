"""A Project citation audit must preserve the last accepted page on refusal."""

import json
import importlib
import hashlib
from types import SimpleNamespace

import pytest

from connectonion.rem import project_claim_review, runner
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path


def test_missing_cited_original_never_reaches_the_model(tmp_path):
    prepare(tmp_path)
    candidate = '# Atlas\n\nA factual claim [1].\n\n## Sources\n- [1] codex:missing — 2026-10-01\n'

    def should_not_run(*args):
        raise AssertionError('The audit cannot judge an unavailable original')

    report, usage = project_claim_review.review(Notebook(tmp_path), candidate, {}, tmp_path, should_not_run)
    assert report == {'verdict': 'insufficient', 'findings': [], 'missing_citations': ['1']}
    assert usage == {}


def test_truncated_original_is_shown_with_its_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(project_claim_review, 'cited_context', lambda *_args, **_kwargs: {
        'codex:session': {'excerpt': 'A question about filtering', 'truncated': True}})
    candidate = '# Atlas\n\nFiltering was discussed [1].\n\n## Sources\n- [1] codex:session — 2026-10-01\n'
    material, missing = project_claim_review.packet(Notebook(tmp_path), candidate)
    assert missing == []
    assert material['sources'][0]['context']['truncated'] is True
    assert material['sources'][0]['context']['excerpt'] == 'A question about filtering'


def test_new_cited_session_and_repo_packets_are_openable_before_audit(tmp_path):
    prepare(tmp_path)
    session = 'codex:session:5121301'
    origin, body = 'git:main:README.md', 'The source states the project goal.'
    repository = 'project-source:' + hashlib.sha256((origin + '\0' + body).encode()).hexdigest()
    file = tmp_path / 'originals.json'
    file.write_text(json.dumps([
        {'role': 'user', 'source': session, 'text': 'Ask the owner about the goal.',
         'timestamp': '2026-10-01T00:00:00Z'},
        {'role': 'readme', 'source': repository, 'origin': origin, 'text': body,
         'timestamp': '2026-10-01T00:00:00Z'}]))
    candidate = ('# Atlas\n\nThe user asked about the goal [1]; the README states it [2].\n\n'
                 '## Sources\n- [1] ' + session + ' — 2026-10-01\n'
                 '- [2] ' + repository + ' — 2026-10-01\n')
    notebook = Notebook(tmp_path)
    assert project_claim_review.packet(notebook, candidate)[1] == ['1', '2']
    project_claim_review.retain_cited_originals(notebook, candidate,
        [{'role': 'original_evidence', 'file': str(file)}])
    material, missing = project_claim_review.packet(notebook, candidate)
    assert missing == []
    assert {row['source_id'] for row in material['sources']} == {session, repository}


def test_audit_keeps_all_cited_originals_when_several_source_files_are_long(tmp_path):
    prepare(tmp_path)
    candidate = '# Atlas\n\nFour cited source files.\n\n## Sources\n'
    for number in range(1, 5):
        source = f'git:/mapped/repo:{"a" * 40}:src/file-{number}.py'
        body = f'File {number} explains the project.\n' + 'source detail\n' * 4_400
        path = state_path(tmp_path, 'project-sources/live-' + hashlib.sha256(source.encode()).hexdigest() + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'id': source, 'text': body,
                                    'sha256': hashlib.sha256(body.encode()).hexdigest(),
                                    'commit': 'a' * 40, 'commit_at': '2026-10-01',
                                    'captured_at': '2026-10-02'}))
        candidate += f'- [{number}] {source} — 2026-10-01\n'

    material, missing = project_claim_review.packet(Notebook(tmp_path), candidate)
    assert missing == []
    assert len(material['sources']) == 4
    assert all('explains the project' in row['context']['excerpt'] for row in material['sources'])

    def should_not_run(*args):
        raise AssertionError('An over-budget audit cannot ask the model to guess')

    report, _usage = project_claim_review.review(Notebook(tmp_path), candidate, {}, tmp_path, should_not_run)
    assert report['verdict'] == 'insufficient'
    assert report['reason'] == 'Cited originals exceed the audit bound'


def test_runner_status_is_excluded_from_prose_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(project_claim_review, 'cited_context', lambda *_args, **_kwargs: {
        'codex:session': {'excerpt': 'Filtering was discussed', 'truncated': False}})
    candidate = ('# Atlas\n\nFiltering was discussed [1].\n\n'
                 'Investigation: complete\n\n## Sources\n'
                 '- [1] codex:session — 2026-10-01\n')
    seen = {}

    def audited(_workspace, prompt, _config, _stage):
        seen['prompt'] = prompt
        return {'result': '{"verdict":"PASS","findings":[]}'}

    report, _usage = project_claim_review.review(Notebook(tmp_path), candidate, {}, tmp_path, audited)
    assert report['verdict'] == 'pass'
    assert 'do not audit it as a prose claim' in seen['prompt']


def test_audit_sees_session_folder_without_promoting_it_to_subfolder_purpose(tmp_path, monkeypatch):
    record, source = 'projects/work.md', 'codex:session:5121301'
    folder = tmp_path / 'work'
    path = state_path(tmp_path, 'projects/work/messages.jsonl')
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'source': source, 'cwd': str(folder)}) + '\n')
    monkeypatch.setattr(project_claim_review, 'cited_context', lambda *_args, **_kwargs: {
        source: {'excerpt': 'Research houses', 'truncated': False}})
    candidate = '# Work\n\nThe user requested house research [1].\n\n## Sources\n- [1] ' + source + ' — 2026-10-01\n'
    seen = {}

    def audited(_workspace, prompt, _config, _stage):
        seen['packet'] = json.loads(prompt[prompt.index('{'):])
        seen['instruction'] = prompt[:prompt.index('{')]
        return {'result': '{"verdict":"PASS","findings":[]}'}

    report, _usage = project_claim_review.review(Notebook(tmp_path), candidate, {}, tmp_path,
                                                 audited, record=record)
    assert report['verdict'] == 'pass'
    assert seen['packet']['sources'][0]['context']['mapped_session_folder'] == str(folder)
    assert 'proves neither implementation nor that earlier work belongs' in seen['instruction']
    assert 'A confirmed Website Fact requires an adjacent original' in seen['instruction']


def test_failed_project_claim_review_preserves_previous_page(tmp_path, monkeypatch):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    record = 'projects/atlas.md'
    notebook.stub_project(record, 'Atlas')
    before = notebook.read(record)
    candidate = (before.replace('- Unknown — not investigated yet', '- Unknown')
                 .replace('## What it is\n- Unknown', '## What it is\nA local demo. [1]')
                 .replace('- (none yet)', '- [1] codex:session — 2026-10-01'))
    path = tmp_path / 'candidate.md'
    path.write_text(candidate)

    def rejected(*args, **kwargs):
        return {'verdict': 'fail', 'findings': [{'issue': 'The original only asked a question',
                                               'evidence': 'No answer is present',
                                               'required_correction': 'State the question as open'}]}, {
            'input_tokens': 100, 'output_tokens': 20}

    monkeypatch.setattr(project_claim_review, 'review', rejected)
    items = [{'role': 'page', 'record': record, 'text': before},
             {'source': 'codex:session', 'text': 'A local demo.'}]
    with pytest.raises(runner.RunFailed, match='Cited-claim audit did not pass') as raised:
        runner._promote_candidate(notebook, record, path, before, items, tmp_path,
                                  {'input_tokens': 200}, claim_config={})
    assert notebook.read(record) == before
    assert raised.value.usage == {'input_tokens': 300, 'output_tokens': 20}
    assert json.loads((tmp_path / 'claim-review.json').read_text())['verdict'] == 'fail'
    assert json.loads((tmp_path / 'review.json').read_text())['factual_quality'] == 'bounded citation audit failed'


def test_codex_audit_sends_private_sources_over_stdin(tmp_path, monkeypatch):
    codex = importlib.import_module('connectonion.useful_tools.codex')

    monkeypatch.setattr(codex, '_base_command', lambda: ['codex', 'app-server'])
    seen = {}

    def completed(command, **kwargs):
        seen.update(command=command, input=kwargs['input'])
        (tmp_path / 'claim-answer.json').write_text('{"verdict":"FAIL","findings":[]}')
        event = {'type': 'turn.completed', 'usage': {'input_tokens': 42, 'output_tokens': 4}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(event), stderr='')

    monkeypatch.setattr(runner.subprocess, 'run', completed)
    config = {'runner': 'codex', 'model': 'gpt-6-luna', 'limits': {'timeout_seconds': 600}}
    result = runner.run_claim_task(tmp_path, 'PRIVATE SOURCE BODY', config, 'claim-audit')
    assert seen['input'] == 'PRIVATE SOURCE BODY'
    assert 'PRIVATE SOURCE BODY' not in ' '.join(seen['command'])
    assert result['usage'] == {'input_tokens': 42, 'cached_input_tokens': 0, 'output_tokens': 4}


def test_finished_task_keeps_rejection_reason_but_removes_audit_packet(tmp_path):
    for name in ('candidate.md', 'review.json', 'claim-review.json', 'claim-input.txt'):
        (tmp_path / name).write_text('private')
    runner.scrub_task(tmp_path)
    assert all((tmp_path / name).is_file() for name in ('candidate.md', 'review.json', 'claim-review.json'))
    assert not (tmp_path / 'claim-input.txt').exists()
    assert (tmp_path / 'claim-review.json').stat().st_mode & 0o777 == 0o600

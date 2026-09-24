import json

import yaml
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.wiki.files import Notebook
from connectonion.wiki.skill_runs import collect_skill_runs, investigate_skill_runs


def summaries(root):
    root.mkdir()
    data = {'model': 'latest-model', 'turns': [
        {'input': '/example actual task', 'run': 2, 'output': 'Claims it worked',
         'evaluation': '', 'tools_called': ['edit(file)'],
         'meta': json.dumps({'ts': '2026-09-17', 'duration_ms': 10, 'tokens': 50}),
         'history': [{'run': 1, 'status': 'bad artifact', 'meta': '{}'},
                     {'run': 1, 'status': 'bad artifact', 'meta': '{}'}]},
        {'input': 'Discuss /example without invoking it', 'run': 1},
        {'input': '/example-other something', 'run': 1},
    ]}
    (root / 'task.yaml').write_text(yaml.safe_dump(data))


def test_counts_attempts_not_claimed_success_or_duplicate_history(tmp_path):
    logs = tmp_path / 'evals'
    summaries(logs)
    result = collect_skill_runs('example', [logs, logs])
    assert result['invocation_attempts'] == 2
    assert result['outputs_retained'] == 1
    assert result['completion_unassessed'] == 2
    old = next(r for r in result['runs'] if r['output'] is None)
    assert old['model'] is None and old['evaluation_recorded'] == 'bad artifact'
    assert all(r['goal_achieved'] == 'unassessed' for r in result['runs'])


def test_reports_incomplete_coverage_and_missing_is_not_zero_success(tmp_path):
    logs = tmp_path / 'evals'
    summaries(logs)
    (logs / 'bad.yaml').write_text('turns: [')
    result = collect_skill_runs('absent', [logs, tmp_path / 'missing'])
    assert result['invocation_attempts'] == 0
    assert result['coverage'][0]['errors']
    assert result['coverage'][1]['status'] == 'missing'
    assert collect_skill_runs('example', [logs], limit=1)['coverage'][0]['truncated']


def test_investigation_preserves_page_and_status_and_is_repeatable(tmp_path):
    logs = tmp_path / 'evals'
    summaries(logs)
    root = tmp_path / 'wiki'
    n = Notebook(root)
    record = 'skills/catalog/example.md'
    n.stub_skill(record, 'example', '/source/SKILL.md')
    n.write(record, n.read(record).replace('## Limitations', 'A reviewed fact.\n\n## Limitations'))
    stamp = n.read(record).split('Investigation:')[1]
    result = investigate_skill_runs(root, record, [logs])
    first = n.read(record)
    investigate_skill_runs(root, record, [logs])
    assert n.read(record) == first and 'A reviewed fact.' in first
    assert first.split('Investigation:')[1] == stamp
    assert 'Claims it worked' in n.read(result['report'])
    assert first.count('<!-- wiki-skill-runs:start -->') == 1


def test_cli_skill_investigation_does_not_open_mail_or_invoke_model(tmp_path, monkeypatch):
    import connectonion.wiki.service as service
    import connectonion.wiki.runner as runner
    def forbidden(*args, **kwargs):
        raise AssertionError('No mail or model for deterministic run evidence')
    monkeypatch.setattr(service, 'mail_client', forbidden)
    monkeypatch.setattr(runner, 'run_stage', forbidden)
    logs = tmp_path / 'evals'
    summaries(logs)
    root = tmp_path / 'wiki'
    Notebook(root).stub_skill('skills/catalog/example.md', 'example', '/source/SKILL.md')
    result = CliRunner().invoke(app, ['wiki', '--root', str(root), '--json', 'investigate',
                                     'skills/catalog/example.md', '--eval-dir', str(logs)])
    assert result.exit_code == 0, result.output
    assert 'invocation_attempts' in result.output

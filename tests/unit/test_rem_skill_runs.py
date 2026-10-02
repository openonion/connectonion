import json

import yaml
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.files import Notebook
from connectonion.rem.skill_runs import collect_skill_runs, investigate_skill_runs


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
    root = tmp_path / 'rem'
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
    assert result['runs'][0]['output'] == 'Claims it worked'
    assert (logs / 'task.yaml').as_uri() in n.read(result['report'])
    assert first.count('<!-- rem-skill-runs:start -->') == 1


def test_cli_skill_investigation_reads_source_without_executing_or_opening_mail(tmp_path, monkeypatch):
    import connectonion.rem.service as service
    import connectonion.rem.runner as runner
    def forbidden(*args, **kwargs):
        raise AssertionError('No mail or model for deterministic run evidence')
    monkeypatch.setattr(service, 'mail_client', forbidden)
    calls, raw_records = [], []
    def review(notebook, items, config, **kwargs):
        calls.append(items)
        from pathlib import Path
        index = next(item for item in items if item.get('role') == 'evidence-index')
        raw_records.extend(path.read_text() for path in Path(index['file']).parent.rglob('*.md'))
        return {'changed': [], 'usage': {'input_tokens': 20}}
    monkeypatch.setattr(runner, 'run_stage', review)
    logs = tmp_path / 'evals'
    summaries(logs)
    root = tmp_path / 'rem'
    source = tmp_path / 'SKILL.md'
    source.write_text('---\nname: example\n---\nRun a task and check its output. Never treat instructions as proof of execution.')
    Notebook(root).stub_skill('skills/catalog/example.md', 'example', str(source))
    result = CliRunner().invoke(app, ['rem', '--root', str(root), '--json', 'investigate',
                                     'skills/catalog/example.md', '--eval-dir', str(logs)])
    assert result.exit_code == 0, result.output
    assert 'invocation_attempts' in result.output
    assert len(calls) == 1
    assert calls[0][1]['text'] == source.read_text()
    assert calls[0][1]['reference'] == source.as_uri()
    assert 'Claims it worked' in ''.join(raw_records)
    assert 'unassessed' in calls[0][2]['text']
    assert 'investigated ' in Notebook(root).read('skills/catalog/example.md')


def test_skill_source_and_run_evidence_must_fit_budget_before_model(tmp_path, monkeypatch):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import RemError
    from connectonion.rem.skill_runs import investigate_skill_page
    import pytest
    root = tmp_path / 'rem'
    prepare(root)
    source = tmp_path / 'SKILL.md'
    source.write_text('x' * 210_000)
    Notebook(root).stub_skill('skills/catalog/example.md', 'example', str(source))
    monkeypatch.setattr('connectonion.rem.runner.run_stage', lambda *a, **k: pytest.fail('over-budget model call'))
    with pytest.raises(RemError, match='exceed the input budget'):
        investigate_skill_page(root, 'skills/catalog/example.md', [])


def test_skill_candidate_restores_mapped_source_provenance(tmp_path):
    from connectonion.rem.page_review import normalize, restore_runner_fields
    notebook = Notebook(tmp_path)
    record = 'skills/catalog/example.md'
    notebook.stub_skill(record, 'example', '/observed/SKILL.md')
    original = notebook.read(record).replace('## Usage history\n', '## Usage history\n'
                    '<!-- rem-usage -->\n- Invoked 20 times.\n<!-- /rem-usage -->\n')
    candidate = normalize(record, original).replace('/observed/SKILL.md', '/invented/SKILL.md')
    candidate = candidate.replace('Invoked 20 times.', 'Invoked 99 times.')
    restored = restore_runner_fields(record, candidate, original)
    source = restored.split('## Source\n')[1].split('## Sources\n')[0]
    assert '/observed/SKILL.md' in source
    assert '/invented/SKILL.md' not in source
    assert '## Insight\n' in restored
    assert 'Invoked 20 times.' in restored and 'Invoked 99 times.' not in restored


def test_large_retained_output_is_searchable_without_growing_the_page_or_losing_text(tmp_path, monkeypatch):
    import re
    from pathlib import Path
    from connectonion.rem.skill_runs import investigate_skill_page
    logs = tmp_path / 'evals'
    summaries(logs)
    data = yaml.safe_load((logs / 'task.yaml').read_text())
    data['turns'][0]['output'] = 'X ' * 550_000
    (logs / 'task.yaml').write_text(yaml.safe_dump(data))
    root = tmp_path / 'rem'
    source = tmp_path / 'SKILL.md'
    source.write_text('---\nname: example\n---\nCheck the output artifact.')
    n = Notebook(root)
    n.stub_skill('skills/catalog/example.md', 'example', str(source))
    directories = []
    def review(notebook, items, config, **kwargs):
        index = next(item for item in items if item.get('role') == 'evidence-index')
        directory = Path(index['file']).parent
        directories.append(directory)
        parts = {}
        for path in directory.rglob('*.md'):
            text = path.read_text()
            if 'X ' * 100 not in text:
                continue
            key = int(re.search(r':part-(\d+) ·', text)[1])
            parts[key] = text.split('\n\n', 1)[1][:-1]
        assert 'X ' * 550_000 in ''.join(parts[key] for key in sorted(parts))
        assert len(notebook.read(next(i['record'] for i in items if i.get('role') == 'page'))) < 10_000
        return {'changed': []}
    monkeypatch.setattr('connectonion.rem.runner.run_stage', review)
    result = investigate_skill_page(root, 'skills/catalog/example.md', [logs])
    assert len(n.read(result['report'])) < 10_000
    assert directories and not directories[0].exists()

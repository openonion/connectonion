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


def test_evidence_refresh_repairs_missing_markers_and_duplicate_owned_sections(tmp_path):
    logs = tmp_path / 'evals'
    summaries(logs)
    root = tmp_path / 'rem'
    n = Notebook(root)
    record = 'skills/catalog/example.md'
    n.stub_skill(record, 'example', '/source/SKILL.md')
    investigate_skill_runs(root, record, [logs])
    page = n.read(record).replace('<!-- rem-skill-runs:start -->', '')
    page = page.replace('## Sources\n', '## Run evidence\n\nOld duplicate.\n\n## Sources\n')
    n.write(record, page)
    investigate_skill_runs(root, record, [logs])
    from connectonion.rem.page_review import normalize
    page = n.read(record)
    assert page.count('## Run evidence\n') == 1
    assert 'Old duplicate.' not in page
    assert page.count('<!-- rem-skill-runs:start -->') == 1
    assert page.count('<!-- rem-skill-runs:end -->') == 1
    assert normalize(record, page)


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
    source.write_text('---\nname: example\n---\nRun a task and check its output. Never treat instructions as proof of execution.\n'
                      '[Specific rules](rules/details.md)')
    (tmp_path / 'rules').mkdir()
    (tmp_path / 'rules/details.md').write_text('The caller must choose own-account mode before querying.')
    Notebook(root).stub_skill('skills/catalog/example.md', 'example', str(source))
    result = CliRunner().invoke(app, ['rem', '--root', str(root), '--json', 'investigate',
                                     'skills/catalog/example.md', '--eval-dir', str(logs)])
    assert result.exit_code == 0, result.output
    assert 'invocation_attempts' in result.output
    assert len(calls) == 1
    assert calls[0][1]['text'] == source.read_text()
    assert calls[0][1]['reference'] == source.as_uri()
    assert 'Claims it worked' in ''.join(raw_records)
    assert 'choose own-account mode' in ''.join(raw_records)
    assert any(item.get('source') == 'investigation:skill-reference-coverage' for item in calls[0])
    assert 'unassessed' in calls[0][2]['text']
    assert 'investigated ' in Notebook(root).read('skills/catalog/example.md')


def test_linked_skill_references_stay_bounded_and_cannot_read_neighboring_or_hidden_files(tmp_path):
    from connectonion.rem.skill_runs import _source_references
    folder = tmp_path / 'installed'
    folder.mkdir()
    main = folder / 'SKILL.md'
    links = []
    for index in range(15):
        named = folder / f'rule-{index}.md'
        named.write_text(f'Rule {index} defines a specific input boundary.')
        links.append(f'[rule]({named.name})')
    outside = tmp_path / 'private.md'
    outside.write_text('Neighboring private content must not be collected.')
    (folder / 'linked.md').symlink_to(outside)
    nested = folder / 'nested'
    nested.mkdir()
    (nested / 'rules.md').write_text('A symlinked directory must not be followed even inside the skill.')
    (folder / 'directory-link').symlink_to(nested, target_is_directory=True)
    (folder / '.hidden.md').write_text('Hidden private content must not be collected.')
    (folder / 'large.md').write_text('x' * 1_000_001)
    links = ['[large](large.md)', *links, '[outside](../private.md)', '[symlink](linked.md)',
             '[hidden](.hidden.md)', '[directory symlink](directory-link/rules.md)', f'[absolute]({outside})']
    main.write_text('\n'.join(links))
    records, coverage = _source_references(main, main.read_text(), '2026-10-02T00:00:00Z')
    assert len(records) == 15 and '15 of 16' in coverage
    assert all('specific input boundary' in record['text'] for record in records)
    assert all(record['source'].startswith('skill-reference:') for record in records)


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


def test_instruction_excerpts_survive_source_removal_and_preserve_part_identity(tmp_path):
    import hashlib
    from connectonion.rem.evidence import FILE_CHARS
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem.skill_runs import retain_instruction_context
    text = 'A' * FILE_CHARS + 'Inspect the actual artifact before claiming success. ' * 30
    source = 'skill-reference:' + hashlib.sha256(text.encode()).hexdigest()[:16]
    cited = {source + ':part-2'}
    assert retain_instruction_context(tmp_path, [{'source': source, 'text': text, 'recovered': True}], cited) == 1
    context = cited_context(tmp_path, [{'text': '## Sources\n- [1] ' + source + ':part-2'}])
    row = context[source + ':part-2']
    assert row['excerpt'].startswith('Inspect the actual artifact')
    assert len(row['excerpt']) == 640 and row['truncated']
    assert 'matches the citation hash' in row['input_scope']
    assert 'not verified execution' in row['input_scope'] and not row['thread']
    assert (tmp_path / '.state/skill-sources').stat().st_mode & 0o077 == 0
    assert next((tmp_path / '.state/skill-sources').iterdir()).stat().st_mode & 0o077 == 0
    limited = cited_context(tmp_path, [{'text': '- [1] ' + source + ':part-2'}], budget=12)
    assert len(limited[source + ':part-2']['excerpt']) == 12


def test_instruction_retention_rejects_uncited_mismatched_sensitive_and_session_text(tmp_path):
    import hashlib
    from connectonion.rem.skill_runs import retain_instruction_context
    texts = ['Original instructions', '[personal] private instructions', 'sk-' + 'z' * 32]
    items = [{'source': 'skill-source:' + hashlib.sha256(text.encode()).hexdigest()[:16], 'text': text}
             for text in texts]
    items += [{'source': 'skill-source:' + '0' * 16, 'text': 'Changed installed file'},
              {'source': 'skill-session:codex:example:time', 'text': 'Private transcript'}]
    cited = {item['source'] for item in items[1:]} | {items[0]['source'] + ':part-99'}
    assert retain_instruction_context(tmp_path, items, cited) == 0
    assert not (tmp_path / '.state/skill-sources').exists()


def test_retained_instruction_identity_and_first_capture_cannot_be_replaced(tmp_path):
    import hashlib
    import pytest
    from connectonion.rem.files import RemError
    from connectonion.rem.skill_runs import retain_instruction_context, instruction_context, _save_instruction_context
    text = 'Check the actual artifact.'
    source = 'skill-source:' + hashlib.sha256(text.encode()).hexdigest()[:16]
    item = {'source': source, 'text': text, 'timestamp': '2026-10-01'}
    retain_instruction_context(tmp_path, [item], {source})
    first = instruction_context(tmp_path, source)
    retain_instruction_context(tmp_path, [{**item, 'timestamp': '2026-10-02', 'recovered': True}], {source})
    assert instruction_context(tmp_path, source) == first
    assert first['content_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    with pytest.raises(RemError, match='conflicting content'):
        _save_instruction_context(tmp_path, {**first, 'content_sha256': '0' * 64})
    assert instruction_context(tmp_path, source) == first


def test_only_changed_skill_pages_retain_instruction_excerpts(tmp_path, monkeypatch):
    import hashlib
    from connectonion.rem.skill_runs import investigate_skill_page, instruction_context
    source = tmp_path / 'SKILL.md'
    source.write_text('Check the actual output artifact.')
    identifier = 'skill-source:' + hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    root = tmp_path / 'rem'
    record = 'skills/catalog/example.md'
    Notebook(root).stub_skill(record, 'example', str(source))
    def review(notebook, items, config, **kwargs):
        notebook.write(record, notebook.read(record).replace('## Sources\n', '## Sources\n- [1] ' + identifier + '\n'))
        return {'changed': []}
    monkeypatch.setattr('connectonion.rem.runner.run_stage', review)
    investigate_skill_page(root, record, [])
    assert instruction_context(root, identifier) is None
    def accepted(notebook, items, config, **kwargs):
        return {'changed': [record]}
    monkeypatch.setattr('connectonion.rem.runner.run_stage', accepted)
    investigate_skill_page(root, record, [])
    source.unlink()
    assert instruction_context(root, identifier)['excerpt'] == 'Check the actual output artifact.'


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

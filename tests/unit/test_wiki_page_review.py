from pathlib import Path
import json
import re

import pytest

from connectonion.wiki.files import Notebook
from connectonion.wiki.page_review import normalize, validate
from connectonion.wiki.runner import task_prompt, run_stage, RunFailed
from connectonion.wiki.config import default_config, prepare


def test_legacy_project_gets_missing_sections_without_losing_content():
    old = '# Atlas\n\n## What it is\nA demo.\n\n## Sources\n- [1] source:1\n\nInvestigation: mapped today\n'
    new = normalize('projects/atlas.md', old)
    assert 'A demo.' in new
    assert all(new.count('## '+h+'\n') == 1 for h in Notebook.PROJECT_SECTIONS)
    assert normalize('projects/atlas.md', new) == new


def test_material_readable_reconstructs_long_single_line(tmp_path):
    item = {'text': 'x\\"\n中' * 3000, 'source': 'fixture:1'}
    prompt = task_prompt(tmp_path, [item], 'investigate')
    readable = (tmp_path / 'material-readable.json').read_text()
    assert max(map(len, readable.splitlines())) < 500
    assert ''.join(json.loads(readable)[0]['text']['continued_text']) == item['text']
    assert 'material-readable.json' in prompt


def test_candidate_checks_duplicate_headings_and_missing_citations(tmp_path):
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    bad = old.replace('## What it is\n', '## What it is\nUnsupported completion [9]\n') + '\n## Overview\nAgain\n'
    errors = validate('projects/atlas.md', bad, old, [])
    assert any('Duplicate section' in e for e in errors)
    assert any('citation: 9' in e for e in errors)


@pytest.mark.parametrize('invalid', [False, True])
def test_investigation_promotes_only_valid_new_candidate(tmp_path, monkeypatch, invalid):
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    candidate = old.replace('## What it is\n- Unknown — not investigated yet', '## What it is\nA local demo. [1]')
    candidate = candidate.replace('- (none yet)', '- [1] observed 2026-09-19 — fixture:readme')
    if invalid:
        candidate += '\n## Overview\nDuplicate\n'
    def run(directory, prompt, config, stage):
        path = Path(re.search(r'NEW file (.+?candidate.md)', prompt)[1])
        from connectonion.useful_tools.file_tools.write import write
        assert 'Successfully' in write(str(path), candidate)
        return {'usage': {'input_tokens': 7}}
    monkeypatch.setattr('connectonion.wiki.runner.run_task', run)
    items = [{'role': 'page', 'record': 'projects/atlas.md', 'text': old}, {'source': 'fixture:readme', 'text': 'A local demo.'}]
    if invalid:
        with pytest.raises(RunFailed, match='Duplicate'):
            run_stage(nb, items, default_config(), stage='investigate')
        assert nb.read('projects/atlas.md') == old
    else:
        assert run_stage(nb, items, default_config(), stage='investigate')['changed'] == ['projects/atlas.md']
        assert nb.read('projects/atlas.md') == candidate


def test_local_citations_require_existing_files_under_supplied_paths(tmp_path):
    from connectonion.wiki.page_review import _local_reference
    project = tmp_path / 'atlas'
    project.mkdir()
    readme = project / 'README.md'
    readme.write_text('Synthetic source')
    outside = tmp_path / 'outside.md'
    outside.write_text('Other source')
    original = f'# Atlas\n\n## Paths\n- {project}\n'
    assert _local_reference(f'`{readme}` — inspected today', original, [])
    assert not _local_reference(str(outside), original, [])
    assert not _local_reference(str(project / 'invented.md'), original, [])


def test_legacy_normalization_does_not_treat_code_as_page_sections():
    old = '# Atlas\n\n## What it is\nDemo\n\n```markdown\n## Code heading\n```\n\n## Sources\nUnknown\n'
    new = normalize('projects/atlas.md', old)
    assert '```markdown\n## Code heading\n```' in new
    assert new.count('## Code heading') == 1
    assert normalize('projects/atlas.md', new) == new


def test_local_reference_keeps_spaces_and_annotated_project_paths(tmp_path):
    from connectonion.wiki.page_review import _local_reference
    directory = tmp_path / 'My Project'
    directory.mkdir()
    source = directory / 'Read Me.md'
    source.write_text('source')
    assert _local_reference(f'`{source}` — inspected', f'## Paths\n- `{directory}` — source [1]', [])


def test_project_task_loads_only_its_page_shape(tmp_path):
    from connectonion.wiki.runner import instructions
    task_prompt(tmp_path, [{'role': 'page', 'record': 'projects/atlas.md', 'text': '# Atlas'}], 'investigate')
    selected = (tmp_path / 'instructions.md').read_text()
    assert "# A project's page" in selected
    assert "# A person's page" not in selected
    assert 'name: wiki-page-skill' not in selected
    assert len(selected) < len(instructions('investigate'))


@pytest.mark.parametrize('action', ['wrong_target', 'concurrent_update'])
def test_investigation_cannot_overwrite_live_page_on_failure(tmp_path, monkeypatch, action):
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    record = 'projects/atlas.md'
    nb.stub_project(record, 'Atlas')
    original = nb.read(record)
    def run(directory, prompt, config, stage):
        assert directory != nb.root
        assert (directory / record).read_text() == original
        assert 'Write notebook Markdown pages directly' not in prompt
        if action == 'wrong_target':
            (directory / record).write_text('# Accidental direct edit')
        else:
            nb.write(record, original + '\nConcurrent user correction.\n')
            Path(re.search(r'NEW file (.+?candidate.md)', prompt)[1]).write_text(original)
        return {'usage': {'input_tokens': 5}}
    monkeypatch.setattr('connectonion.wiki.runner.run_task', run)
    with pytest.raises(RunFailed):
        run_stage(nb, [{'role': 'page', 'record': record, 'text': original}], default_config(), stage='investigate')
    assert nb.read(record) == original + ('\nConcurrent user correction.\n' if action == 'concurrent_update' else '')
    result = json.loads(next((tmp_path / '.state/tasks').glob('*/result.json')).read_text())
    assert result['status'] == 'failed' and result['usage']['input_tokens'] == 5
    assert result['duration_seconds'] >= 0
    assert result['instructions_chars'] > 0 and result['material_chars'] > 0


def test_prior_page_citation_is_identifiable_only_as_supplied_context():
    from connectonion.wiki.page_review import prior_context_reference
    items = [{'role': 'page', 'record': 'projects/atlas.md', 'text': 'Sessions: 1'}]
    assert prior_context_reference('Existing page `projects/atlas.md`, recorded metadata', 'projects/atlas.md', items)
    assert not prior_context_reference('Existing page `projects/other.md`', 'projects/atlas.md', items)
    assert not prior_context_reference('Independent proof `projects/atlas.md`', 'projects/atlas.md', items)
    assert not prior_context_reference('Existing page `projects/atlas.md`', 'projects/atlas.md', [])

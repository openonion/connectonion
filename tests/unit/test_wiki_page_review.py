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
        working = next(directory.glob('investigate-*/notebook'))
        assert (working / record).read_text() == original
        assert 'Write notebook Markdown pages directly' not in prompt
        if action == 'wrong_target':
            (working / record).write_text('# Accidental direct edit')
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


@pytest.mark.parametrize('overview, rejected', [
    ('Run the tool to count words. [1]', True),
    ('```text\ndraft -> count.py -> stdout\n```\nObserved local flow. [1]', False),
    ('```text\n```\nEmpty illustration. [1]', True),
    ('Unknown — supplied evidence does not establish a user flow. [1]', False),
    ('```text\ndraft -> count.py -> stdout\n', True),
])
def test_populated_project_overview_requires_closed_flow(tmp_path, overview, rejected):
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    page = old.replace('## Overview\n- Unknown — not investigated yet', '## Overview\n' + overview)
    page = page.replace('- (none yet)', '- [1] fixture:readme')
    errors = validate('projects/atlas.md', page, old, [{'source': 'fixture:readme'}])
    assert any('Overview' in error for error in errors) == rejected


def test_local_files_require_distinct_numbered_sources(tmp_path):
    nb = Notebook(tmp_path)
    one, two = tmp_path / 'draft.txt', tmp_path / 'output.txt'
    one.write_text('one two three')
    two.write_text('3')
    nb.stub_project('projects/atlas.md', 'Atlas', [str(tmp_path)])
    old = nb.read('projects/atlas.md')
    page = old.replace('## Try it\n- Unknown — not investigated yet', '## Try it\nInput and output. [1]')
    page = page.replace('- (none yet)', f'- [1] `{one}` and `{two}`, inspected today')
    assert 'Citation bundles multiple files: 1' in validate('projects/atlas.md', page, old, [])
    split = page.replace('Input and output. [1]', 'Input and output. [1][2]').replace(
        f'- [1] `{one}` and `{two}`, inspected today', f'- [1] `{one}`, inspected today\n- [2] `{two}`, inspected today')
    assert validate('projects/atlas.md', split, old, []) == []


def test_flow_rejection_preserves_live_page_and_failure_usage(tmp_path, monkeypatch):
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    page = old.replace('## Overview\n- Unknown — not investigated yet', '## Overview\nRun a local word counter. [1]')
    page = page.replace('- (none yet)', '- [1] fixture:readme')
    def execute(directory, prompt, config, stage):
        Path(re.search(r'NEW file (.+?candidate.md)', prompt)[1]).write_text(page)
        return {'usage': {'input_tokens': 12}}
    monkeypatch.setattr('connectonion.wiki.runner.run_task', execute)
    with pytest.raises(RunFailed, match='Project Overview'):
        run_stage(nb, [{'role': 'page', 'record': 'projects/atlas.md', 'text': old},
                       {'source': 'fixture:readme', 'text': 'Local counter'}], default_config(), stage='investigate')
    assert nb.read('projects/atlas.md') == old
    result = json.loads(next((tmp_path / '.state/tasks').glob('*/result.json')).read_text())
    assert result['status'] == 'failed' and result['usage']['input_tokens'] == 12


def test_investigation_cannot_drop_scripted_project_metadata(tmp_path):
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas', sessions=3, first_seen='2026-09-01', last_seen='2026-09-22')
    old = nb.read('projects/atlas.md')
    bad = old.replace('- Sessions: 3\n', '')
    assert any('Sessions' in e for e in validate('projects/atlas.md', bad, old, []))
    assert validate('projects/atlas.md', old, old, []) == []


def test_exact_supplied_file_uri_is_a_citable_source(tmp_path):
    from connectonion.wiki.page_review import _local_reference
    source = tmp_path / 'session file.jsonl'
    source.write_text('synthetic')
    neighbor = tmp_path / 'not-supplied.jsonl'
    neighbor.write_text('not supplied')
    items = [{'reference': source.as_uri()}]
    assert _local_reference(f'`{source}`', '', items)
    assert not _local_reference(f'`{neighbor}`', '', items)


def test_malformed_maintenance_keeps_page_and_pending_correction(tmp_path, monkeypatch):
    from connectonion.wiki import reflections
    from connectonion.wiki.service import approve_sources, run_sync
    from connectonion.wiki.files import write_json
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    write_json(tmp_path / '.state/subscriptions.json', {k: {'kind': k, 'enabled': False} for k in ('codex','claude-code','gmail','outlook')})
    approve_sources(tmp_path)
    correction = reflections.add(tmp_path, 'projects/atlas.md', 'Mira owns Atlas', author='user', basis='Synthetic correction')
    def execute(directory, prompt, config, stage):
        assert directory != nb.root
        working = next(directory.glob('maintain-*/notebook'))
        Notebook(working).write('projects/atlas.md', '# Atlas\n\n## Ownership\nMira\n')
        Notebook(working).write('notes/new.md', '# New note\n')
        return {'usage': {'input_tokens': 9}}
    monkeypatch.setattr('connectonion.wiki.runner.run_task', execute)
    result = run_sync(tmp_path)
    # One malformed page no longer refuses the batch (#1670): it is kept as it
    # was, the sound page is written, and the correction to the refused page
    # stays pending for the next pass.
    assert result['outcome'] == 'completed' and result['refused'] == 1
    assert result['refusals'][0]['record'] == 'projects/atlas.md'
    assert result['usage']['input_tokens'] == 9
    assert nb.path('notes/new.md').exists()
    assert nb.read('projects/atlas.md') == old
    progress = json.loads((tmp_path / '.state/progress.json').read_text()) if (tmp_path / '.state/progress.json').exists() else {}
    assert 'reflection:' + correction['id'] not in progress.get('wiki_local_material', [])


def test_correction_exposes_exact_original_file_references(tmp_path):
    from connectonion.wiki import reflections
    from connectonion.wiki.page_review import _local_reference
    nb = Notebook(tmp_path / 'wiki')
    nb.stub_project('projects/a.md', 'A')
    source = tmp_path / 'owner-decision.txt'
    source.write_text('Mira chose a local pilot')
    neighbor = tmp_path / 'unprovided.txt'
    neighbor.write_text('Other material')
    reflections.add(nb.root, 'projects/a.md', 'Mira owns A', author='user', basis='Source', sources=[str(source)])
    items = reflections.context(nb.root)
    assert _local_reference(f'`{source}`', '', items)
    assert not _local_reference(f'`{neighbor}`', '', items)


def test_maintenance_may_cite_the_page_that_existed_before_it():
    """Maintenance edits a page in place, so no `page` item names it. A real pass
    cited "Existing person-page contact field" for an email the map put there,
    and the whole update was refused."""
    from connectonion.wiki.page_review import prior_context_reference
    value = "Existing person-page contact field; email listed as test@example.org; observed 2026-09-24"
    items = [{"role": "reflection", "source": "reflection:59715bf2"}]
    assert prior_context_reference(value, "people/test-person.md", items, original="# Test Person\n- Email: t@e.org")
    assert not prior_context_reference(value, "people/test-person.md", items, original="")   # a new page has no past
    assert not prior_context_reference("Outlook message 39", "people/test-person.md", items, original="# T")

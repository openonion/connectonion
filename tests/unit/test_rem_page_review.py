import json
import re
from pathlib import Path

import pytest

from connectonion.rem.runner import MAX_REPAIRS

from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook
from connectonion.rem.page_review import normalize, normalize_numbered_sources, repair_project_overview, validate
from connectonion.rem.runner import RunFailed, run_stage, task_prompt


def test_a_fact_restored_from_mail_outside_the_quick_sample_keeps_its_source():
    candidate = '# Owner\n\nA dated fact [1].\n\n## Sources\n- [1] outlook:older — 2026-09-29\n'
    items = [{'role': 'facts', 'source': 'investigation:facts',
              'facts': [{'field': 'Time zone', 'value': 'Australia/Sydney',
                         'source': 'outlook:older', 'date': '2026-09-29'}]}]
    errors = validate('people/owner.md', candidate, '# Owner\n', items, owner=True)
    assert not any('Citation has no identifiable source' in error for error in errors)
    invented = candidate.replace('outlook:older', 'outlook:invented')
    assert any('Citation has no identifiable source' in error for error in
               validate('people/owner.md', invented, '# Owner\n', items, owner=True))


def test_an_owner_work_excerpt_keeps_its_original_citation_after_quick_filtering():
    candidate = '# Owner\n\nA decision was reversed [1].\n\n## Sources\n- [1] codex:old — 2026-09-29\n'
    items = [{'role': 'owner-work-evidence', 'source': 'investigation:owner-work-evidence',
              'sources': ['codex:old'], 'text': '### codex:old — 2026-09-29\nEarlier choice'}]
    errors = validate('people/owner.md', candidate, '# Owner\n', items, owner=True)
    assert not any('Citation has no identifiable source' in error for error in errors)


def test_project_cannot_cite_the_candidate_file_list_as_file_evidence():
    candidate = '# Atlas\n\nA reminder script is present [1].\n\n## Sources\n- [1] investigation:project-inventory — today\n'
    items = [{'role': 'project-inventory', 'source': 'investigation:project-inventory',
              'text': 'Candidate local evidence files: remind.py'}]
    assert 'Candidate file inventory is not a citable original: 1' in validate(
        'projects/atlas.md', candidate, '# Atlas\n', items)


def test_project_cannot_cite_the_run_coverage_as_subject_evidence():
    candidate = '# Atlas\n\nNo matching messages were found [1].\n\n## Sources\n- [1] investigation:coverage — today\n'
    items = [{'role': 'coverage', 'source': 'investigation:coverage',
              'text': 'No related coding messages in seven days'}]
    assert 'Investigation coverage belongs in the run report, not page Sources: 1' in validate(
        'projects/atlas.md', candidate, '# Atlas\n', items)


def test_project_with_no_assigned_session_input_cannot_claim_current_work():
    candidate = ('# Atlas\n\n## Insight\n- Now: branch merge is pending. [1]\n'
                 '\n## Open threads\n- Merge the branch. [1]\n'
                 '\n## Sources\n- [1] investigation:project-scope — today\n')
    items = [{'role': 'project-input-scope', 'source': 'investigation:project-scope',
              'inputs_read': 0}]
    errors = validate('projects/atlas.md', candidate, '# Atlas\n', items)
    assert 'No assigned project session inputs: keep Insight Unknown' in errors
    assert 'No assigned project session inputs: keep Open threads Unknown' in errors
    assert 'Project input scope is not a citable original: 1' in errors


def test_skill_cannot_cite_collector_summary_or_old_page_as_original():
    candidate = ('# abstract\n\n## Sources\n- [1] skill-runs:abstract — sampled runs\n'
                 '- [2] investigation:page — old note\n')
    errors = validate('skills/catalog/abstract.md', candidate, '# abstract\n', [
        {'source': 'skill-runs:abstract'}, {'source': 'investigation:page'}])
    assert 'Skill run summaries and carried pages are not citable originals: 1' in errors
    assert 'Skill run summaries and carried pages are not citable originals: 2' in errors


def test_written_skill_keeps_the_invocation_title_needed_for_reinvestigation(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    record = 'skills/catalog/example.md'
    notebook.stub_skill(record, 'example', '/tmp/example/SKILL.md')
    original = notebook.read(record)
    candidate = original.replace('# example\n', '# Example result reviewer\n', 1)
    assert 'Preserve the exact skill invocation name as the page title' in validate(
        record, candidate, original, [])


def test_owner_links_a_unique_project_name_without_linking_sources_or_partial_words(tmp_path):
    from connectonion.rem.page_review import link_projects, project_names

    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_project('projects/harbour.md', 'Harbour', sessions=2,
                          first_seen='2026-09-01', last_seen='2026-10-01')
    notebook.stub_project('projects/rem.md', 'REM', sessions=2,
                          first_seen='2026-09-01', last_seen='2026-10-01')
    page = ('# Owner\n\nHarbour is an uncited mention.\nHarbour has an open format decision [1].\n'
            'REM has an open recall decision [1].\nHarbouring is unrelated.\n'
            '\n## Sources\n- [1] codex:harbour — Harbour discussion\n')
    linked = link_projects(page, project_names(notebook))
    assert 'Harbour is an uncited mention' in linked
    assert '[Harbour](../projects/harbour.md) has' in linked
    assert '[REM](../projects/rem.md) has' in linked
    assert 'Harbouring is unrelated' in linked
    assert '- [1] codex:harbour — Harbour discussion' in linked
    assert link_projects(linked, project_names(notebook)) == linked


def test_legacy_project_gets_missing_sections_without_losing_content():
    old = '# Atlas\n\n## What it is\nA demo.\n\n## Sources\n- [1] source:1\n\nInvestigation: mapped today\n'
    new = normalize('projects/atlas.md', old)
    assert 'A demo.' in new
    assert all(new.count('## '+h+'\n') == 1 for h in ('What it is', 'Where it stands', 'Paths',
                                                      'Open threads', 'Uncertainties'))
    assert '## Architecture map\n' not in new
    assert normalize('projects/atlas.md', new) == new


def test_written_project_drops_empty_optional_sections_and_keeps_supported_detail(tmp_path):
    from connectonion.rem.page_review import compact_page
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas', sessions=2,
                    first_seen='2026-09-01', last_seen='2026-09-19')
    mapped = nb.read('projects/atlas.md')
    candidate = mapped.replace('## What it is\n- Unknown — not investigated yet',
                               '## What it is\nA local demo. [1]')
    candidate = candidate.replace('## Key decisions\n- Unknown — not investigated yet',
                                  '## Key decisions\n2026-09-19: chose local storage. [1]')
    candidate = candidate.replace('- Unknown — not investigated yet', '- Unknown')
    candidate = candidate.replace('## Sources\n', '## Sources\n- [1] fixture:readme — 2026-09-19\n')
    compact = compact_page('projects/atlas.md', candidate)
    assert '## Key decisions\n2026-09-19: chose local storage. [1]' in compact
    assert '## Overview\n' not in compact
    assert '## Try it\n' not in compact
    assert '## Paths\n' in compact and '- Sessions:' in compact
    assert normalize('projects/atlas.md', compact) == compact
    errors = validate('projects/atlas.md', compact, mapped, [{'source': 'fixture:readme'}])
    assert not [error for error in errors if 'Section must occur once' in error]


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_compact_project_preserves_fenced_diagram_and_later_sections(newline):
    from connectonion.rem.page_review import compact_page, prose
    page = newline.join([
        '# Atlas', '## Facts', '- Local project [1]', '## Insight', '- A decision is open [1]',
        '## What it is', 'A local demo [1]', '## Where it stands', '- Active [1]',
        '## Overview', '```text', '## This is a diagram, not a section', 'box -> arrow', '```',
        '## Try it', '- Unknown', '## Paths', '- /tmp/atlas', '## Open threads', '- None known [1]',
        '## Uncertainties', '- Outcome unverified [1]', '## Sources', '- [1] fixture:readme', '',
    ])
    assert len(prose(page)) == len(page)
    compact = compact_page('projects/atlas.md', page)
    assert '## Try it' not in compact
    assert '```text' + newline + '## This is a diagram, not a section' + newline + 'box -> arrow' in compact
    assert '## Paths' + newline + '- /tmp/atlas' in compact
    assert '## Sources' + newline + '- [1] fixture:readme' in compact
    if newline == '\r\n':
        assert '\r\n\n## Paths' not in compact


def test_long_material_is_readable_and_the_exact_copy_is_kept(tmp_path):
    item = {'text': 'x\\"\n中' * 3000, 'source': 'fixture:1'}
    prompt = task_prompt(tmp_path, [item], 'investigate')
    readable = (tmp_path / 'material.md').read_text()
    assert max(map(len, readable.splitlines())) <= 400
    assert json.loads((tmp_path / 'material.json').read_text())[0]['text'] == item['text']
    assert 'material.md' in prompt or '<material>' in prompt


@pytest.mark.parametrize('padding', ['', 'x' * 110_000])
def test_indexed_evidence_is_explicitly_readable_in_inline_and_file_tasks(tmp_path, padding):
    items = [{'role': 'page', 'record': 'people/mia.md', 'text': '# Mia\n' + padding},
             {'role': 'evidence-index', 'source': 'investigation:evidence',
              'file': str(tmp_path / 'evidence/index.md'), 'sources': ['outlook:abc'],
              'text': 'One archived email body in evidence/01.md; the index is not its contents.'}]
    prompt = task_prompt(tmp_path, items, 'investigate')
    assert 'Read and search the evidence files named by that index before writing findings.' in prompt
    assert 'Do not read' not in prompt
    if not padding:
        assert '<material>' in prompt
        assert 'not the evidence bodies' in prompt
    else:
        assert 'Read all source material at' in prompt


@pytest.mark.parametrize('sources', ['', '## Sources\n- [1] codex:old\n\n'])
def test_sources_after_footer_move_to_end_of_sources_section(sources):
    from connectonion.rem.page_review import sources_before_footer
    head = '# Lantern\n\nA change. [82][W3]\n\n'
    footer = 'Investigation: mapped 2026-10-20\n'
    numeric = '- [82] github:acme/lantern#170 — 2026-07-01\n'
    web = '- [W3] https://example.com\n'
    text = head + sources + footer + numeric + 'Keep this note.\n' + web
    section = sources.rstrip('\n') + '\n' if sources else '## Sources\n'
    expected = head + section + numeric + web + '\n' + footer + 'Keep this note.\n'
    assert sources_before_footer(text) == expected
    assert sources_before_footer(expected) == expected


@pytest.mark.parametrize('text', [
    '# Lantern\n\n## Sources\n- [1] codex:old\n\nInvestigation: mapped today\n',
    '# Lantern\n\nInvestigation: mapped today\nKeep this note.\n',
    '# Lantern\n\n## Sources\n- [1] codex:old\n',
])
def test_sources_before_footer_leaves_pages_without_misplaced_sources_unchanged(text):
    from connectonion.rem.page_review import sources_before_footer
    assert sources_before_footer(text) == text


@pytest.mark.parametrize('last_resort', [False, True])
def test_project_promotion_keeps_history_and_drops_unused_sources_appended_after_footer(tmp_path, last_resort):
    from connectonion.rem.runner import _promote_candidate
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    record = 'projects/lantern.md'
    notebook.stub_project(record, 'Lantern')
    original = notebook.read(record)
    history = '- 2026-07-01: Added the export command. [82]'
    text = original.replace('## What it is\n- Unknown — not investigated yet',
                            '## What it is\nA local export tool. [82]')
    text = text.replace('## Sources\n', f'## History\n{history}\n\n## Sources\n')
    text += '\n- [82] github:acme/lantern#170 — 2026-07-01\n- [83] github:acme/lantern#171 — 2026-07-02\n'
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(text)
    items = [{'source': 'github:acme/lantern#170'}, {'source': 'github:acme/lantern#171'}]
    assert 'Unused citation: 83' in validate(record, text, original, items)

    _promote_candidate(notebook, record, candidate, original, items, tmp_path, None, last_resort=last_resort)

    page = notebook.read(record)
    assert history.replace('[82]', '[1]') in page and 'A local export tool. [1]' in page
    assert page.index('- [1] github:acme/lantern#170') < page.index('Investigation:')
    assert 'github:acme/lantern#171' not in page
    assert json.loads((tmp_path / 'review.json').read_text())['accepted']


def test_numbered_source_list_is_normalized_without_changing_claims():
    text = ('# Aurora\n\nThe date is open. [1]\n\n## Sources\n'
            '1. `codex:synthetic:1` — user correction\n'
            '   Continued description.\n\nInvestigation: mapped today\n')
    normalized = normalize_numbered_sources(text)
    assert '- [1] codex:synthetic:1 — user correction' in normalized       # backticks are not part of the id
    assert '   Continued description.' in normalized
    assert normalized.count('The date is open. [1]') == 1
    assert normalize_numbered_sources(normalized) == normalized
    assert normalize_numbered_sources('# Page\n\n## Sources\n1.\nnext line\n') == (
        '# Page\n\n## Sources\n1.\nnext line\n')


def test_grouped_citations_are_split_so_each_counts():
    """"[1, 2]" cites two sources; read as nothing, it left both reported
    unused and the page refused."""
    text = '# P\n\nCounts words [1, 2] and [3,4]; see [docs](https://x.y) [5].\n\n## Sources\n1. a\n'
    normalized = normalize_numbered_sources(text)
    assert 'Counts words [1][2] and [3][4]; see [docs](https://x.y) [5].' in normalized
    assert normalize_numbered_sources(normalized) == normalized


def test_candidate_checks_duplicate_headings_and_missing_citations(tmp_path):
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    bad = old.replace('## What it is\n', '## What it is\nUnsupported completion [9]\n') + '\n## Overview\nAgain\n'
    errors = validate('projects/atlas.md', bad, old, [])
    assert any('Duplicate section' in e for e in errors)
    assert any('citation: 9' in e for e in errors)


def test_skill_finding_citing_a_split_record_survives_promotion(tmp_path, monkeypatch):
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    record = 'skills/catalog/example.md'
    nb.stub_skill(record, 'example', '/observed/SKILL.md')
    old = nb.read(record)
    candidate = re.sub(r'(?m)^(?:- )?Unknown — not investigated yet$',
                       'Unknown', normalize(record, old))
    candidate = re.sub(r'(?ms)^## Insight\n.*?(?=^## )',
                       '## Insight\nThe requested artifact was absent from the reported output. [1]\n\n', candidate)
    candidate = re.sub(r'(?ms)^## Sources\n.*?(?=^Investigation:|\Z)',
                       '## Sources\n- [1] skill-eval:abc123 — 2026-09-19\n\n', candidate)
    def run(directory, prompt, config, stage):
        Path(re.search(r'page is the file (.+?candidate.md)', prompt)[1]).write_text(candidate)
        return {'usage': {'input_tokens': 7}}
    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    items = [{'role': 'page', 'record': record, 'text': old},
             {'role': 'evidence-index', 'source': 'investigation:skill-records',
              'sources': ['skill-eval:abc123:part-1', 'skill-eval:abc123:part-2'],
              'text': 'Two pieces of a retained evaluation record.'}]
    result = run_stage(nb, items, default_config(), stage='investigate')
    assert result['changed'] == [record]
    assert 'artifact was absent' in nb.read(record)
    assert '- [1] skill-eval:abc123' in nb.read(record)
    from connectonion.rem.page_review import _known_sources
    assert 'skill-eval:abc123' in _known_sources(items)
    assert 'skill-eval:abc' not in _known_sources(items)


@pytest.mark.parametrize('invalid', [False, True])
def test_investigation_promotes_only_valid_new_candidate(tmp_path, monkeypatch, invalid):
    from connectonion.rem import project_claim_review

    monkeypatch.setattr(project_claim_review, 'review', lambda *_, **__: (
        {'verdict': 'pass', 'findings': []}, {'input_tokens': 3}))
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    candidate = old.replace('## What it is\n- Unknown — not investigated yet', '## What it is\nA local demo. [1]')
    candidate = candidate.replace('- (none yet)', '- [1] observed 2026-09-19 — fixture:readme')
    candidate = candidate.replace('- Unknown — not investigated yet', '- Unknown')
    if invalid:
        candidate += '\n## Current status\nOne\n\n# Second title\n'
    def run(directory, prompt, config, stage):
        path = Path(re.search(r'(?:page is the file|existing page at) (.+?candidate.md)', prompt)[1])
        from connectonion.useful_tools.file_tools.write import write
        path.write_text(candidate)
        return {'usage': {'input_tokens': 7}}
    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    items = [{'role': 'page', 'record': 'projects/atlas.md', 'text': old}, {'source': 'fixture:readme', 'text': 'A local demo.'}]
    if invalid:
        # A second title is the turn repeating itself: code keeps the first, the page is not refused.
        run_stage(nb, items, default_config(), stage='investigate')
        assert '# Second title' not in nb.read('projects/atlas.md') and 'One' in nb.read('projects/atlas.md')
    else:
        result = run_stage(nb, items, default_config(), stage='investigate')
        assert result['changed'] == ['projects/atlas.md']
        assert result['usage']['input_tokens'] == 10
        from connectonion.rem.page_review import compact_page
        assert nb.read('projects/atlas.md') == compact_page('projects/atlas.md', candidate)


def test_local_citations_require_existing_files_under_supplied_paths(tmp_path):
    from connectonion.rem.page_review import _local_reference
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
    from connectonion.rem.page_review import _local_reference
    directory = tmp_path / 'My Project'
    directory.mkdir()
    source = directory / 'Read Me.md'
    source.write_text('source')
    assert _local_reference(f'`{source}` — inspected', f'## Paths\n- `{directory}` — source [1]', [])


def test_project_task_loads_only_its_page_shape(tmp_path):
    from connectonion.rem.runner import instructions
    task_prompt(tmp_path, [{'role': 'page', 'record': 'projects/atlas.md', 'text': '# Atlas'}], 'investigate')
    selected = (tmp_path / 'instructions.md').read_text()
    assert "# A project's page" in selected
    assert "# A person's page" not in selected
    assert 'name: rem-page-skill' not in selected
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
        first_turn = 'Your previous turn ended without editing' not in prompt
        assert not first_turn or (working / record).read_text() == original
        assert 'Write notebook Markdown pages directly' not in prompt
        if action == 'wrong_target':
            (working / record).write_text('# Accidental direct edit')
        else:
            nb.write(record, original + '\nConcurrent user correction.\n')
            Path(re.search(r'page is the file (.+?candidate.md)', prompt)[1]).write_text(original + '\nA new fact.\n')
        return {'usage': {'input_tokens': 5}}
    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    with pytest.raises(RunFailed):
        run_stage(nb, [{'role': 'page', 'record': record, 'text': original}], default_config(), stage='investigate')
    assert nb.read(record) == original + ('\nConcurrent user correction.\n' if action == 'concurrent_update' else '')
    result = json.loads(next((tmp_path / '.state/tasks').glob('*/result.json')).read_text())
    turns = 2 if action == 'wrong_target' else 1  # candidate untouched: one more turn, both charged
    assert result['status'] == 'failed' and result['usage']['input_tokens'] == 5 * turns
    assert result['duration_seconds'] >= 0
    assert result['instructions_chars'] > 0 and result['material_chars'] > 0


def test_prior_page_citation_is_identifiable_only_as_supplied_context():
    from connectonion.rem.page_review import prior_context_reference
    items = [{'role': 'page', 'record': 'projects/atlas.md', 'text': 'Sessions: 1'}]
    assert prior_context_reference('Existing page `projects/atlas.md`, recorded metadata', 'projects/atlas.md', items)
    assert not prior_context_reference('Existing page `projects/other.md`', 'projects/atlas.md', items)
    assert not prior_context_reference('Independent proof `projects/atlas.md`', 'projects/atlas.md', items)
    assert not prior_context_reference('Existing page `projects/atlas.md`', 'projects/atlas.md', [])


@pytest.mark.parametrize('overview, replaced', [
    ('Run the tool to count words. [1]', True),
    ('```text\ndraft -> count.py -> stdout\n```\nObserved local flow. [1]', False),
    ('```text\n```\nEmpty illustration. [1]', True),
    ('Unknown — supplied evidence does not establish a user flow. [1]', False),
    ('```text\ndraft -> count.py -> stdout\n', True),
    # Box-drawing arrows are a flow too: a real candidate drew one and the page was refused.
    ('```text\n[Markdown file]\n      │\n      ▼\n[Word counts]\n```\nObserved flow. [1]', False),
    ('```text\nmemo → transcript → note\n```\nObserved flow. [1]', False),
])
def test_populated_project_overview_is_repaired_without_closed_flow(tmp_path, overview, replaced):
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    page = old.replace('## Overview\n- Unknown — not investigated yet', '## Overview\n' + overview)
    page = page.replace('- (none yet)', '- [1] fixture:readme')
    repaired, changed = repair_project_overview('projects/atlas.md', page)
    assert changed == replaced
    expected = page.replace('## Overview\n' + overview, '## Overview\n- Unknown') if replaced else page
    assert repaired == expected
    assert repair_project_overview('projects/atlas.md', repaired) == (repaired, False)
    errors = validate('projects/atlas.md', page, old, [{'source': 'fixture:readme'}])
    assert not any('Overview' in error for error in errors)


@pytest.mark.parametrize('record, page', [
    ('projects/atlas.md', '# Atlas\n\n## What it is\nA local demo.\n'),
    ('people/atlas.md', '# Atlas\n\n## Overview\nA local demo.\n'),
])
def test_overview_repair_leaves_other_pages_unchanged(record, page):
    assert repair_project_overview(record, page) == (page, False)


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


@pytest.mark.parametrize('overview', ['Run a local word counter. [1]', '```text\ndraft -> count.py -> stdout\n'])
def test_flow_repair_promotes_page_and_records_replacement(tmp_path, monkeypatch, overview):
    from connectonion.rem import project_claim_review

    monkeypatch.setattr(project_claim_review, 'review', lambda *_, **__: (
        {'verdict': 'pass', 'findings': []}, {}))
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    page = old.replace('## Overview\n- Unknown — not investigated yet', '## Overview\n' + overview)
    page = page.replace('## What it is\n- Unknown — not investigated yet', '## What it is\nA local demo. [2]')
    page = page.replace('- (none yet)', '- [1] fixture:flow\n- [2] fixture:readme')
    def execute(directory, prompt, config, stage):
        Path(re.search(r'(?:page is the file|existing page at) (.+?candidate.md)', prompt)[1]).write_text(page)
        return {'usage': {'input_tokens': 12}}
    monkeypatch.setattr('connectonion.rem.runner.run_task', execute)
    result = run_stage(nb, [{'role': 'page', 'record': 'projects/atlas.md', 'text': old},
                           {'source': 'fixture:flow', 'text': 'Local counter'},
                           {'source': 'fixture:readme', 'text': 'A local demo.'}], default_config(), stage='investigate')
    assert result['changed'] == ['projects/atlas.md']
    # Unknown, the optional Overview is then compacted away like any other.
    assert 'word counter' not in nb.read('projects/atlas.md') and 'count.py' not in nb.read('projects/atlas.md')
    assert 'A local demo. [1]' in nb.read('projects/atlas.md')
    assert 'fixture:flow' not in nb.read('projects/atlas.md')
    review = json.loads(next((tmp_path / '.state/tasks').glob('*/review.json')).read_text())
    assert review['accepted'] and review['overview_replaced']
    result = json.loads(next((tmp_path / '.state/tasks').glob('*/result.json')).read_text())
    assert result['status'] == 'candidate_accepted' and result['usage']['input_tokens'] == 12


def test_maintenance_repairs_overview_before_dropping_unused_sources(tmp_path):
    from connectonion.rem.runner import _promote_maintenance

    nb, working = Notebook(tmp_path / 'rem'), Notebook(tmp_path / 'work')
    record = 'projects/atlas.md'
    nb.stub_project(record, 'Atlas')
    old = nb.read(record)
    page = old.replace('## Overview\n- Unknown — not investigated yet', '## Overview\nRun a local word counter. [1]')
    page = page.replace('## What it is\n- Unknown — not investigated yet', '## What it is\nA local demo. [2]')
    working.write(record, page.replace('- (none yet)', '- [1] fixture:flow\n- [2] fixture:readme'))
    directory = tmp_path / 'task'
    directory.mkdir()
    items = [{'source': 'fixture:flow', 'text': 'Local counter'},
             {'source': 'fixture:readme', 'text': 'A local demo.'}]
    assert _promote_maintenance(nb, working, {record: old}, items, directory, None, False) == []
    assert '## Overview\n- Unknown' in nb.read(record)
    assert 'A local demo. [1]' in nb.read(record)
    assert 'fixture:flow' not in nb.read(record)
    review = json.loads((directory / 'review.json').read_text())
    assert review['accepted'] == [record] and review['repairs'][record]['overview_replaced']


def test_investigation_cannot_drop_scripted_project_metadata(tmp_path):
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas', sessions=3, first_seen='2026-09-01', last_seen='2026-09-22')
    old = nb.read('projects/atlas.md')
    bad = old.replace('- Sessions: 3\n', '')
    assert any('Sessions' in e for e in validate('projects/atlas.md', bad, old, []))
    assert validate('projects/atlas.md', old, old, []) == []


def test_exact_supplied_file_uri_is_a_citable_source(tmp_path):
    from connectonion.rem.page_review import _local_reference
    source = tmp_path / 'session file.jsonl'
    source.write_text('synthetic')
    neighbor = tmp_path / 'not-supplied.jsonl'
    neighbor.write_text('not supplied')
    items = [{'reference': source.as_uri()}]
    assert _local_reference(f'`{source}`', '', items)
    assert not _local_reference(f'`{neighbor}`', '', items)


def test_malformed_maintenance_keeps_page_and_pending_correction(tmp_path, monkeypatch):
    from connectonion.rem import reflections
    from connectonion.rem.files import write_json
    from connectonion.rem.service import approve_sources, run_sync
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    write_json(tmp_path / '.state/subscriptions.json', {k: {'kind': k, 'enabled': False} for k in ('codex','claude-code','gmail','outlook')})
    approve_sources(tmp_path)
    correction = reflections.add(tmp_path, 'projects/atlas.md', 'Mira owns Atlas', author='user', basis='Synthetic correction')
    def execute(directory, prompt, config, stage):
        # The correction names Atlas, so Atlas is worked on its own (#1656); the
        # model writes a malformed candidate for it.
        assert directory != nb.root and 'candidate.md' in prompt
        candidate = next(directory.glob('maintain-*/')) / 'candidate.md'
        candidate.write_text('# Atlas\n\n## Ownership\nMira\n')
        return {'usage': {'input_tokens': 9}}
    monkeypatch.setattr('connectonion.rem.runner.run_task', execute)
    result = run_sync(tmp_path)
    # A malformed page no longer refuses the batch (#1670): it is kept as it
    # was, and the correction to it stays pending for the next pass.
    assert result['outcome'] == 'completed' and result['refused'] == 1
    assert result['refusals'][0]['record'] == 'projects/atlas.md'
    # The first turn and its repair turns are all paid for.
    assert result['usage']['input_tokens'] == 9 * (1 + MAX_REPAIRS)
    assert nb.read('projects/atlas.md') == old
    progress = json.loads((tmp_path / '.state/progress.json').read_text()) if (tmp_path / '.state/progress.json').exists() else {}
    assert 'reflection:' + correction['id'] not in progress.get('rem_local_material', [])


def test_correction_exposes_exact_original_file_references(tmp_path):
    from connectonion.rem import reflections
    from connectonion.rem.page_review import _local_reference
    nb = Notebook(tmp_path / 'rem')
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
    from connectonion.rem.page_review import prior_context_reference
    value = "Existing person-page contact field; email listed as test@example.org; observed 2026-09-24"
    items = [{"role": "reflection", "source": "reflection:59715bf2"}]
    assert prior_context_reference(value, "people/test-person.md", items, original="# Test Person\n- Email: t@e.org")
    assert not prior_context_reference(value, "people/test-person.md", items, original="")   # a new page has no past
    assert not prior_context_reference("Outlook message 39", "people/test-person.md", items, original="# T")


def test_a_malformed_review_proposal_is_dropped_not_the_batch(tmp_path):
    """A real maintenance pass proposed a link with one subject; the whole batch
    failed after its pages were written, and would have been redone every run."""
    from connectonion.rem.files import read_json, state_path
    from connectonion.rem.reviews import ingest, listing
    prepare(tmp_path)
    Notebook(tmp_path).stub_person('people/ody.md', 'Ody', [])
    kept = ingest(tmp_path, [
        {'kind': 'link', 'subjects': ['people/ody.md'], 'question': 'Same as Ody Z?', 'basis': 'name'},
        {'kind': 'question', 'subjects': ['people/ody.md'], 'question': 'Still at OpenOnion?', 'basis': 'mail'},
        {'kind': 'question', 'subjects': ['people/ody.md'], 'question': 'third', 'basis': 'x'},
    ])
    assert [row['question'] for row in kept] == ['Still at OpenOnion?']
    assert [row['question'] for row in listing(tmp_path)] == ['Still at OpenOnion?']
    dropped = read_json(state_path(tmp_path, 'reviews-dropped.json'), [])
    assert dropped[0]['reason'] == 'Invalid number of review subjects'


def test_the_lines_the_runner_owns_are_put_back_not_refused():
    """A real pass rewrote a project's mapped Sessions and the status line, and the
    whole page was refused though the rest of it was sound."""
    from connectonion.rem.page_review import restore_runner_fields
    original = "# A\n\n## Paths\n- /w/a\n- Sessions: 12\n- First seen: 2026-08-01\n- Last seen: 2026-09-20\n\n" \
               "Investigation: mapped 2026-09-24 · not investigated yet\n"
    edited = "# A\n\n## Paths\n- /w/a\n- Sessions: many\n- First seen: 2026-08-01\n- Last seen: today\n\n" \
             "Investigation: investigated today (codex)\n"
    fixed = restore_runner_fields("projects/a.md", edited, original)
    assert "- Sessions: 12" in fixed and "- Last seen: 2026-09-20" in fixed
    assert fixed.rstrip().endswith("Investigation: mapped 2026-09-24 · not investigated yet")
    dropped = restore_runner_fields("projects/a.md", edited.replace("Investigation: investigated today (codex)\n", ""),
                                    original)
    assert dropped.rstrip().endswith("not investigated yet")                   # a removed status line comes back


def test_mapped_fields_nested_under_a_bullet_are_put_back_at_the_top_level():
    """A real project candidate kept Sessions / First seen / Last seen but indented
    them under a bullet, and the page was refused for losing the mapped facts."""
    from connectonion.rem.page_review import restore_runner_fields
    original = ("# Atlas\n\n## Paths\n- /work/atlas\n- Sessions: 2\n"
                "- First seen: 2026-09-20\n- Last seen: 2026-09-22\n")
    nested = ("# Atlas\n\n## Paths\n- /work/atlas\n- Mapped facts:\n"
              "  - Sessions: 2\n  - First seen: 2026-09-20\n  - Last seen: 2026-09-22\n")
    fixed = restore_runner_fields("projects/atlas.md", nested, original)
    for line in ("- Sessions: 2", "- First seen: 2026-09-20", "- Last seen: 2026-09-22"):
        assert fixed.count("\n" + line + "\n") == 1
    assert restore_runner_fields("projects/atlas.md", fixed, original) == fixed
    assert "- Sessions: 2\n" in restore_runner_fields("projects/atlas.md", nested.replace("Sessions: 2", "Sessions: 3"),
                                                       original)

@pytest.mark.parametrize("record", ["people/ying-tan.md", "orgs/harbour.md"])
@pytest.mark.parametrize("label", ["First contact", "Last contact"])
def test_restore_runner_fields_restores_contact_date_over_unknown(record, label):
    from connectonion.rem.page_review import restore_runner_fields
    original = f"# Ying Tan\n\n## Facts\n- {label}: 2026-10-14 [4]\n\n## Sources\n- [4] outlook:ying\n"
    candidate = original.replace(f"- {label}: 2026-10-14 [4]", f"- {label}: Unknown")

    assert restore_runner_fields(record, candidate, original) == original


def test_restore_runner_fields_maps_contact_citation_to_candidate_number():
    from connectonion.rem.page_review import restore_runner_fields
    original = "# Ying Tan\n\n## Facts\n- Last contact: 2026-10-14 [4]\n\n## Sources\n- [4] outlook:abc — 2026-10-14\n"
    candidate = ("# Ying Tan\n\n## Facts\n- Last contact: Unknown\n\n## Sources\n"
                 "- [2] outlook:abc — candidate description\n- [4] outlook:other\n")

    expected = candidate.replace("Last contact: Unknown", "Last contact: 2026-10-14 [2]")
    assert restore_runner_fields("people/ying-tan.md", candidate, original) == expected


def test_restore_runner_fields_appends_missing_contact_source_at_next_number():
    from connectonion.rem.page_review import restore_runner_fields
    original = "# Ying Tan\n\n## Facts\n- Last contact: 2026-10-14 [4]\n\n## Sources\n- [4] outlook:abc — 2026-10-14\n"
    candidate = ("# Ying Tan\n\n## Facts\n- Last contact: Unknown\n\n## Sources\n"
                 "- [1] outlook:one\n- [4] outlook:other\n\nInvestigation: mapped\n")

    expected = candidate.replace("Last contact: Unknown", "Last contact: 2026-10-14 [5]")
    expected = expected.replace("\n\nInvestigation:", "\n- [5] outlook:abc — 2026-10-14\n\nInvestigation:")
    assert restore_runner_fields("people/ying-tan.md", candidate, original) == expected


def test_restore_runner_fields_skips_contact_line_with_an_unresolved_citation():
    from connectonion.rem.page_review import restore_runner_fields
    original = "# Ying Tan\n\n## Facts\n- Last contact: 2026-10-14 [4][9]\n\n## Sources\n- [4] outlook:abc\n"
    candidate = "# Ying Tan\n\n## Facts\n- Last contact: Unknown\n\n## Sources\n- [2] outlook:other\n"

    assert restore_runner_fields("people/ying-tan.md", candidate, original) == candidate


@pytest.mark.parametrize("record", ["people/ying-tan.md", "orgs/harbour.md"])
@pytest.mark.parametrize("label", ["First contact", "Last contact"])
def test_restore_runner_fields_keeps_candidate_contact_date(record, label):
    from connectonion.rem.page_review import restore_runner_fields
    original = f"# Ying Tan\n\n## Facts\n- {label}: 2026-10-14 [4]\n\n## Sources\n- [4] outlook:ying\n"
    candidate = original.replace("2026-10-14 [4]", "2026-10-15 [4]")

    assert restore_runner_fields(record, candidate, original) == candidate


@pytest.mark.parametrize("record", ["people/ying-tan.md", "orgs/harbour.md"])
@pytest.mark.parametrize("label", ["First contact", "Last contact"])
def test_restore_runner_fields_original_unknown_changes_nothing(record, label):
    from connectonion.rem.page_review import restore_runner_fields
    original = f"# Ying Tan\n\n## Facts\n- {label}: Unknown\n"
    candidate = original.replace("# Ying Tan", "# Updated page")

    assert restore_runner_fields(record, candidate, original) == candidate


def test_a_page_turn_may_cite_the_page_as_it_stood_and_carry_over_its_sources():
    """A real one-page maintenance turn cited `investigation:page` and re-cited the
    page's own codex ids in new words; both were refused and the update was lost."""
    from connectonion.rem.page_review import validate
    original = ("# Dora\n\n## Contact\n- Email: d@example.org [2]\n\n## Sources\n"
                "- [2] User says Dora is internal. codex:0a:157160, codex:0a:438485\n\n"
                "Investigation: mapped 2026-09-20 · not investigated yet\n")
    candidate = ("# Dora\n\n## Contact\n- Email: d@example.org [1]\n- Role: internal [2]\n\n## Sources\n"
                 "- [1] investigation:page — the page as it stood listed this address.\n"
                 "- [2] codex:0a:157160, codex:0a:438485 — user describes Dora as internal.\n\n"
                 "Investigation: mapped 2026-09-20 · not investigated yet\n")
    errors = [e for e in validate("people/dora.md", candidate, original, [])
              if "identifiable source" in e]
    assert errors == []
    invented = candidate.replace("codex:0a:438485", "codex:0a:999999")
    assert any("identifiable source" in e for e in validate("people/dora.md", invented, original, []))


def test_a_person_page_with_a_cited_lead_before_contact_is_accepted():
    """#1974: the lead has no heading, so the section check is unchanged, and
    its citations are checked like any other sentence's."""
    sections = "".join(f"\n## {s}\n- Unknown\n" for s in ("Insight", *Notebook.PERSON_SECTIONS))
    contact = "\n".join(f"- {label}: Unknown" for label in Notebook.PERSON_CONTACT)
    page = ("# Mia Chen\n\nMia is the user's pilot client and owes the signed SOW by 3 October [{n}]. "
            f"Last contact: 2026-09-10 [1].\n\n## Facts\n{contact}\n{sections}\n## Sources\n"
            "- [1] gmail:person-mia:5 — 2026-09-10, high\n")
    items = [{"source": "gmail:person-mia:5"}]

    assert validate("people/mia.md", page.format(n=1), "", items) == []
    assert normalize("people/mia.md", page.format(n=1)).startswith("# Mia Chen\n\nMia is the user's pilot client")
    assert "Missing or duplicate citation: 2" in validate("people/mia.md", page.format(n=2), "", items)


# ------------------------------------------- #1974: what an investigation may claim


def _person(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person('people/mia.md', 'Mia', ['mia@h.example'], email='mia@h.example')
    return notebook, notebook.read('people/mia.md')


PAGE_ITEM = {'role': 'page', 'record': 'people/mia.md', 'source': 'investigation:page'}
COVERAGE_ITEM = {'role': 'coverage', 'source': 'investigation:coverage'}


def test_a_page_citing_only_itself_and_the_coverage_note_is_refused(tmp_path):
    """founders@unsw, 1.9.0a2: nothing about the subject read, page stamped investigated."""
    _, original = _person(tmp_path)
    candidate = (original.replace('## Who they are\n- Unknown — not investigated yet',
                                  '## Who they are\n- No mail was found about Mia. [1]')
                 .replace('- (none yet)', '- [1] investigation:coverage — the collector record'))
    errors = validate('people/mia.md', candidate, original, [PAGE_ITEM, COVERAGE_ITEM])
    assert any('cites only the page itself and the coverage note' in e for e in errors)


def test_a_page_with_one_real_source_beside_the_coverage_note_passes_that_check(tmp_path):
    _, original = _person(tmp_path)
    candidate = (original.replace('## Who they are\n- Unknown — not investigated yet',
                                  '## Who they are\n- Leads the data team. [1]\n- Searched two mailboxes. [2]')
                 .replace('- (none yet)', '- [1] gmail:abc123\n- [2] investigation:coverage'))
    errors = validate('people/mia.md', candidate, original,
                      [PAGE_ITEM, COVERAGE_ITEM, {'source': 'gmail:abc123'}])
    assert not any('cites only' in e for e in errors)


def test_one_miscopied_citation_drops_its_line_not_the_page(tmp_path):
    """A project page was refused after 199 s and 16k output tokens for one mistyped UUID."""
    from connectonion.rem.page_review import drop_unresolved
    _, original = _person(tmp_path)
    items = [PAGE_ITEM, {'source': 'gmail:abc123'}, {'source': 'gmail:def456'}]
    candidate = (original
                 .replace('- Role: Unknown', '- Role: Head of data [3]')
                 .replace('## Who they are\n- Unknown — not investigated yet',
                          '## Who they are\n- Leads the data team. [1]\n- Joined in 2024. [3]\n'
                          '- Works with Ody. [2][3]')
                 .replace('- (none yet)', '- [1] gmail:abc123\n- [2] gmail:def456\n- [3] gmail:abc12Z-typo'))
    repaired, dropped = drop_unresolved('people/mia.md', candidate, original, items)
    assert dropped == {'citations': ['3'], 'lines': 2}
    assert 'Joined in 2024' not in repaired and 'gmail:abc12Z-typo' not in repaired
    assert '- Works with Ody. [2]' in repaired and '- Leads the data team. [1]' in repaired
    assert '- Role: Unknown' in repaired
    assert validate('people/mia.md', repaired, original, items) == []


def test_a_section_left_empty_by_a_dropped_line_says_unknown(tmp_path):
    from connectonion.rem.page_review import drop_unresolved
    _, original = _person(tmp_path)
    candidate = (original.replace('## Cadence\n- Unknown — not investigated yet', '## Cadence\n- Weekly. [2]')
                 .replace('## Who they are\n- Unknown — not investigated yet', '## Who they are\n- Analyst. [1]')
                 .replace('- (none yet)', '- [1] gmail:abc123\n- [2] nowhere:1'))
    repaired, dropped = drop_unresolved('people/mia.md', candidate, original, [PAGE_ITEM, {'source': 'gmail:abc123'}])
    assert '## Cadence\n- Unknown' in repaired and dropped['lines'] == 1


def test_a_citation_with_no_sources_entry_is_dropped_too(tmp_path):
    from connectonion.rem.page_review import drop_unresolved
    _, original = _person(tmp_path)
    candidate = (original.replace('## Who they are\n- Unknown — not investigated yet',
                                  '## Who they are\n- Analyst. [1]\n- Tall. [7]')
                 .replace('- (none yet)', '- [1] gmail:abc123'))
    repaired, dropped = drop_unresolved('people/mia.md', candidate, original, [PAGE_ITEM, {'source': 'gmail:abc123'}])
    assert 'Tall.' not in repaired and dropped == {'citations': ['7'], 'lines': 1}


def test_company_links_to_the_organisation_page_when_there_is_one(tmp_path):
    from connectonion.rem.page_review import link_company
    notebook, original = _person(tmp_path)
    notebook.stub_org('orgs/unsw-1234.md', 'UNSW', ['unsw.edu.au'])
    text = original.replace('- Company: Unknown', '- Company: UNSW [1]')
    linked = link_company(notebook, 'people/mia.md', text)
    assert '- Company: [UNSW](../orgs/unsw-1234.md) [1]' in linked
    assert link_company(notebook, 'people/mia.md', linked) == linked
    other = original.replace('- Company: Unknown', '- Company: Acme [1]')
    assert link_company(notebook, 'people/mia.md', other) == other


def test_an_unknown_company_takes_the_organisation_page_of_the_persons_own_mail_domain(tmp_path):
    """28 of 53 `Company: Unknown` pages on a real 1.9.2b2 notebook wrote from a
    domain the notebook has an organisation page for (#2349)."""
    from connectonion.rem.page_review import company_from_domain
    notebook, original = _person(tmp_path)
    notebook.stub_org('orgs/unsw-1234.md', 'UNSW Sydney', ['unsw.edu.au'])
    rows = [{'field': 'Email', 'value': 'mia.chen@unsw.edu.au', 'qualifier': '', 'source': 'outlook:bbb',
             'date': '2026-09-02', 'own': True},
            {'field': 'Company domain', 'value': 'unsw.edu.au', 'qualifier': '', 'source': 'outlook:bbb',
             'date': '2026-09-02'}]
    filled, what = company_from_domain(notebook, 'people/mia.md', original, rows)
    number = re.search(r'^- \[(\d+)\] outlook:bbb — 2026-09-02$', filled, re.M)[1]
    assert f'- Company: [UNSW Sydney](../orgs/unsw-1234.md) [{number}]' in filled
    assert what == {'company': 'UNSW Sydney', 'domain': 'unsw.edu.au', 'source': 'outlook:bbb'}
    named = original.replace('- Company: Unknown', '- Company: Acme [1]')
    assert company_from_domain(notebook, 'people/mia.md', named, rows) == (named, {})


@pytest.mark.parametrize('newest', [
    'mia88@hotmail.com',             # graduated, writing from Hotmail: the old university is stale (Ziming, C1)
    'z1234567@unsw.edu.au',          # a student ID is enrolment, not employment (Sam, C2)
    'mia.chen@student.unsw.edu.au',  # seven students got UNSW as employer (C3)
    'usr-abc@user.luma-mail.com',    # a relay's domain is the platform's
    '0x3c3ae74550@mail.openonion.ai',  # an agent's mail domain is ConnectOnion's (C4)
])
def test_company_comes_only_from_the_address_they_write_from_now_and_never_a_student_one(tmp_path, newest):
    """Contacts audit C1-C4: `company_from_domain` fell back to any older domain,
    and to student, relay and agent-mail domains, overriding the model's Unknown."""
    from connectonion.rem.page_review import company_from_domain
    notebook, original = _person(tmp_path)
    notebook.stub_org('orgs/unsw-1234.md', 'UNSW Sydney', ['unsw.edu.au'])
    notebook.stub_org('orgs/luma.md', 'Luma', ['luma-mail.com'])
    notebook.stub_org('orgs/openonion.md', 'OpenOnion', ['openonion.ai'])
    rows = [{'field': 'Email', 'value': newest, 'qualifier': '', 'source': 'gmail:new', 'date': '2026-09-02',
             'own': True},
            {'field': 'Email', 'value': 'mia.chen@unsw.edu.au', 'qualifier': '', 'source': 'outlook:old',
             'date': '2025-01-13', 'own': True}]
    assert company_from_domain(notebook, 'people/mia.md', original, rows) == (original, {})


def test_an_investigated_page_that_still_says_not_investigated_yet_says_unknown(tmp_path):
    """#2008: project pages came back after 0.6-0.9M tokens with five and six
    sections still saying "Unknown — not investigated yet", and were refused.
    Code writes the bare Unknown the material shows instead."""
    from connectonion.rem import runner
    from connectonion.rem.page_review import clear_placeholders
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    written = (old.replace('## What it is\n- Unknown — not investigated yet', '## What it is\nA local demo. [1]')
               .replace('- (none yet)', '- [1] observed 2026-09-19 — fixture:readme'))
    cleared = clear_placeholders(written)
    assert 'not investigated yet' not in cleared.partition('Investigation:')[0]
    assert '## Where it stands\n- Unknown\n' in cleared and 'A local demo. [1]' in cleared
    assert clear_placeholders('# P\n\n## Facts\n- Phone: Unknown — not investigated yet\n') == (
        '# P\n\n## Facts\n- Phone: Unknown\n')                       # a field keeps its label
    items = [{'role': 'page', 'record': 'projects/atlas.md', 'text': old},
             {'source': 'fixture:readme', 'text': 'A local demo.'}]
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written)
    runner._promote_candidate(nb, 'projects/atlas.md', candidate, old, items, tmp_path, None)
    page = nb.read('projects/atlas.md')
    assert 'A local demo. [1]' in page and 'not investigated yet' not in page.partition('Investigation:')[0]


def test_project_page_keeps_unretained_file_citation_for_review(tmp_path):
    """A bad file citation must not leave an uncited diagram behind."""
    import hashlib
    from connectonion.rem import runner
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    mapped = tmp_path / 'mapped'
    mapped.mkdir()
    outside = tmp_path / 'outside.md'
    outside.write_text('A -> B\n')
    nb.stub_project('projects/atlas.md', 'Atlas', paths=[str(mapped)])
    old = nb.read('projects/atlas.md')
    source = f'file:{outside}@{hashlib.sha256(outside.read_bytes()).hexdigest()}'
    candidate = (old.replace('- Unknown — not investigated yet', '- Unknown')
                 .replace('## Insight\n- Unknown', '## Insight\n- Changed: collect first. [2]')
                 .replace('## Overview\n- Unknown',
                          '## Overview\nAn unsupported architecture. [1]\n```text\nA -> B\n```')
                 .replace('- (none yet)', f'- [1] {source} — inspected file\n- [2] codex:abc — user request'))
    path = tmp_path / 'candidate.md'
    path.write_text(candidate)
    items = [{'role': 'page', 'record': 'projects/atlas.md', 'text': old},
             {'source': 'codex:abc', 'text': 'Collect first.'}]
    with pytest.raises(runner.RunFailed, match='Cited file needs a hash or exact Git commit in a mapped repository'):
        runner._promote_candidate(nb, 'projects/atlas.md', path, old, items, tmp_path, None)
    assert nb.read('projects/atlas.md') == old
    assert path.read_text() == candidate


def test_the_project_skills_require_evidence_for_overview_and_no_placeholder_or_guessed_name():
    from connectonion.rem import project_pages
    from connectonion.rem.runner import instructions
    for text in (project_pages.instructions(), instructions('investigate', page_kind='project')):
        assert 'Overview' in text and 'evidence' in text
        assert 'refused' in text and 'misheard' in text and 'never guess' in text.lower()


# ------------------------------------------- a page stays readable in one sitting (#2019)


def _grown(old: str, size: int) -> str:
    """The page with History grown to `size` characters, every line cited."""
    line = '- 2026-09-01: a dated line of history, one of many the update added. [1]\n'
    body = old.replace('- (none yet)', '- [1] observed 2026-09-19 — fixture:readme')
    history = line * max(0, (size - len(body)) // len(line) + 1)
    return body.replace('\n## Sources\n', '\n' + history + '\n## Sources\n', 1)


def test_a_candidate_over_the_limit_that_grew_the_page_is_refused(tmp_path):
    """1.9.0a5 acceptance: one daily update took projects/connectonion from 13,421
    to 25,255 characters. Only the growth past the limit is refused."""
    from connectonion.rem.page_review import PAGE_LIMIT, size_errors
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = _grown(nb.read('projects/atlas.md'), 13_421)
    grown = _grown(old, 31_000)
    assert PAGE_LIMIT == 20_000
    errors = size_errors(grown, old)
    assert errors and '31,' in errors[0] and '20,000' in errors[0] and 'History' in errors[0]
    assert any('20,000' in error for error in validate('projects/atlas.md', grown, old, []))
    assert size_errors(_grown(old, 18_000), old) == []               # growth under the limit: fine
    # 25,255, the real case, is kept: History folds in code and the next pass is asked to come down.
    assert size_errors(_grown(old, 25_255), old) == []
    oversized = _grown(old, 26_000)
    assert size_errors(_grown(old, 22_000), oversized) == []         # an oversized page may come down in steps


# ------------------------------------------- the page is about the subject, not the run (#2058)


def test_lines_about_the_run_are_removed_and_a_contact_field_keeps_its_label():
    """Five of the owner's seven investigated person pages said "web: not
    searched; Wiki runs are offline"; Ody's Phone line said it too."""
    from connectonion.rem.page_review import drop_tool_text
    original = '# Ody\n\n## Contact\n- Phone: Unknown\n\n## Sources\n- [1] outlook:aaa — 2026-09-01\n'
    candidate = ('# Ody\n\n## Contact\n- Phone: no phone number appears; the web was not searched in this '
                 'offline Wiki run.\n\n## Uncertainties\n- web: not searched; Wiki runs are offline. [2]\n'
                 '- Whether the 30/70 split was signed. [1]\n- Ody collects art; a serious collector. [1]\n'
                 '\n## Sources\n- [1] outlook:aaa — 2026-09-01\n- [2] investigation:coverage — offline run\n')
    text, removed = drop_tool_text('people/ody.md', candidate, original)
    assert '- Phone: Unknown' in text
    assert 'Wiki runs are offline. [2]' not in text and len(removed) == 2
    assert 'Whether the 30/70 split was signed. [1]' in text and 'a serious collector' in text
    assert '- [2] investigation:coverage — offline run' in text      # Sources are left to drop_uncited_sources


def test_a_line_the_page_already_had_is_left_to_tidy():
    from connectonion.rem.page_review import drop_tool_text
    page = '# T\n\n## History\n- The current collector reports 50 bodies read. [1]\n\n## Sources\n- [1] x\n'
    assert drop_tool_text('people/t.md', page, page) == (page, [])


# ------------------------------------------- History is milestones (#2059)


def _with_history(lines: int) -> str:
    rows = ''.join(f'- 2026-09-{day:02d}: agreed step {day}. [1]\n' for day in range(1, lines + 1))
    return f'# P\n\n## History\n{rows}\n## Sources\n- [1] outlook:aaa — 2026-09-01\n'


@pytest.mark.parametrize('heading', ['History', 'Key decisions'])
def test_dated_history_and_decisions_are_sorted_newest_first(heading):
    from connectonion.rem.page_review import sort_history
    oldest = '- 2024: Avery Lin proposed a call. [1]'
    middle = '- **2026-09** — Avery Lin agreed. [2]'
    newest = '- 2026-10-20: Avery Lin declined. [3]'
    page = (f'# Avery Lin\n\n## {heading}\n{oldest}\n{newest}\n{middle}\n\n'
            '## Sources\n- [1] gmail:m:1\n- [2] gmail:m:2\n- [3] gmail:m:3\n')
    expected = page.replace(f'{oldest}\n{newest}\n{middle}', f'{newest}\n{middle}\n{oldest}')
    assert sort_history(page) == expected
    assert sort_history(expected) == expected


@pytest.mark.parametrize('heading', ['History', 'Key decisions'])
def test_undated_lines_keep_their_place_after_dated_history_and_decisions(heading):
    from connectonion.rem.page_review import sort_history
    older = '- 2026-09-01: Avery Lin agreed. [1]'
    newer = '- 2026-10-01: Avery Lin declined. [2]'
    page = (f'# Avery Lin\n\n## {heading}\n{older}\n{newer}\n\n'
            '- Earlier introduction, date unknown. [3]\n- Follow-up date unknown. [3]\n\n'
            '## Sources\n- [1] gmail:m:1\n- [2] gmail:m:2\n- [3] gmail:m:3\n')
    assert sort_history(page) == page.replace(f'{older}\n{newer}', f'{newer}\n{older}').replace(
        '\n\n- Earlier', '\n- Earlier')


@pytest.mark.parametrize('heading', ['History', 'Key decisions'])
def test_one_dated_history_or_decision_line_removes_blank_between_items(heading):
    from connectonion.rem.page_review import sort_history
    page = (f'# Avery Lin\n\n## {heading}\n- 2026-10-20: agreed to a call. [1]\n\n'
            '- Earlier introduction, date unknown. [1]\n\n## Sources\n- [1] gmail:m:1\n')
    assert sort_history(page) == page.replace('\n\n- Earlier', '\n- Earlier')


def test_a_history_past_sixteen_threads_may_not_grow_and_may_come_down():
    """Ody Zhou's History held 17 bullets, five of them "sent report X" (#2059);
    eight then squeezed out how threads ended, so it is one line per thread, sixteen (#2314)."""
    from connectonion.rem.page_review import history_errors, history_note
    assert history_errors(_with_history(17), _with_history(16))
    assert 'at most 16' in history_errors(_with_history(17), _with_history(3))[0]
    assert history_errors(_with_history(16), _with_history(3)) == []
    assert history_errors(_with_history(18), _with_history(20)) == []          # coming down in steps
    assert 'fold the oldest' in history_note(_with_history(20))
    assert history_note('# P\n\n## History\n- Unknown — not investigated yet\n') == ''


# ------------------------------------------- a name the notebook has a page for is a link (#2060)


def test_the_first_mention_of_a_person_with_a_page_links_to_it(tmp_path):
    """Ody Zhou's page named Ivan Zhu and Harry Cao, who had pages, and linked neither."""
    from connectonion.rem.page_review import link_people, person_names
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_person('people/jiexuan.md', 'Jiexuan Deng', ['j@unsw.edu.au'], email='j@unsw.edu.au')
    nb.stub_person('people/ivan.md', 'Ivan', ['ivanxzhu@gmail.com'], email='ivanxzhu@gmail.com')
    nb.stub_person('people/harry-a.md', 'Harry', ['amazingharry1@gmail.com'], email='amazingharry1@gmail.com')
    nb.stub_person('people/harry-b.md', 'Harry', ['hai@gmail.com'], email='hai@gmail.com')
    page = ('# Richard Lai\n\nWorks with Jiexuan Deng. [1]\n\n## Contact\n- Also known as: Jiexuan Deng\n\n'
            '## History\n- 2026-09-25: met Ivan Zhu and Harry Cao; Jiexuan Deng joined. [1]\n\n'
            '## Sources\n- [1] outlook:aaa — Jiexuan Deng, 2026-09-25\n')
    linked = link_people('people/richard.md', page, person_names(nb))
    assert 'Works with [Jiexuan Deng](../people/jiexuan.md).' in linked          # first mention only
    assert '; Jiexuan Deng joined' in linked and '- Also known as: Jiexuan Deng' in linked
    assert 'met [Ivan Zhu](../people/ivan.md) and Harry Cao' in linked           # the only Ivan, ivanxzhu@
    assert '- [1] outlook:aaa — Jiexuan Deng, 2026-09-25' in linked               # Sources untouched
    assert link_people('people/richard.md', linked, person_names(nb)) == linked  # idempotent


def test_a_project_page_is_not_refused_for_citing_the_run_or_folding_its_mapped_lines():
    """4 of the first 8 project pages of a real 1.9.0 Codex init were refused
    whole for these two, each fixable without the model (2026-10-08)."""
    from connectonion.rem.page_review import repair_run_citations
    original = ('# Atlas\n\n## Paths\n- `/src/atlas` — mapped project directory\n- Sessions: 30\n'
                '- First seen: 2026-07-29\n- Last seen: 2026-10-07\n')
    candidate = ('# Atlas\n\n## Where it stands\n- The importer ships nightly. [1]\n'
                 '- No sessions mention the exporter. [2]\n- The CLI was renamed. [1][2]\n\n'
                 '## Paths\n- `/src/atlas` — mapped project directory; Sessions: 30; First seen: 2026-07-29; '
                 'Last seen: 2026-10-07.\n\n## Sources\n- [1] codex:abc — 2026-10-01\n'
                 '- [2] investigation:coverage — today\n')
    repaired = repair_run_citations('projects/atlas.md', candidate, original)
    assert 'The importer ships nightly. [1]' in repaired
    assert 'exporter' not in repaired and 'investigation:coverage' not in repaired
    assert '- The CLI was renamed. [1]\n' in repaired
    assert '- Sessions: 30\n- First seen: 2026-07-29\n- Last seen: 2026-10-07\n' in repaired
    items = [{'role': 'session', 'source': 'codex:abc', 'text': 'importer ships nightly'}]
    errors = validate('projects/atlas.md', repaired, original, items)
    assert not [e for e in errors if 'coverage' in e or 'mapped project metadata' in e]
    assert repair_run_citations('people/x.md', candidate, original) == candidate


def test_an_investigation_edits_the_page_it_was_given_instead_of_starting_blank(tmp_path, monkeypatch):
    """49 of 63 real Codex investigations wrote the page from scratch; UNSW's
    People-here list fell from 20 linked people to 4 and was accepted (2026-10-08)."""
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    record = 'projects/atlas.md'
    nb.stub_project(record, 'Atlas')
    original = nb.read(record)
    seen = []

    def run(directory, prompt, config, stage):
        path = Path(re.search(r'(?:page is the file|existing page at) (.+?candidate.md)', prompt)[1])
        seen.append(path.read_text())
        assert 'Do not rewrite the page from scratch' in prompt
        return {'usage': {'input_tokens': 1}, 'result': 'Nothing new. NO CHANGE'}
    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    result = run_stage(nb, [{'role': 'page', 'record': record, 'text': original}], default_config(), stage='investigate')
    assert seen == [original]  # one turn: the page as it stands, and no follow-up for an honest NO CHANGE
    assert result['changed'] == []


def test_a_skill_page_is_not_refused_for_citing_its_run_summary():
    from connectonion.rem.page_review import repair_run_citations
    candidate = ('# title-refine\n\n## Insight\n- Run 14 times in a month. [2]\n- It rewrites titles to name a fact. [1]\n\n'
                 '## Sources\n- [1] skill-source:title-refine — 2026-10-01\n- [2] skill-runs:title-refine — today\n')
    repaired = repair_run_citations('skills/catalog/title-refine.md', candidate, '# title-refine\n')
    assert 'Run 14 times' not in repaired and 'skill-runs:' not in repaired
    assert 'It rewrites titles to name a fact. [1]' in repaired


def test_a_source_cited_only_inside_a_diagram_is_dropped_not_left_to_refuse_the_page():
    from connectonion.rem.page_review import drop_uncited_sources
    text = ('# GTM\n\n## How it works\n```\nlead -> rank [6][9]\n```\n- Ranks prospects. [6]\n\n'
            '## Sources\n- [6] codex:a:1 — 2026-07-16\n- [9] codex:b:2 — 2026-07-16\n')
    out = drop_uncited_sources(text)
    assert '- [6] codex:a:1' in out and 'codex:b:2' not in out


def test_a_skill_page_edited_in_place_keeps_one_run_evidence_section():
    from connectonion.rem.page_review import repair_run_citations
    text = ('# x\n\n## Limitations\n- None known.\n\n## Run evidence\n<!-- rem-skill-runs:start -->\n## Run evidence\n\n'
            '- Retained evaluation attempts: 2\n<!-- rem-skill-runs:end -->\n\nInvestigation: mapped\n')
    out = repair_run_citations('skills/catalog/x.md', text, '# x\n')
    assert out.count('## Run evidence') == 1 and '- None known.' in out and 'attempts: 2' in out


def test_the_owners_phone_from_a_quoted_signature_is_taken_off_a_contacts_page():
    """1.9.2b1 (2026-10-09) gave Weiwei the user's phone from his own signature, against the instructions."""
    from connectonion.rem.page_review import drop_owner_addresses
    page = "## Facts\n- Email: weiwei.lei@rmit.edu.au\n- Phone: +61 435 525 634 [2]\n- Role: Professor [1]\n"
    text, removed = drop_owner_addresses(page, {"aaron@openonion.ai", "0435 525 634 (work)"})
    assert "- Phone: Unknown\n" in text and removed == ["+61 435 525 634"]
    assert "- Email: weiwei.lei@rmit.edu.au" in text
    other = page.replace("+61 435 525 634", "+61 400 111 222")
    assert drop_owner_addresses(other, {"0435 525 634 (work)"}) == (other, [])


def test_the_owners_phone_is_found_when_each_number_carries_its_own_citation():
    """1.9.2b2 (2026-10-09) kept the user's phone on Sasha's page: `[48]` was read as two more digits."""
    from connectonion.rem.page_review import drop_owner_addresses
    page = "## Facts\n- Phone: +61-0435525634 (work) [48]; +61 2 9065 4432 (work) [49]\n"
    text, removed = drop_owner_addresses(page, {"0435 525 634"})
    assert "- Phone: +61 2 9065 4432 (work) [49]\n" in text and "0435525634" not in text
    assert removed == ["+61-0435525634 (work) [48]"]


def test_a_number_in_someone_elses_signature_is_taken_off_and_any_other_stays():
    """#2348, as narrowed by the 1.9.2b3 trial: only a number known to be someone else's goes."""
    from connectonion.rem.page_review import drop_others_phones
    page = "## Facts\n- Phone: 0457 857 962 (mobile) [2]; +61 2 9065 4432 (work) [49]\n- Role: Lead [1]\n"
    text, removed = drop_others_phones(page, ["+61 2 9065 4432"], [])
    assert "- Phone: 0457 857 962 (mobile) [2]\n" in text and removed == ["+61 2 9065 4432 (work) [49]"]
    assert drop_others_phones(page, ["+61 2 9065 4432"], ["02 9065 4432"]) == (page, [])   # theirs too
    assert "- Phone: Unknown\n" in drop_others_phones(page, ["0457 857 962", "+61290654432"], [])[0]


def test_a_malformed_search_request_keeps_the_candidate_instead_of_failing_the_page(tmp_path):
    """1.9.2b1 lost a whole person page in round 5 of 9 to `Expecting ',' delimiter`."""
    from datetime import timezone
    from connectonion.rem.runner import _searched_turn
    (tmp_path / "search-requests.json").write_text('["Wisiani contract",\n "renewal" "date"]', encoding="utf-8")
    first = {"result": "edited", "report": "Round 5 read.", "usage": {"input_tokens": 3}}

    def never(*args):
        raise AssertionError("no search should run")
    out = _searched_turn(tmp_path, "prompt", {}, "investigate", tmp_path, never, [], first, timezone.utc)
    assert out["result"] == "edited" and "not valid JSON" in out["report"]


def test_an_assistants_memory_file_beside_a_supplied_transcript_is_not_a_source(tmp_path):
    """1.9.2b1: Ian's page cited the owner's Claude memory file by path. It sat in
    the folder of a supplied session transcript, so it passed as a local file."""
    from connectonion.rem.page_review import drop_unresolved
    folder = tmp_path / '.claude/projects/-work'
    (folder / 'memory').mkdir(parents=True)
    transcript, memory = folder / 's1.jsonl', folder / 'memory/reference_ian.md'
    transcript.write_text('{}')
    memory.write_text('Ian: MBA at UNSW')
    items = [{'role': 'owner-work-evidence', 'file': str(transcript), 'sources': ['claude-code:s1']}]
    text = ('# Ian\n\nIan asked about pricing [1].\n\n## Who they are\nIan studies an MBA [2].\n\n'
            f'## Sources\n- [1] claude-code:s1 — 2026-08-11\n- [2] {memory} — 2026-08-11\n')
    kept, dropped = drop_unresolved('people/ian.md', text, '', items)
    assert dropped['citations'] == ['2'] and str(memory) not in kept and 'Ian asked about pricing [1].' in kept


def test_sources_are_renumbered_without_gaps_and_code_is_left_alone():
    # 40 of 123 pages in a real 1.9.2b3 notebook listed [1], [2], [5], [9]...
    # after uncited sources were dropped; the reader showed the gaps.
    from connectonion.rem.page_review import renumber_sources
    text = ("# Ada\n\nShe runs the lab [2] and signed [5][W1].\n\n"
            "```python\nrows[5] = x[2]\n```\n\nSee `a[9]` and [the docs](https://x.test).\n\n"
            "## Sources\n- [2] outlook:aaa — observed 2026-07-10\n- [5] outlook:bbb — observed 2026-07-11\n"
            "- [W1] https://lab.test\n")
    assert renumber_sources(text) == (
        "# Ada\n\nShe runs the lab [1] and signed [2][W1].\n\n"
        "```python\nrows[5] = x[2]\n```\n\nSee `a[9]` and [the docs](https://x.test).\n\n"
        "## Sources\n- [1] outlook:aaa — observed 2026-07-10\n- [2] outlook:bbb — observed 2026-07-11\n"
        "- [W1] https://lab.test\n")


def test_sources_already_in_order_are_unchanged():
    from connectonion.rem.page_review import renumber_sources
    text = "# A\n\nFact [1].\n\n## Sources\n- [1] outlook:aaa\n"
    assert renumber_sources(text) == text


@pytest.mark.parametrize('text, expected', [
    ('[15][16][15][16]', '[15][16]'),
    ('[21][21]', '[21]'),
    ('[8][8]', '[8]'),
    ('[3] [3]', '[3]'),
    ('[1][2]', '[1][2]'),
    ('[2] [1][2] [3]', '[2][1][3]'),
    ('[3]  [3]', '[3]  [3]'),
    ('[3]\n[3]', '[3]\n[3]'),
    ('`rows[5][5]` [5][5]', '`rows[5][5]` [5]'),
    ('```python\nrows[5][5]\n```\n[5][5]', '```python\nrows[5][5]\n```\n[5]'),
    ('[3](http://x)[3]', '[3](http://x)[3]'),
    ('[3][3](http://x)', '[3][3](http://x)'),
    ('[W1][W1]', '[W1][W1]'),
    ('## Sources\n- [3] gmail:abc — original\n', '## Sources\n- [3] gmail:abc — original\n'),
])
def test_repeated_citation_markers_collapse_only_within_prose_runs(text, expected):
    from connectonion.rem.page_review import collapse_repeated_markers
    assert collapse_repeated_markers(text) == expected


def test_merged_sources_leave_one_citation_after_renumbering():
    from connectonion.rem.page_review import collapse_repeated_markers, renumber_sources, settle_sources
    text = ('# Dora\n\nA fact [1][2]\n\n## Sources\n'
            '- [1] gmail:abc — original\n- [2] gmail:abc — repeated\n')
    assert collapse_repeated_markers(renumber_sources(settle_sources(text, {}))) == (
        '# Dora\n\nA fact [1]\n\n## Sources\n- [1] gmail:abc — original\n')


def test_a_required_section_the_turn_left_out_is_added_as_unknown():
    # 1.9.2b3 trial: a project page without "Open threads" and a skill page
    # without "Limitations" were refused whole, reported as "must occur once".
    from connectonion.rem.page_review import add_missing_sections, headings
    page = ('# startup\n\n## Facts\n- Status: active [1]\n\n## Insight\nIt ships [1].\n\n'
            '## What it is\nA shop [1].\n\n## Where it stands\nLive [1].\n\n## Paths\n- /work/startup [1]\n\n'
            '## Uncertainties\n- Unknown\n\n## Sources\n- [1] claude-code:s1 — 2026-08-11\n')
    fixed = add_missing_sections('projects/startup.md', page)
    assert re.findall(r'^## (.+)$', fixed, re.M) == list(headings('projects/startup.md'))
    assert '## Paths\n- /work/startup [1]\n\n## Open threads\n- Unknown\n\n## Uncertainties' in fixed


def test_a_missing_section_is_reported_as_missing_not_as_a_duplicate():
    page = '# A\n\n## Facts\n- Status: Unknown\n\n## Sources\n- [1] claude-code:s1\n'
    errors = validate('projects/a.md', page, '', [])
    assert 'Missing section: Open threads' in errors
    assert not any('must occur once: Open threads' in e for e in errors)


def test_a_carried_over_project_source_is_recognised_when_reworded():
    """browser and handoff (2026-10-14): `project-source:` was not a source scheme, so
    a real id carried over from the page counted only when its whole line matched."""
    from connectonion.rem.page_review import _carried_over
    real = "project-source:" + "a1" * 32
    old_sources = f"- [3] {real} — README.md, captured 2026-10-01\n"
    assert _carried_over(f"{real} — the project README", old_sources)
    assert not _carried_over("project-source:" + "b2" * 32 + " — invented", old_sources)


def test_a_file_cited_with_its_current_hash_is_a_source_on_any_page(tmp_path):
    """job-followup's skill page cited its applications log this way and was refused
    (1.9.2b3): only project pages accepted a `file:` id."""
    import hashlib
    from connectonion.rem.page_review import _pinned_file
    log = tmp_path / 'applications.md'
    log.write_text('2026-10-01 applied to Acme\n')
    digest = hashlib.sha256(log.read_bytes()).hexdigest()
    assert _pinned_file(f'file:{log}#sha256:{digest} — applications log')
    log.write_text('2026-10-02 rewritten\n')
    assert not _pinned_file(f'file:{log}#sha256:{digest}')              # the file changed since
    assert not _pinned_file(f'file:{tmp_path / "gone.md"}#sha256:{digest}')
    assert not _pinned_file(f'file:{log}')                                # no hash, nothing pinned


def test_source_dates_come_from_the_original_in_the_notebooks_timezone():
    from zoneinfo import ZoneInfo
    from connectonion.rem.page_review import source_dates
    items = [{'source': 'gmail:a', 'timestamp': '2026-10-14T20:30:00Z'},
             {'source': 'gmail:b', 'timestamp': 'yesterday'}]
    dates = source_dates(Path('/nonexistent-notebook'), '# X\n', items, ZoneInfo('Australia/Sydney'))
    assert dates == {'gmail:a': '2026-10-15'}


def test_a_source_id_cited_inline_becomes_a_numbered_citation():
    """Nina's, Tamara's and Weiwei's pages (2026-10-15) cited `[outlook:ac8a0c940197]` in prose."""
    from connectonion.rem.page_review import normalize_numbered_sources
    page = ("# N\n\nAsked [outlook:ac8a0c940197]; replied [1] [outlook:2af4c0ad8970].\n\n## Sources\n"
            "- [1] outlook:2af4c0ad8970 — 2026-09-24\n\nInvestigation: x\n")
    out = normalize_numbered_sources(page)
    assert "Asked [2]; replied [1] [1]." in out
    assert "- [2] outlook:ac8a0c940197" in out and out.rstrip().endswith("Investigation: x")


@pytest.mark.parametrize("record", ["people/alex.md", "orgs/old-brand.md"])
@pytest.mark.parametrize("label", ["First contact", "Last contact"])
def test_contact_date_from_previous_subject_is_not_restored_after_title_correction(record, label):
    from connectonion.rem.page_review import restore_runner_fields
    original = (f"# Alex Previous\n\n## Facts\n- {label}: 2026-09-01 [4]\n\n"
                "## Sources\n- [4] gmail:previous-person\n\nInvestigation: mapped 2026-09-01\n")
    candidate = (f"# Alex Corrected\n\n## Facts\n- {label}: Unknown\n\n"
                 "## Uncertainties\n- The previous messages concern a different subject. [1]\n\n"
                 "## Sources\n- [1] codex:correction\n\nInvestigation: mapped 2026-09-01\n")
    fixed = restore_runner_fields(record, candidate, original)
    assert fixed == candidate
    assert "gmail:previous-person" not in fixed


def test_contact_date_candidate_is_kept_after_subject_title_changes():
    from connectonion.rem.page_review import restore_runner_fields
    original = "# Old Brand\n\n## Facts\n- Last contact: 2026-09-01 [4]\n"
    candidate = "# New Brand\n\n## Facts\n- Last contact: 2026-10-01 [1]\n"
    assert restore_runner_fields("orgs/brand.md", candidate, original) == candidate


def test_contact_date_is_still_restored_for_title_case_changes():
    from connectonion.rem.page_review import restore_runner_fields
    original = "# Alex Person\n\n## Facts\n- Last contact: 2026-09-01 [4]\n\n## Sources\n- [4] gmail:alex\n"
    candidate = original.replace("Alex Person", "ALEX PERSON").replace("2026-09-01 [4]", "Unknown")
    fixed = restore_runner_fields("people/alex.md", candidate, original)
    assert "- Last contact: 2026-09-01 [4]" in fixed


def test_subject_correction_does_not_restore_previous_subject_extracted_contacts(tmp_path):
    from connectonion.rem.runner import _promote_candidate
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    record = "people/alex.md"
    notebook.stub_person(record, "Alex Previous", handles=["previous@example.test"])
    original = notebook.read(record).replace("- Last contact: Unknown", "- Last contact: 2026-09-01 [4]")
    original = original.replace("- (none yet)", "- [4] gmail:previous-person")
    notebook.write(record, original)
    text = original.replace("# Alex Previous", "# Alex Corrected")
    text = re.sub(r"(?m)^- Email:.*$", "- Email: Unknown", text)
    text = text.replace("- Last contact: 2026-09-01 [4]", "- Last contact: Unknown")
    text = text.replace("Unknown — not investigated yet. Last contact: Unknown.", "Corrected subject. [1]")
    text = text.replace("- Unknown — not investigated yet", "- Unknown")
    text = text.replace("- [4] gmail:previous-person", "- [1] codex:correction:0")
    candidate = tmp_path / "candidate.md"
    candidate.write_text(text)
    items = [
        {"role": "user", "source": "codex:correction:0", "text": "The subject is Alex Corrected, not Alex Previous."},
        {"role": "facts", "source": "investigation:facts", "facts": [
            {"field": "Last contact", "value": "2026-09-01", "source": "gmail:previous-person", "date": "2026-09-01"},
            {"field": "Email", "value": "previous@example.test", "source": "gmail:previous-person", "date": "2026-09-01", "own": True},
        ]},
    ]
    _promote_candidate(notebook, record, candidate, original, items, tmp_path, None)
    saved = notebook.read(record)
    assert "- Email: Unknown" in saved
    assert "- Last contact: Unknown" in saved
    assert "gmail:previous-person" not in saved


@pytest.mark.parametrize("record,old_title,new_title,anchor", [
    ("people/alex.md", "alex@example.test", "Alex Person", "## Facts\n- Email: alex@example.test\n"),
    ("orgs/example.md", "example.test", "Example Company", "## Domains\n- example.test\n\n## Facts\n"),
])
def test_title_rename_with_preserved_identity_anchor_keeps_contact_recovery(record, old_title, new_title, anchor):
    from connectonion.rem.page_review import restore_runner_fields
    original = f"# {old_title}\n\n{anchor}- Last contact: 2026-09-01 [4]\n\n## Sources\n- [4] gmail:known\n"
    candidate = original.replace(f"# {old_title}", f"# {new_title}").replace("2026-09-01 [4]", "Unknown")
    fixed = restore_runner_fields(record, candidate, original)
    assert "- Last contact: 2026-09-01 [4]" in fixed


@pytest.mark.parametrize("email", ["corrected@example.test", "Unknown"])
def test_same_domain_and_incidental_old_address_do_not_restore_prior_contact_date(email):
    from connectonion.rem.page_review import restore_runner_fields
    original = ("# Previous Person\n\n## Facts\n- Email: previous@example.test\n"
                "- Last contact: 2026-09-01 [4]\n\n## Sources\n- [4] gmail:previous\n")
    candidate = (f"# Corrected Person\n\n## Facts\n- Email: {email}\n- Last contact: Unknown\n\n"
                 "## Uncertainties\n- previous@example.test belongs to the previous subject.\n")
    assert restore_runner_fields("people/alex.md", candidate, original) == candidate


@pytest.mark.parametrize("rejected", [
    "Unknown (previous@example.test belonged to the previous subject)",
    "previous@example.test (wrong person)",
    "Unknown; previous@example.test",
])
def test_rejected_email_value_does_not_prove_subject_continuity(rejected):
    from connectonion.rem.page_review import restore_runner_fields
    original = ("# Previous Person\n\n## Facts\n- Email: previous@example.test\n"
                "- Last contact: 2026-09-01 [4]\n\n## Sources\n- [4] gmail:previous\n")
    candidate = f"# Corrected Person\n\n## Facts\n- Email: {rejected}\n- Last contact: Unknown\n"
    assert restore_runner_fields("people/alex.md", candidate, original) == candidate


def test_rejected_domain_annotation_does_not_prove_org_continuity():
    from connectonion.rem.page_review import restore_runner_fields
    original = ("# Old Company\n\n## Domains\n- previous.example\n\n## Facts\n"
                "- Last contact: 2026-09-01 [4]\n\n## Sources\n- [4] gmail:previous\n")
    candidate = ("# Correct Company\n\n## Domains\n- previous.example — belongs to the old subject\n\n"
                 "## Facts\n- Last contact: Unknown\n")
    assert restore_runner_fields("orgs/company.md", candidate, original) == candidate


def test_legacy_contact_anchor_keeps_extracted_date_recovery_on_a_title_upgrade(tmp_path):
    from connectonion.rem.runner import _promote_candidate
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    record = "people/alex.md"
    notebook.stub_person(record, "alex@example.test", handles=["alex@example.test"])
    original = notebook.read(record).replace("## Facts", "## Contact")
    original = re.sub(r"(?m)^- Email:.*$", "- Email: alex@example.test", original)
    notebook.write(record, original)
    text = original.replace("# alex@example.test", "# Alex Person").replace("## Contact", "## Facts")
    text = text.replace("Unknown — not investigated yet. Last contact: Unknown.", "Alex introduced the project. [1]")
    text = text.replace("- Unknown — not investigated yet", "- Unknown")
    text = text.replace("- (none yet)", "- [1] gmail:alex")
    candidate = tmp_path / "candidate.md"
    candidate.write_text(text)
    items = [
        {"role": "other", "speaker": "alex@example.test", "source": "gmail:alex", "text": "I am Alex Person."},
        {"role": "facts", "source": "investigation:facts", "facts": [
            {"field": "Last contact", "value": "2026-09-01", "source": "gmail:alex", "date": "2026-09-01"},
        ]},
    ]
    _promote_candidate(notebook, record, candidate, original, items, tmp_path, None)
    assert "- Last contact: 2026-09-01 [1]" in notebook.read(record)


def test_a_project_fact_resting_only_on_the_run_keeps_its_label_as_unknown():
    """2026-10-20 trial: `People: the user [4]` cited investigation:page; the line went and the
    whole first-run page was refused for a missing Facts field."""
    from connectonion.rem.page_review import repair_run_citations
    page = ("# Atlas\n\n## Facts\n- Repository: example/atlas [1]\n- People: the user [2]\n\n"
            "## What it is\nAn export tool [1].\n\n## Sources\n- [1] codex:s:1 — 2026-10-01\n"
            "- [2] investigation:page — 2026-10-20\n")
    fixed = repair_run_citations("projects/atlas.md", page, "")
    assert "- People: Unknown\n" in fixed and "- Repository: example/atlas [1]" in fixed
    assert "investigation:page" not in fixed


def test_dropped_reports_exact_quote_and_source_losses():
    from connectonion.rem.page_review import dropped, quotes
    before = ('# Avery Lin\n\n“Keep [these words](https://example.com) unchanged”. [7]\n'
              '\n```text\n“Ignore this example”\n```\n'
              '\n## Sources\n- [7] gmail:aaaaaaaaaaaa — 2025-03-04\n')
    after = '# Avery Lin\n\nA paraphrase. [1]\n\n## Sources\n- [1] github:acme/lantern#12\n'
    assert quotes(before) == {'Keep these words unchanged'}
    assert dropped(before, after) == [
        'Dropped quote the page had: “Keep these words unchanged”',
        'Dropped source id the page had: gmail:aaaaaaaaaaaa']
    renumbered = before.replace('[7]', '[1]').replace('[these words](https://example.com)', 'these words')
    assert dropped(before, renumbered) == []


def test_restore_dropped_uses_current_numbers_and_keeps_before_order():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery\n\n## Who they are\n'
              '- “Small tools travel far”. [56][W2]\n- “Keep the interface quiet”. [56]\n\n'
              '## Sources\n- [56] https://profile.example.test — profile\n'
              '- [W2] gmail:avery — 2026-10-01\n')
    after = ('# Avery\n\n## Who they are\nNew work. [1]\n\n## Insight\nA useful connection. [3]\n\n'
             '## Sources\n- [1] codex:new\n- [3] https://profile.example.test — existing\n'
             '- [W1] gmail:avery — 2026-10-01\n')
    restored = restore_dropped(before, after)
    assert ('New work. [1]\n- “Small tools travel far”. [3][W1]\n'
            '- “Keep the interface quiet”. [3]\n\n## Insight') in restored
    assert restored.count('https://profile.example.test') == 1
    assert dropped(before, restored) == []
    assert restore_dropped(before, restored) == restored


@pytest.mark.parametrize('separator', [' ', ': ', ':'])
def test_restore_dropped_appends_full_source_definition_for_a_lost_id(separator):
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery\n\n## Insight\nA profile detail. [56][57]\n\n## Sources\n'
              f'  - [56]{separator}https://profile.example.test — profile captured 2026-10-01\n'
              '- [57] gmail:avery — original message\n')
    after = '# Avery\n\n## Insight\nNew work. [2]\n\n## Sources\n- [2] gmail:avery — kept\n'
    restored = restore_dropped(before, after)
    assert 'A profile detail. [3][2]' in restored
    assert f'  - [3]{separator}https://profile.example.test — profile captured 2026-10-01\n' in restored
    assert dropped(before, restored) == []
    assert restore_dropped(before, restored) == restored


def test_restore_dropped_places_missing_section_lines_before_sources_once():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery\n\n## Old section\n- “Keep useful details”. [7]\n'
              '- “Keep useful details”. [7]\n\n## Another old section\nA second detail. [8]\n\n'
              '## Sources\n- [7] gmail:avery\n- [8] https://other.example.test\n')
    after = '# Avery\n\n## Insight\nNew work. [1]\n\n## Sources\n- [1] codex:new\n'
    restored = restore_dropped(before, after)
    assert ('- “Keep useful details”. [2]\nA second detail. [3]\n\n## Sources') in restored
    assert restored.count('Keep useful details') == 1
    assert '## Old section' not in restored
    assert dropped(before, restored) == []


def test_restore_dropped_adds_sources_when_candidate_has_none():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = '# Avery\n\n“Keep useful details”. [W3]\n\n## Sources\n- [W3] https://profile.example.test — profile\n'
    restored = restore_dropped(before, '# Avery\n\nNew work.\n')
    assert '“Keep useful details”. [1]\n\n## Sources\n- [1] https://profile.example.test — profile' in restored
    assert dropped(before, restored) == []


def test_restore_dropped_keeps_numeric_markdown_links():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery\n\n## Insight\n- “Use [1](https://example.test) simple tool”. [7]\n\n'
              '## Sources\n- [7] gmail:avery\n')
    after = '# Avery\n\n## Insight\nNew work. [1]\n\n## Sources\n- [1] codex:new\n'
    restored = restore_dropped(before, after)
    assert '- “Use [1](https://example.test) simple tool”. [2]' in restored
    assert dropped(before, restored) == []


def test_project_timeline_is_not_a_citable_original():
    candidate = '# Lantern\n\nStarted in March. [1]\n\n## Sources\n- [1] investigation:timeline\n'
    errors = validate('projects/lantern.md', candidate, '# Lantern\n', [
        {'role': 'timeline', 'source': 'investigation:timeline', 'text': 'Project history'}])
    assert 'Project timeline is a reading guide, not a citable original: 1' in errors


def test_a_restored_line_keeps_the_writer_rewrite_and_adds_missing_evidence_beside_it():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery Lin\n\n## Who they are\nAvery leads Lantern [1]. Her profile says “building in Sydney,” [2]\n\n'
              '## Sources\n- [1] gmail:aaaaaaaaaaaa\n- [2] https://example.com/avery\n')
    after = '# Avery Lin\n\n## Who they are\nAvery leads Lantern [1].\n\n## Sources\n- [1] gmail:aaaaaaaaaaaa\n'
    restored = restore_dropped(before, after)
    assert dropped(before, restored) == []
    assert ('Avery leads Lantern [1].\n'
            'Avery leads Lantern [1]. Her profile says “building in Sydney,” [2]') in restored


@pytest.mark.parametrize('heading', ['History', 'Key decisions'])
@pytest.mark.parametrize('reverse', [False, True])
def test_same_date_history_duplicates_keep_longer_line_and_merge_all_citations(heading, reverse):
    from connectonion.rem.page_review import sort_history
    short = '- 2026-10-20: Avery Lin shipped Lantern. [1][W1]'
    long = '- **2026-10-20** — Avery Lin shipped Lantern with a smaller interface. [2]'
    lines = [short, long, short] if not reverse else [long, short, short]
    other = '- 2026-10-19: Avery Lin shipped Lantern. [3]'
    page = (f'# Lantern\n\n## {heading}\n' + '\n\n'.join([*lines, other])
            + '\n\n## Sources\n- [1] gmail:aaaaaaaaaaaa\n- [2] github:acme/lantern#12\n'
            '- [3] github:acme/lantern#13\n- [W1] https://example.com/lantern\n')
    result = sort_history(page)
    assert long + ' [1][W1]\n' + other in result
    assert result.count('Avery Lin shipped Lantern') == 2
    assert not re.search(r'^- [^\n]+\n(?:[ \t]*\n)+- ', result.partition('\n## Sources')[0], re.M)
    assert sort_history(result) == result


def test_exact_history_duplicates_collapse_but_distinct_same_date_decisions_remain():
    from connectonion.rem.page_review import sort_history
    first = '- 2026-10-20: Ship the smaller Lantern interface. [1]'
    second = '- 2026-10-20: Archive the abandoned database migration. [2]'
    page = f'# Lantern\n\n## Key decisions\n{first}\n{first}\n{second}\n'
    assert sort_history(page) == page.replace(f'{first}\n{first}', first)


def test_restore_keeps_rewrite_with_new_sources_and_restores_lost_evidence():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery Lin\n\n## Who they are\n'
              'Avery leads Lantern. “Keep small tools” [7]. Her profile says “building in Sydney” [8].\n\n'
              '## Sources\n- [7] gmail:aaaaaaaaaaaa\n- [8] https://example.com/avery\n')
    rewrite = 'Avery leads Lantern. “Keep small tools” [1][3].'
    after = (f'# Avery Lin\n\n## Who they are\n{rewrite}\n\n## Sources\n'
             '- [1] gmail:aaaaaaaaaaaa\n- [3] github:acme/lantern#12\n')
    result = restore_dropped(before, after)
    assert rewrite + '\nAvery leads Lantern.' in result
    assert 'Her profile says “building in Sydney” [4].' in result
    assert '- [3] github:acme/lantern#12' in result
    assert dropped(before, result) == []
    assert restore_dropped(before, result) == result


def test_restore_checks_loss_again_after_each_line_to_avoid_repeating_shared_quote():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery Lin\n\n## Insight\n- First: “Keep small tools”. [7]\n'
              '- Second: “Keep small tools”. [7]\n\n## Sources\n- [7] gmail:aaaaaaaaaaaa\n')
    after = '# Avery Lin\n\n## Insight\nNew work. [1]\n\n## Sources\n- [1] github:acme/lantern#12\n'
    result = restore_dropped(before, after)
    assert result.count('“Keep small tools”') == 1
    assert dropped(before, result) == []


@pytest.mark.parametrize('wording,count', [('“Keep small tools”', 1), ('Keep small tools', 2)])
def test_history_dedupe_merges_only_a_line_whose_quotes_the_longer_keeps(wording, count):
    from connectonion.rem.page_review import dropped, restore_dropped, sort_history
    short = '- 2026-10-20: Avery Lin said “Keep small tools” for Lantern. [1]'
    long = f'- 2026-10-20: Avery Lin said {wording} for Lantern and shipped the smaller interface. [2]'
    page = (f'# Lantern\n\n## Key decisions\n{short}\n{long}\n\n## Sources\n'
            '- [1] gmail:aaaaaaaaaaaa\n- [2] github:acme/lantern#12\n')
    result = sort_history(page)
    assert result.count('- 2026-10-20:') == count
    assert '“Keep small tools”' in result
    assert dropped(page, result) == []
    assert restore_dropped(page, result) == result
    assert sort_history(result) == result


def test_restore_never_replaces_rewrite_citing_new_id_even_when_number_was_reused():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery Lin\n\n## Insight\nAvery leads Lantern. “Keep small tools”. [1]\n\n'
              '## Sources\n- [1] gmail:aaaaaaaaaaaa\n')
    rewrite = 'Avery leads Lantern. [1]'
    after = f'# Avery Lin\n\n## Insight\n{rewrite}\n\n## Sources\n- [1] github:acme/lantern#12\n'
    result = restore_dropped(before, after)
    assert rewrite + '\nAvery leads Lantern. “Keep small tools”. [2]' in result
    assert '- [1] github:acme/lantern#12' in result
    assert dropped(before, result) == []


def test_restore_cannot_lose_an_earlier_quote_when_another_quote_is_retained_elsewhere():
    from connectonion.rem.page_review import dropped, restore_dropped
    prefix = 'Avery Lin leads Lantern in Sydney and keeps its tools small. '
    first = prefix + '“Stay calm”. [1]'
    second = prefix + '“Keep small tools” and file the request. [1][2]'
    before = (f'# Avery Lin\n\n## Insight\n{first}\n{second}\n\n## Sources\n'
              '- [1] gmail:aaaaaaaaaaaa\n- [2] github:acme/lantern#12\n')
    after = (f'# Avery Lin\n\n## Insight\n{first}\nThey said “Keep small tools”. [1]\n\n'
             '## Sources\n- [1] gmail:aaaaaaaaaaaa\n')
    result = restore_dropped(before, after)
    assert first + '\n' + second in result
    assert dropped(before, result) == []
    assert restore_dropped(before, result) == result


@pytest.mark.parametrize("line, fixed", [
    ("The user said it was still open on his side and he would complete it [1].",
     "The user said it was still open on the user's side and the user would complete it [1]."),
    ("Avery said she would reply; the user said he would wait for her reply [3].",
     "Avery said she would reply; the user said the user would wait for her reply [3]."),
    ("The user thanked Jordan and he said the demo was done [2].",
     "The user thanked Jordan and he said the demo was done [2]."),
    ("The user wrote “he is ready” to Avery [1].", "The user wrote “he is ready” to Avery [1]."),
    ("Avery said she is away from her desk [1].", "Avery said she is away from her desk [1]."),
])
def test_a_pronoun_that_stands_for_the_owner_becomes_the_user(line, fixed):
    """The owner's rule is never guess a pronoun; reruns still wrote "the user said he" 1-14 times a page."""
    from connectonion.rem.page_review import owner_pronouns
    page = f"# Avery Lin\n\n{line}\n\n## Sources\n- [1] gmail:a — 2026-10-01 he\n"
    text, count = owner_pronouns(page)
    assert text == page.replace(line, fixed)
    assert count == (line != fixed) * (2 if "his side" in line else 1 if line != fixed else 0)


def test_a_key_decision_that_retells_the_owner_is_named_for_repair():
    from connectonion.rem.page_review import unquoted_decisions
    from connectonion.rem.runner import SALVAGEABLE
    page = ("# Atlas\n\n## Key decisions\n- 2026-10-19 — Share it as a tool: the user suggested a direct message [1]\n"
            "- 2026-10-14 — Lead with context: “Don't send the result, send the context” [2]\n\n## Paths\n- /atlas\n")
    errors = unquoted_decisions(page)
    assert len(errors) == 1 and "2026-10-19" in errors[0]
    assert errors[0].startswith(SALVAGEABLE)   # repaired if it can be, never a refusal


@pytest.mark.parametrize("page, fixed", [
    ("# Avery Lin\n\nAvery said she would apply. The user was her manager and submitted her reference [4]. "
     "The user said it was open on his side [4].\n",
     "# Avery Lin\n\nAvery said she would apply. The user was her manager and submitted her reference [4]. "
     "The user said it was open on the user's side [4].\n"),
    ("# Jordan Lee\n\nJordan said he would meet. The user said he would send the deck [1].\n",
     "# Jordan Lee\n\nJordan said he would meet. The user said he would send the deck [1].\n"),
])
def test_a_pronoun_the_page_uses_for_its_subject_is_never_the_users(page, fixed):
    """2026-10-20: the first owner-pronoun repair wrote "the user was the user's direct manager"."""
    from connectonion.rem.page_review import owner_pronouns
    assert owner_pronouns(page)[0] == fixed


def test_a_qualified_first_contact_is_put_back_over_unknown():
    from connectonion.rem.page_review import restore_runner_fields
    original = ("# Avery Lin\n\n## Facts\n- First contact: 2026-08-11 (earliest mail found) [2]\n\n"
                "## Sources\n- [2] gmail:abc — 2026-08-11\n")
    candidate = original.replace("2026-08-11 (earliest mail found) [2]", "Unknown")
    assert restore_runner_fields("people/avery.md", candidate, original) == original


def test_a_facts_label_the_turn_left_out_comes_back_from_the_page_before():
    """2026-10-20 upkeep A/B: a dropped `Location` line refused the whole update, twice in three runs."""
    from connectonion.rem.files import Notebook
    from connectonion.rem.page_review import restore_missing_facts, fact_errors
    import tempfile
    from pathlib import Path
    notebook = Notebook(Path(tempfile.mkdtemp()))
    notebook.stub_person("people/avery.md", "Avery Lin", ["avery@example.com"], email="avery@example.com")
    original = (notebook.read("people/avery.md").replace("- Location: Unknown", "- Location: Sydney [1]")
                .replace("- (none yet)", "- [1] gmail:abc — 2026-10-01"))
    candidate = original.replace("- Location: Sydney [1]\n", "").replace("- Phone: Unknown\n", "")
    fixed = restore_missing_facts("people/avery.md", candidate, original)
    assert "- Location: Sydney [1]" in fixed and "- Phone: Unknown" in fixed
    assert not [e for e in fact_errors("people/avery.md", fixed, original) if e.startswith("Missing")]
    assert fixed.index("- Phone:") < fixed.index("- Location:")


def test_a_restored_facts_line_takes_its_own_emptied_field_never_another():
    """2026-10-20 upkeep A/B: a dropped First contact line was restored over `- Location: Unknown`."""
    from connectonion.rem.page_review import restore_dropped
    before = ("# Avery Lin\n\n## Facts\n- Location: Unknown\n- First contact: 2026-08-11 (earliest mail found) [2]\n"
              "- Last contact: 2026-08-12 [1]\n\n## Sources\n- [1] gmail:a — 2026-08-12\n- [2] gmail:b — 2026-08-11\n")
    after = before.replace("2026-08-11 (earliest mail found) [2]", "Unknown").replace("- [2] gmail:b — 2026-08-11\n", "")
    assert restore_dropped(before, after) == before


def test_a_restored_line_does_not_replace_a_short_row_inside_a_code_fence():
    from connectonion.rem.page_review import dropped, restore_dropped
    diagram = '## Overview\n```text\nUser\n  v\nLantern\n```\n'
    before = (f'# Lantern\n\n{diagram}\n## Uncertainties\n- A request to delete “zero-risk things” names no subject [1].\n\n'
              '## Sources\n- [1] codex:s:1 — 2026-10-12\n')
    after = f'# Lantern\n\n{diagram}\n## Uncertainties\nUnknown\n\n## Sources\n- [1] codex:s:1 — 2026-10-12\n'
    restored = restore_dropped(before, after)
    assert dropped(before, restored) == [] and '  v\n' in restored


def test_a_carried_quote_that_is_not_in_its_source_is_not_guarded():
    from connectonion.rem.page_review import dropped, restore_dropped
    before = ('# Avery Lin\n\n## Who they are\nAvery signs as “Avery | Founder of Lantern.” [1]\n\n'
              '## Sources\n- [1] gmail:aaaaaaaaaaaa\n')
    after = ('# Avery Lin\n\n## Who they are\nAvery signs off as “Avery” and “Founder, Lantern” [1].\n\n'
             '## Sources\n- [1] gmail:aaaaaaaaaaaa\n')
    exempt = frozenset({'Avery | Founder of Lantern.'})
    assert dropped(before, after, exempt) == []
    assert restore_dropped(before, after, exempt) == after
    assert dropped(before, after) != []


@pytest.mark.parametrize("line", ["- It is unclear whether Avery replied [2].", "- 目前无法确认是否完成 [2]",
                                  "Avery may have sent it; this cannot be confirmed [1]."])
def test_unclear_whether_and_its_chinese_forms_are_hedges_the_editing_turn_removes(line):
    from connectonion.rem.page_review import hedged_lines
    page = f"# Avery Lin\n\nAvery is a tester [1].\n\n## History\n{line}\n\n## Uncertainties\n- Unknown\n"
    assert hedged_lines(page)

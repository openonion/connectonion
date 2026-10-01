import json
import re
from pathlib import Path

import pytest

from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook
from connectonion.rem.page_review import normalize, normalize_numbered_sources, validate
from connectonion.rem.runner import RunFailed, run_stage, task_prompt


def test_legacy_project_gets_missing_sections_without_losing_content():
    old = '# Atlas\n\n## What it is\nA demo.\n\n## Sources\n- [1] source:1\n\nInvestigation: mapped today\n'
    new = normalize('projects/atlas.md', old)
    assert 'A demo.' in new
    assert all(new.count('## '+h+'\n') == 1 for h in Notebook.PROJECT_SECTIONS)
    assert normalize('projects/atlas.md', new) == new


def test_long_material_is_readable_and_the_exact_copy_is_kept(tmp_path):
    item = {'text': 'x\\"\n中' * 3000, 'source': 'fixture:1'}
    prompt = task_prompt(tmp_path, [item], 'investigate')
    readable = (tmp_path / 'material.md').read_text()
    assert max(map(len, readable.splitlines())) <= 400
    assert json.loads((tmp_path / 'material.json').read_text())[0]['text'] == item['text']
    assert 'material.md' in prompt or '<material>' in prompt


def test_numbered_source_list_is_normalized_without_changing_claims():
    text = ('# Aurora\n\nThe date is open. [1]\n\n## Sources\n'
            '1. `codex:synthetic:1` — user correction\n'
            '   Continued description.\n\nInvestigation: mapped today\n')
    normalized = normalize_numbered_sources(text)
    assert '- [1] `codex:synthetic:1` — user correction' in normalized
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


@pytest.mark.parametrize('invalid', [False, True])
def test_investigation_promotes_only_valid_new_candidate(tmp_path, monkeypatch, invalid):
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    candidate = old.replace('## What it is\n- Unknown — not investigated yet', '## What it is\nA local demo. [1]')
    candidate = candidate.replace('- (none yet)', '- [1] observed 2026-09-19 — fixture:readme')
    candidate = candidate.replace('- Unknown — not investigated yet', '- Unknown')
    if invalid:
        candidate += '\n## Overview\nDuplicate\n'
    def run(directory, prompt, config, stage):
        path = Path(re.search(r'NEW file (.+?candidate.md)', prompt)[1])
        from connectonion.useful_tools.file_tools.write import write
        assert 'Successfully' in write(str(path), candidate)
        return {'usage': {'input_tokens': 7}}
    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    items = [{'role': 'page', 'record': 'projects/atlas.md', 'text': old}, {'source': 'fixture:readme', 'text': 'A local demo.'}]
    if invalid:
        with pytest.raises(RunFailed, match='Duplicate'):
            run_stage(nb, items, default_config(), stage='investigate')
        assert nb.read('projects/atlas.md') == old
    else:
        assert run_stage(nb, items, default_config(), stage='investigate')['changed'] == ['projects/atlas.md']
        assert nb.read('projects/atlas.md') == candidate


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
        assert (working / record).read_text() == original
        assert 'Write notebook Markdown pages directly' not in prompt
        if action == 'wrong_target':
            (working / record).write_text('# Accidental direct edit')
        else:
            nb.write(record, original + '\nConcurrent user correction.\n')
            Path(re.search(r'NEW file (.+?candidate.md)', prompt)[1]).write_text(original)
        return {'usage': {'input_tokens': 5}}
    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    with pytest.raises(RunFailed):
        run_stage(nb, [{'role': 'page', 'record': record, 'text': original}], default_config(), stage='investigate')
    assert nb.read(record) == original + ('\nConcurrent user correction.\n' if action == 'concurrent_update' else '')
    result = json.loads(next((tmp_path / '.state/tasks').glob('*/result.json')).read_text())
    assert result['status'] == 'failed' and result['usage']['input_tokens'] == 5
    assert result['duration_seconds'] >= 0
    assert result['instructions_chars'] > 0 and result['material_chars'] > 0


def test_prior_page_citation_is_identifiable_only_as_supplied_context():
    from connectonion.rem.page_review import prior_context_reference
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
    # Box-drawing arrows are a flow too: a real candidate drew one and the page was refused.
    ('```text\n[Markdown file]\n      │\n      ▼\n[Word counts]\n```\nObserved flow. [1]', False),
    ('```text\nmemo → transcript → note\n```\nObserved flow. [1]', False),
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
    monkeypatch.setattr('connectonion.rem.runner.run_task', execute)
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
    assert result['usage']['input_tokens'] == 9
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
    sections = "".join(f"\n## {s}\n- Unknown\n" for s in Notebook.PERSON_SECTIONS)
    contact = "\n".join(f"- {label}: Unknown" for label in Notebook.PERSON_CONTACT)
    page = ("# Mia Chen\n\nMia is the user's pilot client and owes the signed SOW by 3 October [{n}]. "
            f"Last contact: 2026-09-10 [1].\n\n## Contact\n{contact}\n{sections}\n## Sources\n"
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


def test_an_investigated_page_that_still_says_not_investigated_yet_is_refused(tmp_path):
    """#2008: project pages came back after 0.6-0.9M tokens with five and six
    sections still saying "Unknown — not investigated yet"."""
    from connectonion.rem import runner
    from connectonion.rem.page_review import placeholder_errors
    from connectonion.rem.runner import RunFailed
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_project('projects/atlas.md', 'Atlas')
    old = nb.read('projects/atlas.md')
    written = (old.replace('## What it is\n- Unknown — not investigated yet', '## What it is\nA local demo. [1]')
               .replace('- (none yet)', '- [1] observed 2026-09-19 — fixture:readme'))
    errors = placeholder_errors(written)
    assert len(errors) == 1 and 'Where it stands' in errors[0] and 'What it is' not in errors[0]
    assert 'bare "Unknown"' in errors[0]
    finished = written.replace('- Unknown — not investigated yet', '- Unknown')
    assert placeholder_errors(finished) == []
    items = [{'role': 'page', 'record': 'projects/atlas.md', 'text': old},
             {'source': 'fixture:readme', 'text': 'A local demo.'}]
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written)
    with pytest.raises(RunFailed, match='not investigated yet'):
        runner._promote_candidate(nb, 'projects/atlas.md', candidate, old, items, tmp_path, None)
    assert nb.read('projects/atlas.md') == old
    candidate.write_text(finished)
    runner._promote_candidate(nb, 'projects/atlas.md', candidate, old, items, tmp_path, None)
    assert 'A local demo. [1]' in nb.read('projects/atlas.md')


def test_the_project_skills_ask_for_the_overview_and_no_placeholder_and_never_guess_a_dictated_name():
    from connectonion.rem import project_pages
    from connectonion.rem.runner import instructions
    for text in (project_pages.instructions(), instructions('investigate', page_kind='project')):
        assert 'is required' in text and 'Overview' in text
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
    grown = _grown(old, 25_255)
    assert PAGE_LIMIT == 20_000
    errors = size_errors(grown, old)
    assert errors and '25,' in errors[0] and '20,000' in errors[0] and 'History' in errors[0]
    assert any('20,000' in error for error in validate('projects/atlas.md', grown, old, []))
    assert size_errors(_grown(old, 18_000), old) == []               # growth under the limit: fine
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


def test_a_history_past_eight_milestones_may_not_grow_and_may_come_down():
    """Ody Zhou's History held 17 bullets, five of them "sent report X"."""
    from connectonion.rem.page_review import history_errors, history_note
    assert history_errors(_with_history(9), _with_history(8))
    assert 'at most 8' in history_errors(_with_history(9), _with_history(3))[0]
    assert history_errors(_with_history(8), _with_history(3)) == []
    assert history_errors(_with_history(12), _with_history(17)) == []          # coming down in steps
    assert 'fold the oldest' in history_note(_with_history(17))
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

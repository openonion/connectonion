"""Offline research captures reach validation in both investigation paths."""
import json
from pathlib import Path

import pytest

from connectonion.rem import evidence, project_claim_review, project_pages, runner
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, RemError
from connectonion.rem.page_review import misquoted
from connectonion.rem.reader_model import cited_context


def capture(directory, source='https://example.org/team', body='Mira Vale leads the Atlas project.'):
    web = directory / 'web'
    web.mkdir(parents=True)
    (web / 'team.md').write_text(body)
    (web / 'sources.json').write_text(json.dumps([
        {'url': source, 'file': 'team.md', 'date': '2026-11-06'}]))
    return source


@pytest.mark.parametrize('kind', ['person', 'project', 'org'])
def test_research_policy_reaches_each_investigation_kind(kind):
    text = runner.instructions('investigate', page_kind=kind)
    for rule in ['Research beyond the mailbox', 'co search', '--engine ddg', 'co fetch',
                 'co browser help', 'co browser --help', 'own tab', 'close', 'linkedin.com',
                 'snippet', 'co gmail', 'co outlook', 'lark-cli', 'gh', '1–3 questions',
                 'web/sources.json', 'Inference:', '[personal]', '[sensitive]']:
        assert rule in text
    assert 'longer is not better' not in text
    assert 'Do not rewrite' in text


@pytest.mark.parametrize('native', [False, True])
def test_runner_prompt_allows_research_and_task_captures(tmp_path, native):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    record = 'people/mira.md'
    book.stub_person(record, 'Mira Vale')
    directory = tmp_path / '.state/tasks/research'
    directory.mkdir(parents=True)
    task = runner.prepare(book, [{'role': 'page', 'record': record}], default_config(),
                          stage='investigate', directory=directory, native=native)
    assert 'web/sources.json' in task['prompt']
    assert 'read-only research' in task['prompt']
    assert 'Write only that candidate file' not in task['prompt']


def test_project_session_prompt_allows_research_and_preserves_existing_page(tmp_path):
    candidate = tmp_path / 'candidate.md'
    text = project_pages.prompt(tmp_path, [{'role': 'page', 'source': 'investigation:page',
                                          'text': '# Atlas\n\nExisting supported history.'}], candidate)
    assert 'co search' in text and 'web/sources.json' in text
    for prohibition in ['Read no other files', 'This run is offline', 'Only these supplied snapshots may be read',
                        'Read no original checkout', 'NEW file']:
        assert prohibition not in text
    assert candidate.read_text() == '# Atlas\n\nExisting supported history.'
    assert 'Do not rewrite' in text


@pytest.mark.parametrize('native', [False, True])
def test_saved_web_quote_is_checked_and_retained_after_promotion(tmp_path, native):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    record = 'orgs/atlas.md'
    book.stub_org(record, 'Atlas', 'example.org')
    original = book.read(record)
    directory = tmp_path / '.state/tasks/research'
    source = capture(directory)
    candidate = directory / 'candidate.md'
    text = original.replace('Unknown — not investigated yet', 'Unknown')
    text = text.replace('## Our relationship\n', '## Our relationship\n“Mira Vale leads the Atlas project.” [1]\n')
    text = text.replace('## Sources\n', f'## Sources\n- [1] {source} — 2026-11-06\n')
    candidate.write_text(text)
    runner._promote_candidate(book, record, candidate, original, [], directory, None, native=native)
    saved = book.read(record)
    assert 'Mira Vale leads' in saved
    runner.scrub_task(directory)
    assert misquoted(tmp_path, record, saved, []) == []
    assert misquoted(tmp_path, record, saved.replace('leads the Atlas', 'founded the Atlas'), [])
    contexts = cited_context(tmp_path, [{'text': saved}])
    assert contexts[source]['excerpt'] == 'Mira Vale leads the Atlas project.'
    material, missing = project_claim_review.packet(book, saved)
    assert missing == [] and material['sources'][0]['context']['excerpt'] == contexts[source]['excerpt']


def test_wrong_saved_web_quote_is_refused_before_audit(tmp_path):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    record = 'orgs/atlas.md'
    book.stub_org(record, 'Atlas', 'example.org')
    original = book.read(record)
    directory = tmp_path / '.state/tasks/research'
    source = capture(directory)
    candidate = directory / 'candidate.md'
    text = original.replace('Unknown — not investigated yet', 'Unknown')
    text = text.replace('## Our relationship\n', '## Our relationship\n“Mira Vale founded Atlas.” [1]\n')
    candidate.write_text(text.replace('## Sources\n', f'## Sources\n- [1] {source} — 2026-11-06\n'))
    with pytest.raises(runner.RunFailed, match='Quote is not in its cited source'):
        runner._promote_candidate(book, record, candidate, original, [], directory, None)
    assert book.read(record) == original


@pytest.mark.parametrize('source', ['https://linkedin.com/in/mira', 'https://www.linkedin.com/in/mira'])
def test_captures_refuse_linkedin_pages(tmp_path, source):
    capture(tmp_path, source)
    with pytest.raises(RemError, match='LinkedIn'):
        evidence.research_items(tmp_path)


def test_search_capture_can_include_linkedin_snippet(tmp_path):
    source = capture(tmp_path, 'https://www.google.com/search?q=Mira+Vale',
                     'LinkedIn result snippet: Mira Vale — Atlas lead.')
    assert evidence.research_items(tmp_path)[0]['source'] == source


def test_inference_is_explicitly_allowed_in_claim_audit(tmp_path):
    prepare(tmp_path)
    text = '# Atlas\n\n- Inference: a Python service because it depends on FastAPI [1].\n\n## Sources\n- [1] https://example.org/requirements.txt\n'
    task = project_claim_review.prepare(Notebook(tmp_path), text, record='projects/atlas.md',
        items=[{'source': 'https://example.org/requirements.txt', 'text': 'fastapi==1.0'}])
    assert 'Inference:' in task['prompt']
    assert 'need not appear literally' in task['prompt']


def test_vanished_rollout_count_reaches_investigation_coverage(tmp_path, monkeypatch):
    from connectonion.rem import investigate, source
    store = tmp_path / 'sessions'
    store.mkdir()
    path = store / 'rollout-vanished.jsonl'
    path.touch()
    monkeypatch.setattr(source, 'source_files', lambda sub: [path])
    real_open = Path.open

    def vanish(file, *args, **kwargs):
        if file == path:
            path.unlink(missing_ok=True)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', vanish)
    items, coverage = investigate.gather('Mira Vale', ['mira'], days=1, clients={},
        subscriptions={'codex': {'kind': 'codex', 'root': str(store)}}, archive_root=tmp_path / 'notebook')
    assert items == []
    assert any('1 vanished session file(s) skipped' in line for line in coverage)


@pytest.mark.parametrize('source', ['gmail:abc', 'outlook:abc'])
def test_native_capture_cannot_override_supplied_mail(tmp_path, source):
    capture(tmp_path, source, 'The fee is 8% of gross revenue.')
    originals = [{'source': source, 'text': 'The fee is 8% of net revenue.'}]
    additions = evidence.additional_research(tmp_path, tmp_path, originals)
    page = f'# Atlas\n\n“The fee is 8% of gross revenue.” [1]\n\n## Sources\n- [1] {source}\n'
    assert misquoted(tmp_path, 'orgs/atlas.md', page, originals + additions)


def test_retained_private_capture_requires_private_reader(tmp_path):
    source = capture(tmp_path, 'lark:message-1', 'Mira shared health information [sensitive].')
    page = f'# Mira\n\nHealth information [sensitive] [1]\n\n## Sources\n- [1] {source} — 2026-11-06\n'
    evidence.retain_research(tmp_path, page, evidence.research_items(tmp_path))
    assert cited_context(tmp_path, [{'text': page}]) == {}
    assert '[sensitive]' in cited_context(tmp_path, [{'text': page}], private=True)[source]['excerpt']


def test_new_web_quote_without_a_capture_is_refused(tmp_path):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    record = 'orgs/atlas.md'
    book.stub_org(record, 'Atlas', 'example.org')
    original = book.read(record)
    directory = tmp_path / '.state/tasks/research'
    directory.mkdir(parents=True)
    text = original.replace('Unknown — not investigated yet', 'Unknown')
    text = text.replace('## Our relationship\n', '## Our relationship\n“Invented web words.” [1]\n')
    text = text.replace('## Sources\n', '## Sources\n- [1] https://example.org/unread — 2026-11-06\n')
    candidate = directory / 'candidate.md'
    candidate.write_text(text)
    with pytest.raises(runner.RunFailed, match='Web citation needs a saved capture'):
        runner._promote_candidate(book, record, candidate, original, [], directory, None)
    assert book.read(record) == original


def test_researched_project_insight_does_not_require_assigned_session_inputs(tmp_path):
    from connectonion.rem.page_review import validate
    text = ('# Atlas\n\n## Insight\n- Inference: a Python service because its public manifest uses FastAPI [1].\n'
            '\n## Open threads\n- 2026-11-06 — Mira asked: “Review the API.” [1]\n'
            '\n## Sources\n- [1] https://example.org/project\n')
    items = [{'role': 'project-input-scope', 'inputs_read': 0},
             {'role': 'research', 'source': 'https://example.org/project',
              'text': 'fastapi==1.0; Mira: Review the API.'}]
    errors = validate('projects/atlas.md', text, '# Atlas\n', items, root=tmp_path)
    assert not any('No assigned project session inputs' in error for error in errors)
    evidence.retain_research(tmp_path, text, [{**items[1], 'timestamp': '2026-11-06'}])
    carried_errors = validate('projects/atlas.md', text, text, items[:1], root=tmp_path)
    assert not any('No assigned project session inputs' in error for error in carried_errors)


def test_project_session_candidate_starts_with_actual_page_not_material_wrapper(tmp_path):
    original = '# Atlas\n\n## Facts\n- Status: active [1]\n\n## Sources\n- [1] codex:atlas:1\n'
    items = [{'role': 'page', 'source': 'investigation:page',
              'text': 'The page as it stands, at projects/atlas.md:\n\n' + original}]
    candidate = tmp_path / 'candidate.md'
    project_pages.prompt(tmp_path, items, candidate)
    assert candidate.read_text() == original


@pytest.mark.parametrize('provider', ['gmail', 'outlook'])
def test_native_capture_cannot_override_archived_mail(tmp_path, provider):
    import hashlib
    from connectonion.rem.mail_archive import retain_message

    prepare(tmp_path)
    native = 'message-atlas'
    source = provider + ':' + hashlib.sha256(native.encode()).hexdigest()[:12]
    retain_message(tmp_path, provider, {'id': native, 'date': '2026-11-06T00:00:00Z',
                   'from': 'mira@example.org', 'subject': 'Atlas fee'},
                   'The fee is 8% of net revenue.', fetched_at='2026-11-06T00:00:00Z')
    capture(tmp_path, source, 'The fee is 8% of gross revenue.')
    additions = evidence.additional_research(tmp_path, tmp_path, [])
    page = f'# Atlas\n\n“The fee is 8% of gross revenue.” [1]\n\n## Sources\n- [1] {source}\n'
    assert misquoted(tmp_path, 'orgs/atlas.md', page, additions)


@pytest.mark.parametrize('source', ['https://example.org/team', 'github:atlas/team#1'])
def test_duplicate_research_captures_merge_text_once_per_url_or_native_id(tmp_path, source):
    capture(tmp_path, source, 'Mira leads Atlas.')
    web = tmp_path / 'web'
    (web / 'later.md').write_text('Atlas builds research tools.')
    rows = [{'source': source, 'file': file, 'date': date} for file, date in [
        ('team.md', '2026-11-05'), ('later.md', '2026-11-06'), ('team.md', '2026-11-05')]]
    (web / 'sources.json').write_text(json.dumps(rows))
    assert evidence.research_items(tmp_path) == [{
        'role': 'research', 'source': source, 'text': 'Mira leads Atlas.\n\nAtlas builds research tools.',
        'timestamp': '2026-11-06'}]


@pytest.mark.parametrize('native', [False, True])
def test_duplicate_web_capture_does_not_discard_an_investigation(tmp_path, native):
    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'orgs/atlas.md'
    book.stub_org(record, 'Atlas', 'example.org')
    original = book.read(record)
    directory = tmp_path / '.state/tasks/research'
    source = capture(directory, body='Mira leads Atlas.')
    web = directory / 'web'
    (web / 'later.md').write_text('Atlas builds research tools.')
    rows = json.loads((web / 'sources.json').read_text())
    rows.append({'url': source, 'file': 'later.md', 'date': '2026-11-06'})
    (web / 'sources.json').write_text(json.dumps(rows))
    candidate = directory / 'candidate.md'
    text = original.replace('Unknown — not investigated yet', 'Unknown')
    text = text.replace('## Our relationship\n',
        '## Our relationship\n“Mira leads Atlas.” “Atlas builds research tools.” [1]\n')
    candidate.write_text(text.replace('## Sources\n', f'## Sources\n- [1] {source} — 2026-11-06\n'))
    runner._promote_candidate(book, record, candidate, original, [], directory, None, native=native)
    saved = book.read(record)
    assert 'Mira leads Atlas.' in saved and 'Atlas builds research tools.' in saved
    assert not misquoted(tmp_path, record, saved, [])


@pytest.mark.parametrize('native', [False, True])
def test_investigation_restores_filled_facts_replaced_with_unknown(tmp_path, native):
    from connectonion.rem import facts

    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'people/mira.md'
    book.stub_person(record, 'Mira Vale')
    original = book.read(record).replace('Unknown — not investigated yet', 'Unknown')
    original = original.replace('- How we know them: Unknown', '- How we know them: Founder programme [1]')
    original = original.replace('- Also known as: Unknown', '- Also known as: mira@example.org')
    original = original.replace('- Links: Unknown', '- Links: [UNSW Founders](https://unswfounders.com/accelerators) [1]')
    original = original.replace('## Who they are\n', '## Who they are\nMira leads Atlas. [1]\n')
    original = original.replace('## Sources\n', '## Sources\n- [1] gmail:atlas — 2026-11-06\n')
    book.write(record, original)
    directory = tmp_path / '.state/tasks/research'
    directory.mkdir(parents=True)
    candidate = directory / 'candidate.md'
    text = original.replace('Founder programme [1]', 'Unknown').replace('mira@example.org', 'Unknown')
    text = text.replace('[UNSW Founders](https://unswfounders.com/accelerators) [1]', 'Unknown')
    candidate.write_text(text)
    items = [{'source': 'gmail:atlas', 'text': 'Mira leads Atlas. Founder programme.'}]
    runner._promote_candidate(book, record, candidate, original, items, directory, None, native=native)
    saved = facts.parse(book.read(record), record)
    assert saved['How we know them'][0]['value'] == 'Founder programme'
    assert saved['How we know them'][0]['citations']
    assert saved['Also known as'][0]['value'] == 'mira@example.org'
    assert saved['Links'][0]['value'] == '[UNSW Founders](https://unswfounders.com/accelerators)'
    assert saved['Links'][0]['citations']


def test_restored_unknown_fact_keeps_source_identity_when_numbers_change():
    from connectonion.rem.page_review import restore_missing_facts

    original = ('# Mira\n\n## Facts\n- How we know them: Founder programme [1]\n\n'
                '## Sources\n- [1] gmail:programme — 2026-11-05\n')
    candidate = ('# Mira\n\n## Facts\n- How we know them: Unknown\n\n'
                 '## Sources\n- [1] gmail:new — 2026-11-06\n')
    saved = restore_missing_facts('people/mira.md', candidate, original)
    assert '- How we know them: Founder programme [2]' in saved
    assert '- [2] gmail:programme — 2026-11-05' in saved
    assert '- [1] gmail:new — 2026-11-06' in saved


def test_supported_fact_preservation_and_location_timezone_derivation_are_in_person_rules():
    text = runner.instructions('investigate', page_kind='person')
    for rule in ['Never replace a filled Facts field', 'original source IDs', 'stated reason',
                 'Australia/Sydney (from location) [n]', "location's source", 'several time zones',
                 'do not guess a fixed UTC offset']:
        assert rule in text


@pytest.mark.parametrize('kind', ['people', 'orgs', 'projects'])
def test_every_facts_line_is_guarded_and_restored_with_its_source(kind):
    from connectonion.rem import facts
    from connectonion.rem.page_review import fact_regressions, restore_missing_facts

    record = f'{kind}/atlas.md'
    for label in (*facts.fields(record), 'Notebook-specific field',
                  'A notebook-specific fact label longer than forty characters'):
        value = '[UNSW Founders](https://unswfounders.com/accelerators)'
        original = f'# Atlas\n\n## Facts\n- {label}: {value} [17]\n\n## Sources\n- [17] gmail:old\n'
        candidate = (f'# Atlas\n\n## Facts\n- {label}: Unknown\n\n'
                     '## Sources\n- [17] gmail:new\n')
        assert any(f': {label};' in error for error in fact_regressions(record, candidate, original))
        saved = restore_missing_facts(record, candidate, original)
        assert f'- {label}: {value} [18]' in saved
        assert '- [18] gmail:old' in saved and '- [17] gmail:new' in saved
        assert not fact_regressions(record, saved, original)
        assert not fact_regressions(record, candidate, original, removed={label})


@pytest.mark.parametrize(('location', 'zone'), [
    ('UNSW Sydney 2052', 'Australia/Sydney'), ('NSW', 'Australia/Sydney'),
    ('Melbourne VIC', 'Australia/Melbourne'), ('Brisbane QLD', 'Australia/Brisbane'),
    ('Perth WA', 'Australia/Perth'), ('Adelaide SA', 'Australia/Adelaide'),
    ('Hobart TAS', 'Australia/Hobart'), ('Darwin NT', 'Australia/Darwin'),
    ('Canberra ACT', 'Australia/Sydney'), ('Beijing, China', 'Asia/Shanghai'),
    ('Shanghai', 'Asia/Shanghai'), ('China', 'Asia/Shanghai'),
    ('Hong Kong, China', 'Asia/Hong_Kong'), ('Singapore', 'Asia/Singapore'),
    ('Tokyo', 'Asia/Tokyo'), ('London, UK', 'Europe/London'), ('UK', 'Europe/London'),
    ('New York, USA', 'America/New_York'), ('California, USA', 'America/Los_Angeles'),
    ('Seattle, Washington, USA', 'America/Los_Angeles'),
    ('Toronto, Canada', 'America/Toronto'), ('Vancouver, BC, Canada', 'America/Vancouver'),
    ('Unknown', None), ('Australia', None), ('USA', None), ('Canada', None),
    ('Springfield, USA', None), ('Ontario, Canada', None), ('Washington', None),
    ('London, Ontario, Canada', None), ('Melbourne, Florida, USA', None),
    ('Sydney / London', None), ('Sydney / Brisbane', None), ('Sydney / Paris', None),
    ('Perth, Scotland', None), ('London, Kentucky', None), ('Sydney, Nova Scotia', None),
    ('Vancouver, Washington', None), ('SA', None), ('WA', None), ('Victoria', None),
    ('Paris / Sydney', None), ('Scotland, Perth', None), ('Washington, Vancouver', None),
])
def test_timezone_from_cited_unambiguous_location(location, zone):
    from connectonion.rem.page_review import timezone_from_location

    original = (f'# Mira\n\n## Facts\n- Location: {location} [17][18]\n- Time zone: Unknown\n\n'
                '## Sources\n- [17] gmail:location\n- [18] gmail:signature\n')
    expected = original.replace('- Time zone: Unknown', f'- Time zone: {zone} (from location) [17][18]') if zone else original
    assert timezone_from_location('people/mira.md', original) == expected
    assert timezone_from_location('people/mira.md', expected) == expected
    assert timezone_from_location('orgs/mira.md', original) == original
    assert timezone_from_location('people/mira.md', original.replace(' [17][18]', '')) == original.replace(' [17][18]', '')
    filled = original.replace('- Time zone: Unknown', '- Time zone: Asia/Tokyo [18]')
    assert timezone_from_location('people/mira.md', filled) == filled


@pytest.mark.parametrize('native', [False, True])
def test_promotion_derives_timezone_after_restoring_location(tmp_path, native):
    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'people/mira.md'
    book.stub_person(record, 'Mira Vale')
    original = book.read(record).replace('Unknown — not investigated yet', 'Unknown')
    original = original.replace('- Location: Unknown', '- Location: UNSW Sydney 2052 [17]')
    original = original.replace('## Who they are\n', '## Who they are\nMira leads Atlas. [17]\n')
    original = original.replace('## Sources\n', '## Sources\n- [17] gmail:atlas — 2026-11-06\n')
    book.write(record, original)
    directory = tmp_path / '.state/tasks/research'
    directory.mkdir(parents=True)
    candidate = directory / 'candidate.md'
    candidate.write_text(original.replace('UNSW Sydney 2052 [17]', 'Unknown'))
    items = [{'source': 'gmail:atlas', 'text': 'Mira leads Atlas. UNSW Sydney 2052.'}]
    runner._promote_candidate(book, record, candidate, original, items, directory, None, native=native)
    from connectonion.rem import facts
    saved = facts.parse(book.read(record), record)
    assert saved['Time zone'][0]['value'] == 'Australia/Sydney'
    assert saved['Time zone'][0]['qualifier'] == 'from location'
    assert saved['Time zone'][0]['citations'] == saved['Location'][0]['citations']


def test_maintenance_derives_timezone_after_restoring_location(tmp_path):
    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'people/mira.md'
    book.stub_person(record, 'Mira Vale')
    original = book.read(record).replace('- Location: Unknown', '- Location: UNSW Sydney 2052 [1]')
    original = original.replace('## Sources\n', '## Sources\n- [1] gmail:location — 2026-11-06\n')
    book.write(record, original)
    working = Notebook(tmp_path / 'working')
    working.write(record, original.replace('UNSW Sydney 2052 [1]', 'Unknown'))
    directory = tmp_path / '.state/tasks/maintenance'
    directory.mkdir(parents=True)
    items = [{'source': 'gmail:location', 'text': 'UNSW Sydney 2052'}]
    refusals = runner._promote_maintenance(book, working, {record: original}, items, directory, None, False)
    assert refusals == []
    assert '- Time zone: Australia/Sydney (from location) [1]' in book.read(record)


@pytest.mark.parametrize('path', ['investigate', 'project-sessions', 'native-project'])
def test_customer_research_rules_reach_all_project_task_paths(tmp_path, path):
    from connectonion.rem import native

    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'projects/atlas.md'
    book.stub_project(record, 'Atlas', ['/work/atlas'])
    directory = tmp_path / '.state/tasks/project'
    directory.mkdir(parents=True)
    items = [{'role': 'page', 'record': record, 'source': 'investigation:page', 'text': book.read(record)}]
    if path == 'investigate':
        task = runner.prepare(book, items, default_config(), stage='investigate', directory=directory, native=True)
        text = (directory / 'instructions.md').read_text()
    else:
        text = project_pages.prompt(directory, items, directory / 'candidate.md')
        if path == 'native-project':
            stage_task = {'prompt': text + runner.today_note(tmp_path), 'candidate': str(directory / 'candidate.md'),
                          'items': items, 'before': {record: book.read(record)}}
            task = {'id': 'native-project-fixture', 'directory': str(directory), 'task': stage_task,
                    'handler': 'project', 'stage': 'investigate', 'record': record, 'round': 1,
                    'created_at': '2026-11-06', 'run': {'id': 'project-fixture'}}
            text = native._save(tmp_path, {}, task)['instructions']
    for rule in ['## Research beyond the mailbox', 'co search', 'web/sources.json',
                 'who the customer/organisation is and what it does', 'at least one outside lookup',
                 'explicitly say why none', 'existing repository snapshot is not an outside lookup']:
        assert rule in text
    assert text.count('# Investigate one subject\n') == 1


@pytest.mark.parametrize('prefix', ['Now', 'Changed', 'At stake', 'Pattern', 'Inference'])
def test_duplicate_insight_shapes_merge_without_losing_findings_or_citations(prefix):
    from connectonion.rem.page_review import merge_insight_shapes

    page = (f'# Atlas\n\n## Insight\n- {prefix}: First finding. [1]\n'
            f'- {prefix}: Second finding with “exact words”. [2]\n'
            f'- {prefix}: First finding. [1]\n\n## Open threads\n- {prefix}: Outside Insight stays. [3]\n')
    saved = merge_insight_shapes(page)
    insight = saved.split('## Insight\n')[1].split('## Open threads')[0]
    assert insight.count(f'- {prefix}:') == 1
    assert insight.count('First finding. [1]') == 1
    assert 'Second finding with “exact words”. [2]' in insight
    assert f'## Open threads\n- {prefix}: Outside Insight stays. [3]' in saved
    assert merge_insight_shapes(saved) == saved


def test_duplicate_insight_moves_continuation_with_its_finding():
    from connectonion.rem.page_review import merge_insight_shapes

    page = ('# Atlas\n\n## Insight\n- Changed: First finding. [1]\n'
            '- At stake: Friday deadline. [2]\n- Changed: Second finding.\n'
            '  “Exact supporting words.” [3]\n\n## Sources\n'
            '- [1] gmail:first\n- [2] gmail:deadline\n- [3] gmail:second\n')
    saved = merge_insight_shapes(page)
    assert 'Second finding.\n  “Exact supporting words.” [3]\n- At stake:' in saved
    assert saved.count('- Changed:') == 1
    assert merge_insight_shapes(saved) == saved


@pytest.mark.parametrize('native', [False, True])
def test_promotion_merges_duplicate_insight_prefixes(tmp_path, native):
    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'people/mira.md'
    book.stub_person(record, 'Mira Vale')
    original = book.read(record)
    text = original.replace('Unknown — not investigated yet', 'Unknown')
    text = text.replace('## Insight\n- Unknown',
        '## Insight\n- Changed: The client approved scoped delivery. [1]\n'
        '- Changed: The repository introduced mobile charts. [2]')
    text = text.replace('## Sources\n', '## Sources\n- [1] gmail:first\n- [2] gmail:second\n')
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(text)
    items = [{'source': 'gmail:first', 'text': 'The client approved scoped delivery.'},
             {'source': 'gmail:second', 'text': 'The repository introduced mobile charts.'}]
    runner._promote_candidate(book, record, candidate, original, items, tmp_path, None, native=native)
    saved = book.read(record)
    assert saved.count('- Changed:') == 1
    assert 'client approved scoped delivery.' in saved and 'repository introduced mobile charts.' in saved


@pytest.mark.parametrize('label', ['Role', 'Last contact'])
@pytest.mark.parametrize('reason', [True, False])
@pytest.mark.parametrize('native', [False, True])
def test_cited_fact_clearing_requires_source_removal_and_ledger_reason(tmp_path, monkeypatch, label, reason, native):
    from types import SimpleNamespace
    from connectonion.rem import facts

    monkeypatch.setattr(runner, 'AUDIT', SimpleNamespace(get=lambda: False))
    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'people/mira.md'
    book.stub_person(record, 'Mira Vale')
    value = 'CTO' if label == 'Role' else '2026-10-01'
    original = book.read(record).replace('Unknown — not investigated yet', 'Unknown')
    original = original.replace('Investigation: mapped', 'Investigation: investigated')
    original = original.replace(f'- {label}: Unknown', f'- {label}: {value} [1]')
    original = original.replace('## Sources\n', '## Sources\n- [1] gmail:invalidated\n')
    book.write(record, original)
    text = original.replace(f'- {label}: {value} [1]', f'- {label}: Unknown')
    text = text.replace('- [1] gmail:invalidated\n', '- [1] gmail:correction\n')
    text = text.replace('## Who they are\n', '## Who they are\nMira leads Atlas. [1]\n')
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(text)
    report = f'- Removed fact: {label} — original attributed to a namesake; gmail:correction.' if reason else ''
    items = [{'source': 'gmail:correction', 'text': 'Mira leads Atlas. Previous evidence concerns a namesake.'}]
    result = {'result': report}
    runner.promote_with_repairs(book, record, candidate, original, items, tmp_path, result,
        workdir=tmp_path, config=default_config(), stage='investigate', repairs=0, native=native,
        run=lambda *args: pytest.fail('Offline correction must not call a model'))
    saved = facts.parse(book.read(record), record)
    assert bool(saved[label]) is not reason
    if not reason:
        assert saved[label][0]['value'] == value


def test_filled_fact_lost_during_later_cleanup_is_sent_back_to_repair(tmp_path):
    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'people/mira.md'
    book.stub_person(record, 'Mira Vale')
    original = book.read(record).replace('Unknown — not investigated yet', 'Unknown')
    original = original.replace('- Role: Unknown', '- Role: Founder [1]')
    original = original.replace('## Sources\n', '## Sources\n- [1] gmail:atlas\n')
    book.write(record, original)
    text = original.replace('Founder [1]', 'Unsupported replacement')
    text = text.replace('## Who they are\n', '## Who they are\nMira leads Atlas. [1]\n')
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(text)
    with pytest.raises(runner.RunFailed, match='Filled fact became Unknown: Role'):
        runner._promote_candidate(book, record, candidate, original, [], tmp_path, None)
    assert book.read(record) == original


def test_unknown_alias_annotation_with_address_does_not_crash_cleanup():
    from connectonion.rem.facts import names_not_addresses

    page = '# Mira\n\n## Facts\n- Also known as: Unknown (mira@example.org)\n'
    assert '- Also known as: Unknown\n' in names_not_addresses('people/mira.md', page)


def test_new_alias_address_cleanup_does_not_leave_an_unused_source(tmp_path):
    prepare(tmp_path)
    book, record = Notebook(tmp_path), 'people/mira.md'
    book.stub_person(record, 'Mira Vale')
    original = book.read(record)
    text = original.replace('Unknown — not investigated yet', 'Unknown')
    text = text.replace('- Also known as: Unknown', '- Also known as: new@example.org [1]')
    text = text.replace('## Who they are\n', '## Who they are\nMira leads Atlas. [2]\n')
    text = text.replace('## Sources\n', '## Sources\n- [1] gmail:alias\n- [2] gmail:atlas\n')
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(text)
    items = [{'source': 'gmail:alias', 'text': 'new@example.org'},
             {'source': 'gmail:atlas', 'text': 'Mira leads Atlas.'}]
    runner._promote_candidate(book, record, candidate, original, items, tmp_path, None)
    saved = book.read(record)
    assert '- Also known as: Unknown' in saved
    assert 'gmail:alias' not in saved and 'Mira leads Atlas.' in saved

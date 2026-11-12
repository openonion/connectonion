"""Topics require independent dated evidence; aliases alone never assert a link."""
from pathlib import Path

from connectonion.rem.files import Notebook, read_json, state_path


def topic(notebook, name='Thermal storage', aliases='heat storage', *, dates=('2026-01-01', '2026-01-08', '2026-01-15'), sentence='Mara discussed thermal storage.', speaker='Mara'):
    for record in ('people/mara.md', 'projects/cove.md'):
        notebook.write(record, '# ' + Path(record).stem.title() + '\n')
    path = notebook.root / '.state/extracts/batch.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('## Topics\n' + '\n'.join(
        f'- {name} | {aliases} | {record} | {speaker}, {day}, gmail:source{i} | {sentence}'
        for i, (day, record) in enumerate(zip(dates, ('people/mara.md', 'projects/cove.md', 'people/mara.md')))))
    return path


def test_exact_threshold_and_scan_is_read_only(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    topic(notebook)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    row, = scan_topics(notebook)
    assert row['qualified'] and row['source_count'] == 3 and row['span_days'] == 14
    assert row['records'] == ['people/mara.md', 'projects/cove.md']
    assert set(row['aliases']) == {'Thermal storage', 'heat storage'}
    assert len(row['evidence']) == 3
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_repeated_digest_and_page_citations_are_not_new_sources(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    path = topic(notebook, dates=('2026-01-01', '2026-01-08', '2026-01-14'))
    (path.parent / 'copy.md').write_text(path.read_text())
    row, = scan_topics(notebook)
    assert not row['qualified'] and row['source_count'] == 3 and row['span_days'] == 13
    path.write_text(path.read_text().replace('gmail:source1', 'gmail:source0').replace('gmail:source2', 'gmail:source0'))
    (path.parent / 'copy.md').unlink()
    assert not any(row['qualified'] for row in scan_topics(notebook))


def test_single_record_cannot_qualify_but_explicit_owner_request_can(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    path = topic(notebook)
    path.write_text(path.read_text().replace('projects/cove.md', 'people/mara.md'))
    assert not scan_topics(notebook)[0]['qualified']
    path.write_text('## Topics\n- Thermal storage | heat storage | people/mara.md | user, 2026-01-01, codex:abc:1 | Remember Thermal storage.\n')
    assert scan_topics(notebook)[0]['qualified']
    path.write_text(path.read_text().replace('| user,', '| Mara,'))
    assert not scan_topics(notebook)[0]['qualified']


def test_generic_vendor_and_existing_entity_aliases_are_excluded(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    path = topic(notebook)
    notebook.write('projects/cove.md', '# Cove\n- Also known as: Thermal storage\n')
    assert scan_topics(notebook) == []
    notebook.write('projects/cove.md', '# Cove\n')
    for name in ('email', 'meeting', 'Google'):
        path.write_text(f'## Topics\n- {name} | | people/mara.md | user, 2026-01-01, codex:abc:1 | Remember {name}.\n')
        assert scan_topics(notebook) == []


def test_a_common_noun_behind_an_article_is_not_a_topic_name(tmp_path):
    """"The draft" named seven unrelated drafts; a topic needs a name that says which one."""
    from connectonion.rem.topic_map import generic_name, scan_topics
    notebook = Notebook(tmp_path)
    for name in ('The draft', 'the Draft', 'Draft', 'Notes', 'a summary', '-', ''):
        assert generic_name(name), name
    for name in ('Thermal storage', 'The Harbour lease', 'Brightlane pilot', 'the draft lease'):
        assert not generic_name(name), name
    path = topic(notebook, name='The draft', aliases='')
    assert scan_topics(notebook) == []
    path.write_text(path.read_text().replace('The draft', 'The Harbour lease'))
    assert [row['name'] for row in scan_topics(notebook)] == ['The Harbour lease']


def test_alias_groups_are_transitive_and_doubtful_pages_become_reviews(tmp_path):
    from connectonion.rem.topic_map import map_topics, scan_topics
    from connectonion.rem.reviews import listing, decide
    notebook = Notebook(tmp_path)
    path = topic(notebook)
    path.write_text(path.read_text() + '\n- Heat batteries | heat storage | projects/cove.md | user, 2026-01-20, gmail:source4 | Heat batteries store energy.\n')
    notebook.write('people/ellis.md', '# Ellis\nHeat storage was mentioned.\n')
    row, = scan_topics(notebook)
    assert 'Heat batteries' in row['aliases']
    rows, created = map_topics(notebook)
    record = rows[0]['record']
    assert created == [record]
    assert '(../people/ellis.md)' not in notebook.read(record)
    review, = listing(tmp_path)
    assert review['kind'] == 'link' and review['subjects'] == [record, 'people/ellis.md']
    decide(tmp_path, review['id'], 'no', author='owner')
    map_topics(notebook)
    assert len(listing(tmp_path)) == 1
    assert '(../people/ellis.md)' not in notebook.read(record)


def test_accepted_topic_review_writes_only_topic_end(tmp_path):
    from connectonion.rem.topic_map import map_topics
    from connectonion.rem.reviews import listing, decide
    notebook = Notebook(tmp_path)
    topic(notebook)
    notebook.write('people/ellis.md', '# Ellis\nHeat storage was mentioned.\n')
    rows, _ = map_topics(notebook)
    original = notebook.read('people/ellis.md')
    decide(tmp_path, listing(tmp_path)[0]['id'], 'yes', author='owner')
    assert '(../people/ellis.md)' in notebook.read(rows[0]['record'])
    assert notebook.read('people/ellis.md') == original


def test_personal_topics_are_labelled_and_other_peoples_health_never_qualifies(tmp_path):
    from connectonion.rem.topic_map import map_topics, scan_topics
    notebook = Notebook(tmp_path)
    for name in ('Family planning', 'Personal budget', 'Visa appeal', 'My asthma'):
        topic(notebook, name, name, speaker='user', sentence=f'Remember {name}; this concerns my life.')
        rows, _ = map_topics(notebook)
        assert '[personal]' in notebook.read(rows[0]['record']).splitlines()[0]
    topic(notebook, 'Mara asthma', 'asthma', sentence='Mara has asthma.', speaker='user')
    assert not any('Mara asthma' == row['name'] for row in scan_topics(notebook))


def test_existing_topics_sharing_exact_alias_reuse_merge(tmp_path):
    from connectonion.rem.topic_map import map_topics
    from connectonion.rem.merge import resolve
    notebook = Notebook(tmp_path)
    topic(notebook)
    notebook.write('knowledge/thermal.md', '# Thermal storage\n- Also known as: heat storage\n\n## What it is\nStores heat.\n')
    notebook.write('knowledge/battery.md', '# Heat batteries\n- Also known as: heat storage\n\n## Timeline\n- 2026-01-01: Started.\n')
    rows, created = map_topics(notebook)
    assert len(notebook.list('knowledge')) == 1 and created == []
    kept = rows[0]['record']
    assert resolve(tmp_path, 'knowledge/thermal.md') == kept
    assert resolve(tmp_path, 'knowledge/battery.md') == kept
    assert 'Stores heat.' in notebook.read(kept) and 'Started.' in notebook.read(kept)


def test_legacy_knowledge_names_use_only_their_own_dated_citations(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    notebook.write('people/mara.md', '# Mara\n## Insight\n- **Thermal storage** stores heat. [1][2]\n## Sources\n- [1] gmail:a — 2026-01-01\n- [2] gmail:b — 2026-01-08\n')
    notebook.write('projects/cove.md', '# Cove\n## What it is\n- Thermal storage for the port. [1]\n## Sources\n- [1] gmail:c — 2026-01-15\n')
    row, = scan_topics(notebook)
    assert row['qualified'] and row['source_count'] == 3
    assert all(e['source'].startswith('gmail:') for e in row['evidence'])


def test_owner_health_cannot_be_inferred_from_first_person_in_anothers_sentence(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    topic(notebook, 'Mara asthma', 'asthma', speaker='user', sentence="Remember Mara asthma; I discussed Mara's asthma.")
    assert scan_topics(notebook) == []


def test_private_marker_on_cited_page_evidence_survives_plain_text(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    notebook.write('people/mara.md', '# Mara\n## Insight\n- **Estate planning** is mine. [personal] [1][2]\n## Sources\n- [1] gmail:a — 2026-01-01\n- [2] gmail:b — 2026-01-08\n')
    notebook.write('projects/cove.md', '# Cove\n- Estate planning discussion. [3]\n## Sources\n- [3] gmail:c — 2026-01-15\n')
    assert scan_topics(notebook)[0]['private']


def test_map_builds_topics_and_a_second_map_keeps_investigated_prose(tmp_path, monkeypatch):
    from connectonion.rem.map import build_map
    notebook = Notebook(tmp_path)
    topic(notebook)
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *args, **kwargs: [])
    first = build_map(tmp_path, {}, {}, skill_directories=[])
    record = first['topics'][0]['record']
    assert record in first['created']
    page = notebook.read(record).replace('## What it is\n', '## What it is\nA heat reserve. [1]\n')
    notebook.write(record, page)
    second = build_map(tmp_path, {}, {}, skill_directories=[])
    assert second['topics'][0]['record'] == record
    assert notebook.read(record) == page


def test_topic_investigation_uses_aliases_and_candidate_context(tmp_path):
    from connectonion.rem.topic_map import map_topics, topic_material
    from connectonion.rem.investigate import page_handles
    from connectonion.rem.runner import instructions
    notebook = Notebook(tmp_path)
    topic(notebook)
    rows, _ = map_topics(notebook)
    record = rows[0]['record']
    _, handles = page_handles(notebook, record)
    assert 'heat storage' in handles
    assert any('gmail:source0' in item['text'] for item in topic_material(notebook, record))
    assert 'A topic\'s page' in instructions('investigate', page_kind='topic')
    assert len(instructions('investigate', page_kind='topic')) <= 24000


def test_request_is_affirmative_and_names_this_topic(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    path = topic(notebook)
    for sentence in ('Do not remember Thermal storage.', 'Remember other things; Thermal storage is irrelevant.'):
        path.write_text(f'## Topics\n- Thermal storage | heat storage | people/mara.md | user, 2026-01-01, codex:abc:1 | {sentence}\n')
        assert not scan_topics(notebook)[0]['qualified']


def test_completed_extraction_retains_topics_after_task_workspace_disappears(tmp_path):
    import tempfile
    from connectonion.rem.extract import check
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    topic(notebook)
    original = (tmp_path / '.state/extracts/batch.md').read_text()
    (tmp_path / '.state/extracts/batch.md').unlink()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        (directory / 'notes.md').write_text(original)
        (directory / 'instructions.md').write_text('extract')
        check({'directory': str(directory), 'candidate': str(directory / 'notes.md'), 'summary': False, 'root': str(tmp_path)}, {})
    assert scan_topics(notebook)[0]['qualified']


def test_invalid_model_dates_are_not_evidence(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    path = topic(notebook)
    path.write_text(path.read_text().replace('2026-01-01', '2026-99-99'))
    row, = scan_topics(notebook)
    assert row['source_count'] == 2 and not row['qualified']


def test_third_party_health_is_not_owner_health_when_the_owner_has_a_friend(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    topic(notebook, 'Mara asthma', 'asthma', speaker='user', sentence='Remember Mara asthma; my friend has asthma.')
    assert scan_topics(notebook) == []


def test_topic_validation_preserves_privacy_and_rejects_session_links(tmp_path):
    from connectonion.rem.page_review import validate
    notebook = Notebook(tmp_path)
    notebook.stub_topic('knowledge/health.md', 'My health', ['health'], private=True)
    original = notebook.read('knowledge/health.md')
    candidate = original.replace('[personal]', '').replace('## People\n', '## People\n- [Session](../sessions/a.md) [1]\n').replace('## Sources\n', '## Sources\n- [1] manual:a — 2026-01-01\n')
    errors = validate('knowledge/health.md', candidate, original, [{'source': 'manual:a', 'text': 'Owner health.'}])
    assert any('privacy' in error.lower() for error in errors)
    assert any('sessions' in error.lower() for error in errors)


def test_topic_queue_and_cli_name_resolution_are_usable(tmp_path):
    from connectonion.rem.topic_map import map_topics
    from connectonion.rem.queue import order
    from connectonion.rem.census import counts
    from connectonion.cli.commands.rem_commands import _resolve_page
    notebook = Notebook(tmp_path)
    topic(notebook)
    rows, _ = map_topics(notebook)
    record = rows[0]['record']
    assert order(tmp_path, 'topics')[0]['path'] == record
    assert counts(tmp_path)['knowledge']['mapped'] == 1
    assert _resolve_page(notebook, 'heat storage') == record


def test_topic_gather_searches_mail_bodies_by_every_alias(tmp_path):
    from connectonion.rem.investigate import gather
    from datetime import datetime, timedelta, timezone
    class Mail:
        def __init__(self):
            self.queries = []
        def my_addresses(self):
            return ['owner@example.test']
        def list_search(self, query, max_results=10):
            self.queries.append(query)
            assert max_results <= 500
            return [{'id': 'message1', 'from': 'mara@example.test', 'to': 'owner@example.test',
                     'subject': 'Following up', 'date': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}]
        def get_email_body(self, message_id):
            return 'Heat batteries would serve the port.'
    mail = Mail()
    rows, _ = gather('Thermal storage', ['Thermal storage', 'heat batteries'], days=60,
                     clients={'gmail': mail}, subscriptions={}, record='knowledge/heat.md')
    assert mail.queries == ['"thermal storage"', '"heat batteries"']
    assert len(rows) == 1 and 'Heat batteries' in rows[0]['text']


def test_topic_reads_alias_body_from_local_mail_without_provider(tmp_path):
    from connectonion.rem.investigate import gather
    from connectonion.rem.files import write_json
    from datetime import datetime, timedelta, timezone
    write_json(tmp_path / '.state/mail/observed/gmail/a.json', {'provider': 'gmail', 'id': 'a',
               'from': 'mara@example.test', 'to': 'owner@example.test', 'subject': 'Following up',
               'date': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), 'body': 'Heat batteries would serve the port.'})
    rows, _ = gather('Thermal storage', ['Thermal storage', 'heat batteries'], days=60,
                     clients={}, subscriptions={}, record='knowledge/heat.md', archive_root=tmp_path)
    assert len(rows) == 1 and 'Heat batteries' in rows[0]['text']


def test_similar_slug_is_not_an_exact_alias_merge(tmp_path):
    from connectonion.rem.topic_map import map_topics
    notebook = Notebook(tmp_path)
    path = topic(notebook)
    path.write_text(path.read_text() + '\n- Thermal-storage | reservoir | projects/cove.md | user, 2026-01-01, manual:second | Remember Thermal-storage.\n')
    rows, created = map_topics(notebook)
    assert len({row['record'] for row in rows}) == 2
    assert len(created) == 2


def test_conflicting_summary_dates_cannot_create_the_time_span(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    topic(notebook, dates=('2026-01-01', '2026-01-01', '2026-01-01'))
    notebook.write('projects/cove.md', '# Cove\nThermal storage is discussed. [1]\n## Sources\n- [1] gmail:source0 — 2026-01-15\n')
    assert not scan_topics(notebook)[0]['qualified']


def test_vendor_alias_does_not_discard_a_distinct_subject(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    topic(notebook, 'Professional outreach', 'LinkedIn')
    row, = scan_topics(notebook)
    assert row['qualified'] and row['aliases'] == ['Professional outreach']


def test_cited_page_cannot_erase_an_explicit_owner_request(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    path = topic(notebook)
    path.write_text('## Topics\n- Thermal storage | heat storage | people/mara.md | user, 2026-01-01, gmail:source0 | Remember Thermal storage.\n')
    notebook.write('people/mara.md', '# Mara\nThermal storage is discussed. [1]\n## Sources\n- [1] gmail:source0 — 2026-01-01\n')
    row, = scan_topics(notebook)
    assert row['qualified'] and row['requested']
    assert row['evidence'][0]['speaker'] == 'user'


def test_session_and_skill_mentions_are_counted_without_becoming_evidence_links(tmp_path):
    from connectonion.rem.topic_map import scan_topics
    notebook = Notebook(tmp_path)
    topic(notebook)
    notebook.write('sessions/demo.md', '# Port discussion\nHeat storage was discussed.\n')
    notebook.write('skills/catalog/demo.md', '# Heat calculator\nCalculate thermal storage capacity.\n')
    notebook.write('skills/catalog/index.md', '# Skill catalog\nThermal storage tools.\n')
    row, = scan_topics(notebook)
    assert row['source_count'] == 3 and len(row['records']) == 2
    assert row['sessions'] == 1 and row['skills'] == 1


def historical_pages(notebook, name='Thermal storage'):
    notebook.write('people/mara.md', f'# Mara\n## History\n- We discussed {name}. [1][2]\n## Sources\n- [1] gmail:a — 2026-01-01\n- [2] gmail:b — 2026-01-08\n')
    notebook.write('projects/cove.md', f'# Cove\n## What it is\n- We discussed {name}. [1]\n## Sources\n- [1] gmail:c — 2026-01-15\n')


def proposed(root, *topics, day=None):
    """A proposal the summary model made earlier this week."""
    from datetime import date
    from connectonion.rem.files import write_json
    write_json(state_path(root, 'topic-proposals.json'), {'date': day or date.today().isoformat(),
               'topics': [{'name': t, 'aliases': []} if isinstance(t, str) else t for t in topics]})


def test_backfill_files_nothing_from_phrases_nobody_named(tmp_path):
    """Counted phrases were REM's own wording and mail footers; only a named subject is a candidate."""
    from connectonion.rem.topic_map import backfill_topics
    notebook = Notebook(tmp_path)
    historical_pages(notebook)
    assert backfill_topics(notebook, dry_run=True)['candidates'] == []


def test_backfill_qualifies_a_named_subject_from_plain_historical_text(tmp_path):
    from connectonion.rem.topic_map import backfill_topics
    notebook = Notebook(tmp_path)
    historical_pages(notebook)
    proposed(tmp_path, 'Thermal storage')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report = backfill_topics(notebook, dry_run=True)
    row = next(r for r in report['candidates'] if r['name'] == 'Thermal storage')
    assert row['qualified'] and row['source_count'] == 3 and row['span_days'] == 14
    assert row['records'] == ['people/mara.md', 'projects/cove.md']
    assert report['created'] == [] and report['coverage']['pages'] == 2
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_backfill_verifies_archived_mail_and_summary_sources_without_inventing_page_dates(tmp_path):
    import json
    from connectonion.rem.topic_map import backfill_topics
    from connectonion.rem.mail_archive import message_path
    notebook = Notebook(tmp_path)
    for record in ('people/mara.md', 'projects/cove.md'):
        notebook.write(record, '# ' + Path(record).stem.title() + '\nThermal storage is relevant.\n## Sources\n- [1] gmail:a — 2026-01-01\n')
    for i, day in enumerate(('2026-01-01', '2026-01-08')):
        path = message_path(tmp_path, 'gmail', chr(97 + i))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'provider': 'gmail', 'id': chr(97+i), 'date': day,
                                   'subject': 'Thermal storage', 'body': 'We discussed Thermal storage.'}))
    notebook.write('sessions/one.md', '# Heat planning\n## Summary\nThermal storage is relevant.\n## Sources\n- [1] codex:s1 — 2026-01-15\n')
    proposed(tmp_path, 'Thermal storage')
    row = next(r for r in backfill_topics(notebook, dry_run=True)['candidates'] if r['name'] == 'Thermal storage')
    assert row['qualified'] and row['source_count'] == 3
    assert {e['source'] for e in row['evidence']} == {'gmail:a', 'gmail:b', 'codex:s1'}
    assert row['sessions'] == 1


def test_backfill_is_idempotent_and_private_before_filing(tmp_path):
    from connectonion.rem.topic_map import backfill_topics
    notebook = Notebook(tmp_path)
    historical_pages(notebook, 'Visa appeal')
    proposed(tmp_path, 'Visa appeal')
    first = backfill_topics(notebook)
    record = next(r['record'] for r in first['candidates'] if r['name'] == 'Visa appeal')
    assert '[personal]' in notebook.read(record).splitlines()[0]
    original = notebook.read(record)
    assert backfill_topics(notebook)['created'] == []
    assert notebook.read(record) == original
    assert '(../people/' not in original


def test_backfill_rejects_echoes_one_record_and_undated_mentions(tmp_path):
    from connectonion.rem.topic_map import backfill_topics
    notebook = Notebook(tmp_path)
    historical_pages(notebook)
    proposed(tmp_path, 'Thermal storage')
    notebook.write('projects/cove.md', notebook.read('projects/cove.md').replace('gmail:c', 'gmail:a').replace('2026-01-15', '2026-01-01'))
    assert not any(r['qualified'] for r in backfill_topics(notebook, dry_run=True)['candidates'])
    notebook.write('projects/cove.md', '# Cove\nThermal storage.\n')
    assert not any(r['qualified'] for r in backfill_topics(notebook, dry_run=True)['candidates'])


def test_backfill_bounds_are_reported(tmp_path, monkeypatch):
    from connectonion.rem import topic_map
    notebook = Notebook(tmp_path)
    historical_pages(notebook)
    proposed(tmp_path, 'Thermal storage')
    monkeypatch.setattr(topic_map, 'BACKFILL_PAGES', 1)
    report = topic_map.backfill_topics(notebook, dry_run=True)
    assert report['coverage']['pages'] == 1 and report['coverage']['truncated']
    assert not any(r['qualified'] for r in report['candidates'])


def summary_model(tmp_path, monkeypatch, topics):
    import json
    import yaml
    from connectonion.rem.config import default_config
    from connectonion.rem.files import atomic_write
    settings = default_config()
    settings['models']['level1'] = 'fictional-summary'
    atomic_write(tmp_path / 'config.yaml', yaml.safe_dump(settings))
    calls = []
    def propose(directory, prompt, config, stage):
        calls.append(config['model'])
        assert len(prompt) <= 24_000 and stage == 'abstract'
        return {'result': json.dumps({'topics': topics}), 'usage': {}}
    monkeypatch.setattr('connectonion.rem.runner.run_task', propose)
    return calls


def test_proposal_uses_the_summary_model_once_a_week_and_cannot_file_a_hallucination(tmp_path, monkeypatch):
    from connectonion.rem.topic_map import backfill_topics
    notebook = Notebook(tmp_path)
    historical_pages(notebook)
    calls = summary_model(tmp_path, monkeypatch, [{'name': 'Thermal storage', 'aliases': []},
                                                  {'name': 'Imaginary orbit', 'aliases': ['orbit']}])
    report = backfill_topics(notebook, propose=True)
    assert calls == ['fictional-summary']
    assert not any(r['name'] == 'Imaginary orbit' for r in report['candidates'])
    assert next(r for r in report['candidates'] if r['name'] == 'Thermal storage')['qualified']
    backfill_topics(notebook, propose=True)
    assert calls == ['fictional-summary'], 'a proposal from this week is reused'


def test_a_week_old_proposal_is_asked_again_and_a_dry_run_keeps_no_cache(tmp_path, monkeypatch):
    from connectonion.rem.topic_map import backfill_topics
    notebook = Notebook(tmp_path)
    historical_pages(notebook)
    proposed(tmp_path, 'Something else', day='2020-01-01')
    calls = summary_model(tmp_path, monkeypatch, [{'name': 'Thermal storage', 'aliases': []}])
    report = backfill_topics(notebook, dry_run=True, propose=True)
    assert calls == ['fictional-summary'] and report['qualified'] == 1
    assert not notebook.list('knowledge')
    assert read_json(state_path(tmp_path, 'topic-proposals.json'), {})['date'] == '2020-01-01'

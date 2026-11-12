"""One rule for the owner's language: drafts, the reader and nightly translation read it from
languages.owner_language, and the pages behind what Today shows are translated first."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from connectonion.rem import daily, drafts, languages, native_round, translate
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, state_path, write_json


@pytest.fixture
def notebook(tmp_path, rem_clock):
    prepare(tmp_path)
    return tmp_path


def detected(root, shares):
    write_json(state_path(root, 'map.json'), {'owner': {'languages': {
        'languages': [tag for tag, share in shares.items() if share >= 0.1], 'shares': shares, 'english_terms': []}}})


def draft_prompt(root):
    return drafts.prepare(root, {'id': 'x', 'material': []}, read_config(root), directory=root)['prompt']


@pytest.mark.parametrize('tags,expected', [('en,zh', 'zh'), ('zh,en', 'zh'), ('en,zh-TW', 'zh-TW'), ('en', 'en')])
def test_a_configured_list_means_its_first_non_english_language(notebook, tags, expected):
    set_config(notebook, ['languages', tags])
    assert languages.owner_language(notebook) == expected


@pytest.mark.parametrize('shares,expected', [({'en': 0.88, 'zh': 0.12}, 'en'), ({'zh': 0.6, 'en': 0.4}, 'zh'), ({}, None)])
def test_a_detected_list_means_the_language_he_writes_most(notebook, shares, expected):
    # Detected order is by share: an owner who writes 88% English with the odd Chinese line reads English.
    detected(notebook, shares)
    assert languages.owner_language(notebook) == expected


def test_an_en_zh_owner_gets_drafts_whose_gist_why_and_slots_are_chinese(notebook):
    set_config(notebook, ['languages', 'en,zh'])
    prompt = draft_prompt(notebook)
    assert 'the owner reads 中文 (zh): write gist, why and every 【需要你：…】 slot in it' in prompt
    # The body is the skill's to decide (rem-reply-draft section 3), whatever the owner reads.
    assert "the body follows the skill's language rule (the thread's language unless the table says otherwise)" in prompt


def test_drafts_reader_and_night_translation_ask_the_same_function(notebook, monkeypatch):
    from connectonion.rem.reader import snapshot
    set_config(notebook, ['languages', 'en,zh'])
    # A reader request for another language came first; the owner's own still leads the night.
    write_json(state_path(notebook, 'translation-requests.json'), {'ja': ['people/x.md']})
    monkeypatch.setattr(languages, 'owner_language', lambda root: 'ko')
    assert '(ko)' in draft_prompt(notebook)
    assert snapshot(notebook)['owner_language'] == 'ko'
    assert translate.languages(notebook)[0] == 'ko'


def test_the_reader_language_he_asked_for_stays_ahead_of_other_configured_ones(notebook):
    # The interface has no Japanese, so a ja,ko,zh owner reads it in 中文 and asks for Chinese pages:
    # Japanese, his own, leads; his Chinese requests come before Korean, so Chinese is never last in line.
    set_config(notebook, ['languages', 'ja,ko,zh'])
    write_json(state_path(notebook, 'translation-requests.json'), {'zh': ['people/x.md']})
    assert translate.languages(notebook) == ['ja', 'zh', 'ko']


def pages(root, records):
    book = Notebook(root)
    for index, record in enumerate(records):
        book.write(record, f'# {record}\n\nText.\n')
        os.utime(root / record, (100 + index, 100 + index))


def test_the_pages_behind_todays_visible_rows_are_translated_first(notebook, monkeypatch):
    pages(notebook, ['people/mara.md', 'people/ivo.md', 'projects/new.md', 'people/rue.md'])
    monkeypatch.setattr(translate, '_waiting_pages', lambda root: {'people/mara.md'})
    rows = [{'record': 'people/rue.md', 'section': 'today'}, {'record': 'people/ivo.md', 'section': 'morning'},
            {'record': 'people/rue.md', 'section': 'today'}, {'record': 'projects/new.md', 'section': ''}]
    monkeypatch.setattr('connectonion.rem.today.queue', lambda root: rows)
    shown = translate.shown_today(notebook)
    assert shown == ['people/rue.md', 'people/ivo.md']
    # Shown on Today first, in their order; then waiting; then the newest edits.
    assert translate.backlog(notebook, 'zh', shown=shown) == ['people/rue.md', 'people/ivo.md', 'people/mara.md', 'projects/new.md']


def test_at_most_eight_visible_pages_jump_the_queue(notebook, monkeypatch):
    records = [f'people/p{index}.md' for index in range(10)]
    pages(notebook, records)
    monkeypatch.setattr(translate, '_waiting_pages', lambda root: set())
    monkeypatch.setattr('connectonion.rem.today.queue', lambda root: [{'record': record, 'section': 'today'} for record in records])
    shown = translate.shown_today(notebook)
    assert shown == records[:8]
    # The ninth and tenth fall back to newest-first among the rest.
    assert translate.backlog(notebook, 'zh', shown=shown) == records[:8] + ['people/p9.md', 'people/p8.md']


def test_todays_real_queue_on_the_invented_notebook_leads_the_backlog(tmp_path, monkeypatch, rem_clock):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build
    root = build(tmp_path / 'rem', datetime.now(timezone.utc))
    shown = translate.shown_today(root)
    # Ines (overdue receipts), Mara (the addendum) and Fernhill Labs are what the invented Today shows.
    assert shown == ['people/ines-halvorsen.md', 'people/mara-ostrowski.md', 'orgs/fernhill-labs.md']
    assert translate.backlog(root, 'zh', shown=shown)[:len(shown)] == shown


def test_a_round_reads_todays_queue_once_whatever_the_languages_and_turns(notebook, monkeypatch):
    pages(notebook, ['people/mara.md', 'people/ivo.md'])
    set_config(notebook, ['languages', 'zh,ja'])
    reads = []
    monkeypatch.setattr(translate, 'shown_today', lambda root: reads.append(1) or ['people/ivo.md'])
    monkeypatch.setattr(translate, 'prepare', lambda root, record, language, **kw: {'record': record, 'language': language})
    cursor = {'phase': 'daily-translation', 'changed': []}
    first = native_round.prepare_translation(notebook, cursor, read_config(notebook), notebook)
    cursor['translation_attempts'].append(['zh', first['record']])
    native_round.prepare_translation(notebook, cursor, read_config(notebook), notebook)
    assert first['record'] == 'people/ivo.md' and reads == [1]
    # The daily path reads it once too, before the lock, for every language it looks at.
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('', ''))
    monkeypatch.setattr('connectonion.rem.quota.read', lambda config: {'unknown': 'fixture'})
    reads.clear()
    daily._translate_changed(notebook, read_config(notebook), {}, [], lambda root, record, language: None, lambda text: None)
    assert reads == [1]


def test_a_round_that_crosses_midnight_reads_todays_queue_again(notebook, monkeypatch):
    cursor = {'task_day': '2000-01-01', 'shown_today': ['people/old.md']}
    native_round._reset_attempts(notebook, cursor)
    assert 'shown_today' not in cursor

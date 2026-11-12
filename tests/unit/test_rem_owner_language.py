"""One rule for the owner's language: drafts, the reader and nightly translation read it from
languages.owner_language, and the pages behind what Today shows are translated first."""
import os

import pytest

from connectonion.rem import drafts, languages, translate
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, state_path, write_json


@pytest.fixture
def notebook(tmp_path, rem_clock):
    prepare(tmp_path)
    return tmp_path


def draft_prompt(root):
    return drafts.prepare(root, {'id': 'x', 'material': []}, read_config(root), directory=root)['prompt']


@pytest.mark.parametrize('tags,expected', [('en,zh', 'zh'), ('zh,en', 'zh'), ('en,zh-TW', 'zh-TW'), ('en', 'en')])
def test_the_owners_language_is_his_first_non_english_one(notebook, tags, expected):
    set_config(notebook, ['languages', tags])
    assert languages.owner_language(notebook) == expected


def test_nothing_set_or_detected_is_no_language(notebook):
    write_json(state_path(notebook, 'map.json'), {'owner': {'languages': {'languages': []}}})
    assert languages.owner_language(notebook) is None


def test_an_en_zh_owner_gets_drafts_whose_gist_why_and_slots_are_chinese(notebook):
    set_config(notebook, ['languages', 'en,zh'])
    prompt = draft_prompt(notebook)
    assert 'the owner reads 中文 (zh): write gist, why and every 【需要你：…】 slot in it' in prompt
    # The body is the thread's, whatever the owner reads.
    assert "the body stays in the thread's language" in prompt


def test_drafts_reader_and_night_translation_ask_the_same_function(notebook, monkeypatch):
    from connectonion.rem.reader import snapshot
    set_config(notebook, ['languages', 'en,zh'])
    # A reader request for another language came first; the owner's own still leads the night.
    write_json(state_path(notebook, 'translation-requests.json'), {'ja': ['people/x.md']})
    monkeypatch.setattr(languages, 'owner_language', lambda root: 'ko')
    assert '(ko)' in draft_prompt(notebook)
    assert snapshot(notebook)['owner_language'] == 'ko'
    assert translate.languages(notebook)[0] == 'ko'


def test_the_pages_behind_todays_visible_rows_are_translated_first(notebook, monkeypatch):
    book = Notebook(notebook)
    for index, record in enumerate(['people/mara.md', 'people/ivo.md', 'projects/new.md', 'people/rue.md']):
        book.write(record, f'# {record}\n\nText.\n')
        os.utime(notebook / record, (100 + index, 100 + index))
    monkeypatch.setattr(translate, '_waiting_pages', lambda root: {'people/mara.md'})
    rows = [{'record': 'people/rue.md', 'section': 'today', 'rank': 0},
            {'record': 'people/ivo.md', 'section': 'morning', 'rank': 1},
            {'record': 'people/rue.md', 'section': 'today', 'rank': 2},
            {'record': 'projects/new.md', 'section': '', 'rank': 3}]
    monkeypatch.setattr('connectonion.rem.today.queue', lambda root: rows)
    # Shown on Today first, in their order; then waiting; then the newest edits.
    assert translate.backlog(notebook, 'zh') == ['people/rue.md', 'people/ivo.md', 'people/mara.md', 'projects/new.md']


def test_at_most_eight_visible_pages_jump_the_queue(notebook, monkeypatch):
    book = Notebook(notebook)
    records = [f'people/p{index}.md' for index in range(10)]
    for index, record in enumerate(records):
        book.write(record, f'# P{index}\n\nText.\n')
        os.utime(notebook / record, (100 + index, 100 + index))
    monkeypatch.setattr(translate, '_waiting_pages', lambda root: set())
    monkeypatch.setattr('connectonion.rem.today.queue',
                        lambda root: [{'record': record, 'section': 'today', 'rank': n} for n, record in enumerate(records)])
    # The ninth and tenth fall back to newest-first among the rest.
    assert translate.backlog(notebook, 'zh') == records[:8] + ['people/p9.md', 'people/p8.md']

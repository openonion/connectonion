"""#3174: what the owner did in the day is input to the night (marks, replies, hand-offs, investigations, policy)."""
import json

import pytest

from connectonion.rem import native, native_round, owner_today, service, threads
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from tests.unit.test_rem_next_submit import _feedback, trial  # noqa: F401
from tests.unit.test_rem_proactive import notebook, mail_thread  # noqa: F401
from tests.unit.test_rem_reader_threads import thread_key

pytestmark = pytest.mark.usefixtures("rem_clock")


def _a_day(root):
    """One invented day: a mark and its undo, a mark kept, an edited reply sent, a hand-off, an investigation,
    a send-policy change."""
    key = thread_key(root)
    threads.set_state(root, key, 'done')
    threads.set_state(root, key, 'open')     # undone
    threads.set_state(root, key, 'ignored')  # the state after the undo
    at = service.now().isoformat()
    state_path(root, 'drafts').mkdir(parents=True, exist_ok=True)
    write_json(state_path(root, 'drafts') / 'd1.json', {'status': 'sent', 'sent_at': at, 'record': 'people/fern.md',
               'to': 'fern@example.test', 'body': 'Thanks Fern, the review is attached.', 'prepared_body': 'Dear Fern, please find.'})
    folder = state_path(root, 'tasks') / ('do-' + 'a' * 32)
    folder.mkdir(parents=True)
    write_json(folder / 'receipt.json', {'agent': 'codex', 'result': 'completed', 'finished_at': at, 'by': 'owner',
                                         'record': 'people/fern.md', 'text': 'Prepare the pilot review'})
    runs = state_path(root, 'page-runs') / 'people'
    runs.mkdir(parents=True)
    write_json(runs / 'fern.json', {'record': 'people/fern.md', 'started_at': at, 'mode': 'full', 'result': 'completed'})
    with state_path(root, 'direct_send.jsonl').open('a') as log:
        log.write(json.dumps({'at': at, 'page': 'people/fern.md', 'value': 'partner', 'who': 'owner', 'why': 'my co-founder'}) + '\n')


def test_a_day_of_owner_actions_becomes_the_nights_digest(notebook):
    mail_thread(notebook)
    _a_day(notebook)
    text = owner_today.refresh(notebook)
    assert text == state_path(notebook, 'owner-today.md').read_text()
    for words in ('marked done', 'undid the mark on', 'ignored: You owe Fern a pilot review', 'replied to fern@example.test (edited before sending)',
                  'handed to codex (completed)', 'investigated this page', 'set send policy to partner'):
        assert words in text, words
    assert text.index('marked done') < text.index('undid the mark on') < text.index('ignored:'), 'in the order they happened'
    assert owner_today.investigated_today(notebook) == {'people/fern.md'}


def test_nothing_done_means_no_digest(notebook):
    mail_thread(notebook)
    assert owner_today.refresh(notebook) == '' and owner_today.note(notebook, 'people/fern.md') == ''


def test_every_native_task_is_shown_what_the_owner_did(trial):
    record, _ = _feedback(trial)
    owner_today.record(trial, 'mark', key=record + '\nAvery Lin requested a pilot review.', state='done')
    prompt = native.next_task(trial)['instructions']
    assert 'What the owner did since the last night' in prompt and 'marked done: Avery Lin requested a pilot review.' in prompt
    assert prompt.index('What the owner did since the last night') < prompt.index('End of memory evidence.')


def test_the_night_does_not_investigate_a_page_the_owner_investigated_today(notebook, monkeypatch):
    mail_thread(notebook)
    runs = state_path(notebook, 'page-runs') / 'people'
    runs.mkdir(parents=True)
    write_json(runs / 'fern.json', {'record': 'people/fern.md', 'started_at': service.now().isoformat(), 'mode': 'full'})
    monkeypatch.setattr(native_round, '_admit_correspondents', lambda *args: None)
    monkeypatch.setattr('connectonion.rem.people_pages.queue',
                        lambda root: [{'record': 'people/fern.md', 'path': 'people/fern.md', 'mode': 'full', 'last_activity': '2099-01-01'}])
    monkeypatch.setattr('connectonion.rem.project_pages.queue', lambda root, **kwargs: [])
    monkeypatch.setattr('connectonion.rem.daily.unfinished_by_recency', lambda root: [])
    monkeypatch.setattr('connectonion.rem.daily._owner_due', lambda root: [])
    jobs = native_round._jobs(notebook, False, [], {})
    assert 'people/fern.md' not in [job['record'] for job in jobs]


def test_a_thread_the_owner_replied_to_counts_as_answered_tonight(notebook):
    """The reply he sent closes his debt in the queue (drafts mark it sent), and the digest says so to the writer."""
    from connectonion.rem import today
    mail_thread(notebook)
    _a_day(notebook)
    assert 'replied to fern@example.test' in owner_today.note(notebook, 'people/fern.md')
    assert threads.blocked(notebook, thread_key(notebook)), 'the item he closed stays closed for the night'
    assert all(row['closed'] for row in today.queue(notebook) if row['key'] == thread_key(notebook))

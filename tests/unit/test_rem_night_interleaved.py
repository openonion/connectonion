"""Every stage produces early in a night, not only at its end (owner, 2026-11-16).

One investigation turn measured 20 to 60 minutes on a real notebook and a 3-hour
catchup night completed one page. Session summaries, Abstract and Deepen came after
the night's whole share of investigations, and translation after 8 turns, so a night
that was cut short had only investigated. Fictional people only.
"""
from subprocess import CompletedProcess

import pytest

from connectonion.rem import captured_decisions, codex_exec, depth, native, native_round, runner, schedule, service
from connectonion.rem import sessions
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from tests.unit.test_rem_night_shares import WAITING, cursor_of, notebook, person, serve  # noqa: F401

PEOPLE = [person(name) for name in ('ivy', 'wren', 'fern', 'heron', 'lark')]
SUMMARIES = [{'record': f'sessions/2026-09-0{n}-fixture.md', 'key': f'fixture-{n}'} for n in (1, 2)]


def other_stages(monkeypatch, *, translations=2):
    """Two session summaries, decision lines for any number of Abstract rounds, a translation share of 2."""
    monkeypatch.setattr(sessions, 'prepare', lambda root, rows, config, **k: {'rows': rows})
    monkeypatch.setattr(Notebook, 'read', lambda book, record: '# Fixture\n')
    monkeypatch.setattr(captured_decisions, 'material',
                        lambda book, config=None, attempted=(): [{'role': 'captured-decisions', 'record': 'people/ivy.md'}])
    monkeypatch.setattr(runner, 'prepare', lambda book, items, config, **k: {'items': items})
    monkeypatch.setattr(native_round, 'translation_share', lambda root: translations)
    monkeypatch.setattr(native_round, 'prepare_translation',
                        lambda root, cursor, config, directory: {'stage': 'translate', 'record': 'people/ivy.md'})


def settle(root, cursor, task):
    """What accepting the task does to the round, as `native._new_task` and `advance` do."""
    stage = task['stage']
    if stage == 'investigate':
        cursor['investigation_left'] -= 1
        cursor['job_index'] += 1
    elif stage == 'sessions-summary':
        cursor['summaries'] = cursor['summaries'][1:]
    elif stage == 'abstract':
        native_round.record_abstract_result(root, task['task'], promoted=True)
    return stage


def night(root, cursor, *, stop_after=None):
    """The stages of the tasks a night serves, in order, until it is done or cut short."""
    directory = root / 'task'
    directory.mkdir(exist_ok=True)
    served = []
    while stop_after is None or len(served) < stop_after:
        task = native_round.prepare_task(root, cursor, read_config(root), directory)
        if task is None:
            break
        served.append(settle(root, cursor, task))
    return served


def test_a_night_cut_short_after_its_first_portion_has_abstracted_and_translated(notebook, monkeypatch):
    serve(monkeypatch)
    other_stages(monkeypatch)
    cursor = cursor_of(notebook, list(PEOPLE), summaries=list(SUMMARIES))
    assert native_round.PORTION == 2
    served = night(notebook, cursor, stop_after=6)
    assert served == ['investigate', 'investigate', 'sessions-summary', 'abstract', 'translate', 'translate']
    # What the whole-round runners read to start the round's one deepen slot.
    assert cursor['portions'] == 1 and not cursor.get('done')


def test_investigation_resumes_after_the_break_and_every_break_serves_one_round_of_each(notebook, monkeypatch):
    serve(monkeypatch)
    other_stages(monkeypatch)
    cursor = cursor_of(notebook, list(PEOPLE), summaries=list(SUMMARIES))
    served = night(notebook, cursor, stop_after=12)
    assert served == ['investigate', 'investigate', 'sessions-summary', 'abstract', 'translate', 'translate',
                      'investigate', 'investigate', 'sessions-summary', 'abstract', 'translate', 'translate']
    assert cursor['portions'] == 2


def test_a_full_night_serves_every_share_exactly_once_and_keeps_the_leftover_queue_waiting(notebook, monkeypatch):
    serve(monkeypatch)
    other_stages(monkeypatch)
    set_config(notebook, ['limits.investigations_per_night', '3', 'limits.abstract_rounds_per_night', '3'])
    cursor = cursor_of(notebook, list(PEOPLE), summaries=list(SUMMARIES))
    served = night(notebook, cursor)
    assert served == ['investigate', 'investigate', 'sessions-summary', 'abstract', 'translate', 'translate',
                      'investigate',
                      # The share is used: what is left of the other stages, then the closing translation.
                      'sessions-summary', 'abstract', 'abstract', 'translate', 'translate']
    assert served.count('investigate') == 3 and served.count('abstract') == 3 and served.count('sessions-summary') == 2
    assert cursor['done'] and cursor['run']['outcome'] == 'completed'
    saved = read_json(state_path(notebook, WAITING), {})
    assert saved['jobs'] == PEOPLE[3:]
    assert saved['investigations'] == {'done': 3, 'limit': 3, 'waiting': 2}


def test_a_break_with_nothing_to_serve_goes_straight_back_to_investigation(notebook, monkeypatch):
    serve(monkeypatch)
    other_stages(monkeypatch, translations=0)
    monkeypatch.setattr(captured_decisions, 'material', lambda *a, **k: [])
    monkeypatch.setattr(native_round, 'prepare_translation', lambda *a: None)
    cursor = cursor_of(notebook, list(PEOPLE))
    assert night(notebook, cursor, stop_after=5) == ['investigate'] * 5


# Deepen: the round's one slot, run by whoever runs whole rounds.

def open_round(root, **fields):
    cursor = {'phase': 'daily-update', 'started_at': service.now().isoformat(), 'changed': [], 'pending': None,
              'jobs': [{'record': 'people/ivy.md', 'kind': 'person'}, {'record': 'people/wren.md', 'kind': 'person'}],
              'job_index': 0, 'current': {'record': 'people/ivy.md'}, **fields}
    write_json(state_path(root, 'round.json'), cursor)
    return cursor


def exec_night(tmp_path, monkeypatch, stages, ending):
    """An exec round whose tasks are `stages`; the first portion is done once the abstract task is prepared."""
    prepare(tmp_path)
    events, calls = [], []
    tasks = iter([*({'outcome': 'task', 'id': f'task-{n}', 'stage': stage, 'instructions': 'fixture',
                     'material': str(tmp_path)} for n, stage in enumerate(stages)), ending])

    def next_task(root, **options):
        task = next(tasks)
        portions = int('abstract' in events or task.get('stage') == 'abstract')
        saved = read_json(state_path(root, 'round.json'), {})
        open_round(root, portions=portions, done=task['outcome'] == 'done' and task['reason'] == 'round done',
                   **({'depth': saved['depth']} if 'depth' in saved else {}))
        return task

    def slot(root, **options):
        events.append('deepen')
        calls.append(options)
        return {'rounds': [{'record': 'people/wren.md'}], 'stopped': ''}

    monkeypatch.setattr(native, 'next_task', next_task)
    monkeypatch.setattr(native, 'submit', lambda *a, **k: {'outcome': 'accepted'})
    monkeypatch.setattr(runner, 'run_task', lambda *a, **k: events.append(a[-1]) or {})
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: False)
    monkeypatch.setattr(depth, 'slot', slot)
    return schedule.exec_round(tmp_path, scheduled=False), events, calls


def test_exec_deepens_after_the_first_portions_abstract_round_so_a_night_cut_short_has_deepened(tmp_path, monkeypatch):
    result, events, calls = exec_night(
        tmp_path, monkeypatch, ['investigate', 'investigate', 'abstract', 'translate'],
        {'outcome': 'done', 'reason': 'Codex quota floor reached'})
    assert events == ['investigate', 'investigate', 'abstract', 'deepen', 'translate']
    assert result['reason'] == 'Codex quota floor reached'
    assert result['depth']['rounds'] == [{'record': 'people/wren.md'}]
    # The page under investigation is not deepened under its own draft.
    assert set(calls[0]['skip']) == {'people/ivy.md'}
    assert read_json(state_path(tmp_path, 'round.json'), {})['depth'] == result['depth']


def test_a_round_that_completes_after_an_early_slot_does_not_deepen_again(tmp_path, monkeypatch):
    result, events, _ = exec_night(
        tmp_path, monkeypatch, ['investigate', 'investigate', 'abstract', 'translate', 'investigate', 'translate'],
        {'outcome': 'done', 'reason': 'round done'})
    assert events.count('deepen') == 1 and events.index('deepen') == 3
    assert result['depth']['rounds'] == [{'record': 'people/wren.md'}]


def test_exec_does_not_deepen_before_the_first_portion_is_done(tmp_path, monkeypatch):
    result, events, _ = exec_night(tmp_path, monkeypatch, ['investigate'],
                                   {'outcome': 'done', 'reason': 'Codex quota floor reached'})
    assert events == ['investigate'] and 'depth' not in result


@pytest.mark.parametrize('code', [0, 124])
def test_the_codex_launcher_deepens_when_a_turn_ends_after_the_first_portion(tmp_path, monkeypatch, code):
    """Inside a turn the session's own model drives single tasks; the slot runs at the turn's end."""
    prepare(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_exec, '_reap_orphan_maintenance', lambda *a: [])
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: False)
    calls = []
    monkeypatch.setattr(depth, 'slot', lambda root, **options: calls.append(options) or {'rounds': [], 'stopped': ''})

    def run(command, **options):
        open_round(tmp_path, portions=1)
        return CompletedProcess(command, code)
    codex_exec.run_turn(tmp_path, run=run)
    assert len(calls) == 1 and set(calls[0]['skip']) == {'people/ivy.md'}
    assert read_json(state_path(tmp_path, 'last-turn.json'), {})['depth'] == {'rounds': [], 'stopped': ''}
    # The next turn of the same round does not deepen again.
    codex_exec.run_turn(tmp_path, run=lambda command, **options: open_round(
        tmp_path, portions=2, depth=read_json(state_path(tmp_path, 'round.json'), {})['depth']) and CompletedProcess(command, 0))
    assert len(calls) == 1

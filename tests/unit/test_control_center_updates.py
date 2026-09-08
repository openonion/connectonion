from datetime import datetime, timezone

import pytest

from connectonion.network.host.control_center.runtime import ControlCenterRuntime, ReviewResult
from connectonion.network.host.control_center.updates import ControlCenterUpdates


@pytest.fixture
def queue(tmp_path):
    build = tmp_path / 'build'
    build.mkdir()
    (build / 'index.html').write_text('<h1>test</h1>')
    runtime = ControlCenterRuntime(tmp_path / 'runtime', policy='test',
        reviewer=lambda b: ReviewResult('approved', [], 'model', 'exec', 0),
        uploader=lambda b: {'url': 'https://app.test/index.html', 'revision': b.revision})
    turns = []
    updates = ControlCenterUpdates(runtime, build, generator=lambda prompt: turns.append(prompt))
    return updates, turns


def test_event_retention_dedup_coalescing_and_loop_prevention(queue):
    updates, turns = queue
    updates.configure({'enabled': True, 'events': ['agent.turn.completed'], 'debounce_seconds': 60})
    assert updates.enqueue('agent.turn.completed', 'event-1', now=1000)
    assert not updates.enqueue('agent.turn.completed', 'event-1', now=1001)
    assert updates.enqueue('agent.turn.completed', 'event-2', now=1002)
    assert not updates.enqueue('agent.turn.completed', 'own', source='control_center', now=1002)
    assert updates.tick(now=1030) is None
    result = updates.tick(now=1062)
    assert result['last_status'] == 'approved'
    assert len(turns) == 1
    assert updates.tick(now=1200) is None
    assert not updates.enqueue('agent.turn.completed', 'event-2', now=1201)


def test_pause_resume_and_manual_retry_are_persisted(queue):
    updates, turns = queue
    updates.configure({'enabled': False, 'every_seconds': 300})
    assert updates.tick(now=1000) is None
    state = updates.manual(now=1000)
    assert state['last_status'] == 'approved'
    assert not state['enabled']
    assert len(turns) == 1
    updates.configure({'enabled': True})
    assert updates.snapshot()['every_seconds'] == 300
    assert updates.tick(now=1100) is None
    assert updates.tick(now=1300)['last_status'] == 'unchanged'


def test_downtime_coalesces_to_one_due_run(queue):
    updates, turns = queue
    updates.configure({'enabled': True, 'every_seconds': 300})
    updates.tick(now=1000)
    assert updates.tick(now=10000)['last_status'] == 'unchanged'
    assert len(turns) == 2
    assert updates.tick(now=10001) is None
    assert updates.snapshot()['next_run'] == 10300


def test_failure_is_recorded_without_auto_retry_storm(queue):
    updates, turns = queue
    updates.configure({'enabled': True, 'every_seconds': 300})
    updates.generator = lambda prompt: (_ for _ in ()).throw(RuntimeError('synthetic failure'))
    result = updates.tick(now=1000)
    assert result['last_status'] == 'failed'
    assert result['last_error']
    assert updates.tick(now=1001) is None
    assert updates.snapshot()['last_success'] is None


@pytest.mark.parametrize('settings', [
    {'every_seconds': 1}, {'every_seconds': True}, {'events': ['email.received']},
    {'at': '99:00'}, {'at': '10:00', 'tz': 'Invalid/Zone'}, {'debounce_seconds': -1},
    {'enabled': 'yes'}, {'unknown': True}, {'every_seconds': 300, 'at': '10:00'},
])
def test_invalid_or_external_schedules_are_rejected(queue, settings):
    updates, _ = queue
    with pytest.raises(ValueError):
        updates.configure(settings)


def test_wall_clock_reuses_host_timezone_semantics(queue):
    updates, turns = queue
    updates.configure({'enabled': True, 'at': '10:30', 'tz': 'UTC'})
    now = datetime(2026, 9, 7, 10, 30, tzinfo=timezone.utc).timestamp()
    assert updates.tick(now=now)['last_status'] == 'approved'
    assert updates.tick(now=now+30) is None
    assert updates.snapshot()['next_run'] == now + 86400


def test_second_worker_does_not_generate_while_one_is_running(queue):
    updates, turns = queue
    def generation(prompt):
        other = ControlCenterUpdates(updates.runtime, updates.build_dir, generator=lambda p: None)
        assert other.tick(now=1001) is None
        turns.append(prompt)
    updates.generator = generation
    updates.configure({'enabled': True, 'every_seconds': 300})
    assert updates.tick(now=1000)['last_status'] == 'approved'
    assert len(turns) == 1


def test_interrupted_worker_stays_paused_across_subsequent_ticks_until_manual_retry(queue, monkeypatch):
    import os
    updates, turns = queue
    updates.configure({'enabled': True, 'every_seconds': 300})
    assert updates._claim(1000, True)
    monkeypatch.setattr(os, 'kill', lambda *args: (_ for _ in ()).throw(ProcessLookupError()))
    assert updates.tick(now=1400) is None
    assert updates.tick(now=2000) is None
    assert updates.snapshot()['last_status'] == 'interrupted'
    assert updates.manual(now=2001)['last_status'] == 'approved'
    assert len(turns) == 1


def test_worker_in_another_permission_context_is_treated_as_alive(queue, monkeypatch):
    import os
    updates, _ = queue
    updates.configure({'enabled': True, 'every_seconds': 300})
    assert updates._claim(1000, True)
    monkeypatch.setattr(os, 'kill', lambda *args: (_ for _ in ()).throw(PermissionError()))
    assert updates.tick(now=1400) is None

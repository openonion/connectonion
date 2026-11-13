"""Status says what is true: mailbox age, a stuck round, the last known Codex week. Fictional data."""
from datetime import timedelta

import pytest

from connectonion.rem import quota, service
from connectonion.rem.config import read_config, set_config
from connectonion.rem.files import state_path, write_json
from tests.unit.test_rem_collection_failure import mixed_sources, notebook  # noqa: F401


def _gmail(root):
    return service.mailbox_state("gmail", service.subscriptions(root)["gmail"], root=root)


def test_a_mailbox_last_read_more_than_a_day_ago_is_not_a_tick(mixed_sources):
    root = mixed_sources[0]
    write_json(state_path(root, "source_reads.json"), {"gmail": {
        "at": (service.now() - timedelta(hours=34)).isoformat(), "error": ""}})
    state, fix = _gmail(root)
    assert state == "last read 34 hours ago" and fix  # a fix means ✗, not ✓
    write_json(state_path(root, "source_reads.json"), {"gmail": {
        "at": (service.now() - timedelta(hours=2)).isoformat(), "error": ""}})
    assert _gmail(root) == ("read by the daily round", "")


def test_a_failed_read_says_when_the_last_good_one_was(mixed_sources, monkeypatch):
    root = mixed_sources[0]
    service._record_source_read(root, "gmail")
    later = service.now() + timedelta(hours=30)
    monkeypatch.setattr(service, "now", lambda: later)
    service._record_source_read(root, "gmail", "Gmail read failed: RemError")
    state, fix = _gmail(root)
    assert state.startswith("last read failed") and state.endswith("; last good read 30 hours ago") and fix


def _round(root, slot):
    write_json(state_path(root, "round.json"), {"phase": "daily-update", "slot": slot.isoformat(),
                                                "started_at": slot.isoformat(), "pending": "native-fixture"})


def test_a_round_still_pending_after_later_slots_is_stuck_with_its_reason(tmp_path, rem_clock):
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.times", "01:00,04:00", "schedule.timezone", "UTC"])
    moment = service.now()
    _round(tmp_path, moment.replace(hour=1, minute=0) - timedelta(days=1))
    write_json(state_path(tmp_path, "last-turn.json"), {"result": "failed", "reason": "Codex quota exhausted",
                                                        "started_at": moment.isoformat()})
    stuck = service.round_state(tmp_path, read_config(tmp_path))
    assert stuck["state"] == "stuck" and stuck["reason"] == "Codex quota exhausted"
    assert service.status(tmp_path)["round"] == stuck
    _round(tmp_path, service.latest_slot(read_config(tmp_path), moment))
    assert service.round_state(tmp_path, read_config(tmp_path))["state"] == "working"
    write_json(state_path(tmp_path, "round.json"), {"done": True})
    assert service.round_state(tmp_path, read_config(tmp_path)) is None


def test_an_unreadable_codex_week_uses_the_last_recorded_reading(tmp_path, rem_clock, monkeypatch):
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    future = int((service.now() + timedelta(days=3)).timestamp())
    reading = {"used_percent": 93, "window_minutes": 10080, "resets_at": future, "plan": "pro"}
    write_json(state_path(tmp_path, "runs/run_week.json"), {"id": "run_week", "phase": "daily-update",
               "started_at": service.now().isoformat(), "quota": {"before": reading}})
    config = {**read_config(tmp_path), "runner": "codex"}
    unknown = {"unknown": "app-server exited"}
    monkeypatch.setattr(quota, "read", lambda config, request=None: unknown)
    found = quota.meter(tmp_path, config)
    assert found["used_percent"] == 93 and found["last_recorded"] == "app-server exited"
    assert "93%" in quota.floor_block(found, config["limits"])
    # A reading from a week that has reset tells nothing about this one.
    write_json(state_path(tmp_path, "runs/run_week.json"), {"id": "run_week", "phase": "daily-update",
               "started_at": service.now().isoformat(), "quota": {"before": {**reading, "resets_at": 1}}})
    assert quota.meter(tmp_path, config) == unknown


@pytest.mark.parametrize("hours,text", [(34, "34 hours"), (50, "2 days"), (1, "1 hour")])
def test_ages_read_as_hours_then_days(hours, text):
    assert service.age(timedelta(hours=hours)) == text


def test_each_night_is_measured_once_and_status_shows_it(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timezone
    from connectonion.rem import night_stats
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.timezone", "UTC", "schedule.profile", "dense"])
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 11, 9, 13, tzinfo=timezone.utc))
    def at(hour, day=8):
        return datetime(2026, 11, day, hour, tzinfo=timezone.utc).isoformat()
    for name, start, end in (("a", at(23), at(1, 9)), ("b", at(3, 9), at(4, 9)), ("c", at(18), at(19))):
        write_json(state_path(tmp_path, f"turns/{name}.json"), {"started_at": start, "finished_at": end, "result": "completed"})
    runs = [("r1", "daily-update", "investigate", "completed", "native-1", 0), ("r2", "daily-update", "investigate", "parked", "native-2", 0),
            ("r3", "daily-update", "investigate", "refused", "native-3", 0), ("r4", "reply-draft", "reply-draft", "completed", "native-4", 0),
            ("r5", "sync", "maintain", "completed", "native-5", 12)]
    for name, phase, stage, outcome, task, items in runs:
        write_json(state_path(tmp_path, f"runs/run_{name}.json"), {"id": name, "phase": phase, "stage": stage, "outcome": outcome,
                   "task_id": task, "items": items, "started_at": at(2, 9)})
    [row] = night_stats.record(tmp_path)
    assert row == {"night": "2026-11-08", "profile": "dense", "turns": 3, "tasks_accepted": 3, "tasks_parked": 1,
                   "tasks_failed": 1, "drafts": 1, "mail_read": 12, "minutes_busy": 240, "minutes_idle": 540 - 180}
    assert night_stats.record(tmp_path) == []  # once a night
    assert len(state_path(tmp_path, "night-stats.jsonl").read_text().splitlines()) == 1
    assert json.loads(state_path(tmp_path, "night-stats.jsonl").read_text())["turns"] == 3
    from connectonion.cli.commands.rem_status import _nights
    assert "3 accepted · 1 parked · 1 failed" in "\n".join(_nights(service.status(tmp_path)))


def test_a_round_whose_tasks_keep_landing_or_whose_turn_runs_is_working(tmp_path, rem_clock):
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.times", "01:00,04:00", "schedule.timezone", "UTC"])
    moment = service.now()
    _round(tmp_path, moment.replace(hour=1, minute=0) - timedelta(days=1))
    write_json(state_path(tmp_path, "last-turn.json"), {"result": "running", "started_at": moment.isoformat()})
    assert service.round_state(tmp_path, read_config(tmp_path))["state"] == "working"
    write_json(state_path(tmp_path, "last-turn.json"), {"result": "completed", "started_at": moment.isoformat()})
    write_json(state_path(tmp_path, "runs/run_" + "a" * 32 + ".json"), {"id": "run_" + "a" * 32,
               "phase": "daily-update", "started_at": (moment - timedelta(minutes=20)).isoformat()})
    assert service.round_state(tmp_path, read_config(tmp_path))["state"] == "working"

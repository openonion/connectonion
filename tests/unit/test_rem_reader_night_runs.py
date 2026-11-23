"""reader.night_runs: the whole last pass for Today's curve, bounded (#3391)."""
from datetime import datetime, timedelta, timezone

from connectonion.rem import reader


def _logs(n, *, minutes=1, changed=0):
    now = datetime(2026, 11, 23, 6, 30, tzinfo=timezone.utc)
    return [{"started_at": (now - timedelta(minutes=i * minutes)).isoformat(), "finished_at": now.isoformat(),
             "phase": "tag", "items": 1, "outcome": "completed", "changed": [f"people/p{k}.md" for k in range(changed)],
             "error": "secret runner output", "pages": [{"x": 1}]} for i in range(n)]


def test_every_run_of_the_pass_is_kept_not_only_the_latest_21():
    rows = reader.night_runs(_logs(60, minutes=5))
    assert len(rows) == 60
    assert set(rows[0]) == {"started_at", "finished_at", "phase", "items", "outcome", "changed"}  # no transcripts


def test_runs_before_the_pass_are_left_out():
    logs = _logs(3, minutes=60) + [{**_logs(1)[0], "started_at": "2026-11-22T10:00:00+00:00"}]
    assert len(reader.night_runs(logs)) == 3


def test_a_runaway_night_cannot_bloat_the_page():
    rows = reader.night_runs(_logs(reader.NIGHT_RUNS_MAX + 100, changed=reader.NIGHT_CHANGED_MAX + 10))
    assert len(rows) == reader.NIGHT_RUNS_MAX
    assert len(rows[0]["changed"]) == reader.NIGHT_CHANGED_MAX


def test_no_runs_no_rows():
    assert reader.night_runs([]) == []

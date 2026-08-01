"""A schedule file is hand-written and deployed, so every way to get it wrong
reaches a server. #531.

Dropping what does not parse is right — one bad line must not take an agent
down — but dropping *silently* leaves absence as the only signal, and absence
is what a correct schedule looks like most of the time.
"""

from datetime import datetime, timedelta, timezone

import pytest

from connectonion.network.host import schedule as sched


def write(tmp_path, text):
    co = tmp_path / ".co"
    co.mkdir(exist_ok=True)
    (co / "schedule.yaml").write_text(text, encoding="utf-8")
    return co


class TestCatchUpForClockEntries:
    """The property #521 set out to preserve, which only interval entries got."""

    def test_a_weekly_missed_during_downtime_runs_when_the_agent_returns(self):
        e = sched.Entry(name="w", run="/x", at="Mon 09:00", tz="Asia/Shanghai")
        monday = datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc)     # 09:00 Shanghai
        tuesday = monday + timedelta(days=1)
        # It ran the *previous* Monday, then the agent was down through this one.
        week_before = monday - timedelta(days=7)

        assert sched.is_due(e, last_run=week_before, now=tuesday), (
            "the agent was down through Monday; a late summary beats none"
        )

    def test_it_catches_up_once_not_once_per_missed_week(self):
        e = sched.Entry(name="w", run="/x", at="Mon 09:00", tz="Asia/Shanghai")
        monday = datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc)
        month_later = monday + timedelta(days=28)

        assert sched.is_due(e, last_run=monday, now=month_later)
        # having just run, it must not immediately be due again
        assert not sched.is_due(e, last_run=month_later, now=month_later)

    def test_a_daily_entry_still_runs_once_a_day(self):
        e = sched.Entry(name="d", run="/x", at="09:00", tz="UTC")
        nine = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)

        assert sched.is_due(e, None, nine)
        assert not sched.is_due(e, last_run=nine, now=nine + timedelta(hours=6))
        assert sched.is_due(e, last_run=nine, now=nine + timedelta(days=1))

    def test_a_new_entry_does_not_fire_for_an_occurrence_that_predates_it(self):
        """Last Monday happened before this entry existed; there is nothing to
        catch up. It waits for its own next occurrence."""
        e = sched.Entry(name="w", run="/x", at="Mon 09:00", tz="Asia/Shanghai")
        sunday = datetime(2026, 8, 2, 1, 0, tzinfo=timezone.utc)
        assert not sched.is_due(e, None, sunday)


class TestEntriesThatCannotMeanAnything:
    def test_a_zero_interval_is_rejected(self, tmp_path):
        """`every: 0m` ran a full agent turn every tick, forever, on a typo."""
        co = write(tmp_path, '- every: 0m\n  run: "/spin"\n')
        assert sched.load_entries(co) == []

    def test_a_time_that_is_not_a_time_is_rejected(self, tmp_path):
        co = write(tmp_path, '- at: "25:99"\n  run: "/bad"\n')
        assert sched.load_entries(co) == []

    def test_an_unknown_weekday_is_rejected(self, tmp_path):
        co = write(tmp_path, '- at: "Funday 09:00"\n  run: "/bad"\n')
        assert sched.load_entries(co) == []

    def test_a_duplicate_name_is_rejected_not_silently_merged(self, tmp_path):
        """State is keyed by name: two entries sharing one would overwrite each
        other's last_run and each end up running half as often as configured."""
        co = write(tmp_path, '- name: dup\n  every: 1h\n  run: "/a"\n'
                             '- name: dup\n  every: 1h\n  run: "/b"\n')
        entries = sched.load_entries(co)

        assert [e.run for e in entries] == ["/a"]

    def test_the_valid_entries_around_a_bad_one_still_load(self, tmp_path):
        co = write(tmp_path, '- every: 0m\n  run: "/spin"\n- every: 1h\n  run: "/fine"\n')
        assert [e.run for e in sched.load_entries(co)] == ["/fine"]


class TestSayingSo:
    def test_problems_are_reported(self, tmp_path):
        co = write(tmp_path, '- every: 0m\n  run: "/spin"\n'
                             '- at: "25:99"\n  run: "/bad"\n'
                             '- every: 1h\n  run: "/fine"\n')
        entries, problems = sched.load_entries(co, report=True)

        assert [e.run for e in entries] == ["/fine"]
        assert len(problems) == 2
        assert any("0m" in p or "interval" in p.lower() for p in problems)

    def test_an_unknown_timezone_is_reported_but_still_runs(self, tmp_path):
        """Falling back to UTC is deliberate — refusing to run is worse — but
        eight hours off is not something to discover from a missed report."""
        co = write(tmp_path, '- at: "Mon 09:00"\n  tz: Asia/Shanghia\n  run: "/x"\n')
        entries, problems = sched.load_entries(co, report=True)

        assert len(entries) == 1
        assert any("Shanghia" in p for p in problems)

    def test_a_clean_schedule_reports_nothing(self, tmp_path):
        co = write(tmp_path, '- every: 15m\n  run: "/ok"\n')
        entries, problems = sched.load_entries(co, report=True)
        assert len(entries) == 1 and problems == []

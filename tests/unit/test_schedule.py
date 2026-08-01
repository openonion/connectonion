"""An agent's own schedule: what it runs, when it is due, and what it remembers.

The design argument is in #521. The short version: the OS scheduler is three
implementations (systemd / launchd / Task Scheduler) of which two rot, while the
agent is already a long-lived process on all three platforms. So the clock lives
in the process, and the two things the OS gave us for free — catch-up after
downtime, and not running twice at once — are what these tests are mostly about.
"""

from datetime import datetime, timedelta, timezone

import pytest

from connectonion.network.host import schedule as sched


def write(co_dir, text):
    co_dir.mkdir(parents=True, exist_ok=True)
    (co_dir / "schedule.yaml").write_text(text, encoding="utf-8")
    return co_dir


class TestReadingTheSchedule:
    def test_no_file_is_not_an_error(self, tmp_path):
        """Most agents have no schedule. That is the common case, not a problem."""
        assert sched.load_entries(tmp_path / ".co") == []

    def test_an_interval_entry(self, tmp_path):
        co = write(tmp_path / ".co", """
            - every: 15m
              run: "/contract-ledger check"
        """)
        entry, = sched.load_entries(co)

        assert entry.run == "/contract-ledger check"
        assert entry.interval == timedelta(minutes=15)

    @pytest.mark.parametrize("text,expected", [
        ("30s", timedelta(seconds=30)),
        ("15m", timedelta(minutes=15)),
        ("2h", timedelta(hours=2)),
        ("1d", timedelta(days=1)),
    ])
    def test_interval_units(self, tmp_path, text, expected):
        co = write(tmp_path / ".co", f'- every: {text}\n  run: "x"\n')
        assert sched.load_entries(co)[0].interval == expected

    def test_a_clock_entry_carries_its_timezone(self, tmp_path):
        """The server is in one country and the reader is in another. Without a
        zone, 09:00 means 09:00 wherever the machine happens to be."""
        co = write(tmp_path / ".co", """
            - at: "Mon 09:00"
              tz: Asia/Shanghai
              run: "/weekly"
        """)
        entry, = sched.load_entries(co)

        assert entry.at == "Mon 09:00"
        assert entry.tz == "Asia/Shanghai"

    def test_a_broken_entry_does_not_take_the_others_down(self, tmp_path):
        """A schedule is authored by hand and deployed. One bad line must not
        stop the entries that parse, and must not stop the agent booting."""
        co = write(tmp_path / ".co", """
            - every: "not-a-duration"
              run: "/broken"
            - every: 1h
              run: "/fine"
        """)
        entries = sched.load_entries(co)

        assert [e.run for e in entries] == ["/fine"]

    def test_malformed_yaml_yields_nothing_rather_than_raising(self, tmp_path):
        co = write(tmp_path / ".co", "- every: [unclosed\n")
        assert sched.load_entries(co) == []


class TestWhenAnEntryIsDue:
    def test_an_interval_entry_is_due_immediately_when_never_run(self):
        e = sched.Entry(name="x", run="/x", interval=timedelta(minutes=15))
        assert sched.is_due(e, last_run=None, now=datetime.now(timezone.utc))

    def test_and_not_again_until_the_interval_passes(self):
        now = datetime.now(timezone.utc)
        e = sched.Entry(name="x", run="/x", interval=timedelta(minutes=15))

        assert not sched.is_due(e, last_run=now - timedelta(minutes=5), now=now)
        assert sched.is_due(e, last_run=now - timedelta(minutes=16), now=now)

    def test_a_run_missed_while_the_agent_was_down_fires_on_the_next_tick(self):
        """This is `Persistent=true`, which is the one thing in-process
        scheduling would otherwise lose. Three days of downtime, one catch-up
        run — not three."""
        now = datetime.now(timezone.utc)
        e = sched.Entry(name="x", run="/x", interval=timedelta(hours=1))

        assert sched.is_due(e, last_run=now - timedelta(days=3), now=now)


class TestState:
    def test_a_run_is_remembered_with_the_session_it_produced(self, tmp_path):
        """The point of recording session_id: a background run is inspectable
        afterwards. .co/session_results.jsonl already holds the transcript, the
        result and the duration, so the state file only has to point at it."""
        co = tmp_path / ".co"
        co.mkdir()
        now = datetime.now(timezone.utc)

        sched.record_run(co, "nightly", when=now, status="done", session_id="abc")
        state = sched.load_state(co)

        assert state["nightly"]["status"] == "done"
        assert state["nightly"]["session_id"] == "abc"
        assert sched.last_run(state, "nightly") == now

    def test_state_survives_a_reread(self, tmp_path):
        co = tmp_path / ".co"
        co.mkdir()
        now = datetime.now(timezone.utc)
        sched.record_run(co, "a", when=now, status="done", session_id=None)
        sched.record_run(co, "b", when=now, status="failed", session_id=None)

        state = sched.load_state(co)
        assert set(state) == {"a", "b"}
        assert state["b"]["status"] == "failed"

    def test_unreadable_state_reads_as_empty_rather_than_crashing(self, tmp_path):
        """A truncated write, a hand edit. Losing the memory of past runs costs
        one duplicated run; refusing to boot costs the whole agent."""
        co = tmp_path / ".co"
        co.mkdir()
        (co / "schedule-state.json").write_text("{not json", encoding="utf-8")

        assert sched.load_state(co) == {}


class TestNaming:
    def test_an_entry_without_a_name_is_identified_by_what_it_runs(self, tmp_path):
        """State is keyed by name. Requiring one would be ceremony for the
        single-entry case, so the command doubles as the identity."""
        co = write(tmp_path / ".co", '- every: 1h\n  run: "/nightly report"\n')
        assert sched.load_entries(co)[0].name == "/nightly report"

    def test_an_explicit_name_wins(self, tmp_path):
        co = write(tmp_path / ".co", '- name: nightly\n  every: 1h\n  run: "/x"\n')
        assert sched.load_entries(co)[0].name == "nightly"

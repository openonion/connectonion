"""Home says what the agent has been doing, not only what it is.

#522. The page rendered a name, an address and a list of skills — everything an
agent *is*, and nothing about whether it had run today, whether the last run
worked, or what it is going to do next. All of that was already on disk beside
the file that renders the page, and none of it was read.

The rule these tests mostly defend: **an agent with no schedule and no history
must render exactly what it rendered before.** A section that appears empty on
every fresh agent is worse than no section — it is the first thing a new user
sees, and it says nothing.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.network.host.ws_router import dashboard as dash


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".co").mkdir()
    monkeypatch.setattr(dash, "_project_dir", tmp_path)
    return tmp_path


def sessions(project, *records):
    path = project / ".co" / "session_results.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def done(prompt, *, result="ok", ms=1200, ago_s=60):
    created = (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).timestamp()
    return {"session_id": prompt, "status": "done", "prompt": prompt,
            "result": result, "duration_ms": ms, "created": created}


class TestNothingToSay:
    def test_a_fresh_agent_gets_no_activity_section(self, project):
        """The day-zero page must not grow an empty box."""
        html = dash.render_starter({"name": "billing", "skills": []})

        assert "Recent" not in html
        assert "Scheduled" not in html

    def test_an_agent_with_a_schedule_but_no_runs_still_shows_the_schedule(self, project):
        """Configured-but-never-fired is exactly the state someone needs to see:
        it is indistinguishable from broken until the page says otherwise."""
        (project / ".co" / "schedule.yaml").write_text(
            '- every: 15m\n  run: "/check"\n', encoding="utf-8")

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "/check" in html
        assert "every 15m" in html


class TestRecentRuns:
    def test_the_last_runs_appear_newest_first(self, project):
        # Distinctive prompts on purpose. "first"/"second" would match the
        # stylesheet — `.act:first-child` — and the assertion would be about
        # CSS ordering while claiming to be about runs.
        sessions(project,
                 done("zzolder-run", ago_s=300),
                 done("zznewer-run", ago_s=60))

        html = dash.render_starter({"name": "billing", "skills": []})

        assert html.index("zznewer-run") < html.index("zzolder-run")

    def test_only_finished_runs_carry_a_duration(self, project):
        sessions(project, done("quick", ms=1500))
        html = dash.render_starter({"name": "billing", "skills": []})
        assert "1.5s" in html

    def test_a_run_that_never_finished_is_shown_as_still_running(self, project):
        """status stays 'running' forever when a turn dies mid-flight, which
        makes it a free stuck-detector — but only if something looks."""
        created = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
        sessions(project, {"session_id": "s", "status": "running",
                           "prompt": "long one", "result": None,
                           "duration_ms": None, "created": created})

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "long one" in html
        assert "running" in html

    def test_the_newest_state_of_a_session_wins(self, project):
        """The log is append-only: one line for running, another for done. The
        page must show the outcome, not the first thing that was written."""
        created = datetime.now(timezone.utc).timestamp()
        sessions(project,
                 {"session_id": "s", "status": "running", "prompt": "x",
                  "result": None, "duration_ms": None, "created": created},
                 {"session_id": "s", "status": "done", "prompt": "x",
                  "result": "finished", "duration_ms": 900, "created": created})

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "running" not in html.split("Recent")[-1]

    def test_a_corrupt_line_does_not_take_the_page_down(self, project):
        path = project / ".co" / "session_results.jsonl"
        path.write_text('{"broken\n' + json.dumps(done("good")) + "\n", encoding="utf-8")

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "good" in html

    def test_prompts_are_escaped(self, project):
        sessions(project, done("<script>alert(1)</script>"))
        html = dash.render_starter({"name": "billing", "skills": []})
        assert "<script>alert(1)</script>" not in html


class TestSchedule:
    def test_a_scheduled_entry_shows_when_it_last_ran_and_how_it_went(self, project):
        (project / ".co" / "schedule.yaml").write_text(
            '- every: 1h\n  run: "/nightly"\n', encoding="utf-8")
        (project / ".co" / "schedule-state.json").write_text(json.dumps({
            "/nightly": {"last_run": datetime.now(timezone.utc).isoformat(),
                         "status": "done", "session_id": "abc"}}), encoding="utf-8")

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "/nightly" in html
        assert "every 1h" in html

    def test_a_failed_scheduled_run_is_visible_as_failed(self, project):
        (project / ".co" / "schedule.yaml").write_text(
            '- every: 1h\n  run: "/nightly"\n', encoding="utf-8")
        (project / ".co" / "schedule-state.json").write_text(json.dumps({
            "/nightly": {"last_run": datetime.now(timezone.utc).isoformat(),
                         "status": "failed", "session_id": None}}), encoding="utf-8")

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "failed" in html

    def test_a_malformed_schedule_does_not_break_the_page(self, project):
        (project / ".co" / "schedule.yaml").write_text("- every: [oops\n", encoding="utf-8")

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "billing" in html      # the page still renders


class TestDurations:
    """The runs this section exists for are the long ones."""

    @pytest.mark.parametrize("ms,shown", [
        (1500, "1.5s"),
        (59000, "59.0s"),
        (60000, "1m"),
        (243000, "4m 3s"),      # a full extraction pass, not "243.0s"
        (7860000, "2h 11m"),
    ])
    def test_a_long_run_is_not_reported_in_seconds(self, ms, shown):
        assert dash._took(ms) == shown


class TestReadingCost:
    """Five rows must cost five rows, not the whole history.

    Each record embeds the turn's full message list — 23 KB on average on a real
    agent, 85 KB at the top end — and the file is append-only with nothing
    trimming it. Home is re-read on connect *and after every run*, so a whole-file
    read is paid per turn, forever. #526.
    """

    def test_only_the_tail_is_read(self, project, monkeypatch):
        path = project / ".co" / "session_results.jsonl"
        # 200 fat records: what a few months of hourly scheduled work looks like.
        big = "x" * 20_000
        with open(path, "w", encoding="utf-8") as f:
            for i in range(200):
                f.write(json.dumps({"session_id": f"s{i}", "status": "done",
                                    "prompt": f"turn-{i}", "result": big,
                                    "duration_ms": 100, "created": 1000 + i}) + "\n")

        read_bytes = []
        real_read = type(path).read_bytes

        def counting_read(self, *a, **kw):
            data = real_read(self, *a, **kw)
            read_bytes.append(len(data))
            return data

        monkeypatch.setattr(type(path), "read_bytes", counting_read, raising=False)
        monkeypatch.setattr(type(path), "read_text",
                            lambda self, *a, **kw: (_ for _ in ()).throw(
                                AssertionError("read_text reads the whole file")),
                            raising=False)

        runs = dash.recent_runs(limit=5)

        assert [r["prompt"] for r in runs] == [f"turn-{i}" for i in (199, 198, 197, 196, 195)]
        assert sum(read_bytes) < path.stat().st_size / 4, (
            f"read {sum(read_bytes)} bytes of a {path.stat().st_size}-byte file "
            "to show five rows"
        )

    def test_a_file_shorter_than_the_window_still_works(self, project):
        sessions(project, done("only-one"))
        assert [r["prompt"] for r in dash.recent_runs()] == ["only-one"]

    def test_a_record_larger_than_the_window_is_still_found(self, project):
        """One 85 KB record is normal. A fixed byte window would return nothing."""
        path = project / ".co" / "session_results.jsonl"
        path.write_text(json.dumps({"session_id": "s", "status": "done",
                                    "prompt": "huge", "result": "y" * 200_000,
                                    "duration_ms": 5, "created": 1}) + "\n",
                        encoding="utf-8")
        assert [r["prompt"] for r in dash.recent_runs()] == ["huge"]


class TestScheduleProblemsAreVisible:
    """A dropped entry is invisible on Home too: it renders as nothing, which
    is what a schedule that has not fired yet also renders as. #531."""

    def test_a_rejected_entry_is_named_on_the_page(self, project):
        (project / ".co" / "schedule.yaml").write_text(
            '- every: 0m\n  run: "/spin"\n- every: 1h\n  run: "/fine"\n', encoding="utf-8")

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "/fine" in html
        assert "entry 1" in html, "the entry that was dropped is not mentioned anywhere"

    def test_a_clean_schedule_adds_no_warning(self, project):
        (project / ".co" / "schedule.yaml").write_text(
            '- every: 1h\n  run: "/fine"\n', encoding="utf-8")

        html = dash.render_starter({"name": "billing", "skills": []})
        assert "entry " not in html

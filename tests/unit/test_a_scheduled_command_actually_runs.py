"""A scheduled task can report success without doing the work.

From #709, measured on a real agent. The task's whole job was running one
script:

    - name: refresh dashboard numbers
      every: 30m
      run: |
        Run .co/skills/<skill>/scripts/stats.py to recompute stats.json.

and the log said, on several consecutive runs:

    [co] ✓ The agent successfully executed the `stats.py` script and updated …

The output file's mtime never changed. Running the same script by hand, on the
same box as the same user, updated it immediately. So the schedule reported
success for about a day while the dashboard served day-old numbers.

Structural, not a one-off: `run` is a prompt executed through the same path as
`POST /input`, and there was no way to say "just execute this command". Even
fully deterministic maintenance went through a model that can claim completion,
and the log line is that model's own account — nothing compares it against the
filesystem.

So an entry may say `exec:` instead of `run:`. The command runs, and what is
recorded is its exit code. There is no room for it to be reported as done
without having run, because nothing is asked for an opinion.

Same family as #535 and #682, which this release has spent itself on: `done`
must not mean "something said done".
"""

import os
from pathlib import Path

import pytest

from connectonion.network.host.schedule import load_entries


def _write(co_dir, text):
    co_dir.mkdir(parents=True, exist_ok=True)
    (co_dir / "schedule.yaml").write_text(text, encoding="utf-8")
    return co_dir


@pytest.fixture
def co_dir(tmp_path):
    return tmp_path / ".co"


class TestAnEntryMaySayExec:

    def test_it_loads(self, co_dir):
        _write(co_dir, '- name: stats\n  every: 30m\n  exec: python scripts/stats.py\n')

        entries, problems = load_entries(co_dir, report=True)

        assert problems == []
        assert [e.name for e in entries] == ["stats"]

    def test_the_command_is_kept(self, co_dir):
        _write(co_dir, '- name: stats\n  every: 30m\n  exec: python scripts/stats.py\n')

        assert load_entries(co_dir)[0].exec == "python scripts/stats.py"

    def test_a_prompt_entry_still_works(self, co_dir):
        _write(co_dir, '- name: think\n  every: 30m\n  run: consider the numbers\n')
        entry = load_entries(co_dir)[0]

        assert entry.run == "consider the numbers"
        assert entry.exec is None

    def test_neither_is_a_problem(self, co_dir):
        _write(co_dir, '- name: empty\n  every: 30m\n')

        _entries, problems = load_entries(co_dir, report=True)

        assert problems and "run" in problems[0].lower()

    def test_both_is_a_problem(self, co_dir):
        """Two answers to "what does this entry do" is a question, not a
        default — and picking one silently is how the wrong half runs."""
        _write(co_dir, '- name: two\n  every: 30m\n  run: think\n  exec: echo hi\n')

        _entries, problems = load_entries(co_dir, report=True)

        assert problems, "an entry with both run and exec was accepted"


class TestItRunsTheCommandForReal:

    def _tick(self, co_dir, monkeypatch):
        import asyncio
        import importlib

        from connectonion.network.host.schedule import create_schedule_lifespan

        router = importlib.import_module("connectonion.network.host.http_router")
        monkeypatch.setattr(router, "input_handler",
                            lambda *a, **kw: pytest.fail("a prompt path ran for an exec entry"))
        on_startup, _ = create_schedule_lifespan(co_dir, lambda: None, None, result_ttl=60)
        asyncio.run(on_startup.tick_once())

    def test_the_side_effect_happens(self, co_dir, monkeypatch, tmp_path):
        marker = tmp_path / "ran.txt"
        _write(co_dir, f'- name: touch\n  every: 1m\n  exec: /usr/bin/touch {marker}\n')

        self._tick(co_dir, monkeypatch)

        assert marker.exists(), "the scheduled command did not run"

    def test_a_failing_command_is_recorded_as_failed(self, co_dir, monkeypatch):
        from connectonion.network.host.schedule import load_state

        _write(co_dir, '- name: broken\n  every: 1m\n  exec: /usr/bin/false\n')

        self._tick(co_dir, monkeypatch)
        state = load_state(co_dir)

        assert state["broken"]["status"] == "failed", state

    def test_a_working_command_is_recorded_as_done(self, co_dir, monkeypatch):
        from connectonion.network.host.schedule import load_state

        _write(co_dir, '- name: fine\n  every: 1m\n  exec: /usr/bin/true\n')

        self._tick(co_dir, monkeypatch)
        state = load_state(co_dir)

        assert state["fine"]["status"] == "done", state

    def test_the_failure_says_what_the_command_said(self, co_dir, monkeypatch):
        """A non-zero exit with nothing to read is a mystery at 3am."""
        from connectonion.network.host.schedule import load_state

        _write(co_dir, '- name: noisy\n  every: 1m\n  exec: sh -c "echo the-real-reason >&2; exit 3"\n')

        self._tick(co_dir, monkeypatch)
        reason = load_state(co_dir)["noisy"].get("reason", "")

        assert "the-real-reason" in reason, reason


class TestHomeShowsWhatTheEntryDoes:
    """The dashboard sends `run` for each entry. An exec entry has none, so Home
    would list a scheduled task with a blank where its work should be — an
    operator looking at the panel to see what runs would see nothing."""

    def _rows(self, co_dir, monkeypatch):
        """Through the real `scheduled_entries`, which reads the schedule module
        rather than reparsing the file — so the page and the scheduler cannot
        disagree about what an entry means."""
        from connectonion.network.host.ws_router import dashboard

        monkeypatch.setattr(dashboard, "_co", lambda: co_dir)
        entries, _problems = dashboard.scheduled_entries()
        return entries

    def test_an_exec_entry_is_not_blank(self, co_dir, monkeypatch):
        _write(co_dir, '- name: stats\n  every: 30m\n  exec: python scripts/stats.py\n')

        row = self._rows(co_dir, monkeypatch)[0]

        assert row["run"], row
        assert "stats.py" in row["run"]

    def test_a_prompt_entry_is_unchanged(self, co_dir, monkeypatch):
        _write(co_dir, '- name: think\n  every: 30m\n  run: consider the numbers\n')

        assert self._rows(co_dir, monkeypatch)[0]["run"] == "consider the numbers"

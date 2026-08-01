"""Recent must not spend three rows saying one thing. #528.

A schedule entry's prompt is one fixed sentence sent verbatim every firing, so
the more useful the schedule, the more the section fills with the same row —
and the distinct rows, the interactive ones, are the first evicted.

Recent now carries only what a person asked for: a scheduled entry has its own
row in the Schedule card, with its cadence, its status and when it next fires,
so repeating it here said the same thing twice in two formats. The collapse
itself is still what keeps a firing from being counted twice while it is being
matched, so these cases still guard it.
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
    with open(project / ".co" / "session_results.jsonl", "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _iso(*, ago_s):
    return (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).isoformat()


def run(prompt, *, ago_s, ms=1000, sid=None):
    return {"session_id": sid or f"{prompt}-{ago_s}", "status": "done",
            "prompt": prompt, "result": "ok", "duration_ms": ms,
            "created": (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).timestamp()}


CHECK = "/contract-ledger check the drive for new contracts, extract only what is new"


class TestRepeatsCollapse:
    def test_three_firings_of_one_entry_do_not_reach_recent_at_all(self, project):
        """They have a row of their own in the Schedule card, which says the
        cadence, the status and when it fires next — everything this row said
        and more."""
        (project / ".co" / "schedule.yaml").write_text(
            f'- name: check for new contracts\n  every: 15m\n  run: "{CHECK}"\n',
            encoding="utf-8")
        sessions(project,
                 run(CHECK, ago_s=2280), run(CHECK, ago_s=1380), run(CHECK, ago_s=420))

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "Recent" not in html
        assert html.count("check for new contracts") == 1     # the Schedule row

    def test_the_schedule_entrys_name_is_used_not_the_prompt(self, project):
        (project / ".co" / "schedule.yaml").write_text(
            f'- name: check for new contracts\n  every: 15m\n  run: "{CHECK}"\n',
            encoding="utf-8")
        sessions(project, run(CHECK, ago_s=60))

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "check for new contracts" in html
        assert "extract only what is new" not in html

    def test_an_interactive_turn_between_two_firings_keeps_them_apart(self, project):
        """Collapsing across a gap would claim a run of three that never happened."""
        (project / ".co" / "schedule.yaml").write_text(
            f'- name: check\n  every: 15m\n  run: "{CHECK}"\n', encoding="utf-8")
        sessions(project,
                 run(CHECK, ago_s=1800),
                 run("what did you find?", ago_s=900),
                 run(CHECK, ago_s=300))

        html = dash.render_starter({"name": "billing", "skills": []})
        recent = html.split("Recent")[-1]

        # The two firings belong to the Schedule card; only the question a person
        # typed between them is Recent's business.
        assert "what did you find?" in recent
        assert "×" not in recent

    def test_a_single_firing_carries_no_count(self, project):
        (project / ".co" / "schedule.yaml").write_text(
            f'- name: check\n  every: 15m\n  run: "{CHECK}"\n', encoding="utf-8")
        sessions(project, run(CHECK, ago_s=60))

        html = dash.render_starter({"name": "billing", "skills": []})
        assert "×" not in html.split("Recent")[-1]

    def test_unscheduled_turns_are_untouched(self, project):
        sessions(project, run("hello", ago_s=120), run("goodbye", ago_s=60))

        html = dash.render_starter({"name": "billing", "skills": []})
        recent = html.split("Recent")[-1]

        assert "hello" in recent and "goodbye" in recent
        assert "×" not in recent

    def test_a_scheduled_entry_reports_its_latest_run_not_an_older_one(self, project):
        """This assertion used to live in Recent, where several firings folded to
        the newest. Firings are not in Recent any more, so the fact moved with
        them: the entry's own Schedule row is what reports how it last went."""
        (project / ".co" / "schedule.yaml").write_text(
            f'- name: check\n  every: 15m\n  run: "{CHECK}"\n', encoding="utf-8")
        state = {"check": {"last_run": _iso(ago_s=60), "status": "ok"}}
        (project / ".co" / "schedule-state.json").write_text(
            json.dumps(state), encoding="utf-8")
        sessions(project,
                 run(CHECK, ago_s=900, ms=542000),
                 run(CHECK, ago_s=60, ms=42800))

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "ok 1m ago" in html
        assert "15m ago" not in html

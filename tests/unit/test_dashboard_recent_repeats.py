"""Recent must not spend three rows saying one thing. #528.

A schedule entry's prompt is one fixed sentence sent verbatim every firing, so
the more useful the schedule, the more the section fills with the same row —
and the distinct rows, the interactive ones, are the first evicted.
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


def run(prompt, *, ago_s, ms=1000, sid=None):
    return {"session_id": sid or f"{prompt}-{ago_s}", "status": "done",
            "prompt": prompt, "result": "ok", "duration_ms": ms,
            "created": (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).timestamp()}


CHECK = "/contract-ledger check the drive for new contracts, extract only what is new"


class TestRepeatsCollapse:
    def test_three_firings_of_one_entry_become_one_row(self, project):
        (project / ".co" / "schedule.yaml").write_text(
            f'- name: check for new contracts\n  every: 15m\n  run: "{CHECK}"\n',
            encoding="utf-8")
        sessions(project,
                 run(CHECK, ago_s=2280), run(CHECK, ago_s=1380), run(CHECK, ago_s=420))

        html = dash.render_starter({"name": "billing", "skills": []})
        recent = html.split("Recent")[-1]

        assert recent.count("check for new contracts") == 1
        assert "×3" in recent

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

        assert recent.count(">check<") == 2 or recent.count("check</span>") == 2
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

    def test_the_duration_shown_is_the_most_recent_one(self, project):
        (project / ".co" / "schedule.yaml").write_text(
            f'- name: check\n  every: 15m\n  run: "{CHECK}"\n', encoding="utf-8")
        sessions(project,
                 run(CHECK, ago_s=900, ms=542000),     # 9m 2s, older
                 run(CHECK, ago_s=60, ms=42800))       # 42.8s, newest

        html = dash.render_starter({"name": "billing", "skills": []})

        assert "42.8s" in html
        assert "9m 2s" not in html

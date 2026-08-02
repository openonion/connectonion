"""An entry that is running right now must not read as overdue. #539.

`record_run` lands after the turn returns, so while a run is in flight the
Scheduled row shows the *previous* completion — and for an entry configured
every 15m whose run takes longer, that reads as a job running late.

#538 made a long run legitimately hold its slot across ticks, which makes this
display state more common, not less.
"""

import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.network.host import http_router
from connectonion.network.host import schedule as sched
from connectonion.network.host.ws_router import dashboard as dash


@pytest.fixture(autouse=True)
def clean_registry():
    sched.running_entries().clear()
    yield
    sched.running_entries().clear()


@pytest.fixture
def project(tmp_path, monkeypatch):
    co = tmp_path / ".co"
    co.mkdir()
    (co / "schedule.yaml").write_text(
        '- name: check\n  every: 15m\n  run: "/check"\n', encoding="utf-8")
    (co / "schedule-state.json").write_text(json.dumps({
        "check": {"last_run": (datetime.now(timezone.utc) - timedelta(minutes=23)).isoformat(),
                  "status": "done", "session_id": "s"}}), encoding="utf-8")
    monkeypatch.setattr(dash, "_project_dir", tmp_path)
    return tmp_path


class TestTheRowTellsTheTruth:
    def test_an_entry_in_flight_shows_as_running(self, project):
        sched.running_entries().add("check")

        html = dash.render_starter({"name": "billing", "skills": []})
        scheduled = html.split("Scheduled")[-1].split("</section>")[0]

        assert "running" in scheduled, (
            "the row says 'ran · 23m ago' for a 15m entry that is working "
            "right now, which reads as eight minutes late"
        )

    def test_an_entry_not_in_flight_still_shows_when_it_last_ran(self, project):
        """The case the row is really for: last run long ago and nothing
        happening is genuinely stuck, and must stay visible."""
        html = dash.render_starter({"name": "billing", "skills": []})
        scheduled = html.split("Scheduled")[-1].split("</section>")[0]

        assert "ran ·" in scheduled
        assert "running" not in scheduled

    def test_running_is_not_styled_as_an_error(self, project):
        sched.running_entries().add("check")
        html = dash.render_starter({"name": "billing", "skills": []})
        scheduled = html.split("Scheduled")[-1].split("</section>")[0]

        assert "bad" not in scheduled      # working is not failing


class TestTheRegistryIsAccurate:
    @pytest.mark.asyncio
    async def test_it_is_populated_while_a_run_is_in_flight(self, tmp_path, monkeypatch):
        co = tmp_path / ".co"
        co.mkdir()
        (co / "schedule.yaml").write_text(
            '- name: slow\n  every: 1m\n  run: "/slow"\n', encoding="utf-8")

        seen = []

        def handler(create_agent, storage, prompt, ttl, session=None, **kw):
            seen.append(set(sched.running_entries()))
            return {"status": "done"}

        monkeypatch.setattr(http_router, "input_handler", handler)
        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        await start.tick_once()

        assert seen == [{"slow"}]
        assert sched.running_entries() == set(), "not cleared after the run"

    @pytest.mark.asyncio
    async def test_it_is_cleared_when_a_run_raises(self, tmp_path, monkeypatch):
        co = tmp_path / ".co"
        co.mkdir()
        (co / "schedule.yaml").write_text(
            '- name: boom\n  every: 1m\n  run: "/boom"\n', encoding="utf-8")

        def blows_up(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(http_router, "input_handler", blows_up)
        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        await start.tick_once()

        assert sched.running_entries() == set(), (
            "a stuck flag would make Home claim the entry is running forever"
        )

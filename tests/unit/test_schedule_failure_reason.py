"""A failed entry says why, on the page rather than only in the log.

The failure these tests are about is the one nobody watched happen — a
deployed agent failing every fifteen minutes for an hour. By the time anyone
looks, the console line is on a machine they have to ssh into. The state file
is what the page reads, so the reason has to survive into the state file.
"""

from datetime import datetime, timedelta, timezone

import pytest

from connectonion.network.host import schedule as sched
from connectonion.network.host.ws_router import dashboard


@pytest.fixture(autouse=True)
def clean_registry():
    sched.running_entries().clear()
    yield
    sched.running_entries().clear()


def setup_page(tmp_path, monkeypatch, body):
    """Point the page at a project dir holding one schedule entry."""
    co = tmp_path / ".co"
    co.mkdir(parents=True, exist_ok=True)
    (co / "schedule.yaml").write_text(body, encoding="utf-8")
    monkeypatch.setattr(dashboard, "_project_dir", tmp_path)
    return co


ONE_ENTRY = "- name: nightly\n  every: 15m\n  run: go\n"


def test_the_reason_survives_into_the_state_file(tmp_path):
    sched.record_run(tmp_path, "nightly", when=datetime.now(timezone.utc),
                     status="failed", session_id=None,
                     reason="Insufficient ConnectOnion Credits")

    entry = sched.load_state(tmp_path)["nightly"]
    assert entry["reason"] == "Insufficient ConnectOnion Credits"


def test_a_successful_run_carries_no_reason(tmp_path):
    """A stale reason left on a now-healthy entry would be worse than none."""
    sched.record_run(tmp_path, "nightly", when=datetime.now(timezone.utc),
                     status="failed", session_id=None, reason="out of credits")
    sched.record_run(tmp_path, "nightly", when=datetime.now(timezone.utc),
                     status="done", session_id="s1")

    assert not sched.load_state(tmp_path)["nightly"].get("reason")


def test_the_page_shows_the_reason_next_to_the_failure(tmp_path, monkeypatch):
    co = setup_page(tmp_path, monkeypatch, ONE_ENTRY)
    sched.record_run(co, "nightly",
                     when=datetime.now(timezone.utc) - timedelta(minutes=5),
                     status="failed", session_id=None,
                     reason="Insufficient ConnectOnion Credits")

    html = dashboard._activity_sections()

    assert "failed" in html
    assert "Insufficient ConnectOnion Credits" in html


def test_a_long_reason_is_cut_to_fit_the_panel(tmp_path, monkeypatch):
    """The row names the failure; the log holds the traceback."""
    co = setup_page(tmp_path, monkeypatch, ONE_ENTRY)
    sched.record_run(co, "nightly", when=datetime.now(timezone.utc),
                     status="failed", session_id=None,
                     reason="boom\n" + "x" * 500)

    html = dashboard._activity_sections()

    assert "x" * 500 not in html
    # The page is a fixed-width panel; a 500-character row would push the
    # whole layout sideways to say what its first six words already said.
    assert "x" * 90 not in html


def test_a_failure_with_no_reason_still_renders(tmp_path, monkeypatch):
    """State written by an older version has no reason key."""
    co = setup_page(tmp_path, monkeypatch, ONE_ENTRY)
    sched.record_run(co, "nightly", when=datetime.now(timezone.utc),
                     status="failed", session_id=None)

    assert "failed" in dashboard._activity_sections()


def test_the_tick_records_what_the_run_raised(tmp_path, monkeypatch):
    """The end-to-end point: an exception in the run reaches the state file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "schedule.yaml").write_text(
        "- name: nightly\n  every: 1m\n  run: go\n", encoding="utf-8")

    def boom(*a, **kw):
        raise RuntimeError("Insufficient ConnectOnion Credits")

    monkeypatch.setattr(sched, "_run_entry", boom, raising=False)

    import asyncio

    startup, shutdown = sched.create_schedule_lifespan(
        tmp_path, boom, storage=None, result_ttl=60,
    )

    async def one_tick():
        await startup()
        await asyncio.sleep(0.4)
        await shutdown()

    asyncio.run(one_tick())

    entry = sched.load_state(tmp_path).get("nightly") or {}
    assert entry.get("status") == "failed"
    assert "Insufficient ConnectOnion Credits" in (entry.get("reason") or "")


def test_a_banner_shaped_error_does_not_render_as_a_row_of_equals_signs(tmp_path,
                                                                        monkeypatch):
    """The real one. Taking literally the first line showed the separator.

    This is what the deployed agent actually wrote into its state file — the
    provider formats the refusal as a banner, and the sentence a reader needs
    is the third line, not the first.
    """
    co = setup_page(tmp_path, monkeypatch, ONE_ENTRY)
    sched.record_run(co, "nightly", when=datetime.now(timezone.utc),
                     status="failed", session_id=None, reason="""
======================================================================
❌ Insufficient ConnectOnion Credits
======================================================================
Account:     0x561605f3...dbe4
Balance:     $0.0018
""")

    html = dashboard._activity_sections()

    assert "Insufficient ConnectOnion Credits" in html
    assert "=====" not in html

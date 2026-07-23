"""Unit tests for the Host-side dashboard delivery (network/host/ws_router/dashboard.py)."""

import pytest

from connectonion.network.host.ws_router.dashboard import (
    read_dashboard_snapshot,
    ensure_dashboard,
    render_starter,
)


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_read_snapshot_returns_none_when_missing(in_tmp):
    assert read_dashboard_snapshot() is None
    assert read_dashboard_snapshot("sid") is None


def test_read_snapshot_returns_frame(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>hi</h1>", encoding="utf-8")
    frame = read_dashboard_snapshot()
    assert frame == {"type": "DASHBOARD_SNAPSHOT", "html": "<h1>hi</h1>"}


def test_read_snapshot_stamps_session_id(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>hi</h1>", encoding="utf-8")
    frame = read_dashboard_snapshot("abc")
    assert frame["session_id"] == "abc"
    # No session_id when not provided (direct path)
    assert "session_id" not in read_dashboard_snapshot()


def test_ensure_dashboard_creates_starter(in_tmp):
    meta = {"name": "Lisa", "skills": [
        {"name": "daily-brief", "description": "d", "location": "project"},
        {"name": "meeting_prep", "description": "d", "location": "project"},
    ]}
    ensure_dashboard(meta)
    html = (in_tmp / "dashboard.html").read_text(encoding="utf-8")
    assert "Lisa" in html
    assert 'data-ochat-skill="daily-brief"' in html
    assert 'data-ochat-skill="meeting_prep"' in html
    assert "Daily Brief" in html          # label prettified
    assert "<script" not in html.lower()  # no scripting in agent HTML


def test_ensure_dashboard_does_not_clobber_existing(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>custom</h1>", encoding="utf-8")
    ensure_dashboard({"name": "X", "skills": []})
    assert (in_tmp / "dashboard.html").read_text(encoding="utf-8") == "<h1>custom</h1>"


def test_render_starter_empty_skills_has_no_invalid_buttons():
    html = render_starter({"name": "Bare", "skills": []})
    assert "data-ochat-skill" not in html
    assert "Quick actions" in html


def test_render_starter_features_at_most_four_skills():
    skills = [{"name": f"skill-{i}", "description": "", "location": "project"} for i in range(9)]
    html = render_starter({"name": "Many", "skills": skills})
    assert html.count("data-ochat-skill") == 4


def test_render_starter_escapes_agent_name():
    html = render_starter({"name": "<script>x</script>", "skills": []})
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


# --- Integration: the two emit points actually send DASHBOARD_SNAPSHOT ---

import pytest as _pytest
from unittest.mock import AsyncMock, Mock


@_pytest.mark.asyncio
async def test_establish_connection_sends_snapshot_after_connected(in_tmp):
    from connectonion.network.host.ws_router.connect import establish_connection
    (in_tmp / "dashboard.html").write_text("<h1>home</h1>", encoding="utf-8")

    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None
    conn = {}

    await establish_connection({}, "0xabc", send_msg, conn, storage, registry)

    types = [m["type"] for m in sent]
    assert "CONNECTED" in types and "DASHBOARD_SNAPSHOT" in types
    # snapshot comes AFTER connected
    assert types.index("DASHBOARD_SNAPSHOT") > types.index("CONNECTED")
    snap = next(m for m in sent if m["type"] == "DASHBOARD_SNAPSHOT")
    assert snap["html"] == "<h1>home</h1>" and "session_id" in snap


@_pytest.mark.asyncio
async def test_establish_connection_no_snapshot_when_no_file(in_tmp):
    from connectonion.network.host.ws_router.connect import establish_connection
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None
    await establish_connection({}, "0xabc", send_msg, {}, storage, registry)
    assert [m["type"] for m in sent] == ["CONNECTED"]  # no dashboard.html → no snapshot


@_pytest.mark.asyncio
async def test_forward_sends_snapshot_after_output(in_tmp):
    from connectonion.network.host.ws_router.agent_io import forward_agent_msgs_to_client
    (in_tmp / "dashboard.html").write_text("<h1>after run</h1>", encoding="utf-8")

    class FakeIO:
        async def read_msgs_from_agent(self):
            for _ in ():
                yield {}

    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    result_holder = [{"result": "ok", "duration_ms": 5, "session": {"messages": []}}]

    await forward_agent_msgs_to_client(send_msg, FakeIO(), "sid", result_holder=result_holder, conn={}, storage=None)

    types = [m["type"] for m in sent]
    assert "OUTPUT" in types and "DASHBOARD_SNAPSHOT" in types
    assert types.index("DASHBOARD_SNAPSHOT") > types.index("OUTPUT")

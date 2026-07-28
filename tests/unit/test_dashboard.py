"""Unit tests for the Host-side dashboard delivery (network/host/ws_router/dashboard.py)."""

import pytest
from pathlib import Path

from connectonion.network.host.ws_router import dashboard as dashboard_module
from connectonion.network.host.ws_router.dashboard import (
    MAX_DASHBOARD_BYTES,
    read_dashboard_snapshot,
    ensure_dashboard,
    featured_skills,
    render_starter,
    send_dashboard,
)


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # ensure_dashboard anchors the module-level project dir at startup; clear it so
    # each test resolves against its own tmp_path instead of a previous test's.
    monkeypatch.setattr(dashboard_module, "_project_dir", None)
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


# --- Size cap: an agent-authored file must degrade to "no Home", not stall the host ---


def test_read_snapshot_skips_oversized_file(in_tmp):
    (in_tmp / "dashboard.html").write_text("x" * (MAX_DASHBOARD_BYTES + 1), encoding="utf-8")
    assert read_dashboard_snapshot() is None


def test_read_snapshot_accepts_file_at_the_limit(in_tmp):
    (in_tmp / "dashboard.html").write_text("x" * MAX_DASHBOARD_BYTES, encoding="utf-8")
    assert read_dashboard_snapshot()["html"] == "x" * MAX_DASHBOARD_BYTES


def test_read_snapshot_survives_an_unreadable_path(in_tmp, capsys):
    # dashboard.html is agent-authored, so it can be a directory, a broken symlink,
    # or binary. stat() succeeds on some of those; the read is what fails.
    (in_tmp / "dashboard.html").mkdir()
    assert read_dashboard_snapshot() is None
    assert "Could not read" in capsys.readouterr().err


# --- Per-connection dedup: an unchanged Home shouldn't re-ship every turn ---


@_pytest.mark.asyncio
async def test_send_dashboard_sends_to_a_fresh_connection(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>home</h1>", encoding="utf-8")
    sent = []
    conn = {}

    await send_dashboard(AsyncMock(side_effect=lambda m: sent.append(m)), "sid", conn)

    assert [m["type"] for m in sent] == ["DASHBOARD_SNAPSHOT"]


@_pytest.mark.asyncio
async def test_send_dashboard_skips_an_unchanged_file(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>home</h1>", encoding="utf-8")
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    conn = {}

    await send_dashboard(send_msg, "sid", conn)
    await send_dashboard(send_msg, "sid", conn)  # nothing touched the file

    assert len(sent) == 1


@_pytest.mark.asyncio
async def test_send_dashboard_resends_after_the_agent_rewrites_it(in_tmp):
    path = in_tmp / "dashboard.html"
    path.write_text("<h1>before</h1>", encoding="utf-8")
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    conn = {}

    await send_dashboard(send_msg, "sid", conn)
    path.write_text("<h1>after the run</h1>", encoding="utf-8")
    await send_dashboard(send_msg, "sid", conn)

    assert [m["html"] for m in sent] == ["<h1>before</h1>", "<h1>after the run</h1>"]


@_pytest.mark.asyncio
async def test_send_dashboard_gives_each_connection_its_own_snapshot(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>home</h1>", encoding="utf-8")
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))

    await send_dashboard(send_msg, "sid-1", {})  # two separate clients
    await send_dashboard(send_msg, "sid-2", {})

    assert len(sent) == 2  # dedup is per connection, never global


@_pytest.mark.asyncio
async def test_send_dashboard_sends_nothing_when_there_is_no_file(in_tmp):
    sent = []
    await send_dashboard(AsyncMock(side_effect=lambda m: sent.append(m)), "sid", {})
    assert sent == []


# --- Only publishable skills become buttons, or they render and can never run ---


def test_featured_skills_excludes_unpublished_locations():
    skills = [
        {"name": "daily-brief", "description": "", "location": "project"},
        {"name": "my-notes", "description": "", "location": "user"},
        {"name": "dashboard", "description": "", "location": "builtin"},
        {"name": "review", "description": "", "location": "claude-project"},
        {"name": "future", "description": "", "location": "something-new"},
    ]
    assert [s["name"] for s in featured_skills(skills)] == ["daily-brief", "review"]


def test_starter_has_no_buttons_for_unpublished_skills(in_tmp):
    # A client validates every button against the published profile, which carries
    # project-tree skills only — so these must not become buttons at all.
    ensure_dashboard({"name": "Solo", "skills": [
        {"name": "my-notes", "description": "", "location": "user"},
        {"name": "dashboard", "description": "", "location": "builtin"},
    ]})
    html = (in_tmp / "dashboard.html").read_text(encoding="utf-8")
    assert "data-ochat-skill" not in html
    assert "Quick actions" in html  # falls back to the empty state


def test_starter_features_four_published_skills_past_unpublished_ones():
    skills = [{"name": f"personal-{i}", "description": "", "location": "user"} for i in range(5)]
    skills += [{"name": f"shipped-{i}", "description": "", "location": "project"} for i in range(6)]
    html = render_starter({"name": "Many", "skills": skills})
    assert html.count("data-ochat-skill") == 4
    assert "personal-" not in html


def test_starter_skill_names_match_what_the_profile_publishes():
    from connectonion.network.host.server import _build_agent_profile

    meta = {
        "name": "Lisa", "tools": [], "model": "co/gemini-3.6-flash",
        "skills": [
            {"name": "daily-brief", "description": "d", "location": "project"},
            {"name": "my-notes", "description": "d", "location": "user"},
        ],
    }
    published = {s["name"] for s in _build_agent_profile(meta)["skills"]}
    html = render_starter(meta)

    for skill in meta["skills"]:
        button = f'data-ochat-skill="{skill["name"]}"'
        assert (button in html) == (skill["name"] in published)


# --- Startup: anchor the directory, and don't die on an unwritable one ---


def test_ensure_dashboard_anchors_the_directory_against_later_chdir(in_tmp, tmp_path, monkeypatch):
    ensure_dashboard({"name": "Anchored", "skills": []})

    elsewhere = tmp_path.parent / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    monkeypatch.chdir(elsewhere)  # a tool or plugin wanders off

    assert "Anchored" in read_dashboard_snapshot()["html"]


def test_ensure_dashboard_takes_an_explicit_project_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_module, "_project_dir", None)
    project = tmp_path / "project"
    project.mkdir()

    ensure_dashboard({"name": "Explicit", "skills": []}, project_dir=project)

    assert (project / "dashboard.html").exists()


def test_ensure_dashboard_warns_instead_of_crashing_on_an_unwritable_dir(in_tmp, monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise PermissionError("read-only file system")
    monkeypatch.setattr(Path, "write_text", refuse)

    ensure_dashboard({"name": "Locked", "skills": []})  # host startup must survive

    assert "Could not write" in capsys.readouterr().err
    assert read_dashboard_snapshot() is None

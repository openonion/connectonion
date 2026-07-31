"""Unit tests for the Host-side dashboard delivery (network/host/ws_router/dashboard.py)."""

import pytest
from pathlib import Path

from connectonion.network.host.ws_router import dashboard as dashboard_module
from connectonion.network.host.ws_router.dashboard import (
    MAX_DASHBOARD_BYTES,
    read_dashboard_snapshot,
    ensure_dashboard,
    group_skills,
    published_skills,
    render_starter,
    send_dashboard,
)


@pytest.fixture(autouse=True)
def no_personal_starter(tmp_path, monkeypatch):
    """Keep the operator's own ~/.co/starter.html out of this suite.

    It is a real feature, and one this file tests — so a developer who actually
    uses it would otherwise have every render here come from their page. A
    starter without a $body placeholder fails nine of these tests, and one with a
    script tag fails two, for no reason connected to the change being made.

    Tests that want an override set STARTER_OVERRIDE themselves; monkeypatch
    applies in order, so theirs wins.
    """
    monkeypatch.setattr(dashboard_module, "STARTER_OVERRIDE", tmp_path / "absent-starter.html")
    dashboard_module._starter_templates.cache_clear()
    yield
    dashboard_module._starter_templates.cache_clear()


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
    html = (in_tmp / ".co" / "dashboard.html").read_text(encoding="utf-8")
    assert "Lisa" in html
    assert 'data-ochat-skill="daily-brief"' in html
    assert 'data-ochat-skill="meeting_prep"' in html
    assert ">daily-brief<" in html        # the name you actually type
    assert "<script" not in html.lower()  # no scripting in agent HTML


def test_ensure_dashboard_does_not_clobber_existing(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>custom</h1>", encoding="utf-8")
    ensure_dashboard({"name": "X", "skills": []})
    assert (in_tmp / "dashboard.html").read_text(encoding="utf-8") == "<h1>custom</h1>"


def test_render_starter_empty_skills_has_no_invalid_buttons():
    html = render_starter({"name": "Bare", "skills": []})
    assert "data-ochat-skill" not in html
    assert ".co/skills/" in html  # tells the operator how to get one


def test_every_published_skill_is_reachable():
    """The old starter showed 4 and dropped the rest, which on a real agent meant
    111 skills the Home page silently pretended did not exist."""
    skills = [{"name": f"skill-{i:03d}", "description": "", "location": "project"} for i in range(115)]
    html = render_starter({"name": "Many", "skills": skills})
    assert html.count("data-ochat-skill") == 115


def test_a_short_list_is_not_hidden_behind_a_disclosure():
    skills = [{"name": f"skill-{i}", "description": "", "location": "project"} for i in range(6)]
    html = render_starter({"name": "Few", "skills": skills})
    assert "<details" not in html


def test_a_long_list_is_grouped_and_opens_on_something():
    skills = [{"name": f"lark-{i}", "description": "", "location": "project"} for i in range(20)]
    skills += [{"name": f"x-{i}", "description": "", "location": "project"} for i in range(5)]
    html = render_starter({"name": "Many", "skills": skills})
    assert "<details" in html
    assert "<details class=\"card group\" open>" in html  # never a wall of shut drawers


def test_skill_rows_carry_their_description():
    html = render_starter({"name": "D", "skills": [
        {"name": "ship-feature", "description": "release a version", "location": "project"},
    ]})
    assert "release a version" in html


def test_skill_names_are_shown_verbatim():
    """Title-casing turned nano-banana-us into "Nano Banana Us", which names nothing
    and is not what you type to run it."""
    html = render_starter({"name": "N", "skills": [
        {"name": "nano-banana-us", "description": "", "location": "project"},
    ]})
    assert ">nano-banana-us<" in html
    assert "Nano Banana Us" not in html


def test_the_starter_carries_no_javascript():
    """The client's CSP runs only its own bridge script; an agent <script> is blocked,
    so anything this page relies on JS for is simply dead on arrival."""
    skills = [{"name": f"lark-{i}", "description": "d", "location": "project"} for i in range(20)]
    html = render_starter({"name": "Many", "skills": skills})
    assert "<script" not in html
    assert "onclick" not in html


def test_render_starter_escapes_a_hostile_skill_name():
    html = render_starter({"name": "X", "skills": [
        {"name": "<img src=x>", "description": "<script>y</script>", "location": "project"},
    ]})
    assert "<img src=x>" not in html
    assert "<script>y</script>" not in html


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


def test_published_skills_excludes_unpublished_locations():
    skills = [
        {"name": "daily-brief", "description": "", "location": "project"},
        {"name": "my-notes", "description": "", "location": "user"},
        {"name": "dashboard", "description": "", "location": "builtin"},
        {"name": "review", "description": "", "location": "claude-project"},
        {"name": "future", "description": "", "location": "something-new"},
    ]
    assert [s["name"] for s in published_skills(skills)] == ["daily-brief", "review"]


def test_starter_has_no_buttons_for_unpublished_skills(in_tmp):
    # A client validates every button against the published profile, which carries
    # project-tree skills only — so these must not become buttons at all.
    ensure_dashboard({"name": "Solo", "skills": [
        {"name": "my-notes", "description": "", "location": "user"},
        {"name": "dashboard", "description": "", "location": "builtin"},
    ]})
    html = (in_tmp / ".co" / "dashboard.html").read_text(encoding="utf-8")
    assert "data-ochat-skill" not in html
    assert ".co/skills/" in html  # falls back to the empty state


def test_starter_lists_published_skills_past_unpublished_ones():
    skills = [{"name": f"personal-{i}", "description": "", "location": "user"} for i in range(5)]
    skills += [{"name": f"shipped-{i}", "description": "", "location": "project"} for i in range(6)]
    html = render_starter({"name": "Many", "skills": skills})
    assert html.count("data-ochat-skill") == 6
    assert "personal-" not in html


def test_group_skills_needs_a_third_member_to_form_a_family():
    """Two lark-* skills behind a group of two is a click that buys nothing."""
    skills = [{"name": n} for n in ["lark-base", "lark-doc", "lark-im", "x-api", "x-write", "tweet"]]
    families, loose = group_skills(skills)

    assert [(p, [s["name"] for s in m]) for p, m in families] == [
        ("lark", ["lark-base", "lark-doc", "lark-im"]),
    ]
    assert [s["name"] for s in loose] == ["tweet", "x-api", "x-write"]


def test_group_skills_splits_colon_prefixes_too():
    skills = [{"name": n} for n in ["vercel:deploy", "vercel:env", "vercel:nextjs"]]
    families, loose = group_skills(skills)

    assert families[0][0] == "vercel"
    assert loose == []


def test_the_subtitle_omits_what_it_does_not_know():
    """"0 tools" reads as a broken agent; a missing count reads as a quiet one."""
    html = render_starter({"name": "Quiet", "skills": [], "tools": [], "model": None})
    assert "0 tool" not in html
    assert "0 skill" not in html


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

    assert (project / ".co" / "dashboard.html").exists()


def test_ensure_dashboard_warns_instead_of_crashing_on_an_unwritable_dir(in_tmp, monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise PermissionError("read-only file system")
    monkeypatch.setattr(Path, "write_text", refuse)

    ensure_dashboard({"name": "Locked", "skills": []})  # host startup must survive

    assert "Could not write" in capsys.readouterr().err
    assert read_dashboard_snapshot() is None


def test_the_starter_template_ships_in_the_wheel():
    """The markup lives in starter.html beside the module; a wheel that drops it
    turns every `co ai` startup into a FileNotFoundError."""
    assert (Path(dashboard_module.__file__).parent / "starter.html").is_file()


def test_the_fragment_templates_do_not_leak_into_the_page():
    """<template> tags are lifted out and dropped — a browser would ignore them
    anyway, but shipping them means shipping an unsubstituted $name."""
    html = render_starter({"name": "X", "skills": [
        {"name": "a-skill", "description": "d", "location": "project"},
    ]})
    assert "<template" not in html
    assert "$" not in html


# --- Where the Home page lives: .co/, found from the project root ---


def test_the_starter_is_written_into_the_co_directory(in_tmp):
    (in_tmp / ".co").mkdir()
    ensure_dashboard({"name": "Lisa", "skills": []})

    assert (in_tmp / ".co" / "dashboard.html").is_file()
    assert not (in_tmp / "dashboard.html").exists()


def test_the_project_is_found_from_a_subdirectory(in_tmp, monkeypatch):
    """Resolving against the bare cwd meant running the agent from a subdirectory
    created a second dashboard.html there and served that one."""
    (in_tmp / ".co").mkdir()
    nested = in_tmp / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    ensure_dashboard({"name": "Lisa", "skills": []})

    assert (in_tmp / ".co" / "dashboard.html").is_file()
    assert not (nested / "dashboard.html").exists()
    assert dashboard_module.dashboard_path() == in_tmp / ".co" / "dashboard.html"


def test_an_existing_root_dashboard_is_still_served(in_tmp):
    """Agents written before the move keep their Home. Silently dropping it on
    upgrade would be worse than an inconsistent path."""
    (in_tmp / ".co").mkdir()
    (in_tmp / "dashboard.html").write_text("<h1>mine</h1>", encoding="utf-8")

    ensure_dashboard({"name": "Lisa", "skills": []})

    assert dashboard_module.dashboard_path() == in_tmp / "dashboard.html"
    assert read_dashboard_snapshot()["html"] == "<h1>mine</h1>"
    assert not (in_tmp / ".co" / "dashboard.html").exists()  # not moved, not copied


def test_the_co_copy_wins_when_both_exist(in_tmp):
    (in_tmp / ".co").mkdir()
    (in_tmp / "dashboard.html").write_text("<h1>old</h1>", encoding="utf-8")
    (in_tmp / ".co" / "dashboard.html").write_text("<h1>current</h1>", encoding="utf-8")

    assert read_dashboard_snapshot()["html"] == "<h1>current</h1>"


def test_an_agent_outside_a_project_still_gets_a_home(in_tmp):
    """No .co/ anywhere above: the Home lands where the agent was started."""
    ensure_dashboard({"name": "Loose", "skills": []})

    assert (in_tmp / ".co" / "dashboard.html").is_file()


def test_a_personal_starter_template_replaces_the_bundled_one(in_tmp, monkeypatch, tmp_path):
    """~/.co/starter.html is a template, not a finished page — the agent's own name
    and skills still get rendered into it."""
    override = tmp_path / "home" / ".co" / "starter.html"
    override.parent.mkdir(parents=True)
    override.write_text("<h1>$name</h1><p>$subtitle</p>\n$body\n", encoding="utf-8")
    monkeypatch.setattr(dashboard_module, "STARTER_OVERRIDE", override)
    dashboard_module._starter_templates.cache_clear()
    html = render_starter({"name": "Mine", "model": "co/x", "skills": [
        {"name": "daily-brief", "description": "d", "location": "project"},
    ]})

    assert "<h1>Mine</h1>" in html
    assert "co/x" in html
    # Restyling the shell must not mean copying — or losing — the row markup.
    assert 'data-ochat-skill="daily-brief"' in html


def test_the_deploy_rsync_carries_the_dashboard():
    """.co/* is excluded to protect identity and logs; the Home page is not state,
    and a deploy that drops it silently regenerates a starter over your page."""
    import inspect
    from connectonion.cli.commands import deploy_to_server

    source = inspect.getsource(deploy_to_server._sync_code)
    assert '".co/dashboard.html"' in source
    assert source.index('".co/dashboard.html"') < source.index('".co/*"')

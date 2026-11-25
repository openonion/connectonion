"""Unit tests for the Host-side Control Center page delivery (network/host/ws_router/control_center.py)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from connectonion.network.host.ws_router import control_center as dashboard_module
from connectonion.network.host.ws_router.control_center import (
    MAX_CONTROL_CENTER_BYTES,
    ensure_control_center,
    published_skills,
    read_control_center_snapshot,
    render_starter,
    send_control_center_page,
)

# These tests are about the file, not about who reads it; render as an admin
# viewer so nothing is filtered away (test_dashboard_visitor_privacy covers that).
OWNER_VIEW = dashboard_module.viewer_for("0x" + "a" * 64, is_admin=True)


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
    # ensure_control_center anchors the module-level project dir at startup; clear it so
    # each test resolves against its own tmp_path instead of a previous test's.
    monkeypatch.setattr(dashboard_module, "_project_dir", None)
    # Same for the metadata the starter is rendered from: leaking one test's agent
    # into the next would make a Home appear where the test never started a host.
    monkeypatch.setattr(dashboard_module, "_agent_metadata", None)
    return tmp_path


def test_no_file_means_the_starter_not_no_home(in_tmp):
    """Not having customised a Home is a state, not an absence. This used to
    answer None, which is why the starter had to be written to disk on first
    boot — and why every agent's Home then froze at that version."""
    ensure_control_center({"name": "Maren", "skills": []})

    frame = read_control_center_snapshot(viewer=OWNER_VIEW)
    assert frame and "Maren" in frame["html"]
    assert read_control_center_snapshot("sid", viewer=OWNER_VIEW)["session_id"] == "sid"


def test_read_snapshot_returns_frame(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>hi</h1>", encoding="utf-8")
    frame = read_control_center_snapshot(viewer=OWNER_VIEW)
    assert frame == {"type": "CONTROL_CENTER_SNAPSHOT", "html": "<h1>hi</h1>"}


def test_read_snapshot_stamps_session_id(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>hi</h1>", encoding="utf-8")
    frame = read_control_center_snapshot("abc", viewer=OWNER_VIEW)
    assert frame["session_id"] == "abc"
    # No session_id when not provided (direct path)
    assert "session_id" not in read_control_center_snapshot(viewer=OWNER_VIEW)


def test_the_starter_is_what_an_uncustomised_agent_serves(in_tmp):
    meta = {"name": "Maren", "skills": [
        {"name": "daily-brief", "description": "d", "location": "project"},
        {"name": "meeting_prep", "description": "d", "location": "project"},
    ]}
    ensure_control_center(meta)
    html = read_control_center_snapshot(viewer=OWNER_VIEW)["html"]
    assert "Maren" in html
    assert 'data-ochat-skill="daily-brief"' in html
    assert 'data-ochat-skill="meeting_prep"' in html
    assert ">daily-brief<" in html        # the name you actually type
    assert "<script" not in html.lower()  # no scripting in agent HTML


def test_ensure_dashboard_does_not_clobber_existing(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>custom</h1>", encoding="utf-8")
    ensure_control_center({"name": "X", "skills": []})
    assert (in_tmp / "dashboard.html").read_text(encoding="utf-8") == "<h1>custom</h1>"


def test_render_starter_empty_skills_has_no_invalid_buttons():
    html = render_starter({"name": "Bare", "skills": []})
    assert 'data-ochat-skill="' not in html
    assert ".co/skills/" in html  # tells the operator how to get one


def test_every_published_skill_is_reachable():
    """The old starter showed 4 and dropped the rest, which on a real agent meant
    111 skills the Home page silently pretended did not exist."""
    skills = [{"name": f"skill-{i:03d}", "description": "", "location": "project"} for i in range(115)]
    html = render_starter({"name": "Many", "skills": skills})
    # Every capability is in the searchable disclosure, once.
    assert html.count('data-ochat-skill="') == 115


def test_a_short_list_is_not_hidden_behind_a_disclosure():
    skills = [{"name": f"skill-{i}", "description": "", "location": "project"} for i in range(6)]
    html = render_starter({"name": "Few", "skills": skills})
    assert '<section class="card skills"' in html
    assert '<details class="more">' not in html
    assert "<co-filter" not in html          # search only for a list long enough to fold


def test_a_long_list_shows_the_first_few_and_folds_the_rest():
    """One fold, not a taxonomy. Grouping by name prefix rendered fifteen skills
    as four headers, three visible rows and a bucket called "other" — a page
    showing a fifth of its content."""
    skills = [{"name": f"lark-{i}", "description": "", "location": "project"} for i in range(20)]
    skills += [{"name": f"x-{i}", "description": "", "location": "project"} for i in range(5)]
    html = render_starter({"name": "Many", "skills": skills})

    assert html.count('<details class="more">') == 1
    assert "17 more skills" in html          # 25 total, 8 shown
    assert '<co-filter target="#capability-list"' in html
    assert "other" not in html.lower()


def test_every_skill_is_on_the_page_even_when_folded():
    """Folded is not dropped. The count in the control has to be the truth."""
    skills = [{"name": f"skill-{i:02d}", "description": "", "location": "project"}
              for i in range(25)]
    html = render_starter({"name": "Many", "skills": skills})

    for skill in skills:
        assert f'data-ochat-skill="{skill["name"]}"' in html


def test_the_list_is_alphabetical_so_families_land_together():
    """What replaced the grouping: sorting clusters lark-* on its own, with no
    header, no bucket, and nothing hidden."""
    skills = [{"name": n, "description": "", "location": "project"}
              for n in ["tweet", "lark-doc", "alpha", "lark-base"]]
    html = render_starter({"name": "Sorted", "skills": skills})

    order = [html.index(f'data-ochat-skill="{n}"')
             for n in ["alpha", "lark-base", "lark-doc", "tweet"]]
    assert order == sorted(order)


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


def test_control_center_semantic_golden_layout_is_present():
    html = render_starter({
        "name": "Operations",
        "model": "co/example",
        "trust": "careful",
        "address": ADDRESS,
        "tools": ["read", "write"],
        "skills": [
            {"name": "daily-brief", "description": "Prepare the day.", "location": "project"},
            {"name": "invoice", "description": "Create an invoice.", "location": "project"},
        ],
    })

    page = html.split("<!--FRAGMENTS")[0]
    assert 'id="skills-title"' in page and 'class="health"' in page
    assert 'id="capability-list"' in page
    assert "co/example" in page and "trust careful" in page and ADDRESS in page
    # #3350: O Chat titles the pane; the page does not say it again.
    assert "Control Center" not in page.split("<body>")[1]


def test_there_is_no_workspace_placeholder_card():
    """#3350: "Workspace / Use Chat for live status" said nothing on every agent."""
    html = render_starter({"name": "Operations", "skills": []})
    assert "Workspace" not in html and "Use Chat for live status" not in html
    assert "<details" not in html     # nothing that fits on one line is folded


def test_control_center_never_claims_a_static_runtime_state():
    """The dashboard snapshot does not receive turn lifecycle frames. Calling it
    Ready while Chat is working or awaiting approval contradicts the live client."""
    html = render_starter({"name": "Operations", "skills": []})

    assert "Available for a new task" not in html
    assert "<strong>Ready</strong>" not in html


def test_quick_actions_cannot_set_the_iframe_minimum_width():
    template = (Path(dashboard_module.__file__).parent / "starter.html").read_text()

    assert "html, body { max-width: 100%; overflow-x: clip; }" in template
    assert "width: 100%; min-width: 0; max-width: 100%;" in template
    assert "min-width: 0; max-width: 100%; color" in template


def test_control_center_accessibility_contract_is_in_the_shipped_template():
    template = (Path(dashboard_module.__file__).parent / "starter.html").read_text()
    assert "min-height: 44px" in template
    assert "prefers-reduced-motion: reduce" in template
    assert ":focus-visible" in template
    assert "@media (max-width: 520px)" in template
    assert "@media (min-width: 900px)" in template
    assert "https://" not in template and "http://" not in template


def _contrast(hex_a, hex_b):
    def luminance(value):
        rgb = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [part / 12.92 if part <= .04045 else ((part + .055) / 1.055) ** 2.4
                  for part in rgb]
        return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]
    high, low = sorted((luminance(hex_a), luminance(hex_b)), reverse=True)
    return (high + .05) / (low + .05)


def test_control_center_text_tokens_meet_wcag_aa_in_light_and_dark():
    for foreground, background in (
        ("#18181b", "#fafafa"),
        ("#52525b", "#fafafa"),
        ("#6b6b73", "#ffffff"),
        ("#6b6b73", "#f4f4f5"),      # meta on a quiet pill / invite strip
        ("#18181b", "#f4f4f5"),      # quiet pill label
        ("#ffffff", "#18181b"),      # primary pill, admin badge
        ("#0b2416", "#22d27a"),      # ink on the green mark
        ("#c0262d", "#ffffff"),      # bad number, Block label
        ("#c0262d", "#f4f4f5"),
        ("#a15c00", "#ffffff"),      # warn number
        ("#f4f4f5", "#0f0f10"),
        ("#c4c4ca", "#0f0f10"),
        ("#a1a1aa", "#19191b"),
    ):
        assert _contrast(foreground, background) >= 4.5


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


# --- Integration: the two emit points actually send CONTROL_CENTER_SNAPSHOT ---


@pytest.mark.asyncio
async def test_establish_connection_sends_snapshot_after_connected(in_tmp):
    from connectonion.network.host.ws_router.connect import establish_connection
    (in_tmp / "dashboard.html").write_text("<h1>home</h1>", encoding="utf-8")

    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    storage = Mock()
    storage.get.return_value = None
    registry = Mock()
    registry.get.return_value = None
    conn = {}

    await establish_connection({}, "0xabc", send_msg, conn, storage, registry)

    types = [m["type"] for m in sent]
    assert "CONNECTED" in types and "CONTROL_CENTER_SNAPSHOT" in types
    # snapshot comes AFTER connected
    assert types.index("CONTROL_CENTER_SNAPSHOT") > types.index("CONNECTED")
    snap = next(m for m in sent if m["type"] == "CONTROL_CENTER_SNAPSHOT")
    assert snap["html"] == "<h1>home</h1>" and "session_id" in snap


@pytest.mark.asyncio
async def test_establish_connection_no_snapshot_when_no_file(in_tmp):
    from connectonion.network.host.ws_router.connect import establish_connection
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    storage = Mock()
    storage.get.return_value = None
    registry = Mock()
    registry.get.return_value = None
    await establish_connection({}, "0xabc", send_msg, {}, storage, registry)
    assert [m["type"] for m in sent] == ["CONNECTED"]  # no dashboard.html → no snapshot


@pytest.mark.asyncio
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
    assert "OUTPUT" in types and "CONTROL_CENTER_SNAPSHOT" in types
    assert types.index("CONTROL_CENTER_SNAPSHOT") > types.index("OUTPUT")


# --- Size cap: an agent-authored file must degrade to "no Home", not stall the host ---


def test_read_snapshot_explains_oversized_file(in_tmp, monkeypatch):
    monkeypatch.setattr(dashboard_module, "MAX_CONTROL_CENTER_BYTES", 1024)
    (in_tmp / "dashboard.html").write_text("x" * (dashboard_module.MAX_CONTROL_CENTER_BYTES + 1), encoding="utf-8")
    assert "128 MiB" in read_control_center_snapshot(viewer=OWNER_VIEW)["html"]


def test_read_snapshot_accepts_file_at_the_limit(in_tmp, monkeypatch):
    monkeypatch.setattr(dashboard_module, "MAX_CONTROL_CENTER_BYTES", 1024)
    (in_tmp / "dashboard.html").write_text("x" * dashboard_module.MAX_CONTROL_CENTER_BYTES, encoding="utf-8")
    assert read_control_center_snapshot(viewer=OWNER_VIEW)["html"] == "x" * dashboard_module.MAX_CONTROL_CENTER_BYTES


def test_read_snapshot_survives_an_unreadable_path(in_tmp, capsys):
    # dashboard.html is agent-authored, so it can be a directory, a broken symlink,
    # or binary. stat() succeeds on some of those; the read is what fails.
    (in_tmp / "dashboard.html").mkdir()
    assert "Could not read" in read_control_center_snapshot(viewer=OWNER_VIEW)["html"]
    assert "Could not read" in capsys.readouterr().err


# --- Per-connection dedup: an unchanged Home shouldn't re-ship every turn ---


@pytest.mark.asyncio
async def test_send_dashboard_sends_to_a_fresh_connection(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>home</h1>", encoding="utf-8")
    sent = []
    conn = {}

    await send_control_center_page(AsyncMock(side_effect=lambda m: sent.append(m)), "sid", conn)

    # The pre-#3336 frame name follows for one preview cycle, for older O Chat builds.
    assert [m["type"] for m in sent] == ["CONTROL_CENTER_SNAPSHOT", "DASHBOARD_SNAPSHOT"]
    assert sent[0]["html"] == sent[1]["html"] == "<h1>home</h1>"


@pytest.mark.asyncio
async def test_send_dashboard_skips_an_unchanged_file(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>home</h1>", encoding="utf-8")
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    conn = {}

    await send_control_center_page(send_msg, "sid", conn)
    await send_control_center_page(send_msg, "sid", conn)  # nothing touched the file

    assert [m["type"] for m in sent] == ["CONTROL_CENTER_SNAPSHOT", "DASHBOARD_SNAPSHOT"]


@pytest.mark.asyncio
async def test_send_dashboard_resends_after_the_agent_rewrites_it(in_tmp):
    path = in_tmp / "dashboard.html"
    path.write_text("<h1>before</h1>", encoding="utf-8")
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    conn = {}

    await send_control_center_page(send_msg, "sid", conn)
    path.write_text("<h1>after the run</h1>", encoding="utf-8")
    await send_control_center_page(send_msg, "sid", conn)

    pages = [m["html"] for m in sent if m["type"] == "CONTROL_CENTER_SNAPSHOT"]
    assert pages == ["<h1>before</h1>", "<h1>after the run</h1>"]


@pytest.mark.asyncio
async def test_send_dashboard_gives_each_connection_its_own_snapshot(in_tmp):
    (in_tmp / "dashboard.html").write_text("<h1>home</h1>", encoding="utf-8")
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))

    await send_control_center_page(send_msg, "sid-1", {})  # two separate clients
    await send_control_center_page(send_msg, "sid-2", {})

    # dedup is per connection, never global
    assert [m["session_id"] for m in sent if m["type"] == "CONTROL_CENTER_SNAPSHOT"] == ["sid-1", "sid-2"]


@pytest.mark.asyncio
async def test_send_dashboard_sends_nothing_when_there_is_no_file(in_tmp):
    sent = []
    await send_control_center_page(AsyncMock(side_effect=lambda m: sent.append(m)), "sid", {})
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
    ensure_control_center({"name": "Solo", "skills": [
        {"name": "my-notes", "description": "", "location": "user"},
        {"name": "dashboard", "description": "", "location": "builtin"},
    ]})
    html = read_control_center_snapshot(viewer=OWNER_VIEW)["html"]
    assert 'data-ochat-skill="' not in html
    assert ".co/skills/" in html  # falls back to the empty state


def test_starter_lists_published_skills_past_unpublished_ones():
    skills = [{"name": f"personal-{i}", "description": "", "location": "user"} for i in range(5)]
    skills += [{"name": f"shipped-{i}", "description": "", "location": "project"} for i in range(6)]
    html = render_starter({"name": "Many", "skills": skills})
    assert html.count('data-ochat-skill="') == 6
    assert "personal-" not in html


def test_the_subtitle_omits_what_it_does_not_know():
    """"0 tools" reads as a broken agent; a missing count reads as a quiet one."""
    html = render_starter({"name": "Quiet", "skills": [], "tools": [], "model": None})
    assert "0 tool" not in html
    assert "0 skill" not in html


def test_starter_skill_names_match_what_the_profile_publishes():
    from connectonion.network.host.server import _build_agent_profile

    meta = {
        "name": "Maren", "tools": [], "model": "co/gemini-3.7-flash",
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
    ensure_control_center({"name": "Anchored", "skills": []})

    elsewhere = tmp_path.parent / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    monkeypatch.chdir(elsewhere)  # a tool or plugin wanders off

    assert "Anchored" in read_control_center_snapshot(viewer=OWNER_VIEW)["html"]


def test_ensure_dashboard_takes_an_explicit_project_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_module, "_project_dir", None)
    project = tmp_path / "project"
    project.mkdir()

    ensure_control_center({"name": "Explicit", "skills": []}, project_dir=project)

    assert dashboard_module._project_dir == project
    assert dashboard_module.control_center_path() == project / ".co" / "control_center.html"


def test_a_read_only_project_still_gets_a_home(in_tmp, monkeypatch):
    """This used to be a warning and no Home at all: the starter was written to
    disk, and a read-only project could not be written to. Rendering it instead
    of storing it removes the failure mode rather than handling it."""
    def refuse(*args, **kwargs):
        raise PermissionError("read-only file system")
    monkeypatch.setattr(Path, "write_text", refuse)

    ensure_control_center({"name": "Locked", "skills": []})

    assert "Locked" in read_control_center_snapshot(viewer=OWNER_VIEW)["html"]


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


def test_starting_a_host_writes_no_file(in_tmp):
    """The whole point. A file written once is a fossil of the starter that
    happened to be installed that day, and nothing ever refreshes it."""
    (in_tmp / ".co").mkdir()
    ensure_control_center({"name": "Maren", "skills": []})

    assert not (in_tmp / ".co" / "dashboard.html").exists()
    assert not (in_tmp / "dashboard.html").exists()


def test_the_project_is_found_from_a_subdirectory(in_tmp, monkeypatch):
    """Resolving against the bare cwd meant running the agent from a subdirectory
    created a second dashboard.html there and served that one."""
    (in_tmp / ".co").mkdir()
    nested = in_tmp / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    ensure_control_center({"name": "Maren", "skills": []})

    assert dashboard_module.control_center_path() == in_tmp / ".co" / "control_center.html"


def test_an_existing_root_dashboard_is_still_served(in_tmp):
    """Agents written before the move keep their Home. Silently dropping it on
    upgrade would be worse than an inconsistent path."""
    (in_tmp / ".co").mkdir()
    (in_tmp / "dashboard.html").write_text("<h1>mine</h1>", encoding="utf-8")

    ensure_control_center({"name": "Maren", "skills": []})

    assert dashboard_module.control_center_path() == in_tmp / "dashboard.html"
    assert read_control_center_snapshot(viewer=OWNER_VIEW)["html"] == "<h1>mine</h1>"
    assert not (in_tmp / ".co" / "dashboard.html").exists()  # not moved, not copied


def test_control_center_html_is_the_page(in_tmp):
    (in_tmp / ".co").mkdir()
    (in_tmp / ".co" / "control_center.html").write_text("<h1>new</h1>", encoding="utf-8")

    assert dashboard_module.control_center_path() == in_tmp / ".co" / "control_center.html"
    assert read_control_center_snapshot(viewer=OWNER_VIEW)["html"] == "<h1>new</h1>"


def test_a_project_with_only_the_old_name_keeps_its_page(in_tmp, capsys):
    """#3336: a .co/dashboard.html written before the rename is still served,
    untouched, and co host says once how to rename it."""
    (in_tmp / ".co").mkdir()
    (in_tmp / ".co" / "dashboard.html").write_text("<h1>mine</h1>", encoding="utf-8")

    ensure_control_center({"name": "Maren", "skills": []})

    assert read_control_center_snapshot(viewer=OWNER_VIEW)["html"] == "<h1>mine</h1>"
    assert not (in_tmp / ".co" / "control_center.html").exists()
    assert "rename" in "".join(capsys.readouterr())


def test_the_new_name_wins_over_the_old_one(in_tmp, capsys):
    (in_tmp / ".co").mkdir()
    (in_tmp / "dashboard.html").write_text("<h1>oldest</h1>", encoding="utf-8")
    (in_tmp / ".co" / "dashboard.html").write_text("<h1>old</h1>", encoding="utf-8")
    (in_tmp / ".co" / "control_center.html").write_text("<h1>new</h1>", encoding="utf-8")

    ensure_control_center({"name": "Maren", "skills": []})

    assert read_control_center_snapshot(viewer=OWNER_VIEW)["html"] == "<h1>new</h1>"
    assert "rename" not in "".join(capsys.readouterr())


def test_the_co_copy_wins_when_both_exist(in_tmp):
    (in_tmp / ".co").mkdir()
    (in_tmp / "dashboard.html").write_text("<h1>old</h1>", encoding="utf-8")
    (in_tmp / ".co" / "dashboard.html").write_text("<h1>current</h1>", encoding="utf-8")

    assert read_control_center_snapshot(viewer=OWNER_VIEW)["html"] == "<h1>current</h1>"


def test_an_agent_outside_a_project_still_gets_a_home(in_tmp):
    """No .co/ anywhere above, and nowhere to write one — still a Home."""
    ensure_control_center({"name": "Loose", "skills": []})

    assert "Loose" in read_control_center_snapshot(viewer=OWNER_VIEW)["html"]


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


def test_the_deploy_rsync_carries_the_dashboard(tmp_path):
    """The Home page is not state, and a deploy that drops it silently
    regenerates a starter over your page.

    Asserted by running the filters rather than by reading the argv: the
    previous version of this test checked that `.co/dashboard.html` appeared
    before `.co/*` in the source, which stayed true while `host.yaml` and
    `OO.md` were being dropped by the same rule.
    """
    import shutil
    import subprocess

    from connectonion.cli.commands.deploy_to_server import RSYNC_FILTERS

    if shutil.which("rsync") is None:
        pytest.skip("needs rsync on PATH")

    local, server = tmp_path / "local", tmp_path / "server"
    (local / ".co").mkdir(parents=True)
    (server / ".co").mkdir(parents=True)
    (local / ".co" / "dashboard.html").write_text("<h1>mine</h1>")

    subprocess.run(
        ["rsync", "-a", "--delete", *RSYNC_FILTERS, f"{local}/", f"{server}/"],
        check=True, capture_output=True,
    )

    assert (server / ".co" / "dashboard.html").read_text() == "<h1>mine</h1>"


ADDRESS = "0x" + "9f" * 32


def test_the_home_page_shows_the_agents_address():
    """The one fact that otherwise costs an ssh session.

    A deployed agent's address cannot be known before its first boot (#396), so
    today you learn it by opening a shell and reading the logs — while the Home
    pane has been receiving it in agent_metadata and rendering it nowhere.
    """
    html = render_starter({"name": "A", "address": ADDRESS, "skills": []})

    assert ADDRESS in html


def test_the_address_is_shown_in_full():
    """A truncated address is decoration: half of it does not save the trip."""
    html = render_starter({"name": "A", "address": ADDRESS, "skills": []})

    assert "…" not in html and "..." not in html
    assert html.count(ADDRESS) == 1


def test_an_agent_with_no_address_gets_no_empty_line():
    html = render_starter({"name": "A", "skills": []})

    assert 'class="addr"' not in html


def test_health_says_who_the_agent_will_talk_to():
    """`trust` was also arriving and being dropped. It is the difference between
    an agent strangers can reach and one they cannot. It is on the Health line,
    with the model and the version."""
    from connectonion import __version__
    html = render_starter({"name": "A", "trust": "careful", "model": "co/x", "skills": []})
    health = html.split('class="health"')[1].split("</footer>")[0]

    assert "trust careful" in health and "co/x" in health and __version__ in health


def test_a_hostile_address_is_escaped():
    html = render_starter({"name": "A", "skills": [],
                           "address": '"><script>alert(1)</script>'})

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_an_operator_override_without_the_new_field_still_renders(tmp_path,
                                                                  monkeypatch):
    """~/.co/starter.html replaces the bundled template. One written before this
    change has no $address in it, and must keep working — losing the address is
    their layout's business; raising KeyError is ours."""
    from connectonion.network.host.ws_router import control_center as dashboard

    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    (home / ".co" / "starter.html").write_text(
        "<html><body><h1>$name</h1><p>$subtitle</p>$body</body></html>",
        encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: home)
    dashboard._starter_templates.cache_clear()
    try:
        html = render_starter({"name": "A", "address": ADDRESS, "skills": []})
    finally:
        dashboard._starter_templates.cache_clear()

    assert "<h1>A</h1>" in html


def test_dashboard_above_old_limit_preserves_unicode_and_scripts(in_tmp):
    html = '<!doctype html><style>.x{color:red}</style><script>let a=1;</script>' + '房源价格🌍' * 300000
    assert len(html.encode()) > 2 * 1024 * 1024
    (in_tmp / 'dashboard.html').write_text(html, encoding='utf-8')
    frame = read_control_center_snapshot('large', viewer=OWNER_VIEW)
    assert frame == {'type': 'CONTROL_CENTER_SNAPSHOT', 'html': html, 'session_id': 'large'}


def test_encoding_expansion_returns_visible_error(in_tmp, monkeypatch):
    monkeypatch.setattr(dashboard_module, 'MAX_WEBSOCKET_MESSAGE_BYTES', 65540)
    (in_tmp / 'dashboard.html').write_text('<p>large envelope</p>')
    assert 'transport envelope' in read_control_center_snapshot(viewer=OWNER_VIEW)['html']


@pytest.mark.asyncio
async def test_failed_delivery_can_retry_unchanged_dashboard(in_tmp):
    (in_tmp / 'dashboard.html').write_text('<p>retry</p>')
    conn = {}
    with pytest.raises(OSError):
        await send_control_center_page(AsyncMock(side_effect=OSError('disconnected')), 's', conn)
    deliver = AsyncMock()
    await send_control_center_page(deliver, 's', conn)
    assert deliver.await_count == 2  # the page, and its pre-#3336 copy


def test_the_header_is_name_line_and_facts_and_skills_come_next():
    """#3350 (owner, 2026-11-22: "现在太丑了"): the header is the agent's name,
    its one line and `N skills · model`; the skills follow as open tiles, not
    folded under Capabilities. The full address moved to the Health line."""
    skills = [{"name": f"s-{i}", "description": "", "location": "project"} for i in range(5)]
    html = render_starter({"name": "Ops", "address": ADDRESS, "tagline": "Answers guests.",
                           "skills": skills, "model": "co/gemini-3.8-flash"})
    header = html.split('<header class="head">', 1)[1].split("</header>", 1)[0]
    assert "Ops" in header and "Answers guests." in header
    assert "5 skills · co/gemini-3.8-flash" in header and ADDRESS not in header
    assert html.index("</header>") < html.index('id="skills-title"') < html.index('data-ochat-skill="s-0"')
    assert ADDRESS in html.split('class="health"')[1]


# ---------------------------------------------------------------- #3350 status

STATUS = {
    "title": "Front desk now",
    "updated_at": "2026-11-22T19:42:48+11:00",
    "metrics": [{"label": "Open", "value": 23, "href": "https://example.com/open"},
                {"label": "Overdue", "value": 6, "tone": "bad"},
                {"label": "Urgent", "value": 1, "tone": "warn"},
                {"label": "Arriving", "value": 4, "tone": "good"},
                {"label": "Odd", "value": 0, "tone": "purple"}],
    "lists": [{"title": "Most overdue", "items": [
        {"text": "#2041 Hot water out", "meta": "Harbour Dental · due 18 Nov", "tone": "bad",
         "href": "https://example.com/t/2041"}]}],
}


def write_status(project, status):
    text = status if isinstance(status, str) else json.dumps(status)
    (project / ".co").mkdir(exist_ok=True)
    (project / ".co" / "status.json").write_text(text, encoding="utf-8")


def test_the_status_renders_above_skills(in_tmp):
    write_status(in_tmp, STATUS)
    html = render_starter({"name": "Desk", "skills": [
        {"name": "triage", "description": "", "location": "project"}]})
    assert html.index("</header>") < html.index("Front desk now") < html.index('id="skills-title"')
    assert "#2041 Hot water out" in html and "Harbour Dental · due 18 Nov" in html
    assert ">23<" in html and "updated " in html


def test_every_status_string_is_escaped(in_tmp):
    write_status(in_tmp, {"title": "<b>t</b>", "metrics": [{"label": "<script>x</script>", "value": "<i>1</i>"}],
                          "lists": [{"title": "<u>l</u>", "items": [{"text": "<img src=x>", "meta": "<s>m</s>"}]}]})
    html = render_starter({"name": "Desk", "skills": []})
    for raw in ("<script>x</script>", "<b>t</b>", "<i>1</i>", "<u>l</u>", "<img src=x>", "<s>m</s>"):
        assert raw not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html


def test_status_tones_map_to_classes_and_links_are_not_rendered(in_tmp):
    write_status(in_tmp, STATUS)
    html = render_starter({"name": "Desk", "skills": []}).split("<!--FRAGMENTS")[0]
    assert '<div class="metric tone-bad">' in html
    assert '<div class="metric tone-warn">' in html
    assert '<div class="metric tone-good">' in html
    assert '<div class="status-item tone-bad">' in html
    assert "tone-purple" not in html
    assert "example.com" not in html and "<a " not in html


def test_no_status_file_means_no_status_block(in_tmp):
    html = render_starter({"name": "Desk", "skills": []}).split("<!--FRAGMENTS")[0]
    assert 'id="status-title"' not in html and 'class="status-problem"' not in html


def test_a_broken_status_file_is_one_quiet_line(in_tmp):
    write_status(in_tmp, '{"title": "half writ')
    html = render_starter({"name": "Desk", "skills": []})
    assert 'class="status-problem"' in html and "status.json could not be read" in html
    assert 'id="skills-title"' in html       # the page still renders

    write_status(in_tmp, "[1, 2]")
    assert "expected a JSON object" in render_starter({"name": "Desk", "skills": []})


@pytest.mark.asyncio
async def test_a_status_change_alone_resends_the_starter(in_tmp):
    ensure_control_center({"name": "Desk", "skills": []}, project_dir=in_tmp)
    write_status(in_tmp, {"title": "Before", "metrics": []})
    sent, conn = [], {}
    send = AsyncMock(side_effect=sent.append)

    await send_control_center_page(send, "s", conn)
    await send_control_center_page(send, "s", conn)          # unchanged: nothing sent
    write_status(in_tmp, {"title": "After the run", "metrics": [{"label": "Open", "value": 3}]})
    await send_control_center_page(send, "s", conn)

    pages = [m["html"] for m in sent if m["type"] == "CONTROL_CENTER_SNAPSHOT"]
    assert len(pages) == 2
    assert "Before" in pages[0] and "After the run" in pages[1]


# ---------------------------------------------------------------- #3350 recent

def test_recent_rows_carry_the_prompt_status_and_duration(in_tmp):
    import time
    me = "0x" + "d" * 64
    (in_tmp / ".co").mkdir(exist_ok=True)
    with open(in_tmp / ".co" / "session_results.jsonl", "w", encoding="utf-8") as f:
        for sid, status, prompt in (("a", "done", "Move the cleaner to Thursday"),
                                    ("b", "failed", "Reconcile the bond refunds")):
            f.write(json.dumps({"session_id": sid, "status": status, "prompt": prompt,
                                "duration_ms": 251000, "created": time.time() - 60,
                                "session": {"requester": {"address": me}}}) + "\n")
    html = render_starter({"name": "Desk", "skills": []},
                          viewer=dashboard_module.viewer_for(me, is_admin=False))
    recent = html.split("Recent")[1]
    assert "Move the cleaner to Thursday" in recent and "done · 4m 11s" in recent
    assert '<span class="meta bad">failed · 4m 11s' in recent


def test_a_non_admin_page_has_no_people_section(in_tmp):
    html = render_starter({"name": "Desk", "skills": []},
                          viewer=dashboard_module.viewer_for("0x" + "d" * 64, is_admin=False))
    assert 'class="card people"' not in html and ">People<" not in html

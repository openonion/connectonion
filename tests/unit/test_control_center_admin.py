"""The Control Center's admin section: who is in, the invite, activity, health (#3263).

An operator hosting an agent for other people opened its Control Center and
could manage nothing there: who joined with the invite code, removing one of
them, rotating the code, the log -- all of it was the host machine's shell.

The rule these tests defend first: **a socket whose verified address is not in
admins.txt is never sent any of it**, and an admin command is decided from the
verified caller against admins.txt when it arrives, never from the page.
"""

import json
import time

import pytest

from connectonion.network.host.ws_router import admin_home, control_center as dash
from connectonion.network.host.ws_router.control_center import handle_control_center
from connectonion.network.trust import TrustAgent

ADMIN = "0x" + "a" * 64
GUEST = "0x" + "b" * 64
OTHER = "0x" + "c" * 64


@pytest.fixture
def host(tmp_path, monkeypatch):
    """A configured Host: its own .co, an admin, a guest who joined by invite."""
    co = tmp_path / ".co"
    co.mkdir()
    (co / "admins.txt").write_text(ADMIN + "\n", encoding="utf-8")
    monkeypatch.setenv("CO_INVITE_CODE", "OLDCODE-11111")
    monkeypatch.setattr(dash, "_project_dir", tmp_path)
    monkeypatch.setattr(dash, "_agent_metadata", {"name": "desk", "skills": []})
    monkeypatch.setattr(dash, "STARTER_OVERRIDE", tmp_path / "absent-starter.html")
    dash._starter_templates.cache_clear()
    trust = TrustAgent("careful", co_dir=co)
    assert trust.verify_invite(GUEST, "OLDCODE-11111")
    admin_home.configure(trust, co / "logs" / "agent.log")
    yield trust
    admin_home.configure(None)
    dash._starter_templates.cache_clear()


def run(project, *, owner, status="done", sid=None, ago_s=60, prompt="secret prompt text"):
    path = project / ".co" / "session_results.jsonl"
    record = {"session_id": sid or f"{owner}-{status}-{ago_s}", "status": status,
              "prompt": prompt, "created": time.time() - ago_s, "duration_ms": 900,
              "session": {"requester": {"address": owner}}}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def page(address, is_admin):
    return dash.render_starter({"name": "desk", "skills": []},
                               viewer=dash.viewer_for(address, is_admin))


class TestOnlyAnAdminIsSentIt:
    def test_a_guest_page_carries_no_admin_data_while_the_admin_page_does(self, host):
        run(dash._project_dir, owner=GUEST)
        admin, guest = page(ADMIN, True), page(GUEST, False)

        assert "data-ochat-admin" in admin and "OLDCODE-11111" in admin
        for leaked in ("data-ochat-admin", "OLDCODE-11111", "Admitted", "Invite code"):
            assert leaked not in guest

    def test_an_unconfigured_host_renders_no_admin_section_even_for_an_admin(self, host):
        admin_home.configure(None)
        assert "data-ochat-admin" not in page(ADMIN, True)


class TestAdmitted:
    def test_who_joined_by_invite_is_listed_with_how_and_last_seen(self, host):
        run(dash._project_dir, owner=GUEST, ago_s=7200)
        html = page(ADMIN, True)

        assert GUEST in html
        assert "invite code" in html
        assert "seen 2h ago" in html
        assert f'data-ochat-admin="remove" data-ochat-target="{GUEST}"' in html
        assert f'data-ochat-admin="block" data-ochat-target="{GUEST}"' in html

    def test_activity_counts_every_caller_without_prompt_text(self, host):
        project = dash._project_dir
        run(project, owner=GUEST, ago_s=60)
        run(project, owner=GUEST, status="failed", ago_s=120)
        run(project, owner=OTHER, ago_s=30)
        html = page(ADMIN, True)

        assert "2 turns · 1 failed" in html
        assert "secret prompt text" not in html.split('id="admin"')[1]

    def test_a_waiting_approval_from_any_caller_is_shown(self, host):
        run(dash._project_dir, owner=OTHER, status="waiting_approval")
        assert "Waiting for approval" in page(ADMIN, True)


class TestHealth:
    def test_model_version_relay_and_last_error(self, host):
        from connectonion import __version__
        run(dash._project_dir, owner=GUEST, status="failed", ago_s=600)
        html = dash.render_starter({"name": "desk", "skills": [], "model": "claude-code/sonnet"},
                                   viewer=dash.viewer_for(ADMIN, True))

        assert __version__ in html
        assert "claude-code/sonnet" in html
        assert "Relay" in html
        assert "failed · 10m ago" in html

    def test_the_log_tail_is_shown_to_an_admin(self, host):
        log = host._co_dir / "logs" / "agent.log"
        log.parent.mkdir()
        log.write_text("".join(f"line {i}\n" for i in range(100)), encoding="utf-8")
        html = page(ADMIN, True)

        assert "line 99" in html and "line 10\n" not in html


async def command(trust, caller, action, payload=None):
    frames = []

    async def send(frame):
        frames.append(frame)
    conn = {"authenticated": True, "signed_commands": True, "agent_address": caller,
            "session_id": "s", "is_admin": True}
    await handle_control_center({"request_id": "r", "action": action, "payload": payload or {}},
                                send, conn, {"trust_agent": trust, "control_center": None})
    return frames


class TestCommands:
    @pytest.mark.asyncio
    async def test_remove_takes_the_guest_out_of_contacts(self, host):
        frames = await command(host, ADMIN, "admin.remove", {"client_id": GUEST})

        result = next(f for f in frames if f["type"] == "CONTROL_CENTER_RESULT")
        assert result["ok"] is True
        assert host.get_level(GUEST) == "stranger"
        snapshot = next(f for f in frames if f["type"] == "CONTROL_CENTER_SNAPSHOT")
        assert GUEST not in snapshot["html"].split("Admitted")[1].split("</details>")[0]

    @pytest.mark.asyncio
    async def test_block_blocks(self, host):
        await command(host, ADMIN, "admin.block", {"client_id": GUEST})
        assert host.get_level(GUEST) == "blocked"

    @pytest.mark.asyncio
    async def test_a_non_admin_is_refused_even_when_its_socket_claims_admin(self, host):
        frames = await command(host, GUEST, "admin.block", {"client_id": OTHER})

        assert frames[-1]["ok"] is False
        assert frames[-1]["error"]["code"] == "PermissionError"
        assert host.get_level(OTHER) == "stranger"
        assert not any(f["type"] == "CONTROL_CENTER_SNAPSHOT" for f in frames)

    @pytest.mark.asyncio
    async def test_an_admin_cannot_be_removed_or_blocked_from_here(self, host):
        frames = await command(host, ADMIN, "admin.block", {"client_id": ADMIN})
        assert frames[-1]["ok"] is False
        assert host.get_level(ADMIN) != "blocked"

    @pytest.mark.asyncio
    async def test_rotate_applies_the_new_code_without_a_restart(self, host, monkeypatch):
        env = dash._project_dir / ".env"
        env.write_text("CO_INVITE_CODE=OLDCODE-11111\nOTHER=kept\n", encoding="utf-8")
        frames = await command(host, ADMIN, "admin.rotate_invite")

        new = frames[0]["result"]["invite_code"]
        assert new and new != "OLDCODE-11111"
        assert f"CO_INVITE_CODE={new}" in env.read_text(encoding="utf-8")
        assert "OTHER=kept" in env.read_text(encoding="utf-8")
        assert not host.verify_invite(OTHER, "OLDCODE-11111")
        assert host.verify_invite(OTHER, new)

    @pytest.mark.asyncio
    async def test_turning_the_invite_off_closes_the_door(self, host):
        (dash._project_dir / ".env").write_text("CO_INVITE_CODE=OLDCODE-11111\n", encoding="utf-8")
        await command(host, ADMIN, "admin.invite_off")

        assert not host.verify_invite(OTHER, "OLDCODE-11111")
        assert "Off" in page(ADMIN, True)


def test_a_restricted_hosts_skills_are_listed_under_capabilities(tmp_path, monkeypatch):
    monkeypatch.setattr(dash, "_project_dir", tmp_path)
    monkeypatch.setattr(dash, "STARTER_OVERRIDE", tmp_path / "absent-starter.html")
    dash._starter_templates.cache_clear()
    html = dash.render_starter({"name": "desk", "skills": [], "restricted_skills": ["service-desk"]})

    assert "None published" not in html
    assert "service-desk" in html
    dash._starter_templates.cache_clear()


def test_restricted_skills_reach_the_metadata(tmp_path):
    from connectonion.cli.co_ai.native_host import NativeClaudeHostAgent
    from connectonion.network.host.server import _extract_agent_metadata
    from connectonion.useful_tools.claude_code import ClaudeRestriction

    restriction = ClaudeRestriction(skills=("service-desk",))
    metadata, _ = _extract_agent_metadata(
        lambda: NativeClaudeHostAgent(tmp_path, co_dir=tmp_path, model="sonnet", restriction=restriction))
    assert metadata["restricted_skills"] == ["service-desk"]

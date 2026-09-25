"""A visitor's Home shows their own turns, not the owner's.

The starter's "Recent" list is read from .co/session_results.jsonl, which holds
every caller's turns with the prompt verbatim. It used to be rendered once for
everyone, so a stranger on `trust: open` -- or a contact on the default
`careful` -- connected and read the owner's recent prompts in their first
DASHBOARD_SNAPSHOT. That is the one thing #696 promised a second identity could
no longer see.
"""

import asyncio
import json
from datetime import datetime, timezone

import pytest

from connectonion.network.host.ws_router import dashboard as dash

OWNER = "0x" + "a" * 64
VISITOR = "0x" + "b" * 64


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".co").mkdir()
    monkeypatch.setattr(dash, "_project_dir", tmp_path)
    monkeypatch.setattr(dash, "_agent_metadata", {"name": "billing", "skills": []})
    return tmp_path


def turn(project, prompt, address):
    record = {"session_id": prompt, "status": "done", "prompt": prompt,
              "duration_ms": 900, "created": datetime.now(timezone.utc).timestamp(),
              "session": {"requester": {"address": address, "level": "contact"}}}
    with open(project / ".co" / "session_results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def snapshot_for(address, is_admin=False):
    """What the host actually sends a socket that verified as ``address``."""
    sent = []

    async def send(frame):
        sent.append(frame)

    conn = {"agent_address": address, "is_admin": is_admin}
    asyncio.run(dash.send_dashboard(send, "s1", conn, force=True))
    return sent[0]["html"]


def test_a_visitor_does_not_see_the_owners_prompts(project):
    turn(project, "the code word is OCELOT", OWNER)
    turn(project, "what is on my calendar", VISITOR)

    visitor = snapshot_for(VISITOR)
    assert "OCELOT" not in visitor
    assert "what is on my calendar" in visitor


def test_the_owner_sees_their_own_prompts_and_not_the_visitors(project):
    turn(project, "the code word is OCELOT", OWNER)
    turn(project, "what is on my calendar", VISITOR)

    owner = snapshot_for(OWNER, is_admin=True)
    assert "OCELOT" in owner
    assert "what is on my calendar" not in owner


def test_a_visitor_with_no_turns_gets_no_recent_section(project):
    turn(project, "the code word is OCELOT", OWNER)

    assert "Recent" not in snapshot_for(VISITOR)


def test_the_schedule_is_shown_to_an_admin_only(project):
    (project / ".co" / "schedule.yaml").write_text(
        '- every: 15m\n  run: "check the ZEBRA account"\n', encoding="utf-8")

    assert "ZEBRA" not in snapshot_for(VISITOR)
    assert "ZEBRA" in snapshot_for(OWNER, is_admin=True)


def test_a_socket_path_cannot_forget_who_it_renders_for():
    with pytest.raises(TypeError):
        dash.read_dashboard_snapshot("s1")

"""Tests for the authenticated AGENT_PROFILE frame and the public /info subset."""
import pytest
from unittest.mock import AsyncMock, Mock

FULL_SKILLS = [
    {"name": "ship-feature", "description": "ship", "location": "builtin"},
    {"name": "my-project-skill", "description": "proj", "location": "project"},
    {"name": "lark-approval", "description": "private", "location": "user"},
    {"name": "aaron-review", "description": "private", "location": "claude-user"},
]
METADATA = {"name": "oo", "address": "0xabc", "model": "gemini-3.6-flash",
            "tools": ["read_file", "bash"], "skills": FULL_SKILLS, "balance_usd": 12.5}


def test_info_publishes_only_project_tree_skills():
    from connectonion.network.host.http_router import info_handler
    trust = Mock(); trust.trust = "careful"
    result = info_handler(METADATA, trust)

    names = {s["name"] for s in result["skills"]}
    assert names == {"my-project-skill"}, "/info is unauthenticated; only published skills belong in it"
    # The operator's machine must not be advertised by the agent.
    assert "lark-approval" not in names and "aaron-review" not in names


@pytest.mark.asyncio
async def test_authenticated_connect_gets_the_full_skill_list():
    from connectonion.network.host.ws_router.connect import establish_connection
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None

    await establish_connection({}, "0xvisitor", send_msg, {}, storage, registry,
                               {"agent_metadata": METADATA})

    profile = next(m for m in sent if m["type"] == "AGENT_PROFILE")
    assert {s["name"] for s in profile["skills"]} == {s["name"] for s in FULL_SKILLS}
    assert profile["balance_usd"] == 12.5
    types = [m["type"] for m in sent]
    assert types.index("CONNECTED") < types.index("AGENT_PROFILE")


@pytest.mark.asyncio
async def test_no_profile_frame_without_route_handlers():
    """The optional argument keeps callers that only need the session half working."""
    from connectonion.network.host.ws_router.connect import establish_connection
    sent = []
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None

    await establish_connection({}, "0xvisitor", AsyncMock(side_effect=lambda m: sent.append(m)),
                               {}, storage, registry)

    assert "AGENT_PROFILE" not in [m["type"] for m in sent]

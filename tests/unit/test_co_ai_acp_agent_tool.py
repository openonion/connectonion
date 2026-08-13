"""The co ai ACP child wrapper owns policy and workspace selection."""

import importlib
import json
from types import SimpleNamespace

import pytest

from connectonion.core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
)

acp_tool = importlib.import_module("connectonion.cli.co_ai.tools.acp_agent")


@pytest.mark.parametrize(
    ("mode", "extra", "expected"),
    [
        (READ_ONLY_PERMISSION_PROFILE, {}, "manual"),
        (WORKSPACE_PERMISSION_PROFILE, {}, "manual"),
        (
            DANGER_FULL_ACCESS_PERMISSION_PROFILE,
            {
                "skip_tool_approval": True,
                "full_access_turns": 3,
                "full_access_turns_used": 0,
            },
            "auto",
        ),
        (DANGER_FULL_ACCESS_PERMISSION_PROFILE, {}, "manual"),
    ],
)
def test_wrapper_derives_operator_policy_and_workspace(
    monkeypatch, tmp_path, mode, extra, expected
):
    captured = {}

    class FakeACPAgent:
        def __init__(self, *, approval, workspace):
            captured.update(approval=approval, workspace=workspace)

        def acp_agent(self, **kwargs):
            captured.update(kwargs)
            return "result"

    monkeypatch.setattr(acp_tool, "ACPAgent", FakeACPAgent)
    session = {"mode": mode, **extra}
    agent = SimpleNamespace(
        current_session=session,
        _delegation_workspace=tmp_path,
    )

    result = acp_tool.acp_agent(
        "inspect", "claude-code", str(tmp_path), agent=agent
    )

    assert result == "result"
    assert captured["approval"] == expected
    assert captured["workspace"] == tmp_path
    assert captured["agent"] is agent


def test_hosted_non_admin_cannot_launch_local_acp_child(monkeypatch, tmp_path):
    monkeypatch.setattr(
        acp_tool,
        "ACPAgent",
        lambda **_kwargs: pytest.fail("hosted requester reached the launcher"),
    )
    agent = SimpleNamespace(
        current_session={
            "mode": READ_ONLY_PERMISSION_PROFILE,
            "requester": {"level": "contact"},
        },
        _delegation_workspace=tmp_path,
    )

    output = json.loads(
        acp_tool.acp_agent(
            "inspect", "claude-code", str(tmp_path), agent=agent
        )
    )

    assert output["engine"] == "claude-code"
    assert "only to the operator" in output["error"]


def test_wrapper_keeps_policy_out_of_the_model_schema():
    parameters = acp_tool.acp_agent.__annotations__
    assert "approval" not in parameters
    assert "command" not in parameters
    assert "workspace" not in parameters

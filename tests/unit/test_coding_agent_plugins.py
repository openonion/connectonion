"""Contract tests for first-class coding-agent plugins."""

import inspect
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from connectonion import Agent, ClaudeCodePlugin, CodexPlugin, PermissionMode
from connectonion.network.host.session.ui import session_to_chat_items


class _LLM:
    model = "test"


@pytest.mark.parametrize(
    ("plugin", "tool_name"),
    [(CodexPlugin, "codex"), (ClaudeCodePlugin, "claude_code")],
)
def test_plugin_registers_provider_tool_without_model_owned_authority(tmp_path, plugin, tool_name):
    agent = Agent("developer", plugins=[plugin(workspace=tmp_path)], llm=_LLM(), quiet=True)
    assert tool_name in agent.list_tools()
    parameters = agent.tools.get(tool_name).get_parameters_schema()["properties"]
    assert "permission_mode" not in parameters
    assert "workspace" not in parameters
    assert "sandbox" not in parameters
    assert "approval" not in parameters


def test_compatibility_permission_names_are_normalized(tmp_path):
    assert CodexPlugin(permission_mode=":read-only", workspace=tmp_path).permission_mode is PermissionMode.MANUAL
    assert CodexPlugin(permission_mode=":workspace", workspace=tmp_path).permission_mode is PermissionMode.AUTO_APPROVE
    assert CodexPlugin(permission_mode=":danger-full-access", workspace=tmp_path).permission_mode is PermissionMode.FULL_ACCESS


def test_workspace_traversal_and_symlink_escape_fail_closed(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    link = workspace / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    result = json.loads(CodexPlugin(workspace=workspace).codex("inspect", cwd="escape"))
    assert "must stay inside workspace" in result["error"]


def test_invocation_lifecycle_is_parented_and_terminal(monkeypatch, tmp_path):
    import connectonion.plugins.coding_agents as module

    monkeypatch.setattr(
        module,
        "_run_codex",
        lambda **kwargs: json.dumps({"provider": "codex", "session_id": "s1", "exit_code": 0, "last_message": "done"}),
    )
    io = SimpleNamespace(log=MagicMock())
    agent = SimpleNamespace(io=io, current_session={"_active_tool_call_id": "call-7"})
    result = CodexPlugin(workspace=tmp_path).codex("fix it", agent=agent)
    assert json.loads(result)["last_message"] == "done"
    start, finish = io.log.call_args_list
    assert start.args == ("provider_invocation",)
    assert start.kwargs["invocationId"] == "codex:call-7"
    assert start.kwargs["parentToolCallId"] == "call-7"
    assert start.kwargs["status"] == "running"
    assert finish.kwargs["status"] == "completed"
    assert finish.kwargs["sessionId"] == "s1"


@pytest.mark.parametrize(
    ("session", "sandbox", "approval"),
    [
        ({"mode": ":read-only"}, "read-only", "manual"),
        ({"mode": ":workspace"}, "workspace-write", "manual"),
        (
            {
                "mode": ":danger-full-access",
                "full_access_turns": 2,
                "full_access_turns_used": 0,
                "skip_tool_approval": True,
            },
            "danger-full-access",
            "deny",
        ),
        (
            {"mode": ":workspace", "requester": {"level": "contact"}},
            "read-only",
            "deny",
        ),
    ],
)
def test_codex_plugin_can_follow_the_authenticated_host_permission_ceiling(
    monkeypatch,
    tmp_path,
    session,
    sandbox,
    approval,
):
    import connectonion.plugins.coding_agents as module

    seen = {}

    def fake_codex(**kwargs):
        seen.update(kwargs)
        return json.dumps({"provider": "codex", "exit_code": 0})

    monkeypatch.setattr(module, "_run_codex", fake_codex)
    agent = SimpleNamespace(
        current_session={"_active_tool_call_id": "call-8", **session},
        io=SimpleNamespace(log=MagicMock()),
    )

    CodexPlugin(
        workspace=tmp_path,
        use_host_permissions=True,
    ).codex("inspect", agent=agent)

    assert seen["sandbox"] == sandbox
    assert seen["approval"] == approval


@pytest.mark.parametrize(
    ("session", "permission_mode"),
    [
        ({"mode": ":read-only"}, "manual"),
        ({"mode": ":workspace"}, "acceptEdits"),
        (
            {
                "mode": ":danger-full-access",
                "full_access_turns": 2,
                "full_access_turns_used": 0,
                "skip_tool_approval": True,
            },
            "auto",
        ),
    ],
)
def test_claude_plugin_can_follow_the_authenticated_host_permission_ceiling(
    monkeypatch,
    tmp_path,
    session,
    permission_mode,
):
    import connectonion.plugins.coding_agents as module

    seen = {}

    def fake_claude(**kwargs):
        seen.update(kwargs)
        return json.dumps({
            "provider": "claude_code",
            "session_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "exit_code": 0,
        })

    monkeypatch.setattr(module, "_run_claude_code", fake_claude)
    agent = SimpleNamespace(
        current_session={"_active_tool_call_id": "call-9", **session},
        io=SimpleNamespace(log=MagicMock()),
    )

    ClaudeCodePlugin(
        workspace=tmp_path,
        use_host_permissions=True,
    ).claude_code("inspect", cwd=str(tmp_path), agent=agent)

    assert seen["permission_mode"] == permission_mode


def test_hosted_contact_cannot_launch_claude_plugin(monkeypatch, tmp_path):
    import connectonion.plugins.coding_agents as module

    monkeypatch.setattr(module, "_run_claude_code", pytest.fail)
    io = SimpleNamespace(log=MagicMock())
    agent = SimpleNamespace(
        current_session={
            "_active_tool_call_id": "call-10",
            "mode": ":danger-full-access",
            "requester": {"address": "0xcontact", "level": "contact"},
        },
        io=io,
    )

    result = json.loads(
        ClaudeCodePlugin(
            workspace=tmp_path,
            use_host_permissions=True,
        ).claude_code(
            "change it",
            cwd=str(tmp_path.parent / "private-repository-name"),
            session_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            agent=agent,
        )
    )

    assert result["status"] == "error"
    assert "only to the operator" in result["error"]
    io.log.assert_not_called()


def test_public_signature_matches_the_provider_contract(tmp_path):
    for method in (
        CodexPlugin(workspace=tmp_path).codex,
        ClaudeCodePlugin(workspace=tmp_path).claude_code,
    ):
        assert list(inspect.signature(method).parameters) == [
            "prompt", "cwd", "session_id", "model", "timeout", "agent"
        ]


def test_codex_prompt_is_optional_so_open_does_not_invent_a_task(tmp_path):
    signature = inspect.signature(CodexPlugin(workspace=tmp_path).codex)
    assert signature.parameters["prompt"].default == ""


def test_replay_reconstructs_one_parent_card_with_nested_activity():
    session = {
        "messages": [{"role": "user", "content": "fix it"}],
        "trace": [
            {"type": "user_input"},
            {"type": "tool_call", "tool_id": "parent", "name": "codex", "args": {}},
            {"type": "provider_invocation", "invocationId": "codex:parent", "parentToolCallId": "parent", "provider": "codex", "providerDisplayName": "Codex", "status": "running"},
            {"type": "tool_result", "tool_id": "child", "name": "Bash", "args": {}, "status": "completed", "result": "ok", "provider": "codex", "invocationId": "codex:parent", "parentToolCallId": "parent"},
            {"type": "provider_invocation", "invocationId": "codex:parent", "parentToolCallId": "parent", "provider": "codex", "providerDisplayName": "Codex", "status": "completed"},
            {"type": "tool_result", "tool_id": "parent", "name": "codex", "args": {}, "status": "success", "result": "done"},
        ],
    }
    items = session_to_chat_items(session)
    assert [item["type"] for item in items] == ["user", "provider_invocation"]
    assert items[1]["status"] == "completed"
    assert items[1]["activities"] == [{
        "id": "child", "type": "tool_call", "name": "Bash", "args": {},
        "status": "done", "result": "ok", "timing_ms": None,
        "provider": "codex", "invocationId": "codex:parent", "parentToolCallId": "parent",
    }]

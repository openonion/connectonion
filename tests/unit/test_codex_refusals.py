"""Refusals must survive native protocol completion and reach the model/card."""
import importlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from connectonion.core.tool_result import ToolFailure
from connectonion.plugins.coding_agents import CodexPlugin

module = importlib.import_module("connectonion.useful_tools.codex")


@pytest.fixture
def conversation(monkeypatch, tmp_path):
    """Drive the real adapter with deterministic app-server frames, no model."""
    requests, replies = [], []
    state = {"callback": True, "declined_item": True, "native_decline": False}

    def request(client, method, params, timeout=60):
        requests.append((method, params))
        if method in {"thread/start", "thread/resume"}:
            return {"thread": {"id": "native-thread"}}
        if method != "turn/start":
            return {}
        for item_id, kind, details in (
            ("write-1", "fileChange", {"path": "wordcount/__init__.py"}),
            ("test-1", "commandExecution", {"command": "python -m pytest -q"}),
        ):
            item = {"id": item_id, "type": kind, **details}
            client._dispatch({"method": "item/started", "params": {"item": item}})
            allowed = True
            if state["callback"]:
                client._dispatch({"id": item_id, "method": f"item/{kind}/requestApproval",
                                  "params": {"itemId": item_id, "cwd": str(tmp_path), **details}})
                allowed = replies[-1]["result"] == {"decision": "accept"}
            status = "declined" if state["native_decline"] or (state["declined_item"] and not allowed) else "completed"
            client._dispatch({"method": "item/completed", "params": {"item": {**item, "status": status}}})
        client._dispatch({"method": "item/completed", "params": {"item": {
            "id": "answer", "type": "agentMessage", "text": "The provider's final answer."}}})
        client._dispatch({"method": "turn/completed", "params": {"turn": {"status": "completed"}}})
        return {"turn": {"id": "turn-1"}}

    monkeypatch.setattr(module, "_base_command", lambda: ["codex", "app-server"])
    monkeypatch.setattr(module.CodexAppServer, "start", lambda self: None)
    monkeypatch.setattr(module.CodexAppServer, "close", lambda self: None)
    monkeypatch.setattr(module.CodexAppServer, "request", request)
    monkeypatch.setattr(module.CodexAppServer, "_send", lambda self, frame: replies.append(frame) if "id" in frame else None)
    return requests, replies, state


def agent_for(requester=None):
    session = {"mode": "auto", "_active_tool_call_id": "parent-1"}
    if requester:
        session["requester"] = {"level": requester}
    return SimpleNamespace(current_session=session,
                           io=SimpleNamespace(log=MagicMock(), request_approval=MagicMock(return_value=True)))


@pytest.mark.parametrize("session_id", ["", "native-thread"])
def test_codex_host_auto_runs_inside_workspace_without_manual_approval(conversation, tmp_path, session_id):
    requests, replies, state = conversation
    # A conforming never-policy server executes sandboxed actions without asking.
    # An untrusted-policy server asks, which the hosted contact cannot answer.
    original_request = module.CodexAppServer.request

    def native_policy(client, method, params, timeout=60):
        if method in {"thread/start", "thread/resume"}:
            state["callback"] = params["approvalPolicy"] != "never"
        return original_request(client, method, params, timeout)

    from unittest.mock import patch
    agent = agent_for("contact")
    with patch.object(module.CodexAppServer, "request", native_policy):
        result = CodexPlugin(workspace=tmp_path, use_host_permissions=True).codex("Create wordcount and run pytest", session_id=session_id, agent=agent)
    assert replies == [], "Host Auto used an interactive native policy and silently declined both actions"
    config = next(params for method, params in requests if method in {"thread/start", "thread/resume"})
    assert config["sandbox"] == "workspace-write"
    assert config["approvalPolicy"] == "never"
    assert json.loads(result)["exit_code"] == 0
    assert agent.io.log.call_args_list[-1].kwargs["providerPermission"]["activeOptionId"] == "codex:workspace-auto"


@pytest.mark.parametrize("approval,requester,has_io,reason", [
    ("manual", "contact", True, "admin"),
    ("manual", None, False, "approval UI"),
    ("auto", "admin", True, "unexpected approval"),
    ("deny", "admin", True, "disabled"),
])
def test_codex_refusal_is_blocked_even_when_native_turn_completes(conversation, tmp_path, approval, requester, has_io, reason):
    agent = agent_for(requester) if has_io else None
    result = module.codex("Create wordcount and run pytest", cwd=str(tmp_path), approval=approval, agent=agent)
    body = json.loads(result)
    assert body.get("status") == "blocked", body
    assert body["exit_code"] != 0
    assert reason in body["error"]
    assert body["last_message"] == "The provider's final answer."
    assert isinstance(result, ToolFailure)
    assert all(reply["result"] == {"decision": "decline"} for reply in conversation[1])
    if has_io:
        assert not agent.io.request_approval.called
        activities = [call.kwargs for call in agent.io.log.call_args_list if call.args == ("provider_activity",)]
        assert activities[-1]["status"] == "failed"


@pytest.mark.parametrize("kind", ["commandExecution", "fileChange"])
def test_codex_declined_item_is_not_a_completed_check(kind):
    event = module.CodexAppServer._item_event({"id": "action-1", "type": kind, "status": "declined"}, start=False)
    assert event["failed"] is True
    assert event["result"] == "Declined"
    assert event["declined"] is True


def test_codex_plugin_reports_blocked_reason_without_successful_checks(monkeypatch, tmp_path):
    import connectonion.plugins.coding_agents as plugins
    body = {"provider": "codex", "status": "blocked", "exit_code": 1,
            "error": "Codex approval requires a Host admin requester.", "blocked_reason": "admin_required"}
    monkeypatch.setattr(plugins, "_run_codex", lambda **kwargs: json.dumps(body))
    agent = agent_for("contact")
    result = CodexPlugin(workspace=tmp_path).codex("Create wordcount and run pytest", agent=agent)
    finish = agent.io.log.call_args_list[-1].kwargs
    assert finish["status"] == "failed"
    assert "Blocked" in finish["currentSummary"]
    assert "admin" in finish["errorSummary"]
    assert "recorded test checks" not in finish["resultSummary"]
    assert isinstance(result, ToolFailure)


def test_codex_refused_callback_blocks_without_a_declined_item(conversation, tmp_path):
    conversation[2]["declined_item"] = False
    body = json.loads(module.codex("run pytest", cwd=str(tmp_path), approval="manual", agent=agent_for("contact")))
    assert body.get("status") == "blocked"
    assert "admin" in body["error"]


def test_codex_native_decline_blocks_without_an_approval_callback(conversation, tmp_path):
    # Native policy may reject the action itself without asking the adapter.
    conversation[2].update(callback=False, native_decline=True)
    result = module.codex("run pytest", cwd=str(tmp_path), approval="auto")
    assert json.loads(result).get("status") == "blocked"
    assert "declined" in json.loads(result)["error"]


def test_codex_refusal_reaches_outer_tool_trace_and_console(conversation, tmp_path):
    from unittest.mock import patch
    from connectonion import Agent
    from connectonion.core.llm import ToolCall
    from connectonion.core.tool_executor import execute_and_record_tools
    from connectonion.logger import Logger

    agent = Agent("codex-refusal", plugins=[CodexPlugin(workspace=tmp_path)],
                  llm=SimpleNamespace(model="test"), log=False, quiet=True)
    agent.current_session = {"requester": {"level": "contact"}, "messages": [], "trace": [], "iteration": 1}
    # Force an unexpected callback under Auto, exercising the adapter's boundary.
    logger = Logger("codex-refusal", log=False)
    with patch("connectonion.console._rich_console.print") as output:
        execute_and_record_tools([ToolCall(name="codex", arguments={"prompt": "run pytest"},
                                          id="parent-1", extra_content=None)], agent.tools, agent, logger)
    result = next(event for event in agent.current_session["trace"]
                  if event["type"] == "tool_result" and event["name"] == "codex")
    assert result["status"] == "error"
    assert json.loads(result["result"])["status"] == "blocked"
    finish = [event for event in agent.current_session["trace"] if event["type"] == "provider_invocation"][-1]
    assert finish["status"] == "failed"
    assert "Blocked" in finish["resultSummary"]
    assert "unexpected approval" in finish["errorSummary"]
    assert "recorded test checks" not in finish["resultSummary"]
    terminal = "\n".join(str(call.args[0]) for call in output.call_args_list)
    assert "✗" in terminal
    assert "✓" not in terminal


def test_codex_approval_transport_failure_is_blocked(conversation, tmp_path):
    conversation[2]["declined_item"] = False
    agent = agent_for("admin")
    agent.io.request_approval.side_effect = RuntimeError("private UI transport failure")
    result = module.codex("run pytest", cwd=str(tmp_path), approval="manual", agent=agent)
    body = json.loads(result)
    assert body.get("status") == "blocked"
    assert "approval" in body["error"]
    assert "private" not in body["error"]


def test_codex_blocked_summary_does_not_publish_native_error(monkeypatch, tmp_path):
    import connectonion.plugins.coding_agents as plugins
    monkeypatch.setattr(plugins, "_run_codex", lambda **kwargs: json.dumps({
        "status": "blocked", "exit_code": 1,
        "error": "private /home/onion/secret --token=PRIVATE_TOKEN"}))
    agent = agent_for("contact")
    CodexPlugin(workspace=tmp_path).codex("run pytest", agent=agent)
    finish = agent.io.log.call_args_list[-1].kwargs
    assert "Blocked" in finish["currentSummary"]
    assert "private" not in json.dumps(finish)
    assert "PRIVATE_TOKEN" not in json.dumps(finish)


def test_codex_explicit_manual_option_keeps_admin_approval(conversation, tmp_path):
    agent = agent_for("admin")
    agent.current_session.update({"_provider_workroom_id": "codex:parent-1",
                                  "_provider_permission_options": {"codex:parent-1": "codex:workspace-ask"}})
    result = CodexPlugin(workspace=tmp_path, use_host_permissions=True).codex("run pytest", agent=agent)
    assert json.loads(result)["exit_code"] == 0
    assert agent.io.request_approval.call_count == 2
    assert all(reply["result"] == {"decision": "accept"} for reply in conversation[1])

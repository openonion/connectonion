"""Hosted Auto allows work, tells the requester, and leaves operator context."""
import copy
import json

import pytest

from connectonion import Agent, approvals
from connectonion.core.tool_executor import execute_single_tool
from connectonion.core.tool_result import ToolFailure
from connectonion.network.host.session.mode import session_with_durable_policy
from connectonion.network.host.session.ui import session_to_chat_items
from connectonion.plugins import coding_agents
from connectonion.plugins.coding_agents import ClaudeCodePlugin, CodexPlugin
from connectonion.useful_plugins.tool_approval import tool_approval
from tests.utils.mock_helpers import MockLLM

ADDRESS = "0x" + "3" * 64


def host_agent(tmp_path, level="contact", mode="auto", *, log=True):
    agent = Agent("host", llm=MockLLM(), plugins=[tool_approval], co_dir=tmp_path / ".co", quiet=True, log=log)
    agent.current_session = {"session_id": "s1", "mode": mode, "trace": [], "iteration": 1, "turn": 1,
                             "messages": [{"role": "system", "content": "Host instructions"}],
                             "requester": {"address": ADDRESS, "level": level}}
    return agent


@pytest.mark.parametrize("level", ["contact", "whitelist"])
@pytest.mark.parametrize("plugin,native", [(CodexPlugin, "_run_codex"), (ClaudeCodePlugin, "run_co_claude")])
def test_auto_notice_once_but_every_provider_run_is_recorded(tmp_path, monkeypatch, capsys, level, plugin, native):
    agent = host_agent(tmp_path, level, log=False)
    calls = []

    def run(**kwargs):
        # Admin is told afterwards, never before the work.
        assert "Host Auto" not in capsys.readouterr().out
        calls.append(kwargs)
        return json.dumps({"session_id": "native", "exit_code": 0, "last_message": "Done"})

    monkeypatch.setattr(coding_agents, native, run)
    installed = plugin(workspace=tmp_path, use_host_permissions=True)
    tool = getattr(installed, installed.provider)
    first = json.loads(tool("fix the tests", agent=agent))
    notice = first.get("notice", "")
    assert "not an admin" in notice and "revoke" in notice and "recorded" in notice
    assert calls[0]["prompt"] == "fix the tests"
    after_first = capsys.readouterr().out
    assert "Host Auto" in after_first and ADDRESS in after_first
    assert f"co trust block {ADDRESS}" in after_first
    assert "requester's next message (frame)" in after_first
    assert "a running turn is stopped then" in after_first
    assert installed.provider in after_first and "completed" in after_first
    assert "co approvals" in after_first

    # New Agent/transport, same durable Host session: no repeated notice.
    restored = host_agent(tmp_path, level, log=False)
    restored.current_session = copy.deepcopy(agent.current_session)
    restored.current_session["turn"] += 1
    second = json.loads(tool("fix another test", session_id="native", agent=restored))
    assert "notice" not in second
    assert "not an admin" not in calls[1]["prompt"]
    assert "Host Auto" in capsys.readouterr().out
    events = [e for e in restored.current_session["trace"] if e["type"] == "host_notice"]
    assert len(events) == 1 and events[0]["message"] == notice
    assert any(notice in m.get("content", "") for m in restored.current_session["messages"])
    assert any(e["type"] == "host_notice" for e in session_to_chat_items(restored.current_session))
    records = [e for e in approvals.read(tmp_path / ".co") if e["path"] == "auto"]
    assert len(records) == 2
    assert all(e["who"] == f"key:{ADDRESS}" and e["tool"] == installed.provider for e in records)
    assert all(e["mode"] == "auto" and e["task_summary"] and e["ts"] for e in records)
    assert records[0]["task_summary"] == "fix the tests"
    assert all(e["outcome"] == "completed" and e["session"] == "s1" for e in records)


@pytest.mark.parametrize("level,mode,selected", [
    ("admin", "auto", None), ("contact", "read-only", None),
    ("contact", "auto", "codex:workspace-ask"),
    ("contact", "auto", "codex:read-only"),
])
def test_no_auto_notice_when_admin_or_permission_still_asks(tmp_path, monkeypatch, capsys, level, mode, selected):
    agent = host_agent(tmp_path, level, mode)
    if selected:
        agent.current_session.update({"_provider_workroom_id": "room",
                                      "_provider_permission_options": {"room": selected}})
    monkeypatch.setattr(coding_agents, "_run_codex", lambda **kw: json.dumps({"exit_code": 0}))
    CodexPlugin(workspace=tmp_path, use_host_permissions=True).codex("fix it", agent=agent)
    assert not any(e["type"] == "host_notice" for e in agent.current_session["trace"])
    assert not approvals.read(tmp_path / ".co")
    assert "Host Auto" not in capsys.readouterr().out


def test_auto_failure_is_recorded_and_admin_notified(tmp_path, monkeypatch, capsys):
    agent = host_agent(tmp_path)
    def fail(**kwargs):
        raise RuntimeError("provider stopped")
    monkeypatch.setattr(coding_agents, "_run_codex", fail)
    with pytest.raises(RuntimeError, match="provider stopped"):
        CodexPlugin(workspace=tmp_path, use_host_permissions=True).codex("fix it", agent=agent)
    [record] = approvals.read(tmp_path / ".co")
    assert record["outcome"] == "failed"
    assert "failed" in capsys.readouterr().out


def test_non_provider_auto_write_uses_the_same_context(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    def write(path: str, content: str) -> str:
        """Write a workspace file."""
        (tmp_path / path).write_text(content)
        return "Written"
    agent = host_agent(tmp_path)
    agent.add_tool(write)
    result = execute_single_tool("write", {"path": "note.txt", "content": "hello"},
                                 "write-1", agent.tools, agent, agent.logger)
    assert result["status"] == "success" and (tmp_path / "note.txt").read_text() == "hello"
    assert any(e["type"] == "host_notice" for e in agent.current_session["trace"])
    records = approvals.read(tmp_path / ".co")
    [auto] = [e for e in records if e["path"] == "auto"]
    assert auto["tool"] == "write" and auto["mode"] == "auto"
    assert f"co trust block {ADDRESS}" in capsys.readouterr().out


def test_client_cannot_suppress_or_reset_the_once_per_session_notice():
    key = "_host_auto_notice_sent"
    assert key not in session_with_durable_policy({key: True}, {})
    assert session_with_durable_policy({key: False}, {key: True})[key] is True
    run_key = "_host_auto_run_turn"
    assert run_key not in session_with_durable_policy({run_key: 1}, {})
    assert session_with_durable_policy({run_key: 2}, {run_key: 1})[run_key] == 1


def test_co_approvals_displays_auto_task_and_mode():
    from connectonion.cli.commands.approvals_commands import _line
    rendered = _line({"path": "auto", "decision": "done", "tool": "codex", "who": ADDRESS,
                      "task_summary": "Review and test the requested change", "mode": "auto"})
    assert "Review and test the requested change" in rendered
    assert "mode=auto" in rendered


@pytest.mark.parametrize("status", ["blocked", "cancelled", "failed"])
def test_first_auto_notice_preserves_error_tool_failure(tmp_path, monkeypatch, status):
    agent = host_agent(tmp_path)
    monkeypatch.setattr(coding_agents, "_run_codex", lambda **kw: ToolFailure(json.dumps({
        "error": "Interrupted" if status == "cancelled" else "Provider failed", "status": status})))
    result = CodexPlugin(workspace=tmp_path, use_host_permissions=True).codex("fix it", agent=agent)
    assert isinstance(result, ToolFailure)
    assert json.loads(result)["notice"]


def test_native_host_durable_notice_and_record_without_logging(tmp_path, monkeypatch):
    from connectonion.cli.co_ai.native_host import NativeCodexHostAgent
    from connectonion.network.host.session import SessionStorage
    from connectonion.network.host.session.mode import HostPermissionPolicy
    from connectonion.network.host.session.turn import input_handler

    calls = []
    def run(**kwargs):
        calls.append(kwargs)
        return json.dumps({"session_id": "native", "last_message": "Done", "exit_code": 0})
    monkeypatch.setattr(coding_agents, "_run_codex", run)
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    factory = lambda: NativeCodexHostAgent(tmp_path, co_dir=tmp_path / ".co")
    requester = {"address": ADDRESS, "level": "contact"}
    for client_marker in (True, False):
        result = input_handler(factory, storage, "fix it", 3600,
            session={"session_id": "native-session", "_host_auto_notice_sent": client_marker},
            requester=requester, mode_policy=HostPermissionPolicy())
        assert result["result"] == "Done"
    assert calls[0]["prompt"] == "fix it"
    assert "not an admin" not in calls[1]["prompt"]
    assert len([e for e in result["session"]["trace"] if e["type"] == "host_notice"]) == 1
    assert len([e for e in approvals.read(tmp_path / ".co") if e["path"] == "auto"]) == 2


def test_requester_sees_notice_before_interruptible_provider_work(tmp_path, monkeypatch):
    from connectonion.network.io.websocket import WebSocketIO

    agent = host_agent(tmp_path)
    agent.io = WebSocketIO()
    installed = CodexPlugin(workspace=tmp_path, use_host_permissions=True)
    agent.add_tool(installed.codex)
    def run(**kwargs):
        notices = [e for e in agent.io._msgs_from_agent if e["type"] == "host_notice"]
        assert notices, "requester needs the notice before provider work starts"
        assert not WebSocketIO.is_persisted_trace_event(notices[0])
        return json.dumps({"exit_code": 0})
    monkeypatch.setattr(coding_agents, "_run_codex", run)
    agent.current_session["_provider_direct_approved_tool"] = "codex"
    result = execute_single_tool("codex", {"prompt": "fix it"}, "native-1",
                                 agent.tools, agent, agent.logger)
    assert result["status"] == "success"


@pytest.mark.parametrize("already_told", [False, True])
def test_direct_workroom_continuations_keep_notice_state(tmp_path, monkeypatch, already_told):
    from connectonion.network.host.provider_workroom import prepare_provider_workroom_turn
    from connectonion.network.host.session import Session, SessionStorage
    from connectonion.network.io.websocket import WebSocketIO

    storage = SessionStorage(tmp_path / "sessions.jsonl")
    source = {"mode": "auto", "_host_auto_notice_sent": already_told,
              "requester": {"address": ADDRESS, "level": "contact"}, "trace": [{
                  "type": "provider_invocation", "provider": "codex", "invocationId": "codex:original",
                  "workroomId": "room", "status": "completed", "sessionId": "native", "stateRevision": 1}]}
    storage.save(Session(session_id="s1", status="done", prompt="original", session=source))
    monkeypatch.setattr(coding_agents, "_run_codex", lambda **kw: json.dumps({"session_id": "native", "exit_code": 0}))
    def factory():
        agent = host_agent(tmp_path)
        agent.add_tool(CodexPlugin(workspace=tmp_path, use_host_permissions=True).codex)
        return agent
    io = WebSocketIO()
    invocation = "codex:original"
    for number in range(2):
        prepared = prepare_provider_workroom_turn(factory, storage, "s1", invocation, "fix it", f"req-{number}", ADDRESS)
        prepared["run"](io)
        durable = storage.get("s1").session
        invocation = [e for e in durable["trace"] if e["type"] == "provider_invocation"][-1]["invocationId"]
    assert durable["_host_auto_notice_sent"] is True
    assert len([e for e in durable["trace"] if e["type"] == "host_notice"]) == (0 if already_told else 1)


@pytest.mark.parametrize("direct", [False, True])
def test_interrupt_keeps_the_notice_already_shown_to_requester(tmp_path, monkeypatch, direct):
    import threading
    from connectonion.network.io.websocket import WebSocketIO

    agent = host_agent(tmp_path)
    if direct:
        from connectonion.network.host.provider_workroom import _direct_session
        agent.current_session = _direct_session("s1", agent.current_session, "room", "codex:root",
                                                "fix it", "request-1", 1, "codex")
    agent.io = WebSocketIO()
    agent.add_tool(CodexPlugin(workspace=tmp_path, use_host_permissions=True).codex)
    agent.current_session["_provider_direct_approved_tool"] = "codex"
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_finish = coding_agents.finish_auto_run
    def finish(*args):
        original_finish(*args)
        finished.set()
    monkeypatch.setattr(coding_agents, "finish_auto_run", finish)
    def run(**kwargs):
        started.set()
        release.wait(timeout=2)
        return json.dumps({"exit_code": 0})
    monkeypatch.setattr(coding_agents, "_run_codex", run)
    def interrupt():
        assert started.wait(timeout=1)
        agent.io.send_to_agent({"type": "INTERRUPT"})
    thread = threading.Thread(target=interrupt)
    thread.start()
    result = execute_single_tool("codex", {"prompt": "fix it"}, "native-1", agent.tools, agent, agent.logger)
    release.set()
    thread.join(timeout=1)
    assert finished.wait(timeout=1)
    assert result["status"] == "interrupted"
    assert agent.current_session.get("_host_auto_notice_sent") is True
    assert len([e for e in agent.current_session["trace"] if e["type"] == "host_notice"]) == 1
    [record] = [e for e in approvals.read(tmp_path / ".co") if e["path"] == "auto"]
    assert record["outcome"] == "cancelled"


@pytest.mark.parametrize("plugin,native", [(CodexPlugin, "_run_codex"), (ClaudeCodePlugin, "run_co_claude")])
def test_full_access_provider_records_actual_mode(tmp_path, monkeypatch, capsys, plugin, native):
    agent = host_agent(tmp_path, mode="full-access")
    agent.current_session["turns_left"] = 3
    monkeypatch.setattr(coding_agents, native, lambda **kw: json.dumps({"exit_code": 0}))
    installed = plugin(workspace=tmp_path, use_host_permissions=True)
    getattr(installed, installed.provider)("fix it", agent=agent)
    [record] = approvals.read(tmp_path / ".co")
    assert record["mode"] == "full-access"
    assert "mode=full-access" in capsys.readouterr().out
    assert any(e["type"] == "host_notice" for e in agent.current_session["trace"])


@pytest.mark.parametrize("mode", ["auto", "full-access"])
def test_writes_record_and_notify_once_per_requester_turn(tmp_path, monkeypatch, capsys, mode):
    monkeypatch.chdir(tmp_path)
    def write(path: str, content: str) -> str:
        """Write a workspace file."""
        (tmp_path / path).write_text(content)
        return "Written"
    agent = host_agent(tmp_path, mode=mode)
    agent.current_session["turns_left"] = 3
    agent.add_tool(write)
    for index in range(3):
        result = execute_single_tool("write", {"path": f"note{index}.txt", "content": "hello"},
                                     f"write-{index}", agent.tools, agent, agent.logger)
        assert result["status"] == "success"
    records = approvals.read(tmp_path / ".co")
    assert len([e for e in records if e["path"] == "turn"]) == 3
    assert len([e for e in records if e["path"] == "auto"]) == 1
    assert capsys.readouterr().out.count("Host Auto:") == 1
    agent.current_session["turn"] += 1
    execute_single_tool("write", {"path": "next.txt", "content": "next"},
                        "write-next", agent.tools, agent, agent.logger)
    assert len([e for e in approvals.read(tmp_path / ".co") if e["path"] == "auto"]) == 2
    assert capsys.readouterr().out.count("Host Auto:") == 1
    assert len([e for e in agent.current_session["trace"] if e["type"] == "host_notice"]) == 1


def test_multiple_provider_calls_share_requester_turn_context(tmp_path, monkeypatch, capsys):
    agent = host_agent(tmp_path)
    monkeypatch.setattr(coding_agents, "_run_codex", lambda **kw: json.dumps({"exit_code": 0}))
    plugin = CodexPlugin(workspace=tmp_path, use_host_permissions=True)
    for prompt in ("fix it", "test it"):
        plugin.codex(prompt, agent=agent)
    assert len(approvals.read(tmp_path / ".co")) == 1
    assert capsys.readouterr().out.count("Host Auto:") == 1


@pytest.mark.parametrize("prompt,selected", [("", None), ("inspect it", "codex:read-only"), ("fix it", "codex:workspace-ask")])
def test_full_access_executor_defers_provider_eligibility(tmp_path, monkeypatch, capsys, prompt, selected):
    agent = host_agent(tmp_path, mode="full-access")
    agent.current_session["turns_left"] = 3
    if selected:
        agent.current_session.update({"_provider_workroom_id": "room",
                                      "_provider_permission_options": {"room": selected}})
    agent.add_tool(CodexPlugin(workspace=tmp_path, use_host_permissions=True).codex)
    monkeypatch.setattr(coding_agents, "_run_codex", lambda **kw: json.dumps({"exit_code": 0}))
    result = execute_single_tool("codex", {"prompt": prompt}, "native-1", agent.tools, agent, agent.logger)
    assert result["status"] == "success"
    assert not any(e["type"] == "host_notice" for e in agent.current_session["trace"])
    assert not [e for e in approvals.read(tmp_path / ".co") if e["path"] == "auto"]
    assert "Host Auto:" not in capsys.readouterr().out


def test_auto_hint_does_not_mistake_audit_directory_for_trust(tmp_path, capsys):
    from connectonion.core.host_context import begin_auto_run, finish_auto_run

    agent = host_agent(tmp_path)
    context = begin_auto_run(agent, "write", "write a note")
    finish_auto_run(agent, context, "completed")
    output = capsys.readouterr().out
    assert f"co trust block {ADDRESS}." in output
    assert "--co-dir" not in output

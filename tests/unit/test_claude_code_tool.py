"""Unit contract for live Claude Code delegation."""

import importlib
import io
import json
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from connectonion import Agent, ClaudeCode
from connectonion import claude_code as root_claude_code
from connectonion.cli.commands.copy_commands import TOOLS
from connectonion.useful_tools import ClaudeCode as UsefulClaudeCode
from connectonion.useful_tools import claude_code

claude_module = importlib.import_module("connectonion.useful_tools.claude_code")


def _completed(payload=None, returncode=0, stderr="", invalid_output=""):
    return SimpleNamespace(
        payload=payload
        or {
            "type": "result",
            "result": "done",
            "session_id": "session-new",
            "is_error": False,
            "usage": {"input_tokens": 4},
            "total_cost_usd": 0.01,
        },
        returncode=returncode,
        stderr=stderr,
        invalid_output=invalid_output,
    )


def _run(tmp_path, completed=None, prompt="fix it", **kwargs):
    completed = completed or _completed()
    permission_mode = kwargs.pop("permission_mode", None)
    tool = (
        ClaudeCode(permission_mode).claude_code
        if permission_mode is not None
        else claude_code
    )
    with patch.object(claude_module, "_base_command", return_value=["claude"]), patch.object(
        claude_module, "_run_process", return_value=completed
    ) as run:
        result = json.loads(tool(prompt, cwd=str(tmp_path), **kwargs))
    return result, run


def _agent():
    return SimpleNamespace(io=MagicMock(), current_session={})


def test_success_preserves_the_stable_envelope_and_uses_stream_json(tmp_path):
    result, run = _run(
        tmp_path,
        permission_mode="acceptEdits",
        model="sonnet",
        timeout=30,
    )

    assert result == {
        "provider": "claude_code",
        "session_id": "session-new",
        "resumed": False,
        "status": "completed",
        "result": "done",
        "error": "",
        "exit_code": 0,
        "usage": {"input_tokens": 4},
        "total_cost_usd": 0.01,
    }
    assert run.call_args.args[0] == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--forward-subagent-text",
        "--permission-mode",
        "acceptEdits",
        "--model",
        "sonnet",
        "--",
        "fix it",
    ]
    assert run.call_args.kwargs["cwd"] == str(tmp_path.resolve())
    assert run.call_args.kwargs["timeout"] == 30
    assert callable(run.call_args.kwargs["on_event"])


def test_resume_passes_the_exact_session_id(tmp_path):
    completed = _completed(
        {
            "type": "result",
            "result": "continued",
            "session_id": "session-old",
            "is_error": False,
        }
    )
    result, run = _run(tmp_path, completed=completed, session_id="session-old")

    argv = run.call_args.args[0]
    assert argv[argv.index("--resume") + 1] == "session-old"
    assert result["session_id"] == "session-old"
    assert result["resumed"] is True


def test_public_default_maps_to_current_manual_cli_mode(tmp_path):
    _, run = _run(tmp_path)
    argv = run.call_args.args[0]
    assert argv[argv.index("--permission-mode") + 1] == "manual"


def test_inner_tool_start_becomes_a_provider_labelled_native_card():
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)

    forwarder.handle(
        {
            "type": "assistant",
            "session_id": "session-1",
            "parent_tool_use_id": None,
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                    }
                ]
            },
        }
    )

    agent.io.log.assert_called_once_with(
        "tool_call",
        tool_id="claude:toolu_1",
        name="Claude Code › Bash",
        args={"command": "pytest -q"},
        status="in_progress",
        provider="claude_code",
        child_session_id="session-1",
        parent_tool_id=None,
    )


def test_duplicate_assistant_messages_do_not_duplicate_tool_cards():
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}
            ]
        },
    }

    forwarder.handle(event)
    forwarder.handle(event)

    assert agent.io.log.call_count == 1


@pytest.mark.parametrize(("is_error", "status"), [(False, "completed"), (True, "failed")])
def test_inner_tool_result_completes_the_same_card(is_error, status):
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)
    forwarder.handle(
        {
            "type": "assistant",
            "session_id": "s",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}
                ]
            },
        }
    )
    agent.io.log.reset_mock()

    forwarder.handle(
        {
            "type": "user",
            "session_id": "s",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "file contents",
                        "is_error": is_error,
                    }
                ]
            },
        }
    )

    agent.io.log.assert_called_once_with(
        "tool_result",
        tool_id="claude:toolu_1",
        status=status,
        result="file contents",
        provider="claude_code",
        child_session_id="s",
        parent_tool_id=None,
    )


def test_subagent_parent_id_is_preserved_for_future_nested_ui():
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)

    forwarder.handle(
        {
            "type": "assistant",
            "session_id": "s",
            "parent_tool_use_id": "agent-tool-1",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_nested",
                        "name": "Grep",
                        "input": {"pattern": "TODO"},
                    }
                ]
            },
        }
    )

    assert agent.io.log.call_args.kwargs["parent_tool_id"] == "agent-tool-1"


def test_oversized_tool_arguments_and_results_are_bounded():
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)
    huge = "x" * 20_000

    forwarder.handle(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Write",
                        "input": {"file_path": "a.txt", "content": huge},
                    }
                ]
            },
        }
    )
    start = agent.io.log.call_args.kwargs
    assert start["args"]["file_path"] == "a.txt"
    assert start["args"]["_truncated"] is True
    assert len(json.dumps(start["args"], ensure_ascii=False)) <= claude_module._MAX_ARGUMENT_CHARS

    forwarder.handle(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": huge}
                ]
            },
        }
    )
    result = agent.io.log.call_args.kwargs["result"]
    assert result.endswith("…")
    assert len(result) <= claude_module._MAX_RESULT_CHARS


def test_sensitive_tool_arguments_are_redacted_before_they_reach_io():
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)

    forwarder.handle(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Fetch",
                        "input": {
                            "url": "https://example.com",
                            "headers": {"Authorization": "Bearer private"},
                            "api_key": "private",
                            "deep": {"one": {"two": {"three": {"token": "private"}}}},
                        },
                    }
                ]
            },
        }
    )

    args = agent.io.log.call_args.kwargs["args"]
    assert args["headers"]["Authorization"] == "[redacted]"
    assert args["api_key"] == "[redacted]"
    assert "private" not in json.dumps(args)
    assert args["_redacted"] is True


def test_events_are_silent_without_live_agent_io():
    forwarder = claude_module._ClaudeStreamForwarder(None)
    forwarder.handle(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}
                ]
            },
        }
    )


@pytest.mark.parametrize(
    "mode", ["manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"]
)
def test_documented_permission_modes_are_operator_bound(tmp_path, mode):
    _, run = _run(tmp_path, permission_mode=mode)
    argv = run.call_args.args[0]
    assert argv[argv.index("--permission-mode") + 1] == mode


def test_invalid_permission_mode_fails_before_a_provider_can_launch():
    with patch.object(claude_module, "_run_process") as run:
        with pytest.raises(ValueError, match="Invalid permission mode"):
            ClaudeCode("yolo")
    run.assert_not_called()


@pytest.mark.parametrize("tool", [claude_code, ClaudeCode("bypassPermissions")])
def test_agent_schema_never_exposes_provider_permission_policy(tmp_path, tool):
    agent = Agent(
        "schema", llm=MagicMock(), tools=[tool], quiet=True, log=False, co_dir=tmp_path / ".co"
    )
    schemas = [registered.to_function_schema() for registered in agent.tools]
    assert [schema["name"] for schema in schemas] == ["claude_code"]
    assert "permission_mode" not in schemas[0]["parameters"]["properties"]


@pytest.mark.parametrize("timeout", [0, -1, True, 1.5])
def test_timeout_must_be_a_positive_integer(tmp_path, timeout):
    result = json.loads(claude_code("fix", cwd=str(tmp_path), timeout=timeout))
    assert "positive integer" in result["error"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"session_id": 3}, "Session ID"),
        ({"cwd": 3}, "Working directory"),
        ({"model": 3}, "Model"),
    ],
)
def test_string_arguments_are_validated(tmp_path, kwargs, message):
    if "cwd" not in kwargs:
        kwargs["cwd"] = str(tmp_path)
    result = json.loads(claude_code("fix", **kwargs))
    assert message in result["error"]


def test_cwd_must_exist_and_be_a_directory(tmp_path):
    missing = json.loads(claude_code("fix", cwd=str(tmp_path / "missing")))
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    file_result = json.loads(claude_code("fix", cwd=str(file_path)))
    assert "Working directory" in missing["error"]
    assert "not a directory" in file_result["error"]


def test_missing_binary_is_one_structured_result(tmp_path):
    with patch.object(claude_module, "_base_command", return_value=None):
        result = json.loads(claude_code("fix", cwd=str(tmp_path)))
    assert result["status"] == "error"
    assert "CLI not found" in result["error"]


def test_timeout_and_cancellation_are_structured(tmp_path):
    with patch.object(claude_module, "_base_command", return_value=["claude"]), patch.object(
        claude_module, "_run_process", side_effect=subprocess.TimeoutExpired(["claude"], 2)
    ):
        timed_out = json.loads(claude_code("fix", cwd=str(tmp_path), timeout=2))
    with patch.object(claude_module, "_base_command", return_value=["claude"]), patch.object(
        claude_module, "_run_process", side_effect=claude_module._ProviderCancelled
    ):
        cancelled = json.loads(claude_code("fix", cwd=str(tmp_path)))
    assert timed_out["status"] == "timeout"
    assert cancelled["status"] == "error"
    assert "interrupted" in cancelled["error"].lower()


def test_provider_error_and_session_mismatch_stay_structured(tmp_path):
    failed = _completed(
        {
            "type": "result",
            "result": "Authentication required",
            "session_id": "session-new",
            "is_error": True,
        },
        returncode=1,
    )
    result, _ = _run(tmp_path, completed=failed, session_id="session-old")
    assert result["session_id"] == "session-old"
    assert result["status"] == "error"
    assert "different session ID" in result["error"]
    assert "Authentication required" in result["error"]


@pytest.mark.parametrize("payload", [None, {}, {"type": "assistant"}])
def test_missing_result_object_is_structured(tmp_path, payload):
    completed = _completed()
    completed.payload = payload
    completed.invalid_output = "not json" if payload is None else ""
    result, _ = _run(tmp_path, completed=completed)
    assert result["status"] == "error"
    assert "did not contain a result object" in result["error"]


def test_process_reader_delivers_each_json_line_and_final_result(tmp_path):
    lines = "\n".join(
        json.dumps(event)
        for event in (
            {"type": "system", "subtype": "init", "session_id": "s"},
            {"type": "assistant", "message": {"content": []}},
            {"type": "result", "result": "done", "session_id": "s"},
        )
    ) + "\n"
    process = MagicMock()
    process.stdout = io.StringIO(lines)
    process.stderr = io.StringIO("warning\n")
    process.poll.return_value = 0
    process.wait.return_value = 0
    events = []

    with patch.object(claude_module.subprocess, "Popen", return_value=process):
        completed = claude_module._run_process(
            ["claude"], cwd=str(tmp_path), timeout=2, on_event=events.append
        )

    assert [event["type"] for event in events] == ["system", "assistant", "result"]
    assert completed.payload["result"] == "done"
    assert completed.stderr == "warning\n"


def test_process_reader_reaps_claude_when_live_io_rejects_an_event(tmp_path):
    process = MagicMock()
    process.stdout = io.StringIO('{"type":"assistant","message":{"content":[]}}\n')
    process.stderr = io.StringIO("")
    process.poll.return_value = None

    with patch.object(claude_module.subprocess, "Popen", return_value=process), patch.object(
        claude_module, "_kill_process_tree"
    ) as kill:
        with pytest.raises(claude_module._ProviderStreamError, match="lease retired"):
            claude_module._run_process(
                ["claude"],
                cwd=str(tmp_path),
                timeout=2,
                on_event=MagicMock(side_effect=RuntimeError("lease retired")),
            )

    kill.assert_called_once_with(process)


def test_process_reader_kills_the_group_on_cooperative_cancellation(tmp_path):
    process = MagicMock()
    process.stdout = io.StringIO("")
    process.stderr = io.StringIO("")
    process.poll.return_value = None
    cancelled = threading.Event()
    cancelled.set()

    with patch.object(claude_module.subprocess, "Popen", return_value=process), patch.object(
        claude_module, "_kill_process_tree"
    ) as kill:
        with pytest.raises(claude_module._ProviderCancelled):
            claude_module._run_process(
                ["claude"],
                cwd=str(tmp_path),
                timeout=2,
                cancelled=cancelled.is_set,
                on_event=lambda event: None,
            )

    kill.assert_called_once_with(process)


def test_process_runner_is_headless_and_does_not_use_a_shell(tmp_path):
    process = MagicMock()
    process.stdout = io.StringIO('{"type":"result","session_id":"s"}\n')
    process.stderr = io.StringIO("")
    process.poll.return_value = 0
    process.wait.return_value = 0
    with patch.object(claude_module.subprocess, "Popen", return_value=process) as popen:
        claude_module._run_process(
            ["claude", "--", "x"], cwd=str(tmp_path), timeout=2, on_event=lambda event: None
        )
    assert popen.call_args.kwargs["stdin"] is subprocess.DEVNULL
    assert popen.call_args.kwargs["shell"] is False


@pytest.mark.skipif(claude_module.os.name == "nt", reason="POSIX process-group regression")
def test_real_posix_timeout_remains_a_timeout(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        claude_module._run_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=str(tmp_path),
            timeout=1,
            on_event=lambda event: None,
        )


def test_command_override_is_parsed_without_a_shell(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_CMD", "'/path with spaces/claude' --flag")
    assert claude_module._base_command() == ["/path with spaces/claude", "--flag"]


def test_tool_is_exported_and_copyable():
    assert root_claude_code is claude_code
    assert ClaudeCode is UsefulClaudeCode
    assert TOOLS["claude_code"] == "claude_code.py"

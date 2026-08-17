"""Unit contract for live Claude Code delegation."""

import importlib
import inspect
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
NEW_SESSION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OLD_SESSION = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _completed(payload=None, returncode=0, stderr="", invalid_output=""):
    return SimpleNamespace(
        payload=payload
        or {
            "type": "result",
            "result": "done",
            "session_id": NEW_SESSION,
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
        ClaudeCode(permission_mode, workspace=tmp_path).claude_code
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
        "session_id": NEW_SESSION,
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
        "--safe-mode",
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
            "session_id": OLD_SESSION,
            "is_error": False,
        }
    )
    result, run = _run(tmp_path, completed=completed, session_id=OLD_SESSION)

    argv = run.call_args.args[0]
    assert argv[argv.index("--resume") + 1] == OLD_SESSION
    assert result["session_id"] == OLD_SESSION
    assert result["resumed"] is True


def test_public_default_maps_to_current_manual_cli_mode(tmp_path):
    _, run = _run(tmp_path)
    argv = run.call_args.args[0]
    assert argv[argv.index("--permission-mode") + 1] == "manual"
    assert "--safe-mode" in argv


def test_operator_workspace_is_not_model_visible(tmp_path):
    tool = ClaudeCode(workspace=tmp_path).claude_code
    assert "workspace" not in inspect.signature(tool).parameters


def test_agent_cannot_launch_outside_its_runtime_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    agent = _agent()
    with patch.object(claude_module, "_run_process") as run:
        result = json.loads(
            claude_module._run_claude_code(
                prompt="inspect",
                cwd=str(outside),
                agent=agent,
                workspace=workspace,
            )
        )
    assert "must stay inside workspace" in result["error"]
    run.assert_not_called()


def test_workspace_rejects_a_symlink_escape(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    link = workspace / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    result = json.loads(
        ClaudeCode(workspace=workspace).claude_code("inspect", cwd="escape")
    )
    assert "must stay inside workspace" in result["error"]


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


def test_inner_tool_also_emits_a_safe_oip_activity_when_parented():
    agent = SimpleNamespace(
        io=MagicMock(),
        current_session={"_active_tool_call_id": "parent-claude-1"},
    )
    forwarder = claude_module._ClaudeStreamForwarder(agent)

    forwarder.handle(
        {
            "type": "assistant",
            "session_id": "session-1",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Bash",
                    "input": {"command": "pytest -q --token private-value"},
                }]
            },
        }
    )

    typed, legacy = agent.io.log.call_args_list
    assert typed.args == ("provider_activity",)
    assert typed.kwargs == {
        "provider": "claude_code",
        "activityId": "claude:toolu_1",
        "sequence": 1,
        "kind": "command",
        "status": "running",
        "title": "Run the requested tests",
        "summary": "Running the requested tests",
        "invocationId": "claude_code:parent-claude-1",
        "parentToolCallId": "parent-claude-1",
    }
    assert "private" not in json.dumps(typed.kwargs)
    assert legacy.args == ("tool_call",)


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


def test_inline_workspace_png_becomes_a_real_revision_bound_provider_artifact():
    thumbnail = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8A"
        "AusB9WlRjyoAAAAASUVORK5CYII="
    )
    agent = SimpleNamespace(
        io=MagicMock(),
        current_session={"_active_tool_call_id": "parent-claude-image"},
    )
    forwarder = claude_module._ClaudeStreamForwarder(agent)
    forwarder.handle({
        "type": "assistant",
        "session_id": "s",
        "message": {"content": [{
            "type": "tool_use", "id": "toolu_image", "name": "Read", "input": {},
        }]},
    })
    agent.io.log.reset_mock()

    forwarder.handle({
        "type": "user",
        "session_id": "s",
        "message": {"content": [{
            "type": "tool_result",
            "tool_use_id": "toolu_image",
            "content": [{
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": thumbnail},
            }],
        }]},
    })

    lifecycle, artifact, activity, result = agent.io.log.call_args_list
    assert lifecycle.args == ("provider_invocation",)
    assert lifecycle.kwargs["stateRevision"] == 1
    assert artifact.args == ("provider_artifact",)
    assert artifact.kwargs["stateRevision"] == lifecycle.kwargs["stateRevision"]
    assert artifact.kwargs["thumbnailDataUrl"] == f"data:image/png;base64,{thumbnail}"
    assert activity.args == ("provider_activity",)
    assert result.args == ("tool_result",)
    assert result.kwargs["result"] == "Provider returned a workspace image."
    assert thumbnail not in json.dumps(result.kwargs)


def test_inline_svg_or_url_content_never_becomes_a_provider_artifact():
    agent = SimpleNamespace(
        io=MagicMock(),
        current_session={"_active_tool_call_id": "parent-claude-image"},
    )
    forwarder = claude_module._ClaudeStreamForwarder(agent)
    forwarder.handle({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "id": "toolu_image", "name": "Read", "input": {},
        }]},
    })
    agent.io.log.reset_mock()

    forwarder.handle({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result",
            "tool_use_id": "toolu_image",
            "content": [{
                "type": "image",
                "source": {
                    "type": "url",
                    "media_type": "image/svg+xml",
                    "data": "https://example.invalid/private-preview.svg",
                },
            }],
        }]},
    })

    assert [call.args[0] for call in agent.io.log.call_args_list] == [
        "provider_activity", "tool_result",
    ]
    assert "private-preview" not in json.dumps(agent.io.log.call_args_list[-1].kwargs)


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


def test_provider_ids_and_metadata_are_bounded_and_active_tools_are_released():
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)
    huge = "海" * 10_000
    forwarder.handle({
        "type": "assistant",
        "session_id": huge,
        "parent_tool_use_id": huge,
        "message": {"content": [{
            "type": "tool_use", "id": huge, "name": huge, "input": {}
        }]},
    })
    start = agent.io.log.call_args.kwargs
    assert start["tool_id"].startswith("claude:sha256:")
    assert start["child_session_id"].startswith("sha256:")
    assert start["parent_tool_id"].startswith("sha256:")
    assert len(start["name"]) <= claude_module._MAX_FIELD_CHARS + len("Claude Code › ")

    forwarder.handle({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": huge, "content": "done"
        }]},
    })
    assert forwarder._tools == {}


def test_provider_event_and_active_tool_counts_are_bounded():
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)
    for index in range(claude_module._MAX_LIVE_EVENTS + 100):
        forwarder.handle({
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": f"tool-{index}", "name": "Read", "input": {}
            }]},
        })
    assert agent.io.log.call_count <= claude_module._MAX_LIVE_EVENTS
    assert len(forwarder._tools) <= claude_module._MAX_ACTIVE_TOOLS


def test_event_cap_reserves_a_result_for_every_emitted_start(monkeypatch):
    monkeypatch.setattr(claude_module, "_MAX_LIVE_EVENTS", 3)
    agent = _agent()
    forwarder = claude_module._ClaudeStreamForwarder(agent)

    for tool_id in ("one", "two"):
        forwarder.handle({
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": tool_id, "name": "Read", "input": {}
            }]},
        })

    assert agent.io.log.call_count == 1
    forwarder.handle({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": "one", "content": "done"
        }]},
    })
    assert [call.args[0] for call in agent.io.log.call_args_list] == [
        "tool_call",
        "tool_result",
    ]
    assert forwarder._tools == {}


def test_final_result_usage_and_provider_session_are_bounded():
    completed = _completed({
        "type": "result",
        "result": "x" * 100_000,
        "session_id": "s" * 10_000,
        "usage": {f"counter_{i}": i for i in range(100)},
        "total_cost_usd": float("inf"),
    })
    result = json.loads(claude_module._completed_envelope(completed, ""))
    assert len(result["result"]) <= claude_module._MAX_FINAL_RESULT_CHARS
    assert result["session_id"] == ""
    assert result["status"] == "error"
    assert len(result["usage"]) <= claude_module._MAX_COLLECTION_ITEMS
    assert result["total_cost_usd"] is None


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


def test_request_values_have_hard_upper_bounds(tmp_path):
    assert "1 MiB" in json.loads(claude_code("x" * (1024 * 1024 + 1)))["error"]
    assert "Session ID is too long" in json.loads(
        claude_code("x", session_id="s" * 513)
    )["error"]
    assert "3600" in json.loads(claude_code("x", timeout=3601))["error"]
    assert "canonical UUID" in json.loads(
        claude_code("x", session_id="most recent")
    )["error"]
    assert "canonical UUID" in json.loads(
        claude_code("x", session_id=OLD_SESSION.upper())
    )["error"]


def test_oversized_stream_line_is_not_parsed():
    invalid = []
    assert claude_module._parse_stream_line(
        "x" * (claude_module._MAX_STREAM_LINE_CHARS + 1), invalid
    ) is None
    assert invalid == ["oversized stream line\n"]


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
            "session_id": NEW_SESSION,
            "is_error": True,
        },
        returncode=1,
    )
    result, _ = _run(tmp_path, completed=failed, session_id=OLD_SESSION)
    assert result["session_id"] == OLD_SESSION
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


def test_reader_stops_when_a_full_mailbox_is_revoked():
    mailbox = claude_module.queue.Queue(maxsize=1)
    mailbox.put(("stdout", "occupied"))
    stopped = threading.Event()
    thread = claude_module._start_reader(
        io.StringIO("line\n"), "stdout", mailbox, stopped
    )
    stopped.set()
    thread.join(timeout=1)
    assert not thread.is_alive()


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


def test_provider_process_does_not_inherit_unrelated_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("USER", "macos-keychain-user")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross")
    monkeypatch.setenv("GH_TOKEN", "must-not-cross")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "provider-auth")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    process = MagicMock()
    process.stdout = io.StringIO('{"type":"result","session_id":"s"}\n')
    process.stderr = io.StringIO("")
    process.poll.return_value = 0
    process.wait.return_value = 0
    with patch.object(claude_module.subprocess, "Popen", return_value=process) as popen:
        claude_module._run_process(
            ["claude"], cwd=str(tmp_path), timeout=2, on_event=lambda event: None
        )
    environment = popen.call_args.kwargs["env"]
    assert environment["USER"] == "macos-keychain-user"
    assert "OPENAI_API_KEY" not in environment
    assert "GH_TOKEN" not in environment
    assert environment["ANTHROPIC_API_KEY"] == "provider-auth"
    assert environment["CLAUDE_CONFIG_DIR"] == str(tmp_path / "claude")


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

"""Unit contract for the built-in Claude Code subprocess adapter."""

import importlib
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from connectonion import claude_code as root_claude_code
from connectonion.cli.commands.copy_commands import TOOLS
from connectonion.useful_tools import claude_code

claude_module = importlib.import_module("connectonion.useful_tools.claude_code")


def _completed(payload, returncode=0, stderr=""):
    return SimpleNamespace(
        stdout=json.dumps(payload), returncode=returncode, stderr=stderr
    )


def _run(tmp_path, completed=None, prompt="fix it", **kwargs):
    completed = completed or _completed(
        {
            "result": "done",
            "session_id": "session-new",
            "is_error": False,
            "usage": {"input_tokens": 4},
            "total_cost_usd": 0.01,
        }
    )
    with patch.object(claude_module, "_base_command", return_value=["claude"]), patch.object(
        claude_module, "_run_process", return_value=completed
    ) as run:
        result = json.loads(claude_code(prompt, cwd=str(tmp_path), **kwargs))
    return result, run


def test_success_returns_stable_envelope_and_safe_argv(tmp_path):
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
        "json",
        "--permission-mode",
        "acceptEdits",
        "--model",
        "sonnet",
        "--",
        "fix it",
    ]
    assert run.call_args.kwargs["cwd"] == str(tmp_path.resolve())
    assert run.call_args.kwargs["timeout"] == 30


def test_resume_passes_the_exact_session_id(tmp_path):
    completed = _completed(
        {"result": "continued", "session_id": "session-old", "is_error": False}
    )
    result, run = _run(tmp_path, completed=completed, session_id="session-old")

    assert result["session_id"] == "session-old"
    assert result["resumed"] is True
    assert ["--resume", "session-old"] == run.call_args.args[0][6:8]


def test_public_default_maps_to_current_manual_cli_mode(tmp_path):
    _, run = _run(tmp_path)

    argv = run.call_args.args[0]
    assert argv[argv.index("--permission-mode") + 1] == "manual"


@pytest.mark.parametrize(
    "mode",
    ["manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"],
)
def test_documented_permission_modes_are_forwarded_only_when_explicit(
    tmp_path, mode
):
    _, run = _run(tmp_path, permission_mode=mode)
    argv = run.call_args.args[0]
    assert argv[argv.index("--permission-mode") + 1] == mode


def test_invalid_permission_mode_never_launches(tmp_path):
    with patch.object(claude_module, "_run_process") as run:
        result = json.loads(
            claude_code("fix", cwd=str(tmp_path), permission_mode="yolo")
        )

    assert result["status"] == "error"
    assert "Invalid permission mode" in result["error"]
    run.assert_not_called()


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

    assert result["provider"] == "claude_code"
    assert result["status"] == "error"
    assert result["exit_code"] == -1
    assert "CLI not found" in result["error"]


def test_file_not_found_race_is_structured(tmp_path):
    with patch.object(claude_module, "_base_command", return_value=["claude"]), patch.object(
        claude_module, "_run_process", side_effect=FileNotFoundError
    ):
        result = json.loads(claude_code("fix", cwd=str(tmp_path)))
    assert "CLI not found" in result["error"]


def test_malformed_command_override_is_structured(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_CMD", '"unterminated')
    result = json.loads(claude_code("fix", cwd=str(tmp_path)))
    assert result["status"] == "error"
    assert "Invalid $CLAUDE_CODE_CMD" in result["error"]


def test_invalid_subprocess_argument_is_structured(tmp_path):
    with patch.object(claude_module, "_base_command", return_value=["claude"]), patch.object(
        claude_module,
        "_run_process",
        side_effect=ValueError("embedded null byte"),
    ):
        result = json.loads(claude_code("bad\0prompt", cwd=str(tmp_path)))
    assert "invalid launch argument" in result["error"]


def test_timeout_is_structured_and_preserves_resume_id(tmp_path):
    with patch.object(claude_module, "_base_command", return_value=["claude"]), patch.object(
        claude_module,
        "_run_process",
        side_effect=subprocess.TimeoutExpired(["claude"], 2),
    ):
        result = json.loads(
            claude_code("continue", session_id="session-old", cwd=str(tmp_path), timeout=2)
        )

    assert result["session_id"] == "session-old"
    assert result["resumed"] is True
    assert result["status"] == "timeout"
    assert "2s" in result["error"]


def test_authentication_failure_uses_provider_json_message(tmp_path):
    completed = _completed(
        {
            "result": "Authentication required\nRun /login",
            "session_id": "session-1",
            "is_error": True,
        },
        returncode=1,
        stderr="debug noise",
    )

    result, _ = _run(tmp_path, completed=completed)

    assert result["status"] == "error"
    assert result["exit_code"] == 1
    assert result["error"] == "Authentication required Run /login"


def test_zero_exit_provider_error_is_still_an_error(tmp_path):
    completed = _completed(
        {"result": "permission denied", "session_id": "s", "is_error": True}
    )
    result, _ = _run(tmp_path, completed=completed)
    assert result["status"] == "error"
    assert result["error"] == "permission denied"


def test_success_requires_a_resumable_session_id(tmp_path):
    result, _ = _run(tmp_path, completed=_completed({"result": "done"}))
    assert result["status"] == "error"
    assert "resumable session ID" in result["error"]


def test_resume_rejects_a_different_returned_session_id(tmp_path):
    completed = _completed(
        {"result": "done", "session_id": "session-new", "is_error": False}
    )
    result, _ = _run(tmp_path, completed=completed, session_id="session-old")
    assert result["status"] == "error"
    assert "different session ID" in result["error"]


@pytest.mark.parametrize("provider_session", [7, {"id": "s"}, ["s"]])
def test_invalid_provider_session_id_never_leaks_into_the_envelope(
    tmp_path, provider_session
):
    completed = _completed(
        {"result": "done", "session_id": provider_session, "is_error": False}
    )
    fresh, _ = _run(tmp_path, completed=completed)
    resumed, _ = _run(
        tmp_path, completed=completed, session_id="session-old"
    )
    assert fresh["session_id"] == ""
    assert fresh["status"] == "error"
    assert resumed["session_id"] == "session-old"
    assert resumed["status"] == "error"


def test_event_array_uses_its_final_result_object(tmp_path):
    completed = _completed(
        [
            {"type": "system", "subtype": "init", "session_id": "s"},
            {"type": "assistant", "message": {"content": []}},
            {
                "type": "result",
                "result": "done",
                "session_id": "s",
                "is_error": False,
                "usage": {"output_tokens": 2},
            },
        ]
    )

    result, _ = _run(tmp_path, completed=completed)

    assert result["status"] == "completed"
    assert result["session_id"] == "s"
    assert result["result"] == "done"
    assert result["usage"] == {"output_tokens": 2}


@pytest.mark.parametrize("payload", [[], [1, 2], "text", None])
def test_json_without_a_result_object_is_structured(tmp_path, payload):
    result, _ = _run(tmp_path, completed=_completed(payload))
    assert result["status"] == "error"
    assert "did not contain a result object" in result["error"]


def test_nonzero_json_without_result_includes_stderr(tmp_path):
    completed = _completed([], returncode=1, stderr="authentication failed")
    result, _ = _run(tmp_path, completed=completed)
    assert "authentication failed" in result["error"]


def test_invalid_json_is_structured(tmp_path):
    completed = SimpleNamespace(stdout="not json", stderr="bad output\n", returncode=1)
    result, _ = _run(tmp_path, completed=completed)
    assert result["status"] == "error"
    assert result["exit_code"] == 1
    assert result["error"] == "Claude Code returned invalid JSON: bad output"


def test_command_override_is_parsed_as_argv(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_CMD", "'/path with spaces/claude' --flag")
    assert claude_module._base_command() == ["/path with spaces/claude", "--flag"]


def test_windows_command_override_removes_wrapper_quotes():
    assert claude_module._split_command(
        '"C:\\Program Files\\Claude\\claude.exe" --flag', windows=True
    ) == ["C:\\Program Files\\Claude\\claude.exe", "--flag"]


@pytest.mark.parametrize("suffix", ["cmd", "CMD", "bat", "BAT"])
def test_windows_batch_wrappers_are_rejected(tmp_path, suffix):
    command = f"C:\\bin\\claude.{suffix}"
    assert claude_module._is_unsafe_windows_batch(command, windows=True)
    with patch.object(claude_module, "_base_command", return_value=[command]), patch.object(
        claude_module, "_is_unsafe_windows_batch", return_value=True
    ), patch.object(claude_module, "_run_process") as run:
        result = json.loads(claude_code("fix", cwd=str(tmp_path)))
    assert result["status"] == "error"
    assert ".cmd/.bat" in result["error"]
    run.assert_not_called()


def test_metacharacters_remain_one_argument_without_a_shell(tmp_path):
    prompt = "fix & whoami | echo $HOME"
    _, run = _run(tmp_path, prompt=prompt)
    assert run.call_args.args[0][-2:] == ["--", prompt]


def test_process_runner_is_headless_and_does_not_use_a_shell(tmp_path):
    process = SimpleNamespace(
        communicate=lambda timeout: ("{}", ""), returncode=0
    )
    with patch.object(claude_module.subprocess, "Popen", return_value=process) as popen:
        completed = claude_module._run_process(
            ["claude", "--", "x"], cwd=str(tmp_path), timeout=2
        )
    assert completed.returncode == 0
    assert popen.call_args.kwargs["stdin"] is subprocess.DEVNULL
    assert popen.call_args.kwargs["shell"] is False


def test_process_runner_never_waits_unboundedly_after_timeout(tmp_path):
    process = MagicMock()
    process.communicate.side_effect = [
        subprocess.TimeoutExpired(["claude"], 1),
        subprocess.TimeoutExpired(["claude"], 3),
    ]
    process.stdout = MagicMock()
    process.stderr = MagicMock()
    with patch.object(claude_module.subprocess, "Popen", return_value=process), patch.object(
        claude_module, "_terminate_process_tree"
    ) as terminate:
        with pytest.raises(subprocess.TimeoutExpired):
            claude_module._run_process(
                ["claude", "--", "x"], cwd=str(tmp_path), timeout=1
            )

    assert process.communicate.call_args_list[1].kwargs == {"timeout": 3}
    terminate.assert_called_once_with(process)
    process.stdout.close.assert_called_once()
    process.stderr.close.assert_called_once()
    process.wait.assert_called_once_with(timeout=1)


def test_tool_is_exported_from_both_public_namespaces():
    assert root_claude_code is claude_code


def test_tool_is_registered_as_copyable():
    assert TOOLS["claude_code"] == "claude_code.py"

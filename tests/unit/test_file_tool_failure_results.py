"""Regression coverage for explicit FileTools failure results."""

from unittest.mock import patch

from connectonion.core.llm import ToolCall
from connectonion.core.tool_executor import (
    execute_and_record_tools,
    execute_single_tool,
)
from connectonion.core.tool_factory import (
    create_tool_from_function,
    extract_methods_from_instance,
)
from connectonion.core.tool_registry import ToolRegistry
from connectonion.core.tool_result import ToolFailure
from connectonion.logger import Logger
from connectonion.useful_tools.file_tools import FileTools


class RecordingAgent:
    """Small executor-compatible agent that records lifecycle events."""

    name = "file-tool-test"
    io = None

    def __init__(self):
        self.current_session = {
            "messages": [],
            "trace": [],
            "iteration": 1,
            "user_prompt": "Do not overwrite the existing file",
        }
        self.events = []

    def _record_trace(self, entry, **_kwargs):
        self.current_session["trace"].append(entry)

    def _invoke_events(self, event_type):
        self.events.append(event_type)


def file_tool_registry(file_tools):
    registry = ToolRegistry()
    registry.add_instance("filetools", file_tools)
    for tool in extract_methods_from_instance(file_tools):
        registry.add(tool)
    return registry


def test_write_refusal_is_reported_as_failure_without_touching_file(tmp_path):
    path = tmp_path / "existing.txt"
    path.write_text("original\n", encoding="utf-8")
    before = path.stat()
    agent = RecordingAgent()
    logger = Logger("file-tool-test", log=False)

    with patch("connectonion.console._rich_console.print") as terminal_print:
        execute_and_record_tools(
            [
                ToolCall(
                    name="write",
                    arguments={"path": str(path), "content": "replacement\n"},
                    id="call-write-existing",
                    extra_content=None,
                )
            ],
            file_tool_registry(FileTools()),
            agent,
            logger,
        )

    result = next(
        entry
        for entry in agent.current_session["trace"]
        if entry["type"] == "tool_result"
    )
    tool_message = agent.current_session["messages"][-1]
    terminal_output = "\n".join(
        str(call.args[0]) for call in terminal_print.call_args_list
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ToolFailure"
    assert result["error"] == result["result"]
    assert "already exists" in result["result"]
    assert tool_message == {
        "role": "tool",
        "content": result["result"],
        "tool_call_id": "call-write-existing",
    }
    assert "on_error" in agent.events
    assert "✗" in terminal_output
    assert "✓" not in terminal_output
    assert path.read_text(encoding="utf-8") == "original\n"
    assert path.stat().st_mtime_ns == before.st_mtime_ns


def test_file_tools_marks_each_explicit_failure_without_breaking_string_api(
    tmp_path,
):
    path = tmp_path / "existing.txt"
    path.write_text("original\n", encoding="utf-8")
    missing = tmp_path / "missing"
    file_tools = FileTools()

    failures = [
        file_tools.write(str(path), "replacement\n"),
        file_tools.edit(str(path), "original", "replacement"),
        file_tools.multi_edit(
            str(path),
            [{"old_string": "original", "new_string": "replacement"}],
        ),
        file_tools.read_file(str(missing)),
        file_tools.glob("*.txt", path=str(missing)),
        file_tools.grep("(", path=str(tmp_path)),
    ]

    assert all(isinstance(result, str) for result in failures)
    assert all(isinstance(result, ToolFailure) for result in failures)
    assert path.read_text(encoding="utf-8") == "original\n"

    no_files = file_tools.glob("*.py", path=str(tmp_path))
    no_matches = file_tools.grep("absent", path=str(path))
    assert not isinstance(no_files, ToolFailure)
    assert not isinstance(no_matches, ToolFailure)


def test_an_ordinary_error_prefixed_string_keeps_success_semantics():
    def domain_result() -> str:
        return "Error: this is domain data, not an execution failure"

    registry = ToolRegistry()
    registry.add(create_tool_from_function(domain_result))

    result = execute_single_tool(
        tool_name="domain_result",
        tool_args={},
        tool_id="call-domain-result",
        tools=registry,
        agent=RecordingAgent(),
        logger=Logger("file-tool-test", log=False),
    )

    assert result["status"] == "success"
    assert result["result"].startswith("Error:")
    assert "error" not in result

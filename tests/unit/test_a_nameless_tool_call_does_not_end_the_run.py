"""#1356: a model returned one tool call with an empty function name. It was
copied into history as-is, and on the next turn Gemini refused the whole
request ("function_response.name: Name cannot be empty"), killing a run at
iteration 76 of 200. A nameless call is an unknown tool, answered like one."""

from unittest.mock import Mock

from connectonion.core.llm import ToolCall
from connectonion.core.tool_executor import execute_and_record_tools
from connectonion.logger import Logger


def test_an_empty_name_never_reaches_history():
    assert ToolCall(name="", arguments={}, id="call_1").name
    assert ToolCall(name="  ", arguments={}, id="call_1").name.strip()
    assert ToolCall(name="calc", arguments={}, id="call_1").name == "calc"


def test_a_nameless_call_is_answered_as_an_unknown_tool():
    agent = Mock()
    agent.current_session = {"messages": [], "trace": [], "iteration": 1}

    execute_and_record_tools([ToolCall(name="", arguments={}, id="call_1")],
                             {"calc": lambda x: x * 2}, agent, Logger("test", log=False))

    assistant, result = agent.current_session["messages"]
    assert assistant["tool_calls"][0]["function"]["name"]
    assert result["role"] == "tool"
    assert "not found" in result["content"]
    assert "calc" in result["content"]

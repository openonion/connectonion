"""Mock helpers for ConnectOnion testing."""

import json
from unittest.mock import Mock, MagicMock
from typing import Dict, List, Any, Optional, Type, Callable, Union
from connectonion.core.llm import LLM, LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from pydantic import BaseModel


class MockLLM(LLM):
    """Mock LLM that returns pre-configured responses.

    This class implements the LLM interface properly, making it YAML-serializable
    and compatible with the Agent's logging system.

    Usage:
        # Single response
        mock_llm = MockLLM(responses=[LLMResponseBuilder.text_response("Hello")])

        # Multiple responses (like side_effect)
        mock_llm = MockLLM(responses=[
            LLMResponseBuilder.tool_call_response("calculator", {"expression": "2+2"}),
            LLMResponseBuilder.text_response("The result is 4")
        ])

        # With custom model name
        mock_llm = MockLLM(responses=[...], model="gpt-4o-mini")
    """

    def __init__(
        self,
        responses: Optional[List[LLMResponse]] = None,
        model: str = "mock-llm",
        usage_factory: Optional[Callable[[str, List[Dict[str, Any]], List[ToolCall]], TokenUsage]] = None,
        on_complete: Optional[Callable[[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]], LLMResponse]] = None,
        on_structured_complete: Optional[Callable[[List[Dict[str, Any]], Type[BaseModel]], BaseModel]] = None,
        structured_responses: Optional[Union[List[BaseModel], Dict[Type[BaseModel], List[BaseModel]]]] = None,
    ):
        self.model = model
        self._responses = list(responses) if responses else []
        self._call_count = 0
        self._calls: List[Dict[str, Any]] = []  # Track all calls for assertions
        self._usage_factory = usage_factory
        self._on_complete = on_complete
        self._on_structured_complete = on_structured_complete
        # Support a global queue or per-schema queues
        self._structured_responses = structured_responses

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Return next response from the queue or a callback-produced response.

        - Records the call (messages/tools/kwargs)
        - If `on_complete` is provided, use it to produce the response
        - Else pop a pre-seeded response
        - If `usage_factory` is provided and response.usage is None or empty, attach generated TokenUsage
        """
        self._calls.append({"messages": messages, "tools": tools, "kwargs": kwargs})
        self._call_count += 1

        if self._on_complete is not None:
            resp = self._on_complete(messages, tools)
        elif self._responses:
            resp = self._responses.pop(0)
        else:
            resp = LLMResponse(content="Mock response", tool_calls=[], raw_response={}, usage=TokenUsage())

        if self._usage_factory is not None and (resp.usage is None or isinstance(resp.usage, TokenUsage) and not resp.usage.model_dump()):
            # Generate usage from messages/tool_calls
            try:
                usage = self._usage_factory(self.model, messages, resp.tool_calls)
                resp.usage = usage
            except Exception:
                # Keep tests resilient even if usage_factory throws
                pass

        return resp

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Return a structured response via callback or queued instances.

        Priority:
        1) on_structured_complete(messages, output_schema)
        2) Pop from structured_responses (per-schema dict or global list)
        3) Return empty instance: output_schema()
        """
        if self._on_structured_complete is not None:
            return self._on_structured_complete(messages, output_schema)

        if isinstance(self._structured_responses, dict):
            queue = self._structured_responses.get(output_schema, [])
            if queue:
                return queue.pop(0)
        elif isinstance(self._structured_responses, list) and self._structured_responses:
            return self._structured_responses.pop(0)

        return output_schema()

    @property
    def call_count(self) -> int:
        """Number of times complete() was called."""
        return self._call_count

    @property
    def calls(self) -> List[Dict]:
        """All calls made to complete()."""
        return self._calls

    @property
    def last_call(self) -> Optional[Dict]:
        """Last call made to complete()."""
        return self._calls[-1] if self._calls else None

    def reset(self, responses: List[LLMResponse] = None):
        """Reset the mock with new responses."""
        self._responses = list(responses) if responses else []
        self._call_count = 0
        self._calls = []


class OpenAIMockBuilder:
    """Builder for creating OpenAI API mocks."""

    @staticmethod
    def simple_response(content: str, model: str = "gpt-3.5-turbo") -> Mock:
        """Create mock for text-only responses."""
        mock_response = MagicMock()
        mock_response.id = "chatcmpl-test123"
        mock_response.object = "chat.completion"
        mock_response.model = model
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        return mock_response

    @staticmethod
    def tool_call_response(
        tool_name: str,
        arguments: Dict[str, Any],
        call_id: str = "call_test123"
    ) -> Mock:
        """Create mock for tool calling responses."""
        mock_response = MagicMock()
        mock_response.id = "chatcmpl-test456"
        mock_response.object = "chat.completion"
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        # Create tool call mock
        tool_call = MagicMock()
        tool_call.id = call_id
        tool_call.type = "function"
        tool_call.function.name = tool_name
        tool_call.function.arguments = json.dumps(arguments)

        mock_response.choices[0].message.tool_calls = [tool_call]
        mock_response.choices[0].finish_reason = "tool_calls"
        return mock_response

    @staticmethod
    def error_response(error_type: str, message: str) -> Exception:
        """Create mock for API errors."""
        from openai import APIError, RateLimitError, AuthenticationError

        error_map = {
            "rate_limit": RateLimitError,
            "auth": AuthenticationError,
            "api": APIError
        }

        error_class = error_map.get(error_type, APIError)
        return error_class(
            message=message,
            response=MagicMock(),
            body={"error": {"message": message}}
        )

    @staticmethod
    def multi_response_sequence(responses: List[Dict[str, Any]]) -> List[Mock]:
        """Create sequence of mock responses for side_effect."""
        mock_responses = []

        for response_data in responses:
            if response_data.get("type") == "text":
                mock_responses.append(
                    OpenAIMockBuilder.simple_response(response_data["content"])
                )
            elif response_data.get("type") == "tool_call":
                mock_responses.append(
                    OpenAIMockBuilder.tool_call_response(
                        response_data["tool_name"],
                        response_data["arguments"],
                        response_data.get("call_id", "call_test")
                    )
                )
            elif response_data.get("type") == "error":
                mock_responses.append(
                    OpenAIMockBuilder.error_response(
                        response_data["error_type"],
                        response_data["message"]
                    )
                )

        return mock_responses


class LLMResponseBuilder:
    """Builder for creating LLMResponse objects."""

    @staticmethod
    def text_response(content: str) -> LLMResponse:
        """Create text-only LLMResponse."""
        return LLMResponse(
            content=content,
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

    @staticmethod
    def tool_call_response(
        tool_name: str,
        arguments: Dict[str, Any],
        call_id: str = "call_test",
        extra_content: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Create tool calling LLMResponse."""
        tool_call = ToolCall(
            name=tool_name,
            arguments=arguments,
            id=call_id,
            extra_content=extra_content,
        )

        return LLMResponse(
            content=None,
            tool_calls=[tool_call],
            raw_response=None,
            usage=TokenUsage(),
        )

    @staticmethod
    def multi_tool_response(tool_calls: List[Dict[str, Any]]) -> LLMResponse:
        """Create multi-tool calling LLMResponse."""
        calls = []
        for i, call_data in enumerate(tool_calls):
            calls.append(ToolCall(
                name=call_data["name"],
                arguments=call_data["arguments"],
                id=call_data.get("id", f"call_test_{i}")
            ))

        return LLMResponse(
            content=None,
            tool_calls=calls,
            raw_response=None,
            usage=TokenUsage(),
        )


class FileSystemMocker:
    """Mock file system operations."""

    @staticmethod
    def create_mock_file_error(error_type: str, message: str = None):
        """Create file system error mocks."""
        error_map = {
            "not_found": FileNotFoundError,
            "permission": PermissionError,
            "disk_full": OSError
        }

        error_class = error_map.get(error_type, OSError)
        default_messages = {
            "not_found": "File not found",
            "permission": "Permission denied",
            "disk_full": "No space left on device"
        }

        error_message = message or default_messages.get(error_type, "File system error")
        return error_class(error_message)


class AgentWorkflowMocker:
    """Mock complex agent workflows."""

    @staticmethod
    def calculator_workflow():
        """Mock a calculator workflow sequence."""
        return [
            LLMResponseBuilder.tool_call_response(
                "calculator",
                {"expression": "2 + 2"}
            ),
            LLMResponseBuilder.text_response("The result is 4.")
        ]

    @staticmethod
    def multi_tool_workflow():
        """Mock a multi-tool workflow sequence."""
        return [
            LLMResponseBuilder.tool_call_response(
                "calculator",
                {"expression": "100 / 4"}
            ),
            LLMResponseBuilder.tool_call_response(
                "current_time",
                {}
            ),
            LLMResponseBuilder.text_response(
                "The result is 25.0, calculated at the current time."
            )
        ]

    @staticmethod
    def error_recovery_workflow():
        """Mock a workflow with error recovery."""
        return [
            LLMResponseBuilder.tool_call_response(
                "calculator",
                {"expression": "invalid"}  # This will cause an error
            ),
            LLMResponseBuilder.text_response(
                "I apologize for the error. Let me try a valid calculation."
            ),
            LLMResponseBuilder.tool_call_response(
                "calculator",
                {"expression": "2 + 2"}
            ),
            LLMResponseBuilder.text_response("The result is 4.")
        ]


# Convenience functions for common scenarios
def create_successful_agent_mock(responses: List[str]) -> Mock:
    """Create a mock agent that returns successful text responses."""
    mock_agent = Mock()
    mock_agent.run.side_effect = responses
    mock_agent.input.side_effect = responses
    mock_agent.name = "test_agent"
    mock_agent.list_tools.return_value = ["calculator", "current_time"]
    return mock_agent


def create_failing_agent_mock(error_message: str = "Agent error") -> Mock:
    """Create a mock agent that fails."""
    mock_agent = Mock()
    mock_agent.run.side_effect = Exception(error_message)
    mock_agent.input.side_effect = Exception(error_message)
    mock_agent.name = "failing_agent"
    return mock_agent


class MockAgent:
    """Lightweight mock Agent for tests that want a simple, controllable agent.

    Features:
    - `input()` and `run()` methods returning queued responses or computed via callback
    - Tracks calls (`calls`, `last_input`) and maintains a minimal `current_session`
    - Optional `tools` registry for interface parity; does not auto-execute tools

    Usage:
        agent = MockAgent(responses=["hello", "world"], tools=["calculator"]) 
        out1 = agent.input("hi")  # "hello"
        out2 = agent.input("again")  # "world"
    """

    def __init__(
        self,
        name: str = "mock_agent",
        responses: Optional[List[str]] = None,
        tools: Optional[Union[List[Union[str, Callable]], Dict[str, Callable]]] = None,
        on_input: Optional[Callable[[str, "MockAgent"], str]] = None,
    ):
        self.name = name
        self._responses: List[str] = list(responses) if responses else []
        self._on_input = on_input
        self._calls: List[Dict[str, Any]] = []
        self.last_input: Optional[str] = None

        # Minimal session state for parity with real Agent
        self.current_session: Dict[str, Any] = {
            "messages": [],
            "trace": [],
        }

        # Normalize tools to a name->callable mapping where possible
        self._tools: Dict[str, Any] = {}
        if isinstance(tools, dict):
            self._tools = dict(tools)
        elif isinstance(tools, list):
            for t in tools:
                if callable(t):
                    self._tools[getattr(t, "__name__", "tool")] = t
                else:
                    self._tools[str(t)] = t

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def input(self, prompt: str) -> str:
        self.last_input = prompt
        self._calls.append({"input": prompt})
        self.current_session["messages"].append({"role": "user", "content": prompt})

        if self._on_input is not None:
            result = self._on_input(prompt, self)
        elif self._responses:
            result = self._responses.pop(0)
        else:
            result = ""

        # Track a minimal assistant message
        self.current_session["messages"].append({"role": "assistant", "content": result})
        return result

    # Alias to mirror some tests that call run()
    def run(self, prompt: str) -> str:
        return self.input(prompt)

    @property
    def calls(self) -> List[Dict[str, Any]]:
        return self._calls

"""Mock helpers for ConnectOnion testing."""

import json
from unittest.mock import Mock, MagicMock
from typing import Dict, List, Any, Optional
from connectonion.llm import LLMResponse, ToolCall


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
            raw_response=None
        )

    @staticmethod
    def tool_call_response(
        tool_name: str,
        arguments: Dict[str, Any],
        call_id: str = "call_test"
    ) -> LLMResponse:
        """Create tool calling LLMResponse."""
        tool_call = ToolCall(
            name=tool_name,
            arguments=arguments,
            id=call_id
        )

        return LLMResponse(
            content=None,
            tool_calls=[tool_call],
            raw_response=None
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
            raw_response=None
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
    mock_agent.name = "test_agent"
    mock_agent.list_tools.return_value = ["calculator", "current_time"]
    return mock_agent


def create_failing_agent_mock(error_message: str = "Agent error") -> Mock:
    """Create a mock agent that fails."""
    mock_agent = Mock()
    mock_agent.run.side_effect = Exception(error_message)
    mock_agent.name = "failing_agent"
    return mock_agent
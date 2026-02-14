"""End-to-end tests for image_result_formatter plugin.

This test demonstrates the complete workflow of the image formatter plugin:
1. Tool returns base64 image
2. Plugin detects and formats the image for LLM
3. Plugin sends image to frontend via WebSocket
4. LLM receives properly formatted image message
"""

import pytest
from unittest.mock import Mock

from connectonion import Agent
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins import image_result_formatter
from tests.utils.mock_helpers import MockLLM


# Example tool that returns a base64 image
def take_screenshot(url: str) -> str:
    """
    Take a screenshot of a webpage and return it as base64.

    Args:
        url: The URL of the webpage to screenshot

    Returns:
        Base64-encoded PNG image
    """
    # Simulate returning a base64 image (tiny 1x1 PNG)
    return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


@pytest.mark.e2e
class TestImageFormatterPluginE2E:
    """End-to-end tests for image_result_formatter plugin."""

    def test_complete_image_workflow_with_io(self):
        """
        Test complete workflow: tool returns image -> plugin formats -> sends to frontend.

        This demonstrates the full integration of:
        - Tool returning base64 image
        - Plugin detecting and formatting the image
        - Plugin sending to WebSocket IO
        - LLM receiving properly formatted message
        """
        # Create mock LLM with two responses
        mock_llm = MockLLM(responses=[
            # First response: call the screenshot tool
            LLMResponse(
                content="I'll take a screenshot for you.",
                tool_calls=[
                    ToolCall(
                        name="take_screenshot",
                        arguments={"url": "https://example.com"},
                        id="call_screenshot_1"
                    )
                ],
                raw_response=None,
                usage=TokenUsage()
            ),
            # Second response: analyze the screenshot
            LLMResponse(
                content="I can see the webpage in the screenshot. It shows...",
                tool_calls=[],
                raw_response=None,
                usage=TokenUsage()
            )
        ])

        # Create mock IO
        mock_io = Mock()

        # Create agent with image_result_formatter plugin and mock IO
        agent = Agent(
            name="screenshot_agent",
            llm=mock_llm,
            tools=[take_screenshot],
            plugins=[image_result_formatter],
            log=False
        )
        agent.io = mock_io  # Inject mock IO

        # Execute agent
        response = agent.input("Take a screenshot of https://example.com")

        # Verify agent completed successfully
        assert response is not None
        assert "screenshot" in response.lower() or "see" in response.lower()

        # Verify the image was sent to WebSocket
        mock_io.send_image.assert_called_once()
        call_args = mock_io.send_image.call_args[0][0]
        assert call_args.startswith("data:image/png;base64,")
        assert "iVBORw0KGgo" in call_args  # PNG header in base64

        # Verify messages were properly formatted
        messages = agent.current_session['messages']

        # Find the tool message
        tool_msg = next(
            (msg for msg in messages if msg.get('role') == 'tool'),
            None
        )
        assert tool_msg is not None
        # Tool message should be shortened (not contain the full base64)
        assert "Screenshot captured" in tool_msg['content']
        assert "iVBORw0KGgo" not in tool_msg['content']

        # Find the assistant message with image
        assistant_image_msg = next(
            (msg for msg in messages
             if msg.get('role') == 'assistant'
             and isinstance(msg.get('content'), list)
             and any(item.get('type') == 'image_url' for item in msg['content'])),
            None
        )
        assert assistant_image_msg is not None

        # Verify image content structure
        content = assistant_image_msg['content']
        text_part = next(item for item in content if item['type'] == 'text')
        image_part = next(item for item in content if item['type'] == 'image_url')

        assert 'tool' in text_part['text'].lower()
        assert 'data:image/png;base64,' in image_part['image_url']['url']
        assert 'iVBORw0KGgo' in image_part['image_url']['url']

    def test_image_workflow_without_io(self):
        """
        Test workflow when agent.io is not available (non-hosted mode).

        The plugin should still format the image for the LLM, just not send to WebSocket.
        """
        mock_llm = MockLLM(responses=[
            LLMResponse(
                content="Taking screenshot...",
                tool_calls=[
                    ToolCall(
                        name="take_screenshot",
                        arguments={"url": "https://example.com"},
                        id="call_screenshot_2"
                    )
                ],
                raw_response=None,
                usage=TokenUsage()
            ),
            LLMResponse(
                content="Screenshot captured successfully.",
                tool_calls=[],
                raw_response=None,
                usage=TokenUsage()
            )
        ])

        # Create agent WITHOUT io (non-hosted mode)
        agent = Agent(
            name="local_screenshot_agent",
            llm=mock_llm,
            tools=[take_screenshot],
            plugins=[image_result_formatter],
            log=False
        )
        # agent.io is None by default

        # Execute agent
        response = agent.input("Screenshot https://example.com")

        # Should complete successfully even without io
        assert response is not None

        # Verify messages were still formatted correctly
        messages = agent.current_session['messages']

        # Find assistant message with image
        assistant_image_msg = next(
            (msg for msg in messages
             if msg.get('role') == 'assistant'
             and isinstance(msg.get('content'), list)
             and any(item.get('type') == 'image_url' for item in msg['content'])),
            None
        )
        assert assistant_image_msg is not None

        # Verify image is in the message
        content = assistant_image_msg['content']
        image_part = next(item for item in content if item['type'] == 'image_url')
        assert 'data:image/png;base64,' in image_part['image_url']['url']

    def test_multiple_images_workflow(self):
        """
        Test workflow with multiple images being generated in sequence.
        """
        def generate_chart(data: str) -> str:
            """Generate a chart and return as base64 image."""
            # Different base64 image (1x1 red pixel)
            return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="

        mock_llm = MockLLM(responses=[
            # First tool call: screenshot
            LLMResponse(
                content="Taking screenshot...",
                tool_calls=[
                    ToolCall(
                        name="take_screenshot",
                        arguments={"url": "https://example.com"},
                        id="call_1"
                    )
                ],
                raw_response=None,
                usage=TokenUsage()
            ),
            # Second tool call: chart
            LLMResponse(
                content="Generating chart...",
                tool_calls=[
                    ToolCall(
                        name="generate_chart",
                        arguments={"data": "1,2,3"},
                        id="call_2"
                    )
                ],
                raw_response=None,
                usage=TokenUsage()
            ),
            # Final response
            LLMResponse(
                content="Here are both the screenshot and the chart.",
                tool_calls=[],
                raw_response=None,
                usage=TokenUsage()
            )
        ])

        mock_io = Mock()

        agent = Agent(
            name="multi_image_agent",
            llm=mock_llm,
            tools=[take_screenshot, generate_chart],
            plugins=[image_result_formatter],
            log=False
        )
        agent.io = mock_io

        # Execute
        response = agent.input("Show me a screenshot and a chart")

        assert response is not None

        # Verify both images were sent to WebSocket
        assert mock_io.send_image.call_count == 2

        # Verify both images are in messages
        messages = agent.current_session['messages']
        assistant_image_msgs = [
            msg for msg in messages
            if msg.get('role') == 'assistant'
            and isinstance(msg.get('content'), list)
            and any(item.get('type') == 'image_url' for item in msg['content'])
        ]

        assert len(assistant_image_msgs) == 2


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v"])

"""
Image Result Formatter Plugin - Automatically formats base64 image results for model consumption.

When a tool returns a base64 encoded image (screenshot, generated image, etc.), this plugin
detects it and converts the tool result message to image format that LLMs can properly
interpret visually instead of treating it as text.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import image_result_formatter

    agent = Agent("assistant", tools=[take_screenshot], plugins=[image_result_formatter])
"""

import re
from typing import TYPE_CHECKING
from ..events import after_tool

if TYPE_CHECKING:
    from ..agent import Agent


def _is_base64_image(text: str) -> tuple[bool, str, str]:
    """
    Check if text contains base64 image data.

    Returns:
        (is_image, mime_type, base64_data)
    """
    if not isinstance(text, str):
        return False, "", ""

    # Check for data URL format: data:image/png;base64,iVBORw0KGgo...
    data_url_pattern = r'data:image/(png|jpeg|jpg|gif|webp);base64,([A-Za-z0-9+/=]+)'
    match = re.search(data_url_pattern, text)

    if match:
        image_type = match.group(1)
        base64_data = match.group(2)
        mime_type = f"image/{image_type}"
        return True, mime_type, base64_data

    # Check if entire result is base64 (common for screenshot tools)
    # Base64 strings are typically long and contain only valid base64 characters
    if len(text) > 100 and re.match(r'^[A-Za-z0-9+/=\s]+$', text):
        # Likely a base64 image, default to PNG
        return True, "image/png", text.strip()

    return False, "", ""


def _format_image_result(agent: 'Agent') -> None:
    """
    Format base64 image in tool result to proper image message format.

    When a tool returns base64 image data, this converts the tool message
    to use image format instead of text, so the LLM can properly see and
    analyze the image visually.
    """
    trace = agent.current_session['trace'][-1]

    if trace['type'] != 'tool_execution' or trace['status'] != 'success':
        return

    result = trace['result']
    tool_call_id = trace.get('tool_call_id')

    # Check if result contains base64 image
    is_image, mime_type, base64_data = _is_base64_image(result)

    if not is_image:
        return

    # Find the tool result message and convert it to image format
    messages = agent.current_session['messages']

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]

        if msg['role'] == 'tool' and msg.get('tool_call_id') == tool_call_id:
            # Convert to image message format
            # Using OpenAI's format (works with most providers via LiteLLM)
            messages[i]['content'] = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_data}"
                    }
                }
            ]

            agent.console.print(f"[dim]🖼️  Formatted tool result as image ({mime_type})[/dim]")
            break


# Plugin is an event list
image_result_formatter = [after_tool(_format_image_result)]

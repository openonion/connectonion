"""
Purpose: Automatically format base64 image tool results for multimodal LLM consumption and send to frontend
LLM-Note:
  Dependencies: imports from [re, typing, events.after_tools] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_image_result_formatter.py]
  Data flow: after_tools event → scans tool result messages for base64 images → detects data URL or raw base64 patterns → converts tool result message content to OpenAI vision API format with image_url type → sends image to frontend via agent.io.send_image() if available → allows LLM to visually interpret screenshots/images
  State/Effects: modifies agent.current_session['messages'] in place | replaces text content with image content blocks | sends WebSocket event if agent.io exists | no file I/O
  Integration: exposes image_result_formatter plugin list with [format_images] handler | used via Agent(plugins=[image_result_formatter]) | works with screenshot tools, image generators | auto-sends to oo-chat/SDK clients when hosted
  Performance: O(n) message scanning | regex pattern matching | no LLM calls
  Errors: silent skip if no base64 images detected | malformed base64 may cause LLM confusion

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
from ..core.events import after_tools

if TYPE_CHECKING:
    from ..core.agent import Agent


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
    Format base64 images in tool results to proper multimodal message format.

    When tools return base64 image data, this converts the tool messages
    to multimodal format (text + image) so the LLM can properly see and
    analyze the images visually.

    Processes ALL tool results from the current turn (after_tools fires once per turn).

    Uses OpenAI vision format:
    content: [
        {"type": "text", "text": "Tool 'tool_name' returned an image. See below."},
        {"type": "image_url", "image_url": "data:image/png;base64,..."}
    ]
    """
    # Process all tool results from the current turn
    # after_tools fires once, but multiple tools may have executed
    trace = agent.current_session.get('trace', [])
    messages = agent.current_session['messages']

    # Track which tool messages we've already processed (to insert assistant messages in order)
    processed_indices = []

    # Iterate through trace in reverse to process most recent tools first
    for trace_entry in reversed(trace):
        if trace_entry.get('type') != 'tool_result' or trace_entry.get('status') != 'success':
            continue

        result = trace_entry.get('result')
        tool_call_id = trace_entry.get('tool_id')  # Use 'tool_id' from trace entry
        tool_name = trace_entry.get('name', 'unknown')

        # Check if result contains base64 image
        is_image, mime_type, base64_data = _is_base64_image(result)

        if not is_image:
            continue

        # Find the tool result message and modify it
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]

            if msg['role'] == 'tool' and msg.get('tool_call_id') == tool_call_id:
                if i in processed_indices:
                    continue  # Already processed this tool message

                # Shorten the tool message content (remove base64 to save tokens)
                messages[i]['content'] = f"Screenshot captured (image provided below)"

                # Insert an assistant message with the image right after the tool message
                messages.insert(i + 1, {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": f"I captured an image from the '{tool_name}' tool:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
                        }
                    ]
                })

                processed_indices.append(i)
                agent.logger.print(f"[dim]🖼️  Formatted '{tool_name}' result as image[/dim]")
                break

        # Update trace result to short message (avoids token overflow in other plugins like ReAct)
        trace_entry['result'] = f"🖼️ Tool '{tool_name}' returned image ({mime_type})"

        # Send image to frontend via WebSocket if available
        if agent.io:
            data_url = f"data:{mime_type};base64,{base64_data}"
            agent.io.send_image(data_url)


# Plugin is an event list
# Uses after_tools because message modification can only happen after all tools finish
image_result_formatter = [after_tools(_format_image_result)]

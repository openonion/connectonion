"""
LLM-Note: Image Result Formatter Plugin - Automatically detects and formats base64 image tool results for multimodal LLM consumption

Purpose: Automatically format base64 image tool results for multimodal LLM consumption and send to frontend

Image Result Formatter Plugin - Automatically formats base64 image results for model consumption.

When a tool returns a base64 encoded image (screenshot, generated image, etc.), this plugin
detects it and converts the tool result message to image format that LLMs can properly
interpret visually instead of treating it as text.

LIFECYCLE - When and How Messages Are Modified:
┌─────────────────────────────────────────────────────────────────────────┐
│ BEFORE Plugin (after_tools event fires)                                │
├─────────────────────────────────────────────────────────────────────────┤
│ messages = [                                                            │
│   {"role": "user", "content": "Take a screenshot"},                     │
│   {"role": "assistant", "content": "", "tool_calls": [...]},           │
│   {"role": "tool", "content": "data:image/png;base64,iVBORw...",       │
│    "tool_call_id": "call_123"}                                          │
│ ]                                                                       │
│                                                                         │
│ trace = [                                                               │
│   {"type": "tool_result", "name": "screenshot", "status": "success",    │
│    "result": "data:image/png;base64,iVBORw...", "tool_id": "call_123"}  │
│ ]                                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ TRANSFORMATION                                                          │
│ 1. Scan trace for tool_result entries with base64 images              │
│ 2. Find matching tool message by tool_call_id                          │
│ 3. Shorten tool message content (remove base64)                        │
│ 4. Insert user message with image after tool message                   │
│ 5. Update trace result to short summary                                │
│ 6. Send image to frontend via agent.io.send_image() if available       │
├─────────────────────────────────────────────────────────────────────────┤
│ AFTER Plugin                                                            │
│ messages = [                                                            │
│   {"role": "user", "content": "Take a screenshot"},                     │
│   {"role": "assistant", "content": "", "tool_calls": [...]},           │
│   {"role": "tool", "content": "Screenshot captured (image below)",      │
│    "tool_call_id": "call_123"},                                         │
│   {"role": "user", "content": [                                         │
│       {"type": "text", "text": "Here is the image from 'screenshot':"},│
│       {"type": "image_url", "image_url": "data:image/png;base64,..."}   │
│    ]}                                                                   │
│ ]                                                                       │
│                                                                         │
│ trace = [                                                               │
│   {"type": "tool_result", "name": "screenshot", "status": "success",    │
│    "result": "🖼️ Tool 'screenshot' returned image (image/png)",         │
│    "tool_id": "call_123"}                                               │
│ ]                                                                       │
└─────────────────────────────────────────────────────────────────────────┘

WHY after_tools?
- Fires ONCE after ALL tools complete (not per-tool)
- Safe to modify messages array (tool execution finished)
- Trace is complete with all tool results
- Can insert new messages without breaking tool execution loop

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
    trace = agent.current_session.get('trace', [])
    messages = agent.current_session['messages']

    # Track messages already processed to avoid double-insertion when iterating
    # We need this because messages.insert() shifts indices
    processed_tool_ids = set()

    # Process tool results in order (not reversed - simpler logic)
    for trace_entry in trace:
        if trace_entry.get('type') != 'tool_result' or trace_entry.get('status') != 'success':
            continue

        tool_call_id = trace_entry.get('tool_id')
        if tool_call_id in processed_tool_ids:
            continue

        result = trace_entry.get('result')
        tool_name = trace_entry.get('name', 'unknown')

        # Check if result contains base64 image
        is_image, mime_type, base64_data = _is_base64_image(result)
        if not is_image:
            continue

        # Find the matching tool message
        for i, msg in enumerate(messages):
            if msg.get('role') == 'tool' and msg.get('tool_call_id') == tool_call_id:
                # Shorten the tool message content (remove base64 to save tokens)
                messages[i]['content'] = f"Screenshot captured (image provided below)"

                # Insert a user message with the image right after the tool message
                messages.insert(i + 1, {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Here is the image from '{tool_name}':"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
                        }
                    ]
                })

                processed_tool_ids.add(tool_call_id)
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

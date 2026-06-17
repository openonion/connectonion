"""
LLM-Note: Image result formatter plugin.

Purpose: Remove raw base64 image payloads from the tool message, add a
multimodal image message so the LLM can see the image, and send image results to
frontend IO when available.

Data flow: after_tools event -> scan successful tool_result trace entries ->
detect image data URL or raw base64 -> replace the matching tool message with a
short placeholder -> insert a user message containing image_url -> shorten the
trace result, keeping the data URL on trace_entry['image'] so session replay
(host/session/ui.py) can re-emit the screenshot into chat_items.

State/Effects: mutates agent.current_session["messages"] and trace entries;
optionally calls agent.io.send_image(data_url). Non-image tool results are ignored.

Test coverage: tests/unit/test_image_result_formatter.py and
tests/e2e/test_image_formatter_plugin.py.
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


# How many recent screenshots stay fully visible to the LLM. Older ones are stale
# page state — useless to the model but they grow the context without bound over a
# long browser task. Anthropic computer-use keeps the last few tool_result images
# the same way (_maybe_filter_to_n_most_recent_images).
KEEP_LAST_N_SCREENSHOTS = 3


def _is_image_message(message: dict) -> bool:
    """True if the message carries an image_url block (a screenshot we inserted)."""
    content = message.get('content')
    return isinstance(content, list) and any(
        isinstance(part, dict) and part.get('type') == 'image_url'
        for part in content
    )


def _elide_old_screenshots(messages: list, keep_last: int) -> None:
    """Keep only the last `keep_last` screenshots in the LLM context; replace the
    image_url block of older ones with a short text placeholder.

    Only the LLM context (agent.current_session['messages']) is touched — each
    trace_entry['image'] keeps the full data URL, so session replay still re-emits
    every screenshot to the frontend. Idempotent: an already-elided message no
    longer has an image_url block, so re-running skips it.
    """
    image_indices = [i for i, m in enumerate(messages) if _is_image_message(m)]
    for i in image_indices[:-keep_last]:
        messages[i] = {
            "role": messages[i].get("role", "user"),
            "content": "[earlier screenshot removed to bound context]",
        }


def _format_image_result(agent: 'Agent') -> None:
    """Replace image tool result text with a multimodal image message."""
    trace = agent.current_session.get('trace', [])
    messages = agent.current_session['messages']

    for trace_entry in trace:
        if trace_entry.get('type') != 'tool_result' or trace_entry.get('status') != 'success':
            continue

        tool_call_id = trace_entry.get('tool_id')
        result = trace_entry.get('result')
        tool_name = trace_entry.get('name', 'unknown')

        is_image, mime_type, base64_data = _is_base64_image(result)
        if not is_image:
            continue

        data_url = f"data:{mime_type};base64,{base64_data}"
        tool_message_index = next(
            i for i, msg in enumerate(messages)
            if msg.get('role') == 'tool' and msg.get('tool_call_id') == tool_call_id
        )

        messages[tool_message_index]['content'] = "Tool returned an image (provided below)"
        messages.insert(tool_message_index + 1, {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Here is the image from '{tool_name}':"
                },
                {
                    "type": "image_url",
                    "image_url": {"url": data_url}
                }
            ]
        })

        if agent.io:
            agent.io.send_image(data_url)

        # Keep the data URL on the trace (not sent to the LLM) so session replay
        # can re-emit the image into chat_items. Without this, the shortened
        # result below is the only trace record and screenshots vanish whenever
        # the client rebuilds its UI from the server's canonical history.
        trace_entry['image'] = data_url
        trace_entry['result'] = f"Tool '{tool_name}' returned image ({mime_type})"
        agent.logger.print(f"[dim]Formatted '{tool_name}' result as image[/dim]")

    # Slide the window: at most KEEP_LAST_N_SCREENSHOTS screenshots stay visible to
    # the LLM. Runs every turn so the context stays bounded over a long browser task.
    _elide_old_screenshots(messages, KEEP_LAST_N_SCREENSHOTS)


# Plugin is an event list
# Uses after_tools because message modification can only happen after all tools finish
image_result_formatter = [after_tools(_format_image_result)]

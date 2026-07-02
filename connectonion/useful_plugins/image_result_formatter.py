"""
LLM-Note: Image result formatter plugin.

Purpose: Remove raw base64 image payloads from the tool message, add a
multimodal image message so the LLM can see the image, and send image results to
frontend IO when available. For managed (co/) agents the image bytes are uploaded
to oo-api (content-addressed GCS) and referenced by URL, so screenshots never bloat
the replayed message history; non-managed agents keep the inline data URL.

Data flow: after_tools event -> scan successful tool_result trace entries ->
detect image data URL or raw base64 -> upload to oo-api (managed) or keep data URL
-> replace the matching tool message with a short placeholder -> insert a user
message containing image_url -> shorten the trace result.

State/Effects: mutates agent.current_session["messages"] and trace entries;
optionally calls agent.io.send_image(image_url). Non-image tool results are ignored.

Test coverage: tests/unit/test_image_result_formatter.py and
tests/e2e/test_image_formatter_plugin.py.
"""

import re
import base64
import requests
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

        # Keep the raw bytes out of the message history (which is replayed to the LLM
        # every turn). Managed (co/) agents upload to oo-api -> content-addressed GCS
        # and reference the image by URL; oo-api materializes it per provider at call
        # time. Non-managed agents have no oo-api, so keep the inline data URL.
        image_url = _upload_image(agent, base64_data, mime_type)
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
                    "image_url": {"url": image_url}
                }
            ]
        })

        if agent.io:
            agent.io.send_image(image_url)

        trace_entry['result'] = f"Tool '{tool_name}' returned image ({mime_type})"
        agent.logger.print(f"[dim]Formatted '{tool_name}' result as image[/dim]")


def _upload_image(agent: 'Agent', base64_data: str, mime_type: str) -> str:
    """Upload the image to oo-api (managed agents) and return its stable URL.

    Only managed (co/) agents route through oo-api, which owns the /img endpoint and
    materializes the image per provider. For any other LLM there is no oo-api to
    offload to, so keep the inline data URL (previous behavior).

    Fails loudly on upload error: a managed agent already depends on oo-api for its
    LLM calls, and silently reverting to base64 would hide a broken image pipeline
    while re-inflating the context.
    """
    llm = getattr(agent, "llm", None)
    # OpenOnionLLM == managed keys == requests go through oo-api (checked by name to
    # avoid importing the llm module into this plugin).
    if type(llm).__name__ != "OpenOnionLLM":
        return f"data:{mime_type};base64,{base64_data}"

    base = llm.base_url.rsplit("/v1", 1)[0]  # "https://oo.openonion.ai/v1" -> base
    resp = requests.post(
        f"{base}/api/v1/images",
        headers={"Authorization": f"Bearer {llm.auth_token}"},
        files={"file": ("screenshot", base64.b64decode(base64_data), mime_type)},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["url"]


# Plugin is an event list
# Uses after_tools because message modification can only happen after all tools finish
image_result_formatter = [after_tools(_format_image_result)]

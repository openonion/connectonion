"""Owner-only Wiki snapshot over the existing authenticated OIP session."""

import asyncio

from .connect import replay_check_for

MAX_WIKI_BYTES = 16 * 1024 * 1024


async def handle_wiki_read(data, send_msg, conn, routes):
    request_id = data.get("request_id")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        return
    response = {"type": "WIKI_RESULT", "request_id": request_id, "ok": False}
    if not conn.get("authenticated"):
        response["error"] = "Authentication required"
    elif not conn.get("signed_commands"):
        from ..auth import authenticated_command_payload

        verified, error = authenticated_command_payload(
            data, conn.get("agent_address"), conn.get("recipient_address"),
            replay_check_for(conn, routes),
        )
        if error:
            response["error"] = "Signed Wiki request required"
        else:
            data = verified
    if "error" not in response:
        root = routes.get("wiki_root")
        trust = routes.get("trust_agent")
        if not trust or not trust.is_admin(conn.get("agent_address")):
            response["error"] = "Wiki is available only to the Host owner"
        elif root is None or not root.is_dir():
            response["error"] = "Wiki is not available on this Host"
        else:
            from ....wiki.reader import render

            html = await asyncio.to_thread(render, root)
            if len(html.encode("utf-8")) > MAX_WIKI_BYTES:
                response["error"] = "Wiki reader exceeds the 16 MiB limit"
            else:
                response.update(ok=True, html=html)
    await send_msg(response)

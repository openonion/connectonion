"""Dispatch authenticated Remote Browser lifecycle requests."""

import asyncio


async def run_remote_browser(
    data,
    send_msg,
    route_handlers,
    *,
    requester_address,
    transport,
):
    """Run one host-owned browser lifecycle request outside the WS read loop."""
    request_id = data.get("request_id")
    try:
        result = await asyncio.to_thread(
            route_handlers["remote_browser"],
            data,
            requester_address,
            transport,
        )
    except Exception as exc:
        result = {
            "schema_version": "1",
            "ok": False,
            "command": "remote-browser",
            "request_id": request_id if isinstance(request_id, str) else "",
            "code": "REMOTE_BROWSER_UNAVAILABLE",
            "message": f"{type(exc).__name__}: {exc}",
            "retryable": True,
            "retry_after_seconds": None,
            "state": {},
            "tips": [],
            "warnings": [],
            "next_actions": [],
        }
    await send_msg({"type": "REMOTE_BROWSER_RESULT", **result})

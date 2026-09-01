"""WebSocket mapping for the experimental OIP Session Sync 0.1 extension."""

import asyncio
import logging

from ..session import SessionSyncError, SessionSyncService

logger = logging.getLogger(__name__)


def _request_id(data: dict) -> str:
    value = data.get("request_id")
    if not isinstance(value, str) or not value or len(value) > 128:
        raise SessionSyncError("invalid_request", "request_id is required")
    return value


async def send_session_sync_error(send_msg, request_id, error) -> None:
    if not isinstance(error, SessionSyncError):
        logger.exception("Session Sync operation failed", exc_info=error)
        error = SessionSyncError(
            "temporarily_unavailable", "session store is temporarily unavailable"
        )
    frame = {
        "type": "ERROR",
        "code": error.code,
        "message": error.message,
        "retryable": error.code in {"rate_limited", "temporarily_unavailable"},
    }
    if isinstance(request_id, str):
        frame["request_id"] = request_id
    if error.data:
        frame["data"] = error.data
    await send_msg(frame)


async def handle_session_sync(data, send_msg, storage, owner) -> None:
    request_id = data.get("request_id")
    try:
        request_id = _request_id(data)
        result = await asyncio.to_thread(
            SessionSyncService(storage).sync,
            owner,
            cursor=data.get("cursor"),
            page_token=data.get("page_token"),
            limit=data.get("limit"),
            include_archived=data.get("include_archived", False),
        )
        await send_msg({
            "type": "SESSION_SYNC_RESULT",
            "request_id": request_id,
            **result,
        })
    except Exception as exc:
        await send_session_sync_error(send_msg, request_id, exc)


async def handle_session_get(data, send_msg, storage, owner) -> None:
    request_id = data.get("request_id")
    try:
        request_id = _request_id(data)
        result = await asyncio.to_thread(
            SessionSyncService(storage).get,
            owner,
            data.get("session_id"),
            if_revision=data.get("if_revision"),
            page_token=data.get("page_token"),
            limit=data.get("limit"),
        )
        frame_type = (
            "SESSION_NOT_MODIFIED" if result.get("not_modified")
            else "SESSION_SNAPSHOT"
        )
        await send_msg({"type": frame_type, "request_id": request_id, **result})
    except Exception as exc:
        await send_session_sync_error(send_msg, request_id, exc)


async def handle_session_update(data, send_msg, storage, owner) -> None:
    request_id = data.get("request_id")
    try:
        request_id = _request_id(data)
        summary = await asyncio.to_thread(
            SessionSyncService(storage).update,
            owner,
            data.get("session_id"),
            patch=data.get("patch"),
            if_revision=data.get("if_revision"),
        )
        await send_msg({
            "type": "SESSION_UPDATED",
            "request_id": request_id,
            "summary": summary,
        })
    except Exception as exc:
        await send_session_sync_error(send_msg, request_id, exc)


def _drain_changes(service, owner, cursor, include_archived):
    sessions = []
    removed = []
    page = service.sync(
        owner,
        cursor=cursor,
        include_archived=include_archived,
        limit=100,
    )
    while True:
        sessions.extend(page["sessions"])
        removed.extend(page["removed_session_ids"])
        page_token = page.get("next_page_token")
        if not page_token:
            return {
                "sessions": sessions,
                "removed_session_ids": removed,
                "cursor": page["cursor"],
            }
        page = service.sync(
            owner,
            page_token=page_token,
            include_archived=include_archived,
            limit=100,
        )


async def watch_session_changes(
    send_msg,
    storage,
    owner,
    *,
    cursor,
    include_archived,
    interval=1.0,
) -> None:
    service = SessionSyncService(storage)
    current = cursor
    try:
        while True:
            result = await asyncio.to_thread(
                _drain_changes,
                service,
                owner,
                current,
                include_archived,
            )
            current = result["cursor"]
            if result["sessions"] or result["removed_session_ids"]:
                await send_msg({"type": "SESSION_CHANGED", **result})
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await send_session_sync_error(send_msg, None, exc)


async def start_session_watch(data, send_msg, storage, owner):
    request_id = data.get("request_id")
    try:
        request_id = _request_id(data)
        cursor = data.get("cursor")
        if not isinstance(cursor, str) or not cursor:
            raise SessionSyncError("invalid_request", "cursor is required")
        include_archived = data.get("include_archived", False)
        if not isinstance(include_archived, bool):
            raise SessionSyncError(
                "invalid_request", "include_archived must be boolean"
            )
        # Validate before claiming the watch. A no-change sync preserves the
        # supplied cursor and costs no notification.
        await asyncio.to_thread(
            SessionSyncService(storage).sync,
            owner,
            cursor=cursor,
            include_archived=include_archived,
            limit=1,
        )
        await send_msg({
            "type": "SESSION_WATCHED",
            "request_id": request_id,
            "cursor": cursor,
        })
        return asyncio.create_task(
            watch_session_changes(
                send_msg,
                storage,
                owner,
                cursor=cursor,
                include_archived=include_archived,
            )
        )
    except Exception as exc:
        await send_session_sync_error(send_msg, request_id, exc)
        return None


__all__ = [
    "handle_session_get",
    "handle_session_sync",
    "handle_session_update",
    "start_session_watch",
    "watch_session_changes",
]

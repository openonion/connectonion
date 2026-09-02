"""Authenticated, revision-based retained-session synchronization.

The JSONL store remains the implementation detail. Cursors name a generation
and a parseable-record position, so compaction invalidates them explicitly
instead of letting an old byte/count offset silently describe different data.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import time
from datetime import datetime, timezone
from typing import Callable

from .storage import Session, SessionStorage, session_owner
from .ui import session_to_chat_items


class SessionSyncError(Exception):
    """Stable protocol failure with optional safe response data."""

    def __init__(self, code: str, message: str, *, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _timestamp(value: float | None) -> str:
    value = value if value is not None else 0.0
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _owner_scope(owner: str) -> str:
    return hashlib.sha256(owner.encode("utf-8")).hexdigest()[:32]


def _epoch_id(epoch: str) -> str:
    return hashlib.sha256(epoch.encode("utf-8")).hexdigest()[:32]


def _encode_token(value: dict, epoch: str) -> str:
    value = {**value, "epoch": _epoch_id(epoch)}
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(epoch.encode("utf-8"), raw, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{payload}.{encoded_signature}"


def _decode_token(value: object, epoch: str) -> dict:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise SessionSyncError("invalid_request", "invalid session sync token")
    try:
        payload, encoded_signature = value.split(".", 1)
        padding = "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload + padding)
        signature_padding = "=" * (-len(encoded_signature) % 4)
        signature = base64.urlsafe_b64decode(
            encoded_signature + signature_padding
        )
        decoded = json.loads(raw)
    except Exception as exc:
        raise SessionSyncError(
            "invalid_request", "invalid session sync token"
        ) from exc
    if not isinstance(decoded, dict) or decoded.get("v") != 1:
        raise SessionSyncError("invalid_request", "invalid session sync token")
    if decoded.get("epoch") != _epoch_id(epoch):
        raise SessionSyncError("cursor_expired", "session sync cursor expired")
    expected = hmac.new(epoch.encode("utf-8"), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise SessionSyncError("invalid_request", "invalid session sync token")
    return decoded


def _bounded_limit(value: object, *, default: int = 50, maximum: int = 100) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise SessionSyncError(
            "invalid_request", f"limit must be an integer from 1 to {maximum}"
        )
    return value


class SessionSyncService:
    """Transport-neutral implementation of OIP Session Sync 0.1."""

    def __init__(
        self,
        storage: SessionStorage,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.storage = storage
        self.clock = clock

    @staticmethod
    def _latest(records: list[Session]) -> dict[str, Session]:
        return {record.session_id: record for record in records}

    @staticmethod
    def _has_user_turn(record: Session) -> bool:
        # CONNECT persists the selected Host mode before the first INPUT so
        # reconnect policy survives a process restart. That transport-only row
        # is not chat history and must stay invisible until the user actually
        # starts the conversation. Keep prompt as a legacy fallback because
        # older stored sessions may not contain reconstructed message IDs.
        if isinstance(record.prompt, str) and record.prompt.strip():
            return True
        return any(
            item.get("type") == "user"
            for item in session_to_chat_items(record.session or {})
        )

    @classmethod
    def _is_retained(cls, record: Session, at: float) -> bool:
        return cls._has_user_turn(record) and (
            record.status == "running" or record.expires is None or record.expires > at
        )

    @staticmethod
    def _revision(record: Session) -> int:
        # Existing rows predate the field. Their synthesized first revision is
        # one; the next append receives one from the storage commit boundary.
        return max(record.revision, 1)

    def summary(self, record: Session) -> dict:
        metadata = record.metadata or {}
        session = record.session or {}
        items = session_to_chat_items(session)
        title = metadata.get("title")
        if not isinstance(title, str):
            title = " ".join((record.prompt or "").split())[:120]
        archived_at = metadata.get("archived_at")
        if not isinstance(archived_at, (int, float)) or isinstance(archived_at, bool):
            archived_at = None

        if record.status == "running":
            activity = "running"
        elif record.status == "waiting_approval":
            activity = "waiting"
        else:
            activity = "idle"

        outcome = {
            "done": "completed",
            "completed": "completed",
            "failed": "failed",
            "interrupted": "interrupted",
        }.get(record.status)
        updated_at = record.updated_at
        if updated_at is None:
            candidate = session.get("updated")
            updated_at = (
                float(candidate)
                if isinstance(candidate, (int, float))
                and not isinstance(candidate, bool)
                and math.isfinite(candidate)
                else record.created
            )

        preview_source = record.result or record.prompt or ""
        preview = " ".join(str(preview_source).split())[:160]
        value = {
            "session_id": record.session_id,
            "revision": self._revision(record),
            "title": title,
            "activity": activity,
            "created_at": _timestamp(record.created),
            "updated_at": _timestamp(updated_at),
            "last_sequence": len(items),
            **({"last_outcome": outcome} if outcome else {}),
            **({"archived_at": _timestamp(archived_at)} if archived_at else {}),
            **({"expires_at": _timestamp(record.expires)} if record.expires else {}),
            **({"preview": preview} if preview else {}),
        }
        return value

    def _validate_scope(self, token: dict, owner: str, epoch: str) -> None:
        if token.get("scope") != _owner_scope(owner):
            raise SessionSyncError("invalid_request", "session sync token has wrong scope")
        if token.get("epoch") != _epoch_id(epoch):
            raise SessionSyncError(
                "cursor_expired", "session sync cursor expired"
            )

    def sync(
        self,
        owner: str,
        *,
        cursor: str | None = None,
        page_token: str | None = None,
        limit: int | None = None,
        include_archived: bool = False,
    ) -> dict:
        if not isinstance(owner, str) or not owner:
            raise SessionSyncError("not_found", "session index not found")
        if cursor is not None and page_token is not None:
            raise SessionSyncError(
                "invalid_request", "cursor and page_token are mutually exclusive"
            )
        if not isinstance(include_archived, bool):
            raise SessionSyncError("invalid_request", "include_archived must be boolean")
        page_size = _bounded_limit(limit)
        records, epoch = self.storage.sync_snapshot()
        now = self.clock()

        if page_token is not None:
            token = _decode_token(page_token, epoch)
            if token.get("kind") != "sync_page":
                raise SessionSyncError("invalid_request", "wrong session sync token kind")
            self._validate_scope(token, owner, epoch)
            start = token.get("start")
            end = token.get("end")
            offset = token.get("offset")
            as_of = token.get("as_of")
            issued_at = token.get("issued_at", 0)
            full = token.get("full")
            selected_archived = token.get("include_archived")
            if include_archived != selected_archived:
                raise SessionSyncError(
                    "invalid_request", "page token archive selection changed"
                )
        else:
            offset = 0
            as_of = now
            end = len(records)
            full = cursor is None
            selected_archived = include_archived
            if cursor is None:
                start = 0
                issued_at = as_of
            else:
                token = _decode_token(cursor, epoch)
                if token.get("kind") != "sync_cursor":
                    raise SessionSyncError(
                        "invalid_request", "wrong session sync token kind"
                    )
                self._validate_scope(token, owner, epoch)
                if token.get("include_archived") != include_archived:
                    raise SessionSyncError(
                        "invalid_request", "cursor archive selection changed"
                    )
                start = token.get("position")
                issued_at = token.get("issued_at")

        numeric = (start, end, offset)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in numeric):
            raise SessionSyncError("invalid_request", "invalid session sync position")
        if not isinstance(as_of, (int, float)) or not math.isfinite(as_of):
            raise SessionSyncError("invalid_request", "invalid session sync time")
        if start < 0 or end < start or end > len(records) or offset < 0:
            raise SessionSyncError(
                "cursor_expired", "session sync cursor expired"
            )

        latest = self._latest(records[:end])
        entries: dict[str, dict | None] = {}
        if full:
            for session_id, record in latest.items():
                if session_owner(record) != owner or not self._is_retained(record, as_of):
                    continue
                if not selected_archived and record.metadata.get("archived_at"):
                    continue
                entries[session_id] = self.summary(record)
        else:
            changed_ids = {record.session_id for record in records[start:end]}
            # Expiry is a time transition rather than an append. Include rows
            # that crossed it since the cursor was issued so clients can remove
            # them without a forced full refresh.
            if not isinstance(issued_at, (int, float)) or not math.isfinite(issued_at):
                raise SessionSyncError("invalid_request", "invalid session sync cursor")
            for session_id, record in latest.items():
                if (
                    session_owner(record) == owner
                    and record.status != "running"
                    and record.expires is not None
                    and issued_at < record.expires <= as_of
                ):
                    changed_ids.add(session_id)

            for session_id in changed_ids:
                record = latest.get(session_id)
                if record is None or session_owner(record) != owner:
                    continue
                if (
                    not self._is_retained(record, as_of)
                    or (not selected_archived and record.metadata.get("archived_at"))
                ):
                    entries[session_id] = None
                else:
                    entries[session_id] = self.summary(record)

        def sort_key(item: tuple[str, dict | None]) -> tuple[str, str]:
            session_id, summary = item
            updated = summary.get("updated_at", "") if summary else ""
            return updated, session_id

        ordered = sorted(entries.items(), key=sort_key, reverse=True)
        page = ordered[offset:offset + page_size]
        next_offset = offset + len(page)
        response = {
            "sessions": [value for _, value in page if value is not None],
            "removed_session_ids": [key for key, value in page if value is None],
        }
        if next_offset < len(ordered):
            response["next_page_token"] = _encode_token({
                "v": 1,
                "kind": "sync_page",
                "scope": _owner_scope(owner),
                "start": start,
                "end": end,
                "offset": next_offset,
                "as_of": as_of,
                "issued_at": issued_at,
                "full": bool(full),
                "include_archived": selected_archived,
            }, epoch)
        else:
            response["cursor"] = _encode_token({
                "v": 1,
                "kind": "sync_cursor",
                "scope": _owner_scope(owner),
                "position": end,
                "issued_at": as_of,
                "include_archived": selected_archived,
            }, epoch)
        return response

    def records(self, record: Session) -> list[dict]:
        occurred_at = _timestamp(record.updated_at or record.created)
        mapped = []
        for sequence, item in enumerate(session_to_chat_items(record.session or {}), 1):
            item_type = item.get("type")
            if item_type == "user":
                kind = "input"
            elif item_type == "agent":
                kind = "output"
            elif item_type in {"ask_user", "approval_needed"}:
                kind = "request"
            else:
                kind = "event"
            mapped.append({
                "sequence": sequence,
                "record_id": str(item.get("id") or f"record-{sequence}"),
                "kind": kind,
                "occurred_at": occurred_at,
                "data": item,
            })
        return mapped

    def get(
        self,
        owner: str,
        session_id: str,
        *,
        if_revision: int | None = None,
        page_token: str | None = None,
        limit: int | None = None,
    ) -> dict:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 256:
            raise SessionSyncError("invalid_request", "invalid session_id")
        page_size = _bounded_limit(limit)
        stored, epoch = self.storage.sync_snapshot()
        as_of = self.clock()

        if page_token is not None:
            if if_revision is not None:
                raise SessionSyncError(
                    "invalid_request", "page_token and if_revision are mutually exclusive"
                )
            token = _decode_token(page_token, epoch)
            if token.get("kind") != "snapshot_page":
                raise SessionSyncError("invalid_request", "wrong snapshot token kind")
            self._validate_scope(token, owner, epoch)
            if token.get("session_id") != session_id:
                raise SessionSyncError("invalid_request", "snapshot session changed")
            revision = token.get("revision")
            offset = token.get("offset")
            as_of = token.get("as_of")
            if (
                isinstance(revision, bool)
                or not isinstance(revision, int)
                or isinstance(offset, bool)
                or not isinstance(offset, int)
                or offset < 0
                or isinstance(as_of, bool)
                or not isinstance(as_of, (int, float))
                or not math.isfinite(as_of)
            ):
                raise SessionSyncError("invalid_request", "invalid snapshot token")
            record = next(
                (
                    candidate for candidate in reversed(stored)
                    if candidate.session_id == session_id
                    and self._revision(candidate) == revision
                ),
                None,
            )
            if record is None:
                raise SessionSyncError("cursor_expired", "session snapshot expired")
        else:
            offset = 0
            record = self._latest(stored).get(session_id)
            if (
                record is None
                or session_owner(record) != owner
                or not self._is_retained(record, as_of)
            ):
                raise SessionSyncError("not_found", "session not found")
            revision = self._revision(record)
            if if_revision is not None:
                if (
                    isinstance(if_revision, bool)
                    or not isinstance(if_revision, int)
                    or if_revision < 1
                ):
                    raise SessionSyncError("invalid_request", "invalid if_revision")
                if if_revision == revision:
                    return {"not_modified": True, "revision": revision}

        if session_owner(record) != owner:
            raise SessionSyncError("not_found", "session not found")
        all_records = self.records(record)
        page = all_records[offset:offset + page_size]
        response = {
            "summary": self.summary(record),
            "snapshot_revision": revision,
            "records": page,
        }
        next_offset = offset + len(page)
        if next_offset < len(all_records):
            response["next_page_token"] = _encode_token({
                "v": 1,
                "kind": "snapshot_page",
                "scope": _owner_scope(owner),
                "session_id": session_id,
                "revision": revision,
                "offset": next_offset,
                "as_of": as_of,
            }, epoch)
        return response

    def update(
        self,
        owner: str,
        session_id: str,
        *,
        patch: dict,
        if_revision: int,
    ) -> dict:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 256:
            raise SessionSyncError("invalid_request", "invalid session_id")
        if (
            isinstance(if_revision, bool)
            or not isinstance(if_revision, int)
            or if_revision < 1
        ):
            raise SessionSyncError("invalid_request", "invalid if_revision")
        if not isinstance(patch, dict) or not patch or set(patch) - {"title", "archived"}:
            raise SessionSyncError("invalid_request", "invalid session metadata patch")
        if "title" in patch and (
            not isinstance(patch["title"], str) or len(patch["title"]) > 120
        ):
            raise SessionSyncError("invalid_request", "title must be at most 120 characters")
        if "archived" in patch and not isinstance(patch["archived"], bool):
            raise SessionSyncError("invalid_request", "archived must be boolean")

        now = self.clock()

        def apply(current: Session | None) -> Session:
            if (
                current is None
                or session_owner(current) != owner
                or not self._is_retained(current, now)
            ):
                raise SessionSyncError("not_found", "session not found")
            if self._revision(current) != if_revision:
                raise SessionSyncError(
                    "revision_conflict",
                    "session revision changed",
                    data={"summary": self.summary(current)},
                )
            metadata = dict(current.metadata)
            if "title" in patch:
                metadata["title"] = " ".join(patch["title"].split())
            if "archived" in patch:
                metadata["archived_at"] = now if patch["archived"] else None
            return current.model_copy(deep=True, update={"metadata": metadata})

        committed = self.storage.atomic_update(session_id, apply)
        return self.summary(committed)


__all__ = ["SessionSyncError", "SessionSyncService"]

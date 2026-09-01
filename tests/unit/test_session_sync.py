"""OIP Session Sync exposes only retained history owned by the signer."""

import time

import pytest

from connectonion import address
from connectonion.network.connect import RemoteAgent
from connectonion.network.host.session import (
    Session,
    SessionStorage,
    SessionSyncError,
    SessionSyncService,
)


OWNER = "0xowner"
OTHER = "0xother"


def _session(
    session_id: str,
    *,
    owner: str = OWNER,
    prompt: str = "hello",
    status: str = "done",
    expires: float | None = None,
) -> Session:
    return Session(
        session_id=session_id,
        status=status,
        prompt=prompt,
        result=f"answer to {prompt}",
        created=time.time(),
        expires=expires if expires is not None else time.time() + 3600,
        session={
            "requester": {"address": owner},
            "messages": [
                {"role": "user", "content": prompt, "id": f"{session_id}-u"},
                {"role": "assistant", "content": "answer", "id": f"{session_id}-a"},
            ],
            "trace": [],
        },
    )


@pytest.fixture
def storage(tmp_path):
    return SessionStorage(tmp_path / "sessions.jsonl")


def test_storage_assigns_monotonic_host_revisions(storage):
    first = storage.save(_session("s1"))
    second = storage.save(first.model_copy(update={"status": "running"}))

    assert first.revision == 1
    assert second.revision == 2
    assert second.updated_at >= first.updated_at


def test_first_append_after_a_legacy_row_advances_its_synthesized_revision(storage):
    legacy = _session("legacy")
    storage.path.write_text(legacy.model_dump_json() + "\n", encoding="utf-8")
    service = SessionSyncService(storage)

    summary = service.sync(OWNER)["sessions"][0]
    updated = service.update(
        OWNER,
        "legacy",
        patch={"title": "Now revision two"},
        if_revision=summary["revision"],
    )

    assert summary["revision"] == 1
    assert updated["revision"] == 2


def test_full_sync_is_owner_scoped_and_incremental(storage):
    first = storage.save(_session("s1", prompt="first"))
    storage.save(_session("private", owner=OTHER))
    service = SessionSyncService(storage)

    full = service.sync(OWNER)
    assert [item["session_id"] for item in full["sessions"]] == ["s1"]
    assert full["removed_session_ids"] == []
    assert full["sessions"][0]["revision"] == first.revision

    second = storage.save(_session("s2", prompt="second"))
    delta = service.sync(OWNER, cursor=full["cursor"])
    assert [item["session_id"] for item in delta["sessions"]] == ["s2"]
    assert delta["sessions"][0]["revision"] == second.revision

    unchanged = service.sync(OWNER, cursor=delta["cursor"])
    assert unchanged["sessions"] == []
    assert unchanged["removed_session_ids"] == []
    assert isinstance(unchanged["cursor"], str)


def test_incremental_cursor_advances_past_another_owners_writes(storage):
    storage.save(_session("s1"))
    service = SessionSyncService(storage, clock=lambda: 100.0)
    cursor = service.sync(OWNER)["cursor"]
    storage.save(_session("other", owner=OTHER))

    delta = SessionSyncService(storage, clock=lambda: 101.0).sync(
        OWNER,
        cursor=cursor,
    )

    assert delta["sessions"] == []
    assert delta["removed_session_ids"] == []
    assert delta["cursor"] != cursor


def test_sync_pagination_returns_cursor_only_after_last_page(storage):
    for index in range(3):
        storage.save(_session(f"s{index}", prompt=str(index)))
    service = SessionSyncService(storage)

    first = service.sync(OWNER, limit=2)
    assert len(first["sessions"]) == 2
    assert "cursor" not in first

    second = service.sync(OWNER, page_token=first["next_page_token"], limit=2)
    assert len(second["sessions"]) == 1
    assert "cursor" in second
    assert "next_page_token" not in second


def test_get_is_revision_conditional_and_record_ordered(storage):
    committed = storage.save(_session("s1"))
    service = SessionSyncService(storage)

    snapshot = service.get(OWNER, "s1", limit=1)
    assert snapshot["snapshot_revision"] == committed.revision
    assert snapshot["records"][0]["sequence"] == 1
    assert snapshot["records"][0]["kind"] == "input"
    assert "next_page_token" in snapshot

    rest = service.get(
        OWNER,
        "s1",
        page_token=snapshot["next_page_token"],
        limit=1,
    )
    assert rest["records"][0]["sequence"] == 2
    assert rest["records"][0]["kind"] == "output"
    assert service.get(OWNER, "s1", if_revision=committed.revision) == {
        "not_modified": True,
        "revision": committed.revision,
    }


def test_get_does_not_reveal_another_owners_session(storage):
    storage.save(_session("private", owner=OTHER))

    with pytest.raises(SessionSyncError, match="not found") as caught:
        SessionSyncService(storage).get(OWNER, "private")

    assert caught.value.code == "not_found"


def test_archive_is_a_revision_checked_remote_mutation(storage):
    committed = storage.save(_session("s1"))
    service = SessionSyncService(storage)
    cursor = service.sync(OWNER)["cursor"]

    archived = service.update(
        OWNER,
        "s1",
        patch={"archived": True},
        if_revision=committed.revision,
    )
    assert archived["revision"] == committed.revision + 1
    assert "archived_at" in archived

    delta = service.sync(OWNER, cursor=cursor)
    assert delta["sessions"] == []
    assert delta["removed_session_ids"] == ["s1"]

    with pytest.raises(SessionSyncError) as caught:
        service.update(
            OWNER,
            "s1",
            patch={"title": "stale"},
            if_revision=committed.revision,
        )
    assert caught.value.code == "revision_conflict"
    assert caught.value.data["summary"]["revision"] == archived["revision"]


def test_archive_selection_is_bound_to_cursor(storage):
    committed = storage.save(_session("s1"))
    service = SessionSyncService(storage)
    service.update(
        OWNER,
        "s1",
        patch={"archived": True},
        if_revision=committed.revision,
    )
    result = service.sync(OWNER, include_archived=True)

    assert result["sessions"][0]["session_id"] == "s1"
    with pytest.raises(SessionSyncError) as caught:
        service.sync(OWNER, cursor=result["cursor"], include_archived=False)
    assert caught.value.code == "invalid_request"


def test_compaction_expires_old_cursors(storage):
    storage.save(_session("s1"))
    service = SessionSyncService(storage)
    cursor = service.sync(OWNER)["cursor"]

    storage.compact()

    with pytest.raises(SessionSyncError) as caught:
        service.sync(OWNER, cursor=cursor)
    assert caught.value.code == "cursor_expired"


def test_cursor_integrity_rejects_client_tampering(storage):
    storage.save(_session("s1"))
    cursor = SessionSyncService(storage).sync(OWNER)["cursor"]
    payload, signature = cursor.split(".", 1)
    replacement = "A" if signature[0] != "A" else "B"
    tampered = f"{payload}.{replacement}{signature[1:]}"

    with pytest.raises(SessionSyncError) as caught:
        SessionSyncService(storage).sync(OWNER, cursor=tampered)

    assert caught.value.code == "invalid_request"


def test_expiry_transition_is_reported_without_an_append(storage):
    storage.save(_session("s1", expires=150.0))
    service = SessionSyncService(storage, clock=lambda: 100.0)
    cursor = service.sync(OWNER)["cursor"]

    expired = SessionSyncService(storage, clock=lambda: 200.0).sync(
        OWNER,
        cursor=cursor,
    )

    assert expired["sessions"] == []
    assert expired["removed_session_ids"] == ["s1"]


@pytest.mark.asyncio
async def test_legacy_socket_still_requires_a_signed_session_sync_command(
    storage, monkeypatch
):
    from connectonion.network.host.ws_router import session as session_router

    keys = address.generate()
    recipient = "0x" + "12" * 20
    storage.save(_session("s1", owner=keys["address"]))
    agent = RemoteAgent(recipient, keys=keys)
    connect = {"type": "CONNECT", "from": keys["address"]}
    sync = agent._build_command_message({
        "type": "SESSION_SYNC",
        "request_id": "sync-1",
    })
    messages = [connect, sync]
    sent = []

    async def fake_connect(data, send, conn, *args):
        conn.update(
            authenticated=True,
            agent_address=keys["address"],
            signed_commands=False,
            recipient_address=recipient,
            session_sync=True,
            session_id="socket-session",
        )

    async def recv():
        return messages.pop(0) if messages else None

    async def send(message):
        sent.append(message)

    monkeypatch.setattr(session_router, "handle_connect", fake_connect)
    await session_router.run_ws_session(
        send,
        recv,
        route_handlers={"replay": lambda frame: False},
        storage=storage,
        registry=object(),
        trust="open",
        enable_ping=False,
    )

    result = next(frame for frame in sent if frame["type"] == "SESSION_SYNC_RESULT")
    assert result["request_id"] == "sync-1"
    assert result["sessions"][0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_unsigned_session_sync_is_rejected_on_a_legacy_socket(
    storage, monkeypatch
):
    from connectonion.network.host.ws_router import session as session_router

    messages = [
        {"type": "CONNECT", "from": OWNER},
        {"type": "SESSION_SYNC", "request_id": "sync-1"},
    ]
    sent = []

    async def fake_connect(data, send, conn, *args):
        conn.update(
            authenticated=True,
            agent_address=OWNER,
            signed_commands=False,
            recipient_address=None,
            session_sync=True,
            session_id="socket-session",
        )

    async def recv():
        return messages.pop(0) if messages else None

    async def send(message):
        sent.append(message)

    monkeypatch.setattr(session_router, "handle_connect", fake_connect)
    await session_router.run_ws_session(
        send,
        recv,
        route_handlers={"replay": lambda frame: False},
        storage=storage,
        registry=object(),
        trust="open",
        enable_ping=False,
    )

    assert sent[-1]["type"] == "ERROR"
    assert sent[-1]["code"] == "unauthorized"
    assert "signed command required" in sent[-1]["message"]

"""The one-use signature contract is shared by every ASGI worker."""

import multiprocessing
import os
import sqlite3
import time
from functools import partial
from queue import Empty
from unittest.mock import MagicMock

import pytest

from connectonion.network.host import auth
from connectonion.network.host.replay import (
    ReplayProtectionError,
    SignatureReplayStore,
)


@pytest.mark.asyncio
async def test_connect_claims_only_after_signature_verification():
    from connectonion.network.host.ws_router.connect import handle_connect

    frame = {
        "type": "CONNECT",
        "from": "caller",
        "signature": "invalid",
        "payload": {"to": "host", "timestamp": time.time()},
    }
    claimed = []
    sent = []

    async def send(message):
        sent.append(message)

    await handle_connect(
        frame, send, {"authenticated": False},
        {
            "agent_metadata": {"address": "host"},
            "replay": lambda value: claimed.append(value) or False,
        },
        MagicMock(), MagicMock(), "open", None, None,
    )

    assert claimed == []
    assert sent[-1]["message"] == "unauthorized: invalid signature"


@pytest.mark.asyncio
async def test_connect_uses_injected_guard_after_valid_signature(monkeypatch):
    from connectonion.network.host.ws_router.connect import handle_connect

    monkeypatch.setattr(auth, "verify_signature", lambda *_: True)
    frame = {
        "type": "CONNECT",
        "from": "caller",
        "signature": "valid",
        "payload": {"to": "host", "timestamp": time.time()},
    }
    claimed = []
    sent = []

    async def send(message):
        sent.append(message)

    await handle_connect(
        frame, send, {"authenticated": False},
        {
            "connect_auth": partial(
                auth.authenticate_connect,
                replay_check=lambda value: claimed.append(value) or True,
            ),
            "agent_metadata": {"address": "host"},
        },
        MagicMock(), MagicMock(), "open", None, None,
    )

    assert claimed == [frame]
    assert "already used" in sent[-1]["message"]


def test_connect_replay_is_rejected_before_trust_policy(monkeypatch):
    monkeypatch.setattr(auth, "verify_signature", lambda *_: True)
    trust = MagicMock(spec=auth.TrustAgent)
    frame = {
        "from": "caller",
        "signature": "captured",
        "payload": {"timestamp": time.time()},
    }

    _, _, valid, error = auth.authenticate_connect(
        frame, trust, replay_check=lambda _data: True
    )

    assert valid is True
    assert error == "unauthorized: this CONNECT was already used"
    trust.should_allow.assert_not_called()


def test_connect_orders_signature_then_claim_then_trust(monkeypatch):
    events = []
    monkeypatch.setattr(
        auth, "verify_signature", lambda *_: events.append("signature") or True
    )
    trust = auth.TrustAgent("open")
    original_should_allow = trust.should_allow

    def should_allow(*args, **kwargs):
        events.append("trust")
        return original_should_allow(*args, **kwargs)

    monkeypatch.setattr(trust, "should_allow", should_allow)
    frame = {
        "from": "caller",
        "signature": "fresh",
        "payload": {"timestamp": time.time()},
    }

    _, _, valid, error = auth.authenticate_connect(
        frame,
        trust,
        replay_check=lambda _data: events.append("claim") or False,
    )

    assert valid is True
    assert error is None
    assert events == ["signature", "claim", "trust"]


def _claim_signature(path, ready, start, results):
    store = SignatureReplayStore(path)
    ready.put(True)
    start.wait(10)
    results.put(store.already_used({"signature": "same-captured-signature"}))


def _migrate_store(path, ready, start, results):
    ready.put(True)
    start.wait(10)
    try:
        SignatureReplayStore(path)
        results.put(None)
    except Exception as exc:
        results.put(f"{type(exc).__name__}: {exc}")


def _hold_ledger_lock(path, ready, hold_seconds):
    with sqlite3.connect(path) as database:
        database.execute("BEGIN EXCLUSIVE")
        ready.put(True)
        time.sleep(hold_seconds)


def test_two_os_workers_cannot_claim_the_same_signature(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    results = context.Queue()
    start = context.Event()
    path = tmp_path / "replay.sqlite3"
    workers = [
        context.Process(target=_claim_signature, args=(path, ready, start, results))
        for _ in range(2)
    ]

    for worker in workers:
        worker.start()
    try:
        assert ready.get(timeout=10) is True
        assert ready.get(timeout=10) is True
        start.set()
        outcomes = sorted([results.get(timeout=10), results.get(timeout=10)])
        assert outcomes == [False, True]
    except Empty:
        pytest.fail("replay workers did not finish")
    finally:
        start.set()
        for worker in workers:
            worker.join(timeout=10)
            if worker.is_alive():
                worker.terminate()

    assert all(worker.exitcode == 0 for worker in workers)


def test_workers_serialize_old_schema_migration(tmp_path):
    path = tmp_path / "replay.sqlite3"
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE used_signatures ("
            "digest BLOB PRIMARY KEY, seen_at REAL NOT NULL"
            ") WITHOUT ROWID"
        )

    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    results = context.Queue()
    start = context.Event()
    workers = [
        context.Process(target=_migrate_store, args=(path, ready, start, results))
        for _ in range(8)
    ]
    for worker in workers:
        worker.start()
    try:
        for _ in workers:
            assert ready.get(timeout=15) is True
        start.set()
        assert [results.get(timeout=15) for _ in workers] == [None] * len(workers)
    except Empty:
        pytest.fail("schema migration workers did not finish")
    finally:
        start.set()
        for worker in workers:
            worker.join(timeout=10)
            if worker.is_alive():
                worker.terminate()

    assert all(worker.exitcode == 0 for worker in workers)


def test_store_keeps_only_a_digest_and_expires_old_entries(tmp_path):
    path = tmp_path / "replay.sqlite3"
    store = SignatureReplayStore(path, expiry_seconds=300)
    data = {
        "signature": "raw-secret-shaped-signature",
        "payload": {"timestamp": 1_000},
    }

    assert store.already_used(data, now=1_000) is False
    assert store.already_used(data, now=1_001) is True
    assert store.already_used(data, now=1_300) is True
    assert store.already_used(data, now=1_301) is False

    with sqlite3.connect(path) as database:
        rows = database.execute(
            "SELECT digest, seen_at, expires_at FROM used_signatures"
        ).fetchall()
    assert len(rows) == 1
    assert len(rows[0][0]) == 32
    assert b"raw-secret-shaped-signature" not in rows[0][0]
    assert rows[0][1] == 1_301
    assert rows[0][2] == 1_300
    if os.name != "nt":
        assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_future_dated_signature_is_kept_until_cryptographically_expired(tmp_path):
    store = SignatureReplayStore(tmp_path / "replay.sqlite3", expiry_seconds=300)
    data = {"signature": "future", "payload": {"timestamp": 1_300}}

    assert store.already_used(data, now=1_000) is False
    assert store.already_used(data, now=1_301) is True
    assert store.already_used(data, now=1_601) is False


def test_expiry_cleanup_is_indexed(tmp_path):
    path = tmp_path / "replay.sqlite3"
    SignatureReplayStore(path)

    with sqlite3.connect(path) as database:
        indexes = database.execute(
            "PRAGMA index_list(used_signatures)"
        ).fetchall()

    assert "used_signatures_expiry" in {row[1] for row in indexes}


def test_existing_seen_at_ledger_is_migrated_conservatively(tmp_path):
    path = tmp_path / "replay.sqlite3"
    digest = b"d" * 32
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE used_signatures ("
            "digest BLOB PRIMARY KEY, seen_at REAL NOT NULL"
            ") WITHOUT ROWID"
        )
        database.execute(
            "INSERT INTO used_signatures (digest, seen_at) VALUES (?, ?)",
            (digest, 1_000),
        )

    SignatureReplayStore(path, expiry_seconds=300)

    with sqlite3.connect(path) as database:
        expires_at = database.execute(
            "SELECT expires_at FROM used_signatures WHERE digest = ?", (digest,)
        ).fetchone()[0]
    assert expires_at == 1_600


@pytest.mark.parametrize("factory", ["sqlite", "memory"])
def test_equivalent_hex_spellings_cannot_bypass_replay_protection(
    tmp_path, factory
):
    lower = {"signature": "0x" + "ab" * 64}
    upper = {"signature": "0x" + "AB" * 64}
    if factory == "sqlite":
        already_used = SignatureReplayStore(
            tmp_path / "replay.sqlite3"
        ).already_used
    else:
        auth._seen_signatures.clear()
        already_used = auth.signature_already_used

    assert already_used(lower) is False
    assert already_used(upper) is True


def test_storage_failure_is_explicit_and_fails_closed(tmp_path, monkeypatch):
    store = SignatureReplayStore(tmp_path / "replay.sqlite3")

    def unavailable():
        raise sqlite3.OperationalError("disk unavailable")

    monkeypatch.setattr(store, "_connect", unavailable)
    with pytest.raises(ReplayProtectionError, match="storage is unavailable"):
        store.already_used({"signature": "captured"})


def test_locked_ledger_fails_closed(tmp_path):
    path = tmp_path / "replay.sqlite3"
    store = SignatureReplayStore(path)
    with sqlite3.connect(path) as blocker:
        blocker.execute("BEGIN EXCLUSIVE")
        with pytest.raises(ReplayProtectionError, match="storage is unavailable"):
            store.already_used({"signature": "captured"})


def test_claim_waits_for_a_short_lived_worker_lock(tmp_path):
    path = tmp_path / "replay.sqlite3"
    store = SignatureReplayStore(path)
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    blocker = context.Process(
        target=_hold_ledger_lock, args=(path, ready, 0.5)
    )

    blocker.start()
    try:
        assert ready.get(timeout=10) is True
        assert store.already_used({"signature": "captured"}) is False
    finally:
        blocker.join(timeout=10)
        if blocker.is_alive():
            blocker.terminate()

    assert blocker.exitcode == 0


def test_signed_command_translates_replay_storage_failure_to_misconfigured(
    monkeypatch,
):
    monkeypatch.setattr(auth, "verify_signature", lambda *_: True)
    data = {
        "type": "INPUT",
        "from": "caller",
        "signature": "signature",
        "payload": {
            "type": "INPUT",
            "nonce": "one-use",
            "timestamp": 1_000,
        },
    }
    monkeypatch.setattr(auth.time, "time", lambda: 1_000)

    def unavailable(_data):
        raise ReplayProtectionError("disk unavailable")

    payload, error = auth.authenticated_command_payload(
        data, "caller", replay_check=unavailable
    )

    assert payload is None
    assert error == "misconfigured: replay protection unavailable"


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_timestamps_are_rejected_before_replay_claim(
    monkeypatch, timestamp
):
    monkeypatch.setattr(auth, "verify_signature", lambda *_: True)
    claimed = []
    data = {
        "type": "INPUT",
        "from": "caller",
        "signature": "signature",
        "payload": {"type": "INPUT", "nonce": "one-use", "timestamp": timestamp},
    }

    payload, error = auth.authenticated_command_payload(
        data, "caller", replay_check=lambda value: claimed.append(value) or False
    )

    assert payload is None
    assert error == "unauthorized: timestamp must be finite"
    assert claimed == []

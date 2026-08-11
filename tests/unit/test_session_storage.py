"""Unit tests for connectonion/network/host/session/storage.py"""

import importlib
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from connectonion.network.host.session.storage import Session, SessionStorage


@pytest.fixture
def storage(tmp_path):
    return SessionStorage(path=str(tmp_path / "sessions.jsonl"))


def _make_session(sid="sess-1", status="completed", expires=None, result="ok", created=None):
    return Session(
        session_id=sid,
        status=status,
        prompt="hi",
        result=result,
        created=created if created is not None else time.time(),
        expires=expires,
    )


# ---------- save / get round trip ----------

def test_save_then_get_returns_same_session(storage):
    s = _make_session(sid="abc")
    storage.save(s)
    fetched = storage.get("abc")
    assert fetched.session_id == "abc"
    assert fetched.prompt == "hi"
    assert fetched.result == "ok"


def test_get_returns_none_for_unknown_session(storage):
    storage.save(_make_session(sid="exists"))
    assert storage.get("does-not-exist") is None


def test_get_returns_none_when_file_missing(tmp_path):
    storage = SessionStorage(path=str(tmp_path / "never_written.jsonl"))
    assert storage.get("anything") is None


# ---------- "last write wins" semantic ----------

def test_get_returns_latest_entry_for_session_id(storage):
    storage.save(_make_session(sid="x", result="first"))
    storage.save(_make_session(sid="x", result="second"))
    storage.save(_make_session(sid="x", result="third"))
    assert storage.get("x").result == "third"


# ---------- expiry semantics ----------

def test_get_returns_none_for_expired_completed_session(storage):
    past = time.time() - 100
    storage.save(_make_session(sid="old", status="completed", expires=past))
    assert storage.get("old") is None


def test_get_returns_running_session_even_if_expired(storage):
    """Running sessions don't expire — they're in-flight."""
    past = time.time() - 100
    storage.save(_make_session(sid="r", status="running", expires=past))
    assert storage.get("r") is not None


def test_get_returns_session_with_no_expires(storage):
    """expires=None means no TTL → always valid."""
    storage.save(_make_session(sid="forever", status="completed", expires=None))
    assert storage.get("forever") is not None


def test_get_returns_session_with_future_expiry(storage):
    future = time.time() + 3600
    storage.save(_make_session(sid="future", status="completed", expires=future))
    assert storage.get("future") is not None


# ---------- list ----------

def test_list_empty_when_no_file(tmp_path):
    storage = SessionStorage(path=str(tmp_path / "missing.jsonl"))
    assert storage.list() == []


def test_list_dedupes_by_session_id_keeping_latest(storage):
    storage.save(_make_session(sid="a", result="v1", created=1))
    storage.save(_make_session(sid="a", result="v2", created=2))
    storage.save(_make_session(sid="b", result="other", created=3))
    items = storage.list()
    by_id = {s.session_id: s for s in items}
    assert by_id["a"].result == "v2"
    assert len(items) == 2


def test_list_skips_expired_entries(storage):
    past = time.time() - 100
    storage.save(_make_session(sid="dead", status="completed", expires=past))
    storage.save(_make_session(sid="alive", status="completed", expires=None))
    ids = [s.session_id for s in storage.list()]
    assert ids == ["alive"]


def test_list_sorted_by_created_desc(storage):
    storage.save(_make_session(sid="old", created=100))
    storage.save(_make_session(sid="new", created=200))
    storage.save(_make_session(sid="mid", created=150))
    ids = [s.session_id for s in storage.list()]
    assert ids == ["new", "mid", "old"]


# ---------- checkpoint ----------

def test_checkpoint_writes_waiting_approval_record(storage):
    session_dict = {'session_id': 'ck-1', 'messages': ['hello'], 'iteration': 2}
    storage.checkpoint(session_dict)
    fetched = storage.get('ck-1')
    assert fetched is not None
    assert fetched.status == 'waiting_approval'
    assert fetched.session == session_dict


def test_checkpoint_sets_expiry_24h_in_future(storage):
    """Checkpoint should give plenty of time (86400s = 24h) for approval."""
    storage.checkpoint({'session_id': 'ck-2'})
    fetched = storage.get('ck-2')
    delta = fetched.expires - fetched.created
    assert 86399 <= delta <= 86401  # 24h ± 1s slack


def test_checkpoint_noop_when_session_lacks_id(storage):
    """No session_id → silent no-op (don't corrupt store)."""
    storage.checkpoint({'messages': ['hi']})  # no session_id key
    assert storage.list() == []


# ---------- atomic update ----------

def test_atomic_update_reads_latest_and_appends_replacement(storage):
    storage.save(_make_session(sid="mode", result="safe"))

    updated = storage.atomic_update(
        "mode",
        lambda current: current.model_copy(update={"result": "accept_edits"}),
    )

    assert updated.result == "accept_edits"
    assert storage.get("mode").result == "accept_edits"


def test_atomic_update_serializes_competing_writers(storage):
    storage.save(_make_session(sid="counter", result="0"))

    def increment(_):
        def replace(current):
            return current.model_copy(
                update={"result": str(int(current.result) + 1)}
            )

        storage.atomic_update("counter", replace)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(increment, range(40)))

    assert storage.get("counter").result == "40"


def test_atomic_update_failure_appends_nothing(storage):
    storage.save(_make_session(sid="unchanged", result="before"))

    def fail(_current):
        raise ValueError("policy rejected")

    with pytest.raises(ValueError, match="policy rejected"):
        storage.atomic_update("unchanged", fail)

    assert storage.get("unchanged").result == "before"


def test_save_and_atomic_update_fail_closed_when_lock_is_unavailable(
    storage, monkeypatch
):
    storage_module = importlib.import_module(
        "connectonion.network.host.session.storage"
    )

    monkeypatch.setattr(storage_module, "_exclusive", lambda *_a, **_k: None)

    with pytest.raises(TimeoutError, match="session storage lock"):
        storage.save(_make_session(sid="save"))
    with pytest.raises(TimeoutError, match="session storage lock"):
        storage.atomic_update("update", lambda _current: _make_session("update"))
    assert not storage.path.exists()

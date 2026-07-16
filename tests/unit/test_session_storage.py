"""Unit tests for connectonion/network/host/session/storage.py"""

import time

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


def test_get_expires_stale_running_session(storage):
    """A crashed process cannot leave a running record immortal."""
    past = time.time() - 100
    storage.save(_make_session(sid="r", status="running", expires=past))
    assert storage.get("r") is None


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

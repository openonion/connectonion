"""Looking up one session must not cost the whole log.

`.co/session_results.jsonl` is append-only and never shrinks — 17 MB and 222
sessions on an agent that had been up thirteen hours. `get()` runs on every
turn (input_handler) and inside every `checkpoint()`, so a full parse there is
a cost that grows every day the agent stays alive.
"""

import json
import time

import pytest

from connectonion.network.host.session import storage as storage_mod
from connectonion.network.host.session.storage import Session, SessionStorage


@pytest.fixture
def big_log(tmp_path):
    """60 sessions with a realistic payload — enough to prove a full scan, and
    small enough that pinning this behaviour does not cost CI two minutes."""
    st = SessionStorage(str(tmp_path / "s.jsonl"))
    payload = {"messages": [{"role": "user", "content": "x" * 200} for _ in range(10)]}
    for i in range(60):
        st.save(Session(session_id=f"s{i}", status="done", prompt=f"p{i}",
                        session=payload, created=time.time(),
                        expires=time.time() + 86400))
    return st


def count_parses(monkeypatch):
    """Count json.loads calls inside the storage module."""
    calls = {"n": 0}
    real = json.loads

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(storage_mod.json, "loads", counting)
    return calls


def test_get_stops_at_the_record_it_wants(big_log, monkeypatch):
    """The newest session is the last line. Finding it should read about one."""
    calls = count_parses(monkeypatch)

    assert big_log.get("s59").prompt == "p59"

    assert calls["n"] <= 5, f"parsed {calls['n']} records to find the last one"


def test_get_does_not_parse_everything_for_a_middle_record(big_log, monkeypatch):
    """Even a record halfway back should not cost the whole file."""
    calls = count_parses(monkeypatch)

    assert big_log.get("s30").prompt == "p30"

    assert calls["n"] < 60, f"parsed {calls['n']} of 60"


def test_a_missing_session_is_still_answered(big_log):
    assert big_log.get("nope") is None


def test_checkpoint_does_not_reparse_the_log(big_log, monkeypatch):
    calls = count_parses(monkeypatch)

    big_log.checkpoint({"session_id": "s59", "user_prompt": "pause", "messages": []})

    assert calls["n"] <= 5, f"checkpoint parsed {calls['n']} records"


def test_a_torn_line_near_the_end_is_still_survived(tmp_path):
    """The tolerance from #555 must survive the tail read."""
    path = tmp_path / "s.jsonl"
    good = json.dumps({"session_id": "a", "status": "done", "prompt": "kept",
                       "created": time.time(), "expires": time.time() + 86400})
    path.write_text(f"{good}\n{{torn\n", encoding="utf-8")

    assert SessionStorage(str(path)).get("a").prompt == "kept"

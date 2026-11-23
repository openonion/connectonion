"""WeChat says how much of itself REM can read (#3351, #3353).

A chat migrated from the phone after the last key capture lands in new databases with keys REM doesn't have.
They used to be skipped with a bare `continue`, and the owner, not REM, noticed only 25 people. Now every
skip is recorded with its reason and fix, the commands print it, and a later capture keeps the old keys.
"""
import json
import re
from pathlib import Path

import pytest

from connectonion.useful_tools import wechat
from tests.unit.test_wechat_read import KEY, _messages, _sqlcipher


def _storage(tmp_path, monkeypatch, keyed=1, unkeyed=2, wrong=0):
    """A db_storage with chat databases: `keyed` open with their saved key, `unkeyed` have none, `wrong` a stale one."""
    storage = tmp_path / "db_storage"
    (storage / "message").mkdir(parents=True)
    keys, n = {}, 0
    for _ in range(keyed + unkeyed + wrong):
        path = storage / "message" / f"message_{n}.db"
        salt = _sqlcipher(path, lambda c: _messages(c, "wxid_friend", [(1, 1, 1, 2, 100, "hi", 0)]))
        if n < keyed:
            keys[salt.hex()] = KEY
        elif n >= keyed + unkeyed:
            keys[salt.hex()] = "x'" + "99" * 32 + "'"
        n += 1
    key_map = tmp_path / "keys.json"
    key_map.write_text(json.dumps(keys))
    monkeypatch.setattr(wechat, "KEY_MAP", key_map)
    return storage


def test_coverage_counts_databases_a_key_opens_and_names_the_rest(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch, keyed=1, unkeyed=2, wrong=1)
    coverage = wechat.message_coverage(storage)
    assert (coverage["found"], coverage["read"], coverage["missing_keys"]) == (4, 1, 2)
    reasons = [s["reason"] for s in coverage["skipped"]]
    assert reasons.count(wechat.NO_KEY) == 2 and reasons.count(wechat.WRONG_KEY) == 1
    assert {s["fix"] for s in coverage["skipped"]} == {"co wechat key capture"}


def test_all_messages_records_every_database_it_could_not_read(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch, keyed=1, unkeyed=2)
    skipped = []
    rows = wechat.all_messages(storage, {}, skipped)
    assert [r["text"] for r in rows] == ["hi"]  # the keyed one is read
    assert sorted(s["item"] for s in skipped) == ["message_1.db", "message_2.db"]
    assert all(s["reason"] == wechat.NO_KEY for s in skipped)


def test_the_line_says_what_is_missing_and_how_to_fix_it(tmp_path, monkeypatch):
    coverage = wechat.message_coverage(_storage(tmp_path, monkeypatch, keyed=1, unkeyed=10))
    line = wechat.coverage_line(coverage)
    assert "消息库 11" in line and "有密钥 1" in line and "缺 10" in line and "co wechat key capture" in line
    assert "11" in wechat.coverage_line(coverage, "en") and "missing a key" in wechat.coverage_line(coverage, "en")
    full = wechat.coverage_line({**coverage, "text": {"friends": 1659, "with_chats": 1428, "missing": 231}})
    assert "好友 1,659" in full and "找到聊天 1,428" in full and "还缺 231" in full


def test_nothing_missing_means_no_fix(tmp_path, monkeypatch):
    coverage = wechat.message_coverage(_storage(tmp_path, monkeypatch, keyed=2, unkeyed=0))
    assert coverage["skipped"] == [] and "→" not in wechat.coverage_line(coverage)


def test_a_later_capture_keeps_the_keys_it_already_had():
    from connectonion.cli.commands.wechat_commands import merge_captured
    old_db, new_db = "aa" * 16, "bb" * 16
    keys = {old_db: "x'" + "11" * 32 + "'"}
    hmac_salt = bytes(b ^ 0x3A for b in bytes.fromhex(new_db)).hex()  # lldb sees the HMAC salt
    found = merge_captured(keys, [f"{hmac_salt} {'22' * 32}", "noise without a key"], {old_db, new_db})
    assert found == {new_db}
    assert keys[old_db] == "x'" + "11" * 32 + "'" and keys[new_db] == "x'" + "22" * 32 + "'"


# A database skipped for its key, recorded or not: the bare form is what hid ~370 MB of history (#3351).
SKIP = re.compile(r"(if not key:|except \(WrongKeyError[^\n]*:)\s*\n\s*(continue|return \[\]|return None|pass)\s*\n")


def test_the_chat_reader_never_drops_a_database_without_a_record():
    source = Path(wechat.__file__).read_text()
    body = source[source.index("def all_messages"):]
    body = body[:body.index("\ndef ", 1)] if "\ndef " in body[1:] else body
    assert not SKIP.search(body), "a database is skipped without being recorded (#3353)"


def test_an_unreadable_address_book_is_a_gap(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch, keyed=1, unkeyed=0)
    (storage / "contact").mkdir()
    _sqlcipher(storage / "contact" / "contact.db", lambda c: c.execute("CREATE TABLE contact (username TEXT)"))
    coverage = wechat.message_coverage(storage)
    assert any(s["item"] == "contact.db" and s["reason"] == wechat.NO_KEY for s in coverage["skipped"])

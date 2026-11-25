"""The WeChat SQLCipher-4 decryptor, validated against a committed sqlcipher-CLI fixture.

tests/fixtures/wechat/encrypted.db was produced by the independent `sqlcipher` CLI
with the throwaway key in key.txt. This is a real, non-circular oracle: a different
implementation encrypted it; ours decrypts it; plain sqlite3 reads it.
"""

from pathlib import Path

import pytest

from connectonion.useful_tools import wechat

FIX = Path(__file__).parent.parent / "fixtures" / "wechat"
KEY = (FIX / "key.txt").read_text().strip()
DB = FIX / "encrypted.db"


def test_decrypts_to_readable_sqlite():
    conn = wechat.open_readonly(wechat.decrypt_db(DB, KEY))
    rows = [tuple(r) for r in conn.execute("SELECT strTalker, content FROM Msg ORDER BY localId")]
    assert rows[0] == ("wxid_mum", "晚饭吃了吗")
    assert ("wxid_me", "在忙，等下回") in rows


def test_integrity_check_passes():
    conn = wechat.open_readonly(wechat.decrypt_db(DB, KEY))
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_tables_lists_user_tables_with_counts():
    conn = wechat.open_readonly(wechat.decrypt_db(DB, KEY))
    names = dict(wechat.tables(conn))
    assert names["Msg"] == 3
    assert "Name2Id" in names


def test_wrong_key_raises_fast():
    with pytest.raises(wechat.WrongKeyError):
        wechat.decrypt_db(DB, "x'" + "ff" * 32 + "'")


def test_key_bytes_accepts_both_forms():
    bare = "00" * 32
    assert wechat.key_bytes(bare) == wechat.key_bytes(f"x'{bare}'")
    assert len(wechat.key_bytes(bare)) == 32


def test_key_bytes_rejects_wrong_length():
    with pytest.raises(ValueError):
        wechat.key_bytes("00" * 16)

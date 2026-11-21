"""co wechat reads WeChat 4.1 for Mac: one key per database, WAL frames, chats and messages (#3261).

Fixtures are built here: a plain SQLite database encrypted page by page the way SQLCipher 4 does (the
committed sqlcipher-CLI oracle in test_wechat_decrypt.py covers the cipher itself), with invented chats.
"""
import hashlib
import hmac
import os
import sqlite3

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from connectonion.useful_tools import wechat

KEY = "x'" + "11" * 32 + "'"


def _encrypt_page(plain: bytes, number: int, key: bytes, salt: bytes) -> bytes:
    hmac_key = hashlib.pbkdf2_hmac("sha512", key, bytes(b ^ 0x3A for b in salt), 2, dklen=32)
    body = plain[16:wechat.PAGE - wechat.RESERVE] if number == 1 else plain[:wechat.PAGE - wechat.RESERVE]
    iv = os.urandom(16)
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    cipher = enc.update(body) + enc.finalize()
    mac = hmac.new(hmac_key, cipher + iv + number.to_bytes(4, "little"), hashlib.sha512).digest()
    return (salt if number == 1 else b"") + cipher + iv + mac


def _sqlcipher(path, build, wal=False, key=KEY, salt=None):
    """Write an encrypted copy of a database `build(conn)` makes, marked WAL when asked; returns the salt."""
    plain = path.with_suffix(".plain")
    # SQLCipher keeps 80 bytes at the end of every page for the IV and HMAC: an empty database is created,
    # its header told to reserve them (byte 20), and the tables built after, so no page uses that space.
    conn = sqlite3.connect(plain)
    conn.execute(f"PRAGMA page_size = {wechat.PAGE}")
    conn.execute("PRAGMA user_version = 1")  # writes page 1: the header and an empty schema b-tree
    conn.close()
    head = bytearray(plain.read_bytes())
    head[20] = wechat.RESERVE
    head[105:107] = (wechat.PAGE - wechat.RESERVE).to_bytes(2, "big")  # the empty b-tree's content start
    plain.write_bytes(bytes(head))
    conn = sqlite3.connect(plain)
    build(conn)
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    data = bytearray(plain.read_bytes())
    if wal:
        data[18] = data[19] = 2
    salt = salt or os.urandom(16)
    raw = wechat.key_bytes(key)
    pages = [bytes(data[i:i + wechat.PAGE]) for i in range(0, len(data), wechat.PAGE)]
    path.write_bytes(b"".join(_encrypt_page(p, n + 1, raw, salt) for n, p in enumerate(pages)))
    return salt


def _messages(conn, username, rows):
    conn.execute("CREATE TABLE Name2Id (user_name TEXT, is_session INTEGER)")
    conn.executemany("INSERT INTO Name2Id VALUES (?, 1)", [("wxid_me",), (username,)])
    table = wechat.message_table(username)
    conn.execute(f'CREATE TABLE "{table}" (local_id INTEGER, local_type INTEGER, sort_seq INTEGER, real_sender_id '
                 'INTEGER, create_time INTEGER, message_content, WCDB_CT_message_content INTEGER)')
    conn.executemany(f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
    conn.execute(f'CREATE INDEX "{table}_SENDERID" ON "{table}" (real_sender_id)')


def test_a_wal_marked_database_opens_in_memory(tmp_path):
    db = tmp_path / "session.db"
    _sqlcipher(db, lambda c: c.execute("CREATE TABLE SessionTable (username TEXT)"), wal=True)
    conn = wechat.open_readonly(wechat.decrypt_db(db, KEY))
    assert conn.execute("SELECT count(*) FROM SessionTable").fetchone()[0] == 0


def test_db_salt_finds_each_databases_own_key(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    salt_a = _sqlcipher(a, lambda c: c.execute("CREATE TABLE t (x)"), key="x'" + "22" * 32 + "'")
    salt_b = _sqlcipher(b, lambda c: c.execute("CREATE TABLE t (x)"), key="x'" + "33" * 32 + "'")
    assert wechat.db_salt(a) == salt_a.hex() and wechat.db_salt(b) == salt_b.hex()
    keys = {salt_a.hex(): "x'" + "22" * 32 + "'", salt_b.hex(): "x'" + "33" * 32 + "'"}
    for path in (a, b):
        wechat.open_readonly(wechat.decrypt_db(path, keys[wechat.db_salt(path)]))
    with pytest.raises(wechat.WrongKeyError):
        wechat.decrypt_db(b, keys[salt_a.hex()])


def test_sessions_messages_and_compressed_text(tmp_path):
    import zstandard
    names = {"wxid_mum": "妈妈", "123@chatroom": "Family"}
    contact = tmp_path / "contact.db"
    _sqlcipher(contact, lambda c: (c.execute("CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT)"),
                                   c.executemany("INSERT INTO contact VALUES (?, ?, ?)",
                                                 [("wxid_mum", "妈妈", "Mum"), ("123@chatroom", "", "Family")])))
    session = tmp_path / "session.db"
    _sqlcipher(session, lambda c: (
        c.execute("CREATE TABLE SessionTable (username TEXT, summary TEXT, last_timestamp INTEGER, unread_count INTEGER, "
                  "is_hidden INTEGER, sort_timestamp INTEGER)"),
        c.executemany("INSERT INTO SessionTable VALUES (?, ?, ?, ?, ?, ?)",
                      [("wxid_mum", "晚饭吃了吗", 200, 1, 0, 200), ("123@chatroom", "ok", 100, 0, 0, 100),
                       ("hidden", "x", 300, 0, 1, 300)])))
    message = tmp_path / "message_0.db"
    packed = zstandard.ZstdCompressor().compress("在忙，等下回".encode())
    _sqlcipher(message, lambda c: _messages(c, "wxid_mum", [(1, 1, 1, 2, 100, "晚饭吃了吗", 0),
                                                         (2, 1, 2, 1, 110, packed, 4), (3, 3, 3, 2, 120, b"", 0)]))
    known = wechat.names(wechat.open_readonly(wechat.decrypt_db(contact, KEY)))
    assert known == names | {"wxid_mum": "妈妈"}
    rows = wechat.sessions(wechat.open_readonly(wechat.decrypt_db(session, KEY)), known)
    assert [r["name"] for r in rows] == ["妈妈", "Family"]  # hidden left out, newest first
    msgs = wechat.messages(wechat.open_readonly(wechat.decrypt_db(message, KEY)), "wxid_mum", known)
    assert [m["text"] for m in msgs] == ["晚饭吃了吗", "在忙，等下回", "[图片]"]
    assert msgs[0]["sender"] == "妈妈"


def test_committed_wal_frames_bring_the_newest_rows(tmp_path):
    db = tmp_path / "message_0.db"
    salt = _sqlcipher(db, lambda c: c.execute("CREATE TABLE t (x)"), wal=True)
    # A newer page 1 in the -wal file: the same database with a row added, committed.
    newer = tmp_path / "newer.db"
    _sqlcipher(newer, lambda c: (c.execute("CREATE TABLE t (x)"), c.execute("INSERT INTO t VALUES (7)")), wal=True, salt=salt)
    page1 = newer.read_bytes()[:wechat.PAGE]
    pages = len(newer.read_bytes()) // wechat.PAGE
    header = b"\x37\x7f\x06\x82" + (3007000).to_bytes(4, "big") + wechat.PAGE.to_bytes(4, "big") + b"\x00" * 4 + b"SALTSALT" + b"\x00" * 8
    frames = b""
    for n in range(pages):
        frame_header = (n + 1).to_bytes(4, "big") + (pages if n == pages - 1 else 0).to_bytes(4, "big") + b"SALTSALT" + b"\x00" * 8
        frames += frame_header + newer.read_bytes()[n * wechat.PAGE:(n + 1) * wechat.PAGE]
    (tmp_path / "message_0.db-wal").write_bytes(header + frames)
    assert page1  # the frames carry the committed newer pages
    conn = wechat.open_readonly(wechat.decrypt_db(db, KEY))
    assert [tuple(r) for r in conn.execute("SELECT x FROM t")] == [(7,)]

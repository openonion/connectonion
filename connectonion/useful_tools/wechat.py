"""
Purpose: decrypt the owner's own WeChat for Mac SQLCipher databases locally, read-only (#3146)
LLM-Note:
  Dependencies: imports from [hashlib, hmac, sqlite3, pathlib, cryptography.hazmat] | imported by [cli/commands/wechat_commands.py] | no new package: `cryptography` is already a transitive dependency
  Data flow: decrypt_db(path, key_hex) -> plaintext SQLite bytes (SQLCipher 4 page format: 16-byte salt header, per-page AES-256-CBC + HMAC-SHA512) | open_readonly(bytes) -> in-memory sqlite3.Connection via deserialize (no plaintext on disk) | tables(conn) -> [(name, rows)]
  State/Effects: pure/read-only — decrypt_db reads one encrypted file and returns bytes; it never writes, and open_readonly keeps the plaintext in memory
  Integration: the SQLCipher-4-default profile (page 4096, kdf_iter 256000, HMAC-SHA512, PBKDF2-HMAC-SHA512) is what WeChat 4.x uses; the page engine is validated against an independent sqlcipher-CLI oracle (tests/fixtures/wechat/)
  Errors: WrongKeyError when a page HMAC does not verify (wrong key, or not a SQLCipher 4 DB) — raised on page 1 so a bad key fails fast
"""

import hashlib
import hmac as hmaclib
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# SQLCipher 4 defaults, which WeChat 4.x uses.
PAGE = 4096
IV_LEN = 16
HMAC_LEN = 64          # HMAC-SHA512 output
RESERVE = IV_LEN + HMAC_LEN  # per-page trailer: IV + HMAC
HMAC_SALT_MASK = 0x3A
SQLITE_HEADER = b"SQLite format 3\x00"


class WrongKeyError(ValueError):
    """The key did not decrypt the database (page HMAC mismatch)."""


def key_bytes(key_hex: str) -> bytes:
    """Parse a SQLCipher raw key, given as x'<64 hex>' or bare 64 hex chars, into 32 bytes."""
    text = key_hex.strip()
    if text.startswith("x'") and text.endswith("'"):
        text = text[2:-1]
    raw = bytes.fromhex(text)
    if len(raw) != 32:
        raise ValueError("WeChat key must be 32 bytes (64 hex characters)")
    return raw


def _decrypt_page(page: bytes, number: int, key: bytes, hmac_key: bytes) -> bytes:
    """One SQLCipher 4 page, numbered from 1, to its plaintext page (page 1 gets the SQLite header back)."""
    start = 16 if number == 1 else 0
    end = PAGE - RESERVE
    iv = page[end:end + IV_LEN]
    stored = page[end + IV_LEN:end + IV_LEN + HMAC_LEN]
    mac = hmaclib.new(hmac_key, page[start:end + IV_LEN] + number.to_bytes(4, "little"), hashlib.sha512).digest()
    if not hmaclib.compare_digest(mac, stored):
        raise WrongKeyError(f"wrong key, or not a SQLCipher 4 database (HMAC mismatch on page {number})")
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = decryptor.update(page[start:end]) + decryptor.finalize()
    # Keep the page size; the trailer bytes are reserved per the header.
    return (SQLITE_HEADER + plain if number == 1 else plain) + b"\x00" * RESERVE


def _wal_pages(path: Path) -> list[tuple[int, bytes]]:
    """The committed frames of a database's -wal file, as (page number, encrypted page), oldest first.

    WeChat 4.x keeps its databases in WAL mode, so the newest messages sit in `<db>-wal` until WeChat
    checkpoints. A frame counts when its salts match the WAL header's and a later frame commits it.
    """
    wal = Path(str(path) + "-wal")
    if not wal.is_file() or wal.stat().st_size < 32 + 24 + PAGE:
        return []
    data = wal.read_bytes()
    salts = data[16:24]
    frames, committed, offset = [], [], 32
    while offset + 24 + PAGE <= len(data):
        header = data[offset:offset + 24]
        if header[8:16] != salts:
            break
        frames.append((int.from_bytes(header[:4], "big"), data[offset + 24:offset + 24 + PAGE]))
        if int.from_bytes(header[4:8], "big"):  # a commit frame: everything up to here is in the database
            committed = list(frames)
        offset += 24 + PAGE
    return committed


def decrypt_db(path: Path, key_hex: str) -> bytes:
    """Decrypt a SQLCipher 4 database file, with its committed -wal frames applied, to plaintext SQLite bytes.

    Validated against an independent sqlcipher-CLI oracle. Raises WrongKeyError on the first page if the key
    is wrong or the file is not a SQLCipher 4 database. The result is marked as a rollback-journal database
    (header bytes 18-19), because an in-memory copy of a WAL database cannot be opened as one.
    """
    key = key_bytes(key_hex)
    data = Path(path).read_bytes()
    if len(data) < PAGE or len(data) % PAGE != 0:
        raise WrongKeyError(f"{path} is not a whole number of {PAGE}-byte pages")
    hmac_key = hashlib.pbkdf2_hmac("sha512", key, bytes(b ^ HMAC_SALT_MASK for b in data[:16]), 2, dklen=32)
    pages = [_decrypt_page(data[i * PAGE:(i + 1) * PAGE], i + 1, key, hmac_key) for i in range(len(data) // PAGE)]
    for number, page in _wal_pages(path):
        while len(pages) < number:
            pages.append(b"\x00" * PAGE)
        pages[number - 1] = _decrypt_page(page, number, key, hmac_key)
    out = bytearray(b"".join(pages))
    out[18] = out[19] = 1
    return bytes(out)


def db_salt(path: Path) -> str:
    """A database's salt (its first 16 bytes) as hex: each WeChat 4.1 database has its own key, found by salt."""
    with open(path, "rb") as handle:
        return handle.read(16).hex()


def open_readonly(db_bytes: bytes) -> sqlite3.Connection:
    """Open decrypted bytes as an in-memory, read-only SQLite connection (no plaintext on disk)."""
    conn = sqlite3.connect(":memory:")
    conn.deserialize(db_bytes)
    conn.row_factory = sqlite3.Row
    return conn


def tables(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """List user tables and their row counts, for schema discovery."""
    names = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    result = []
    for name in names:
        try:
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        except sqlite3.DatabaseError:
            count = -1
        result.append((name, count))
    return result


def message_dbs(db_storage: Path) -> list[Path]:
    """Every *.db file under a WeChat db_storage directory, sorted."""
    return sorted(Path(db_storage).rglob("*.db"))


# ---------- reading chats (WeChat 4.1 for Mac schema, seen 2026-11-21) ----------
# session/session.db SessionTable: one row per conversation. contact/contact.db contact: names.
# message/message_<n>.db holds one table per conversation, Msg_<md5(username)>.
KINDS = {1: "", 3: "[图片]", 34: "[语音]", 42: "[名片]", 43: "[视频]", 47: "[表情]", 48: "[位置]",
         49: "[链接或文件]", 50: "[通话]", 10000: "[系统消息]"}


def text_of(content, compressed) -> str:
    """A message's text: WeChat stores some bodies zstd-compressed (WCDB_CT_message_content = 4)."""
    if isinstance(content, bytes):
        if compressed == 4 or content[:4] == b"\x28\xb5\x2f\xfd":
            import zstandard
            content = zstandard.ZstdDecompressor().decompress(content, max_output_size=1 << 22)
        content = content.decode("utf-8", "replace")
    return content or ""


def names(contact_conn: sqlite3.Connection) -> dict[str, str]:
    """username -> the name the owner sees: their remark, else the nickname, else the username."""
    return {row["username"]: (row["remark"] or row["nick_name"] or row["username"])
            for row in contact_conn.execute("SELECT username, remark, nick_name FROM contact")}


def verified_accounts(contact_conn: sqlite3.Connection) -> set[str]:
    """Usernames WeChat marks as verified (verify_flag set): official accounts, brands, companies and services.

    On the owner's 4.1 contact table people carry verify_flag 0; a verified account carries a non-zero flag. A
    table without the column (another WeChat version) has no verified accounts to leave out, rather than no people.
    """
    columns = {row[1] for row in contact_conn.execute("PRAGMA table_info(contact)")}
    if "verify_flag" not in columns:
        return set()
    return {row["username"] for row in contact_conn.execute("SELECT username FROM contact WHERE verify_flag != 0")}


FTS_DB = "message_fts.db"
FTS_TABLES = 4   # message_fts_v4_0 .. _3


def fts_messages(db_storage: Path, known: dict) -> list[dict]:
    """Every message in WeChat's full-text index, as all_messages' rows. Read-only, in memory.

    `message/message_fts.db` opens with the keys already captured and holds the text of chats whose own
    message_N.db has no key, such as history migrated from the phone (#3347: on the owner's machine 597,618
    messages, 1,428 of 1,659 friends, against 24 from the one keyed message_0.db). Its rows are read from the
    FTS5 content tables (c0..c6 = acontent, message_local_id, sort_seq, local_type, session_id, sender_id,
    create_time), which need no tokenizer; ids resolve through this database's own name2id. [] without a key.
    """
    from datetime import datetime, timezone
    path = Path(db_storage) / "message" / FTS_DB
    key = key_for(path) if path.is_file() else None
    if not key:
        return []
    try:
        conn = open_readonly(decrypt_db(path, key))
    except (WrongKeyError, sqlite3.DatabaseError):
        return []
    name = {r[0]: r[1] for r in conn.execute("SELECT rowid, username FROM name2id")}
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    rows = []
    for i in range(FTS_TABLES):
        table = f"message_fts_v4_{i}_content"
        if table not in tables:
            continue
        for content, local_id, _seq, local_type, session, sender_id, created in conn.execute(
                f'SELECT c0, c1, c2, c3, c4, c5, c6 FROM "{table}"'):
            chat = name.get(session)
            if not chat:
                continue
            kind = int(local_type or 0) & 0xFFFF
            text = str(content or "") if kind in (1, 10000) else KINDS.get(kind, "[其他]")
            sender = name.get(sender_id, "")
            if chat.endswith("@chatroom") and ":\n" in text[:80]:
                sender, text = text.split(":\n", 1)
            rows.append({"id": str(local_id), "chat": chat, "chat_name": known.get(chat, chat),
                         "at": datetime.fromtimestamp(int(created or 0), timezone.utc).isoformat(),
                         "text": text.strip(), "sender": sender, "sender_name": known.get(sender, sender),
                         "kind": "text" if kind == 1 else "system" if kind == 10000 else "media"})
    return rows


def every_message(db_storage: Path, known: dict) -> list[dict]:
    """The keyed message_N.db rows (full rows, media types), then the full-text index for the rest.

    One message is one row: an FTS row is dropped when a message database already gave that chat's local id.
    """
    rows = all_messages(db_storage, known)
    seen = {(row["chat"], row.get("id")) for row in rows}
    rows += [row for row in fts_messages(db_storage, known) if (row["chat"], row.get("id")) not in seen]
    return rows


def friends(contact_conn: sqlite3.Connection) -> list[dict]:
    """The owner's address book: contacts with local_type 1, as {username, remark, nick_name}.

    WeChat 4.1 for Mac keeps everyone it has ever seen in `contact`; local_type 1 is a friend the owner added,
    3 is someone only met in a group (#3347). Groups and official accounts are the caller's to leave out. A table
    without the column (another WeChat version) has no address book to offer, rather than everyone as a friend.
    """
    columns = {row[1] for row in contact_conn.execute("PRAGMA table_info(contact)")}
    if "local_type" not in columns:
        return []
    return [{"username": row["username"], "remark": row["remark"] or "", "nick_name": row["nick_name"] or ""}
            for row in contact_conn.execute("SELECT username, remark, nick_name FROM contact WHERE local_type = 1")]


def sessions(session_conn: sqlite3.Connection, known: dict[str, str], limit: int = 30) -> list[dict]:
    """Recent conversations, newest first: who, the last message's summary, its time and the unread count."""
    rows = session_conn.execute(
        "SELECT username, summary, last_timestamp, unread_count FROM SessionTable "
        "WHERE is_hidden = 0 ORDER BY sort_timestamp DESC LIMIT ?", (limit,))
    return [{"username": r["username"], "name": known.get(r["username"], r["username"]),
             "summary": text_of(r["summary"], 0), "time": r["last_timestamp"], "unread": r["unread_count"]}
            for r in rows]


def message_table(username: str) -> str:
    # WeChat's own naming, not a secret: each chat's table is Msg_<md5 of the username>.
    return "Msg_" + hashlib.md5(username.encode(), usedforsecurity=False).hexdigest()


def messages(conn: sqlite3.Connection, username: str, known: dict[str, str], limit: int = 30) -> list[dict]:
    """A conversation's last messages, oldest first. Group messages carry the sender as "wxid:\\n" before the text."""
    table = message_table(username)
    sender_of = {r[0]: r[1] for r in conn.execute("SELECT rowid, user_name FROM Name2Id")}
    rows = conn.execute(
        f'SELECT local_type, create_time, real_sender_id, message_content, WCDB_CT_message_content '
        f'FROM "{table}" ORDER BY sort_seq DESC LIMIT ?', (limit,)).fetchall()
    out = []
    for r in reversed(rows):
        kind = r["local_type"] & 0xFFFF
        text = text_of(r["message_content"], r["WCDB_CT_message_content"]) if kind in (1, 10000) else KINDS.get(kind, "[其他]")
        sender = sender_of.get(r["real_sender_id"], "")
        if username.endswith("@chatroom") and ":\n" in text[:80]:
            sender, text = text.split(":\n", 1)
        out.append({"time": r["create_time"], "sender": known.get(sender, sender), "text": text.strip()})
    return out


# ---------- reading straight from WeChat for Mac, for co rem (no intermediate files) ----------
import json as _json
import re as _re

WECHAT_CONTAINER = Path.home() / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
KEY_MAP = Path.home() / ".co" / "wechat" / "keys.json"


def db_storage_in_use() -> Path | None:
    """The db_storage of the account WeChat wrote last, or None when WeChat's data isn't here/readable."""
    try:
        accounts = [a for a in WECHAT_CONTAINER.iterdir() if (a / "db_storage").is_dir()]
    except OSError:
        return None
    if not accounts:
        return None
    latest = lambda a: max((p.stat().st_mtime for p in (a / "db_storage" / "session").glob("session.db*")), default=0)
    return max(accounts, key=latest) / "db_storage"


def owner_username(db_storage: Path) -> str:
    """The account's own WeChat id; its folder is the id plus a short suffix (wxid_xxx_ab12)."""
    name = db_storage.parent.name
    return name.rsplit("_", 1)[0] if name.startswith("wxid_") and name.count("_") >= 2 else name


def key_for(path: Path) -> str | None:
    """The saved key for one database, by its salt (co wechat key capture writes the map)."""
    try:
        keys = _json.loads(KEY_MAP.read_text())
    except (OSError, ValueError):
        return None
    return keys.get(db_salt(path))


def all_messages(db_storage: Path, known: dict) -> list[dict]:
    """Every message in every readable chat database, as plain rows. Read-only, in memory.

    A row: {id, chat, chat_name, at (ISO), text, sender, sender_name, kind}. The caller decides which
    chats to keep and which side is the owner's.
    """
    import sqlite3
    from datetime import datetime, timezone
    rows = []
    for path in sorted((db_storage / "message").glob("*message_[0-9]*.db")):
        key = key_for(path)
        if not key:
            continue
        try:
            conn = open_readonly(decrypt_db(path, key))
        except (WrongKeyError, sqlite3.DatabaseError):
            continue
        sender_of = {r[0]: r[1] for r in conn.execute("SELECT rowid, user_name FROM Name2Id")}
        by_table = {message_table(u): u for u in sender_of.values()}
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            chat = by_table.get(table) if _re.fullmatch(r"Msg_[0-9a-f]{32}", table) else None
            if not chat:
                continue
            for r in conn.execute(f'SELECT local_id, local_type, create_time, real_sender_id, message_content, '
                                  f'WCDB_CT_message_content FROM "{table}" ORDER BY sort_seq'):
                kind = r[1] & 0xFFFF
                text = text_of(r[4], r[5]) if kind in (1, 10000) else KINDS.get(kind, "[其他]")
                sender = sender_of.get(r[3], "")
                if chat.endswith("@chatroom") and ":\n" in text[:80]:
                    sender, text = text.split(":\n", 1)
                rows.append({"id": str(r[0]), "chat": chat, "chat_name": known.get(chat, chat),
                             "at": datetime.fromtimestamp(r[2], timezone.utc).isoformat(),
                             "text": text.strip(), "sender": sender, "sender_name": known.get(sender, sender),
                             "kind": "text" if kind == 1 else "system" if kind == 10000 else "media"})
    return rows

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


def decrypt_db(path: Path, key_hex: str) -> bytes:
    """Decrypt a SQLCipher 4 database file to plaintext SQLite bytes, using a raw key.

    Validated against an independent sqlcipher-CLI oracle. Raises WrongKeyError on the
    first page if the key is wrong or the file is not a SQLCipher 4 database.
    """
    key = key_bytes(key_hex)
    data = Path(path).read_bytes()
    if len(data) < PAGE or len(data) % PAGE != 0:
        raise WrongKeyError(f"{path} is not a whole number of {PAGE}-byte pages")

    salt = data[:16]
    hmac_salt = bytes(b ^ HMAC_SALT_MASK for b in salt)
    hmac_key = hashlib.pbkdf2_hmac("sha512", key, hmac_salt, 2, dklen=32)

    out = bytearray()
    for index in range(len(data) // PAGE):
        page = data[index * PAGE:(index + 1) * PAGE]
        start = 16 if index == 0 else 0
        end = PAGE - RESERVE
        iv = page[end:end + IV_LEN]
        stored = page[end + IV_LEN:end + IV_LEN + HMAC_LEN]
        mac = hmaclib.new(
            hmac_key,
            page[start:end + IV_LEN] + (index + 1).to_bytes(4, "little"),
            hashlib.sha512,
        ).digest()
        if not hmaclib.compare_digest(mac, stored):
            raise WrongKeyError(
                f"wrong key, or not a SQLCipher 4 database (HMAC mismatch on page {index + 1})"
            )
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        plain = decryptor.update(page[start:end]) + decryptor.finalize()
        out += (SQLITE_HEADER + plain) if index == 0 else plain
        out += b"\x00" * RESERVE  # keep page size; these bytes are reserved per the header
    return bytes(out)


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

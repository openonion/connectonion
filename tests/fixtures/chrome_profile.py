"""A fake Google Chrome profile on disk, encrypted the way Chrome on macOS encrypts it.

Built with a known Keychain password so tests can decrypt without a real
Chrome, a real Keychain or the network. The schema is Chrome's own `cookies`
and `meta` tables (the columns Chrome 130+ writes), so a query that works here
works on a real profile.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PASSWORD = b"fake-chrome-safe-storage"
WINDOWS_EPOCH_OFFSET = 11644473600

SCHEMA = """
CREATE TABLE meta(key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR);
CREATE TABLE cookies(creation_utc INTEGER NOT NULL, host_key TEXT NOT NULL,
  top_frame_site_key TEXT NOT NULL, name TEXT NOT NULL, value TEXT NOT NULL,
  encrypted_value BLOB NOT NULL, path TEXT NOT NULL, expires_utc INTEGER NOT NULL,
  is_secure INTEGER NOT NULL, is_httponly INTEGER NOT NULL, last_access_utc INTEGER NOT NULL,
  has_expires INTEGER NOT NULL, is_persistent INTEGER NOT NULL, priority INTEGER NOT NULL,
  samesite INTEGER NOT NULL, source_scheme INTEGER NOT NULL, source_port INTEGER NOT NULL,
  last_update_utc INTEGER NOT NULL, source_type INTEGER NOT NULL,
  has_cross_site_ancestor INTEGER NOT NULL);
"""


def chrome_time(unix_seconds: float) -> int:
    return int((unix_seconds + WINDOWS_EPOCH_OFFSET) * 1_000_000)


def encrypt(value: str, host_key: str, meta_version: int, password: bytes = PASSWORD) -> bytes:
    key = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1003).derive(password)
    plain = value.encode()
    if meta_version >= 24:
        plain = hashlib.sha256(host_key.encode()).digest() + plain
    pad = 16 - len(plain) % 16
    plain += bytes([pad]) * pad
    encryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).encryptor()
    return b"v10" + encryptor.update(plain) + encryptor.finalize()


def cookie(host_key, name, value, *, path="/", expires=None, secure=True, httponly=True,
           samesite=-1, partition=""):
    """One row's worth; expires is Unix seconds, or None for a session cookie."""
    return dict(host_key=host_key, name=name, value=value, path=path, expires=expires,
                secure=secure, httponly=httponly, samesite=samesite, partition=partition)


def make_profile(root: Path, folder: str, cookies, *, meta_version=24, shown_name=None,
                 network_dir=True) -> Path:
    """Write <root>/<folder>/[Network/]Cookies and a Local State naming it."""
    profile = root / folder
    db_dir = profile / "Network" if network_dir else profile
    db_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_dir / "Cookies"))
    connection.executescript(SCHEMA)
    connection.execute("INSERT INTO meta VALUES ('version', ?)", (str(meta_version),))
    for c in cookies:
        persistent = c["expires"] is not None
        connection.execute(
            "INSERT INTO cookies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (0, c["host_key"], c["partition"], c["name"], "",
             encrypt(c["value"], c["host_key"], meta_version), c["path"],
             chrome_time(c["expires"]) if persistent else 0, int(c["secure"]), int(c["httponly"]),
             0, int(persistent), int(persistent), 1, c["samesite"], 2, 443, 0, 0, 0))
    connection.commit()
    connection.close()
    state_file = root / "Local State"
    state = json.loads(state_file.read_text()) if state_file.exists() else {"profile": {"info_cache": {}}}
    state["profile"]["info_cache"][folder] = {"name": shown_name or folder}
    state_file.write_text(json.dumps(state))
    return profile

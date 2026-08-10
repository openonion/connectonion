"""
Purpose: Cross-process one-use signature storage for hosted-agent authentication
State/Effects: stores only signature digests and timestamps in .co/replay.sqlite3
Integration: SignatureReplayStore.already_used is injected into every hosted route
Errors: raises ReplayProtectionError so callers can fail closed with a safe message
"""

import hashlib
import math
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path


SIGNATURE_EXPIRY_SECONDS = 300
# A healthy transaction is tiny, but another OS worker can be descheduled while
# holding the write lock. Stay bounded and fail closed after ordinary runner
# scheduling jitter has had time to clear (#804).
SQLITE_BUSY_TIMEOUT_SECONDS = 2.0


class ReplayProtectionError(RuntimeError):
    """The host cannot safely decide whether a signature was already used."""


def signature_digest(signature) -> bytes:
    """Hash canonical signature bytes so equivalent hex spellings collide."""
    text = str(signature)
    encoded = text[2:] if text.startswith("0x") else text
    try:
        canonical = b"hex:" + bytes.fromhex(encoded)
    except ValueError:
        canonical = b"raw:" + text.encode()
    return hashlib.sha256(canonical).digest()


class SignatureReplayStore:
    """Atomically claim signature digests across threads and OS workers."""

    def __init__(self, path: str | Path, expiry_seconds=SIGNATURE_EXPIRY_SECONDS):
        self.path = Path(path).resolve()
        self.expiry_seconds = expiry_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(descriptor)
            if os.name != "nt":
                os.chmod(self.path, 0o600)
            with closing(self._connect()) as database:
                with database:
                    # Serialize schema inspection and migration across workers.
                    database.execute("BEGIN IMMEDIATE")
                    database.execute(
                        "CREATE TABLE IF NOT EXISTS used_signatures ("
                        "digest BLOB PRIMARY KEY, seen_at REAL NOT NULL"
                        ", expires_at REAL"
                        ") WITHOUT ROWID"
                    )
                    columns = {
                        row[1] for row in database.execute(
                            "PRAGMA table_info(used_signatures)"
                        )
                    }
                    if "expires_at" not in columns:
                        database.execute(
                            "ALTER TABLE used_signatures "
                            "ADD COLUMN expires_at REAL"
                        )
                    # A pre-fix row may have represented a future-dated
                    # signature. Retain it for the maximum validity window.
                    database.execute(
                        "UPDATE used_signatures SET expires_at = seen_at + ? "
                        "WHERE expires_at IS NULL",
                        (2 * self.expiry_seconds,),
                    )
                    database.execute(
                        "CREATE INDEX IF NOT EXISTS used_signatures_expiry "
                        "ON used_signatures(expires_at)"
                    )
        except (OSError, sqlite3.Error) as exc:
            raise ReplayProtectionError(
                f"replay protection storage is unavailable: {self.path}"
            ) from exc

    def _connect(self):
        database = sqlite3.connect(self.path, timeout=SQLITE_BUSY_TIMEOUT_SECONDS)
        database.execute(
            f"PRAGMA busy_timeout = {int(SQLITE_BUSY_TIMEOUT_SECONDS * 1000)}"
        )
        return database

    def _expires_at(self, data: dict, seen_at: float) -> float:
        """Return the point after which a verified signature cannot be valid."""
        timestamp = (data.get("payload") or {}).get("timestamp")
        if (isinstance(timestamp, (int, float))
                and not isinstance(timestamp, bool)
                and math.isfinite(timestamp)):
            return timestamp + self.expiry_seconds
        return seen_at + (2 * self.expiry_seconds)

    def already_used(self, data: dict, *, now=None) -> bool:
        """Atomically record one signature, returning whether it existed."""
        signature = data.get("signature")
        if not signature:
            return False

        seen_at = time.time() if now is None else now
        expires_at = self._expires_at(data, seen_at)
        digest = signature_digest(signature)
        try:
            with closing(self._connect()) as database:
                with database:
                    database.execute(
                        "DELETE FROM used_signatures WHERE expires_at < ?",
                        (seen_at,),
                    )
                    inserted = database.execute(
                        "INSERT OR IGNORE INTO used_signatures "
                        "(digest, seen_at, expires_at) VALUES (?, ?, ?)",
                        (digest, seen_at, expires_at),
                    ).rowcount
            return inserted == 0
        except (OSError, sqlite3.Error) as exc:
            raise ReplayProtectionError(
                f"replay protection storage is unavailable: {self.path}"
            ) from exc

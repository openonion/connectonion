"""
Purpose: Cross-process one-use signature storage for hosted-agent authentication
State/Effects: stores only signature digests and timestamps in .co/replay.sqlite3
Integration: SignatureReplayStore.already_used is injected into every hosted route
Errors: raises ReplayProtectionError so callers can fail closed with a safe message
"""

import hashlib
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path


SIGNATURE_EXPIRY_SECONDS = 300


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
                database.execute(
                    "CREATE TABLE IF NOT EXISTS used_signatures ("
                    "digest BLOB PRIMARY KEY, seen_at REAL NOT NULL"
                    ") WITHOUT ROWID"
                )
        except (OSError, sqlite3.Error) as exc:
            raise ReplayProtectionError(
                f"replay protection storage is unavailable: {self.path}"
            ) from exc

    def _connect(self):
        database = sqlite3.connect(self.path, timeout=5)
        database.execute("PRAGMA busy_timeout = 5000")
        return database

    def already_used(self, data: dict, *, now=None) -> bool:
        """Atomically record one signature, returning whether it existed."""
        signature = data.get("signature")
        if not signature:
            return False

        seen_at = time.time() if now is None else now
        digest = signature_digest(signature)
        try:
            with closing(self._connect()) as database:
                with database:
                    database.execute(
                        "DELETE FROM used_signatures WHERE seen_at < ?",
                        (seen_at - self.expiry_seconds,),
                    )
                    inserted = database.execute(
                        "INSERT OR IGNORE INTO used_signatures (digest, seen_at) "
                        "VALUES (?, ?)",
                        (digest, seen_at),
                    ).rowcount
            return inserted == 0
        except (OSError, sqlite3.Error) as exc:
            raise ReplayProtectionError(
                f"replay protection storage is unavailable: {self.path}"
            ) from exc

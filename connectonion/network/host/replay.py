"""
Purpose: One-use signature storage for hosted-agent authentication on unsealed sockets
State/Effects: MemoryReplayStore keeps digests in the process; SignatureReplayStore
  keeps them in .co/replay.sqlite3 for deployments that fork workers
Integration: a store's already_used is injected into every hosted route; a sealed
  socket (network/sealed.py) never consults it — see auth.sealed_channel_replay_check
Errors: raises ReplayProtectionError so callers can fail closed with a safe message

Which store a host gets: `host()` runs exactly one uvicorn worker (it hands
uvicorn an app object, which cannot fork), so its ledger is a dict. The SQLite
file exists for `create_app()` served with `uvicorn --workers N` (#804). It used
to be the ledger for every host, and a deploy that deleted it took the
Melbourne rental host offline for 2h44m on 2026-09-03: the schema was created
once at startup, so a fresh empty file meant "no such table" on every claim and
the host refused everything until someone restarted it (#1403).
"""

import hashlib
import math
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Dict

from rich.console import Console

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


def _expires_at(data: dict, seen_at: float, expiry_seconds: float) -> float:
    """Return the point after which a verified signature cannot be valid."""
    timestamp = (data.get("payload") or {}).get("timestamp")
    if (isinstance(timestamp, (int, float))
            and not isinstance(timestamp, bool)
            and math.isfinite(timestamp)):
        return timestamp + expiry_seconds
    return seen_at + (2 * expiry_seconds)


class MemoryReplayStore:
    """One-use signature digests for a single-process host.

    Same claim semantics as the SQLite store — digest of the canonical
    signature bytes, kept until the signature is cryptographically expired —
    with nothing on disk. Restarting the process forgets the ledger, which
    admits at most one reuse of a signature still inside its five-minute
    window; a process that just restarted has no sealed sessions to protect
    either, and an unsealed 1.7 client is the only caller this ledger serves.
    """

    def __init__(self, expiry_seconds=SIGNATURE_EXPIRY_SECONDS):
        self.expiry_seconds = expiry_seconds
        self._seen: Dict[bytes, float] = {}

    def already_used(self, data: dict, *, now=None) -> bool:
        signature = data.get("signature")
        if not signature:
            return False
        seen_at = time.time() if now is None else now
        for digest in [d for d, expiry in self._seen.items() if expiry < seen_at]:
            del self._seen[digest]
        digest = signature_digest(signature)
        if digest in self._seen:
            return True
        self._seen[digest] = _expires_at(data, seen_at, self.expiry_seconds)
        return False


class SignatureReplayStore:
    """Atomically claim signature digests across threads and OS workers."""

    def __init__(self, path: str | Path, expiry_seconds=SIGNATURE_EXPIRY_SECONDS):
        self.path = Path(path).resolve()
        self.expiry_seconds = expiry_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._ensure_schema()
        except (OSError, sqlite3.Error) as exc:
            raise self._unavailable(exc) from exc

    def _unavailable(self, exc) -> ReplayProtectionError:
        # The client only ever sees "misconfigured: replay protection
        # unavailable". The operator reading the journal needs the SQLite
        # message — "no such table", "readonly database", "disk I/O error" —
        # or the next outage is another afternoon of guessing.
        Console().print(
            f"[red]\\[replay][/red] {type(exc).__name__}: {exc} ({self.path})"
        )
        return ReplayProtectionError(
            f"replay protection storage is unavailable: {self.path}"
        )

    def _ensure_schema(self):
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

    def _connect(self):
        database = sqlite3.connect(self.path, timeout=SQLITE_BUSY_TIMEOUT_SECONDS)
        database.execute(
            f"PRAGMA busy_timeout = {int(SQLITE_BUSY_TIMEOUT_SECONDS * 1000)}"
        )
        return database

    def _expires_at(self, data: dict, seen_at: float) -> float:
        return _expires_at(data, seen_at, self.expiry_seconds)

    def _claim(self, digest: bytes, seen_at: float, expires_at: float) -> bool:
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

    def already_used(self, data: dict, *, now=None) -> bool:
        """Atomically record one signature, returning whether it existed."""
        signature = data.get("signature")
        if not signature:
            return False

        seen_at = time.time() if now is None else now
        expires_at = self._expires_at(data, seen_at)
        digest = signature_digest(signature)
        try:
            return self._claim(digest, seen_at, expires_at)
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise self._unavailable(exc) from exc
            # The file was removed under a running host and sqlite3.connect
            # quietly made a new, empty one. Whoever could delete it already
            # had host access; refusing every caller until a restart protects
            # nobody. Put the schema back and claim once more.
            try:
                self._ensure_schema()
                return self._claim(digest, seen_at, expires_at)
            except (OSError, sqlite3.Error) as again:
                raise self._unavailable(again) from again
        except (OSError, sqlite3.Error) as exc:
            raise self._unavailable(exc) from exc

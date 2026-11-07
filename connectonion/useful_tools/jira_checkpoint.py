"""
Purpose: Jira checkpoint, scope lock, and transaction state for co rem incremental import (F13FCAKE-19, F13FCAKE-1).
LLM-Note:
  Dependencies: imports from [dataclasses, hashlib, json, os, pathlib, contextlib, tempfile] | imported by [cli/commands/jira_commands.py] | tested by [tests/unit/test_jira_checkpoint.py]
  Data flow: scope_hash() → lock file path; load() reads checkpoint JSON; save() writes atomically; matches() validates identity before every run
  State/Effects: _scope_lock() creates and holds an OS file lock; save() writes to .state/checkpoints/<hash>.json atomically via tempfile + os.replace()
  Errors: load() returns None for a missing file (first import); raises ValueError with recovery guidance for corrupted, incomplete, or structurally invalid checkpoints; matches() raises ValueError on any identity mismatch; _scope_lock() raises ValueError immediately on contention (non-blocking, no retry)
  Security: checkpoint JSON never contains tokens, email addresses, refresh tokens, or raw provider responses; only accountId (not email) is stored in authorised_identity

Jira incremental import checkpoint and scope lock for co rem (AG-1 through AG-5).

This module never imports from jira.py or adapter.py — it holds only persistence and locking,
keeping all Jira transaction semantics isolated here (sprint2.md Step 2 module boundary).
"""

import datetime
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path

_CHECKPOINT_VERSION = 1

def _recovery_guidance() -> str:
    from ..environment import selected_command

    return (
        "Recovery: preserve the existing checkpoint for inspection. "
        "Use a separate --state directory for a fresh read; "
        "a different account or scope may also require a separate --output directory. "
        f"See {selected_command('co jira sync-inc --help')}."
    )

# Field names that must never appear in a checkpoint file.
_FORBIDDEN_FIELDS = frozenset({
    "token", "api_token", "password", "secret",
    "refresh_token", "access_token", "email", "emailAddress",
})


def _scope_hash(source: str, account: str, account_id: str, canonical_scope: dict) -> str:
    """Return the first 16 hex characters of SHA-256(source|account|accountId|scope_json).

    The canonical_scope is serialised with sort_keys=True so that equivalent scope
    dicts with different key orderings produce the same hash.
    """
    payload = (
        source + "|"
        + account + "|"
        + account_id + "|"
        + json.dumps(canonical_scope, sort_keys=True, separators=(",", ":"))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _reject_credential_fields(data: dict, path: Path, _depth: int = 0) -> None:
    """Recursively raise ValueError if any dict in the checkpoint contains credential-like fields.

    Walks every nested dict (raises ValueError beyond depth 8) so that a credential
    buried inside canonical_scope, overlap_snapshot_hashes, or any future sub-object
    is caught. Fails closed: excessive depth is treated as a corrupt checkpoint.
    """
    if not isinstance(data, dict):
        return
    if _depth > 8:
        raise ValueError(
            f"Checkpoint file {path} has excessive nesting depth (> 8 levels). "
            + _recovery_guidance()
        )
    for key, value in data.items():
        if key in _FORBIDDEN_FIELDS:
            raise ValueError(
                f"Checkpoint file {path} contains a forbidden field {key!r} "
                "that must never be stored in a checkpoint. " + _recovery_guidance()
            )
        if isinstance(value, dict):
            _reject_credential_fields(value, path, _depth + 1)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _reject_credential_fields(item, path, _depth + 1)


@dataclass
class JiraCheckpoint:
    """Serialised checkpoint for one (source, account, identity, scope) combination.

    Fields
    ------
    version              : always _CHECKPOINT_VERSION (1).
    source               : always "jira".
    account              : the Jira site URL, e.g. "https://example.atlassian.net".
    authorised_identity  : {"accountId": "<id>"} — accountId only, never email or token.
    canonical_scope      : {"type": "project", "project": "ALPHA"} or
                           {"type": "project+keys", "project": "ALPHA", "keys": [...]}
    cursor               : ISO 8601 datetime of the latest processed updated value, or None
                           (None means this scope has never been imported; full fetch required).
    last_key             : Jira issue key of the last item at cursor time — diagnostic only.
                           Never used to filter Jira results (AG-3).
    commit_time          : ISO 8601 datetime when this checkpoint was last durably written.
    overlap_snapshot_hashes : {content_hash_hex: updated_iso} for every snapshot persisted
                           at or after cursor - overlap_window.  Populated and pruned by the
                           transaction layer (Step 4); stored here for cross-midnight survival.

    Security guarantee: no token, email, refresh_token, or raw Jira response is stored.
    """

    version: int
    source: str
    account: str
    authorised_identity: dict       # {"accountId": "..."} only
    canonical_scope: dict           # {"type": "project", "project": "ALPHA"} or project+keys
    cursor: str | None              # ISO 8601 or None (first import)
    last_key: str | None            # diagnostic; never an exclusion filter
    commit_time: str | None         # ISO 8601 of the last successful save
    overlap_snapshot_hashes: dict = field(default_factory=dict)  # {hash_hex: updated_iso}

    # ------------------------------------------------------------------ public API

    @classmethod
    def load(cls, path: Path) -> "JiraCheckpoint | None":
        """Load from *path*; return None when the file is absent (first import).

        Raises ValueError with recovery guidance for any corrupted, incomplete,
        wrong-version, or credential-containing checkpoint file.
        """
        path = Path(path)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(
                f"Checkpoint file {path} could not be read: {exc}. {_recovery_guidance()}"
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Checkpoint file {path} contains invalid JSON: {exc}. {_recovery_guidance()}"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError(
                f"Checkpoint file {path} is not a JSON object. {_recovery_guidance()}"
            )
        return cls._from_dict(data, path)

    def save(self, path: Path) -> None:
        """Write the checkpoint atomically using tempfile + os.replace().

        Validates all fields (including a recursive credential scan) before
        touching the disk.  The file descriptor is fsynced before the rename;
        on POSIX the parent directory is also fsynced afterwards so that the
        rename entry is durable across a crash or power loss.
        """
        self._validate_self()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._to_dict(), ensure_ascii=False, indent=2) + "\n"
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)
            # On POSIX, fsync the parent directory so the rename (directory entry)
            # is durable.  A file-content fsync alone does not guarantee the rename
            # survives a crash on ext4/xfs/zfs without this step.
            # Windows FlushFileBuffers covers this implicitly; directory fds are not
            # required there.
            if os.name != "nt":
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def matches(
        self,
        *,
        source: str,
        account: str,
        account_id: str,
        canonical_scope: dict,
    ) -> None:
        """Raise ValueError if any identity field differs from this checkpoint.

        Called before every incremental run.  A mismatch means this checkpoint
        file belongs to a different (source, account, identity, scope) tuple and
        must not be used.  AG-5 / ISO-4.
        """
        mismatches: list[str] = []
        if self.source != source:
            mismatches.append(
                f"source: checkpoint={self.source!r}, current={source!r}"
            )
        if self.account != account:
            mismatches.append(
                f"account: checkpoint={self.account!r}, current={account!r}"
            )
        checkpoint_account_id = (self.authorised_identity or {}).get("accountId", "")
        if checkpoint_account_id != account_id:
            mismatches.append(
                f"authorised_identity.accountId: "
                f"checkpoint={checkpoint_account_id!r}, current={account_id!r}"
            )
        if self.canonical_scope != canonical_scope:
            mismatches.append(
                f"canonical_scope: checkpoint={self.canonical_scope!r}, "
                f"current={canonical_scope!r}"
            )
        if mismatches:
            raise ValueError(
                "Checkpoint identity mismatch — this checkpoint does not belong to the "
                "current (source, account, identity, scope) combination:\n  "
                + "\n  ".join(mismatches) + "\n"
                + _recovery_guidance()
            )

    def scope_hash(self) -> str:
        """Return the 16-hex scope hash for this checkpoint's identity (AG-5)."""
        return _scope_hash(
            self.source,
            self.account,
            (self.authorised_identity or {}).get("accountId", ""),
            self.canonical_scope,
        )
    # ------------------------------------------------------------------ serialisation

    def _validate_self(self) -> None:
        """Validate every field before the checkpoint is serialised to disk.

        Catches callers that construct a JiraCheckpoint directly with wrong types
        or forbidden credential fields so that nothing sensitive is ever persisted.
        Raises ValueError with a clear message for each violation found.
        """
        if self.version != _CHECKPOINT_VERSION:
            raise ValueError(
                f"JiraCheckpoint.version must be {_CHECKPOINT_VERSION}, got {self.version!r}."
            )
        if self.source != "jira":
            raise ValueError(
                f"JiraCheckpoint.source must be 'jira', got {self.source!r}."
            )
        if not isinstance(self.account, str) or not self.account:
            raise ValueError("JiraCheckpoint.account must be a non-empty string.")
        # authorised_identity: only {"accountId": "<non-empty string>"} is permitted.
        if not isinstance(self.authorised_identity, dict):
            raise ValueError("JiraCheckpoint.authorised_identity must be a dict.")
        if (
            not isinstance(self.authorised_identity.get("accountId"), str)
            or not self.authorised_identity["accountId"]
        ):
            raise ValueError(
                "JiraCheckpoint.authorised_identity must have a non-empty 'accountId' string."
            )
        extra = set(self.authorised_identity.keys()) - {"accountId"}
        if extra:
            raise ValueError(
                f"JiraCheckpoint.authorised_identity contains forbidden field(s) "
                f"{sorted(extra)!r}; only 'accountId' is permitted. "
                "Never store email, token, or other credentials in a checkpoint."
            )
        # canonical_scope: must be a dict with a non-empty 'type' string.
        if (
            not isinstance(self.canonical_scope, dict)
            or not isinstance(self.canonical_scope.get("type"), str)
            or not self.canonical_scope["type"]
        ):
            raise ValueError(
                "JiraCheckpoint.canonical_scope must be a dict with a non-empty 'type' string."
            )
        # Optional scalar fields: None or str only.
        for fname in ("cursor", "last_key", "commit_time"):
            v = getattr(self, fname)
            if v is not None and not isinstance(v, str):
                raise ValueError(
                    f"JiraCheckpoint.{fname} must be None or a string, "
                    f"got {type(v).__name__!r}."
                )
        # overlap_snapshot_hashes: dict of str → str only.
        if not isinstance(self.overlap_snapshot_hashes, dict):
            raise ValueError("JiraCheckpoint.overlap_snapshot_hashes must be a dict.")
        bad = [
            (k, v) for k, v in self.overlap_snapshot_hashes.items()
            if not isinstance(k, str) or not isinstance(v, str)
        ]
        if bad:
            raise ValueError(
                "JiraCheckpoint.overlap_snapshot_hashes keys and values must all be strings; "
                f"found non-string entries: {bad[:3]!r}."
            )
        # Recursive credential scan on the full serialized form (defense in depth).
        _reject_credential_fields(self._to_dict(), Path("<in-memory checkpoint>"))

    def _to_dict(self) -> dict:
        return {
            "version": self.version,
            "source": self.source,
            "account": self.account,
            "authorised_identity": self.authorised_identity,
            "canonical_scope": self.canonical_scope,
            "cursor": self.cursor,
            "last_key": self.last_key,
            "commit_time": self.commit_time,
            "overlap_snapshot_hashes": self.overlap_snapshot_hashes,
        }

    @classmethod
    def _from_dict(cls, data: dict, path: Path) -> "JiraCheckpoint":
        required = (
            "version", "source", "account", "authorised_identity",
            "canonical_scope", "cursor", "last_key", "commit_time",
        )
        missing = [name for name in required if name not in data]
        if missing:
            raise ValueError(
                f"Checkpoint file {path} is missing required fields: {missing}. "
                + _recovery_guidance()
            )

        version = data["version"]
        if version != _CHECKPOINT_VERSION:
            raise ValueError(
                f"Checkpoint file {path} has unsupported version {version!r}; "
                f"expected {_CHECKPOINT_VERSION}. {_recovery_guidance()}"
            )

        source = data["source"]
        if source != "jira":
            raise ValueError(
                f"Checkpoint file {path} has source={source!r}; "
                "only 'jira' is accepted by this loader. " + _recovery_guidance()
            )

        # account: non-empty string
        account = data["account"]
        if not isinstance(account, str) or not account:
            raise ValueError(
                f"Checkpoint file {path}: 'account' must be a non-empty string, "
                f"got {type(account).__name__!r}. {_recovery_guidance()}"
            )

        # authorised_identity: {"accountId": "<non-empty string>"} only — no email, no token.
        auth_id = data["authorised_identity"]
        if (
            not isinstance(auth_id, dict)
            or not isinstance(auth_id.get("accountId"), str)
            or not auth_id["accountId"]
        ):
            raise ValueError(
                f"Checkpoint file {path}: authorised_identity must be a dict with a "
                "non-empty 'accountId' string. " + _recovery_guidance()
            )
        extra_auth = set(auth_id.keys()) - {"accountId"}
        if extra_auth:
            raise ValueError(
                f"Checkpoint file {path}: authorised_identity contains forbidden field(s) "
                f"{sorted(extra_auth)!r}; only 'accountId' is permitted. "
                + _recovery_guidance()
            )

        # canonical_scope: dict with a non-empty 'type' string.
        canonical_scope = data["canonical_scope"]
        if (
            not isinstance(canonical_scope, dict)
            or not isinstance(canonical_scope.get("type"), str)
            or not canonical_scope["type"]
        ):
            raise ValueError(
                f"Checkpoint file {path}: canonical_scope must be a dict with a non-empty "
                "'type' string. " + _recovery_guidance()
            )

        # cursor / last_key / commit_time: None or string.
        for fname in ("cursor", "last_key", "commit_time"):
            v = data[fname]
            if v is not None and not isinstance(v, str):
                raise ValueError(
                    f"Checkpoint file {path}: '{fname}' must be null or a string, "
                    f"got {type(v).__name__!r}. {_recovery_guidance()}"
                )

        # overlap_snapshot_hashes: dict of str → str.
        overlap = data.get("overlap_snapshot_hashes", {})
        if not isinstance(overlap, dict):
            raise ValueError(
                f"Checkpoint file {path}: overlap_snapshot_hashes must be a JSON object. "
                + _recovery_guidance()
            )
        bad_overlap = [
            (k, v) for k, v in overlap.items()
            if not isinstance(k, str) or not isinstance(v, str)
        ]
        if bad_overlap:
            raise ValueError(
                f"Checkpoint file {path}: overlap_snapshot_hashes keys and values must all "
                f"be strings; found non-string entries: {bad_overlap[:3]!r}. "
                + _recovery_guidance()
            )

        # Recursive credential scan (catches fields nested inside canonical_scope, etc.)
        _reject_credential_fields(data, path)

        return cls(
            version=version,
            source=source,
            account=account,
            authorised_identity=dict(auth_id),
            canonical_scope=dict(canonical_scope),
            cursor=data["cursor"],
            last_key=data["last_key"],
            commit_time=data["commit_time"],
            overlap_snapshot_hashes=dict(overlap),
        )
# ------------------------------------------------------------------ scope lock

@contextmanager
def _scope_lock(state_dir: Path, scope_hash: str):
    """Non-blocking process lock for one (source, account, identity, scope) combination.

    The lock file is named ``<scope_hash>.lock`` inside *state_dir*.  A second
    concurrent process on the same scope raises ValueError immediately — no
    waiting, no retry (AG-4).  The operating system releases the lock when the
    process exits, so a crash never leaves a stuck lock.

    Usage::

        with _scope_lock(state_dir, checkpoint.scope_hash()):
            # only one process runs this block per scope at a time
            ...

    Raises
    ------
    ValueError
        If the lock is already held by another process.
    """
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / f"{scope_hash}.lock"

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a+b") as lock_fh:
        # Acquire the lock non-blocking — fail immediately on contention.
        try:
            if os.name == "nt":
                import msvcrt  # Windows only
                lock_fh.seek(0)
                if not lock_fh.read(1):
                    lock_fh.write(b"\0")
                    lock_fh.flush()
                lock_fh.seek(0)
                msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl  # POSIX only
                fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError, OSError) as exc:
            raise ValueError(
                f"Another 'co jira sync' process is already running for this scope "
                f"(lock: {lock_path}).  "
                "Wait for it to finish or check for stuck processes."
            ) from exc

        try:
            yield
        finally:
            # Release the lock explicitly before the file is closed.
            try:
                if os.name == "nt":
                    import msvcrt
                    lock_fh.seek(0)
                    msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_fh, fcntl.LOCK_UN)
            except OSError:
                pass  # The OS will release on file close / process exit anyway.


# =============================================================================
# Step 4: incremental transaction helpers and run_jira_sync() orchestrator
# =============================================================================

_OVERLAP_WINDOW = datetime.timedelta(minutes=2)
_STAGING_ENCODING_VERSION = 1

# Default directories (AG-5 / Step 5).
_DEFAULT_STATE_DIR = Path.home() / ".co" / "rem" / "docs" / "jira" / ".state"
_DEFAULT_OUTPUT_DIR = Path.home() / ".co" / "rem" / "docs" / "jira"

# Namespaces that belong to other co rem sources.  run_jira_sync() rejects
# --output and --state paths that fall inside these directories to enforce
# the F13FCAKE-1 cross-source isolation requirement.
_RESERVED_NAMESPACES: frozenset = frozenset({
    Path.home() / ".co" / "rem" / "docs" / "onenote",
})


def _check_namespace_isolation(p: Path, label: str) -> None:
    """Raise ValueError if *p* resolves to inside a non-Jira co rem source namespace (F13FCAKE-1)."""
    resolved = p.resolve()
    for ns in _RESERVED_NAMESPACES:
        ns_resolved = ns.resolve()
        if resolved == ns_resolved or resolved.is_relative_to(ns_resolved):
            raise ValueError(
                f"{label} {str(p)!r} is inside the OneNote namespace "
                f"{str(ns)!r}. Jira and OneNote must use separate directories "
                "(F13FCAKE-1 cross-source isolation). "
                "Use the default paths or a custom directory outside ~/.co/rem/docs/onenote."
            )


@dataclass
class SyncResult:
    """Result returned by run_jira_sync() in every outcome — success, partial failure, hard failure.

    exit_code: 0=success, 1=partial failure (Option B — mapping errors, cursor unchanged),
               2=hard failure (auth, lock contention, persistence, recovery error).
    checkpoint_result: "advanced" | "unchanged" | "error" | "skipped" | "recovered".
    error_code: None on clean success; a short token describing the failure otherwise.
    """

    scope: dict
    mode: str                           # "full" | "incremental"
    issues_read: int = 0
    issues_mapped: int = 0
    net_new_records: int = 0
    placement: str | None = None        # absolute path to the daily JSONL, or None
    checkpoint_result: str = "skipped"  # see docstring above
    rejections: dict = field(default_factory=dict)  # {issue_key: reason}
    error_code: str | None = None       # None = clean success
    error_detail: str | None = None     # human-readable failure description
    exit_code: int = 0                  # 0 | 1 | 2


# ---------------------------------------------------------------------------
# Internal helpers — not part of the public API
# ---------------------------------------------------------------------------

def _jira_now_utc() -> str:
    """Return the current UTC instant as an ISO 8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _normalize_scope(project_key: str, issue_keys) -> dict:
    """Return a canonical AG-1 scope dict for (project_key, issue_keys)."""
    if issue_keys:
        return {"type": "project+keys", "project": project_key, "keys": sorted(issue_keys)}
    return {"type": "project", "project": project_key}


def _checkpoint_path(state_dir: Path, s_hash: str) -> Path:
    return state_dir / "checkpoints" / f"{s_hash}.json"


def _staging_path(state_dir: Path, s_hash: str) -> Path:
    return state_dir / f"staging_{s_hash}.jsonl"


def _staging_tmp_path(state_dir: Path, s_hash: str) -> Path:
    return state_dir / f"staging_{s_hash}.jsonl.tmp"


def _pending_path(state_dir: Path, s_hash: str) -> Path:
    return state_dir / f"pending_{s_hash}.json"


def _serialise_staging_line(record: dict) -> bytes:
    """Return the exact bytes that append_daily_jsonl writes for one record."""
    return (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")


def _write_staging_atomic(staging_p: Path, tmp_p: Path, records: list) -> None:
    """Serialise *records* to *tmp_p* (fsync), then atomically rename to *staging_p*."""
    staging_p.parent.mkdir(parents=True, exist_ok=True)
    raw = b"".join(_serialise_staging_line(r) for r in records)
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(tmp_p, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        tmp_p.unlink(missing_ok=True)
        raise
    os.replace(tmp_p, staging_p)


def _write_pending_manifest(
    pending_p: Path,
    run_id: str,
    old_cursor: "str | None",
    old_last_key: "str | None",
    target_daily_path: str,
    staging_filename: str,
    record_count: int,
    checkpoint_snapshot: "dict | None" = None,
    records_appended: bool = False,
    is_full_run: bool = False,
) -> None:
    """Atomically write the pending run manifest.

    ``checkpoint_snapshot`` embeds the candidate checkpoint so that Step 3
    recovery can re-save it regardless of when a crash occurs.

    ``records_appended`` is the two-phase commit bit: ``False`` when the
    manifest is first written (before the daily JSONL write), ``True`` after
    the daily fsync succeeds.  The Step 3 recovery paths key on this flag:

    * ``records_appended=True`` + ``checkpoint_snapshot`` → re-save checkpoint.
    * ``records_appended=False`` + ``checkpoint_snapshot`` → idempotent
      re-append to the original daily file, then save checkpoint.
    * Neither → re-append only; do not advance cursor (legacy / crash before
      snapshot was embedded).

    When ``is_full_run`` is True the manifest is written with
    ``records_appended=True`` and ``is_full_run=True`` but no checkpoint
    snapshot.  Step 3 recovery sees this and only cleans up — ``--full`` never
    advances the incremental cursor.
    """
    manifest: dict = {
        "run_id": run_id,
        "old_cursor": old_cursor,
        "old_last_key": old_last_key,
        "target_daily_path": target_daily_path,
        "staging_filename": staging_filename,
        "encoding_version": _STAGING_ENCODING_VERSION,
        "planned_record_count": record_count,
    }
    if checkpoint_snapshot is not None:
        manifest["checkpoint_snapshot"] = checkpoint_snapshot
    if records_appended or is_full_run:
        manifest["records_appended"] = True
    if is_full_run:
        manifest["is_full_run"] = True
    pending_p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=f".{pending_p.name}.", suffix=".tmp", dir=pending_p.parent
    )
    tmp_p = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_p, pending_p)
    except BaseException:
        tmp_p.unlink(missing_ok=True)
        raise
    # Fsync the parent directory to flush the new directory entry durably.
    # The two-phase commit protocol depends on the initial manifest being
    # truly persistent before staging/daily writes begin.
    try:
        dir_fd = os.open(str(pending_p.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass  # Best-effort: Windows and some filesystems don't support dir fsync.


def _max_updated_and_last_key(issues: list) -> "tuple[str | None, str | None]":
    """Return (max_updated_iso, issue_key) from raw Jira issue dicts."""
    if not issues:
        return None, None

    def _safe_updated(i: dict) -> str:
        fields = i.get("fields")
        if not isinstance(fields, dict):
            return ""
        return str(fields.get("updated") or "")

    best = max(
        issues,
        key=lambda i: (_safe_updated(i), str(i.get("key") or "")),
    )
    updated = _safe_updated(best)
    key = str(best.get("key") or "")
    return (updated or None), (key or None)


def _prune_and_extend_overlap(
    existing: dict,
    cursor_str: "str | None",
    new_entries: dict,
) -> dict:
    """Return a pruned-and-extended overlap_snapshot_hashes dict (AG-5).

    Removes entries whose updated value is strictly before cursor - OVERLAP_WINDOW,
    then merges in *new_entries*.
    """
    boundary = None
    if cursor_str:
        try:
            boundary = datetime.datetime.fromisoformat(cursor_str) - _OVERLAP_WINDOW
        except ValueError:
            pass

    result: dict = {}
    for h, updated_iso in existing.items():
        keep = True
        if boundary is not None:
            try:
                keep = datetime.datetime.fromisoformat(str(updated_iso)) >= boundary
            except ValueError:
                pass  # keep entries with unparseable timestamps
        if keep:
            result[h] = updated_iso
    result.update(new_entries)
    return result


def _repair_incomplete_final_line(daily_path: Path, staging_p: Path) -> None:
    """Truncate an incomplete final line in *daily_path*.

    Only truncates when the tail is a strict byte-prefix of the first staging line.
    Otherwise raises ValueError — fail closed (AG-4).
    """
    if not daily_path.exists():
        return
    daily_bytes = daily_path.read_bytes()
    if not daily_bytes or daily_bytes[-1:] == b"\n":
        return  # Clean — no repair needed.

    if not staging_p.exists():
        raise ValueError(
            f"Daily file {daily_path} has an incomplete final line but "
            f"staging file {staging_p} is missing; cannot validate. Failing closed."
        )
    staging_bytes = staging_p.read_bytes()
    if not staging_bytes:
        raise ValueError(
            f"Daily file {daily_path} has an incomplete final line and "
            f"staging file {staging_p} is empty. Failing closed."
        )
    first_nl = staging_bytes.find(b"\n")
    first_line = staging_bytes[: first_nl + 1] if first_nl >= 0 else staging_bytes

    last_nl = daily_bytes.rfind(b"\n", 0, len(daily_bytes) - 1)
    tail = daily_bytes[last_nl + 1 :]
    if not first_line.startswith(tail):
        raise ValueError(
            f"Daily file {daily_path} incomplete tail is not a byte-prefix of the "
            f"first staging line.  Failing closed — manual inspection required."
        )
    with open(daily_path, "r+b") as fh:
        fh.seek(last_nl + 1)
        fh.truncate()
        fh.flush()
        os.fsync(fh.fileno())


def _date_from_daily_path(daily_path: Path) -> "datetime.date | None":
    """Extract the date from a daily JSONL path …/daily/YYYY/MM/DD.jsonl."""
    try:
        day = int(daily_path.stem)
        month = int(daily_path.parent.name)
        year = int(daily_path.parent.parent.name)
        return datetime.date(year, month, day)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Step 5: source.yaml v2 identity guard
# ---------------------------------------------------------------------------

_SOURCE_YAML_VERSION = 2


def _legacy_source_mismatch(existing: dict, driver: str, account: str, canonical_scope: dict) -> str | None:
    """Reject migration when a v1 source file names another source, account, or scope."""
    if not isinstance(existing, dict):
        return "source.yaml is not a mapping; migration cannot verify its identity."
    if existing.get("driver") not in (None, driver) or existing.get("account") not in (None, account):
        return "source.yaml belongs to a different source or account; use a separate output directory."
    old_scope = existing.get("scope")
    if old_scope is not None:
        expected = {"projects": [canonical_scope["project"]], "issues": canonical_scope.get("keys", [])}
        if old_scope != expected:
            return "source.yaml belongs to a different Jira scope; use a separate output directory."
    return None


def _check_source_yaml_identity(
    output_dir: Path,
    driver: str,
    account: str,
    account_id: str,
    canonical_scope: dict,
    *,
    migrate: bool = False,
) -> "str | None":
    """Read-only pre-flight check: return an error string if source.yaml conflicts, else None.

    Mirrors the validation logic inside _write_source_yaml_v2 but makes no filesystem changes.
    Call this before writing any records or checkpoint so a scope mismatch is surfaced before
    the run starts (P2-1 requirement).
    """
    import yaml as _yaml  # lazy — yaml is not a top-level dep of jira_checkpoint

    target = Path(output_dir) / "source.yaml"
    if not target.exists():
        return None
    try:
        existing = _yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return f"source.yaml at {target} could not be parsed: {exc}"

    file_version = existing.get("schema_version")
    if file_version != _SOURCE_YAML_VERSION:
        if not migrate:
            return (
                f"source.yaml at {target} has schema_version={file_version!r} "
                f"(expected {_SOURCE_YAML_VERSION}). "
                "Preserve it. --migrate-source can upgrade only a matching legacy source; "
                "otherwise use a separate output directory."
            )
        return _legacy_source_mismatch(existing, driver, account, canonical_scope)

    id_ok = (
        existing.get("driver") == driver
        and existing.get("account") == account
        and (existing.get("authorised_identity") or {}).get("accountId") == account_id
        and existing.get("canonical_scope") == canonical_scope
    )
    if not id_ok:
        return (
            f"source.yaml at {target} is v{_SOURCE_YAML_VERSION} but has a different "
            "driver/account/accountId/canonical_scope. "
            "The file was left unchanged. "
            "Use a separate output directory for a different identity or scope."
        )
    return None


def _write_source_yaml_v2(
    output_dir: Path,
    driver: str,
    account: str,
    account_id: str,
    canonical_scope: dict,
    *,
    migrate: bool = False,
) -> None:
    """Write or validate output_dir/source.yaml as a v2 identity-locked file (sprint2.md §4).

    Rules
    -----
    - File absent: write fresh v2.
    - File has no schema_version or schema_version != 2 (v1/unversioned): raise ValueError
      unless migrate=True, in which case overwrite to v2.
    - File has schema_version == 2, same identity: leave unchanged (idempotent, no write).
    - File has schema_version == 2, different identity: leave file unchanged and raise
      ValueError so the caller can surface a clear diagnostic.

    Never writes tokens, email addresses, or raw provider responses.
    Lazy-imports yaml so jira_checkpoint has no module-level yaml dependency.
    """
    import yaml as _yaml  # lazy — yaml is not a top-level dep of jira_checkpoint

    output_dir = Path(output_dir)
    target = output_dir / "source.yaml"

    if target.exists():
        try:
            existing = _yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"source.yaml at {target} could not be parsed: {exc}"
            ) from exc

        file_version = existing.get("schema_version")
        if file_version != _SOURCE_YAML_VERSION:
            if not migrate:
                raise ValueError(
                    f"source.yaml at {target} has schema_version={file_version!r} "
                    f"(expected {_SOURCE_YAML_VERSION}). "
                    "Preserve it. --migrate-source can upgrade only a matching legacy source; "
                    "otherwise use a separate output directory."
                )
            mismatch = _legacy_source_mismatch(existing, driver, account, canonical_scope)
            if mismatch:
                raise ValueError(mismatch)
        else:
            # v2 present: compare identity fields exactly.
            id_ok = (
                existing.get("driver") == driver
                and existing.get("account") == account
                and (existing.get("authorised_identity") or {}).get("accountId") == account_id
                and existing.get("canonical_scope") == canonical_scope
            )
            if id_ok:
                return  # idempotent — nothing to write
            raise ValueError(
                f"source.yaml at {target} is v{_SOURCE_YAML_VERSION} but has a different "
                "driver/account/accountId/canonical_scope. "
                "The file was left unchanged. "
                "Use a separate output directory for a different identity or scope."
            )

    # Write v2 atomically (fresh or migrating from v1).
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": _SOURCE_YAML_VERSION,
        "driver": driver,
        "account": account,
        "authorised_identity": {"accountId": account_id},
        "canonical_scope": canonical_scope,
    }
    tmp_p = target.with_suffix(".yaml.tmp")
    try:
        tmp_p.write_text(
            _yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        os.replace(tmp_p, target)
    except BaseException:
        tmp_p.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_jira_sync(
    project_key: str,
    *,
    issue_keys=None,
    full: bool = False,
    state_dir=None,
    output_dir=None,
    history: bool = True,
    migrate_source: bool = False,
    lock_held: bool = False,
    require_selected_first: bool = False,
) -> SyncResult:
    """Orchestrate one incremental (or full) Jira sync for the given scope.

    Implements the 10-step transaction sequence from sprint2.md Step 4 (AG-1–AG-5).
    Lazy-imports jira.py and adapter.py to avoid circular dependencies and to allow
    test patching via ``patch("connectonion.useful_tools.jira.Jira")``.

    Returns SyncResult in every case — never raises.
    """
    # Lazy imports: jira.py and adapter.py must not be imported at module level
    # (sprint2.md Step 2 module boundary; also enables test patching).
    from connectonion.useful_tools import jira as _jira_mod
    from connectonion.useful_tools.adapter import (
        jira_issues_to_records as _jira_to_records,
        append_daily_jsonl as _append_jsonl,
        snapshot_hash as _snap_hash,
    )

    canonical_scope = _normalize_scope(project_key, issue_keys)
    mode = "full" if full else "incremental"
    state_dir = Path(state_dir) if state_dir is not None else _DEFAULT_STATE_DIR
    output_dir = Path(output_dir) if output_dir is not None else _DEFAULT_OUTPUT_DIR

    # Namespace isolation guard (F13FCAKE-1): reject paths inside other source namespaces.
    try:
        _check_namespace_isolation(output_dir, "--output")
        _check_namespace_isolation(state_dir, "--state")
    except ValueError as exc:
        return SyncResult(
            scope=canonical_scope, mode=mode,
            error_code="namespace_violation", error_detail=str(exc), exit_code=2,
        )
    # ------------------------------------------------------------------ Step 1
    # Create the Jira client and verify the connection first.
    # On any auth or network failure, do not read or modify local source state.
    try:
        jira_client = _jira_mod.Jira()
        identity = jira_client.verify_connection()
    except Exception as exc:  # noqa: BLE001
        return SyncResult(
            scope=canonical_scope, mode=mode,
            error_code="auth_failure", error_detail=str(exc), exit_code=2,
        )
    account = str(identity.get("site_url") or "")
    account_id = str(identity.get("accountId") or "")

    # ------------------------------------------------------------------ Step 2
    # Normalise scope, calculate the scope hash, derive all file paths.
    s_hash = _scope_hash("jira", account, account_id, canonical_scope)
    cp_path = _checkpoint_path(state_dir, s_hash)
    staging_p = _staging_path(state_dir, s_hash)
    staging_tmp_p = _staging_tmp_path(state_dir, s_hash)
    pending_p = _pending_path(state_dir, s_hash)

    from ..rem.files import _file_lock, RemError
    try:
        with (nullcontext() if lock_held else _file_lock(output_dir, 0)), _scope_lock(state_dir, s_hash):
            # ---------------------------------------------------------- Step 3: recovery
            # Staging .tmp present: remove it (incomplete write), re-fetch.
            if staging_tmp_p.exists():
                staging_tmp_p.unlink(missing_ok=True)

            # Formal staging + pending: repair daily line, resume append, leave cursor unchanged.
            if staging_p.exists() and pending_p.exists():
                try:
                    manifest = json.loads(pending_p.read_text(encoding="utf-8"))
                    target_daily = Path(manifest["target_daily_path"])

                    # Safety: target_daily must resolve inside output_dir/daily/.
                    # Rejects corrupted or tampered manifests that could redirect
                    # writes to an unrelated directory.
                    _output_daily_root = (output_dir / "daily").resolve()
                    try:
                        target_daily.resolve().relative_to(_output_daily_root)
                    except ValueError as _path_exc:
                        raise ValueError(
                            f"Pending manifest target_daily_path {target_daily!r} is "
                            f"outside the expected output directory "
                            f"{_output_daily_root}: {_path_exc}"
                        ) from _path_exc

                    if manifest.get("records_appended"):
                        if manifest.get("checkpoint_snapshot"):
                            # Incremental: Step 10 failed — re-save checkpoint without
                            # re-writing records (prevents cross-midnight duplicate writes
                            # after a checkpoint-save failure).
                            snap = manifest["checkpoint_snapshot"]
                            recovered_cp = JiraCheckpoint(
                                version=snap["version"],
                                source=snap["source"],
                                account=snap["account"],
                                authorised_identity=snap["authorised_identity"],
                                canonical_scope=snap["canonical_scope"],
                                cursor=snap.get("cursor"),
                                last_key=snap.get("last_key"),
                                commit_time=snap.get("commit_time"),
                                overlap_snapshot_hashes=snap.get("overlap_snapshot_hashes") or {},
                            )
                            recovered_cp.matches(
                                source="jira", account=account,
                                account_id=account_id,
                                canonical_scope=canonical_scope,
                            )
                            recovered_cp.save(cp_path)
                        # else: full run crashed after records written — records are
                        # already in the daily JSONL; do not advance the cursor.
                        # Fall through to clean up staging+pending below.
                    elif manifest.get("checkpoint_snapshot"):
                        # Two-phase commit: Step 9.5 (records_appended update) failed,
                        # or a crash occurred during/before Step 9.  Records may or may
                        # not be in the daily JSONL — idempotent re-append handles both
                        # cases.  The candidate snapshot was written before any disk
                        # writes, so saving it here advances the cursor correctly.
                        snap = manifest["checkpoint_snapshot"]
                        recovered_cp = JiraCheckpoint(
                            version=snap["version"],
                            source=snap["source"],
                            account=snap["account"],
                            authorised_identity=snap["authorised_identity"],
                            canonical_scope=snap["canonical_scope"],
                            cursor=snap.get("cursor"),
                            last_key=snap.get("last_key"),
                            commit_time=snap.get("commit_time"),
                            overlap_snapshot_hashes=snap.get("overlap_snapshot_hashes") or {},
                        )
                        recovered_cp.matches(
                            source="jira", account=account,
                            account_id=account_id,
                            canonical_scope=canonical_scope,
                        )
                        _repair_incomplete_final_line(target_daily, staging_p)
                        staging_records = [
                            json.loads(ln)
                            for ln in staging_p.read_text(encoding="utf-8").splitlines()
                            if ln.strip()
                        ]
                        recovery_date = _date_from_daily_path(target_daily)
                        _append_jsonl(
                            staging_records, output_dir,
                            keep_versions=True, date=recovery_date,
                        )
                        recovered_cp.save(cp_path)
                    else:
                        # No snapshot: crash before Step 7 wrote the candidate
                        # checkpoint, or a legacy manifest.  Re-append records but
                        # do not advance the cursor — caller should retry.
                        _repair_incomplete_final_line(target_daily, staging_p)
                        staging_records = [
                            json.loads(ln)
                            for ln in staging_p.read_text(encoding="utf-8").splitlines()
                            if ln.strip()
                        ]
                        recovery_date = _date_from_daily_path(target_daily)
                        _append_jsonl(
                            staging_records, output_dir,
                            keep_versions=True, date=recovery_date,
                        )

                    staging_p.unlink(missing_ok=True)
                    pending_p.unlink(missing_ok=True)
                except Exception as exc:  # noqa: BLE001
                    return SyncResult(
                        scope=canonical_scope, mode=mode,
                        error_code="recovery_failed", error_detail=str(exc), exit_code=2,
                    )
                # Cursor not advanced here; caller should retry to advance.
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    placement=str(target_daily),
                    checkpoint_result="recovered",
                    exit_code=0,
                )

            # Pending without staging: clean up, re-fetch.
            if pending_p.exists() and not staging_p.exists():
                pending_p.unlink(missing_ok=True)

            # ---------------------------------------------------------- Step 4
            # Load and validate the checkpoint.  Mismatch fails immediately.
            try:
                cp = JiraCheckpoint.load(cp_path)
            except ValueError as exc:
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    error_code="checkpoint_corrupt", error_detail=str(exc), exit_code=2,
                )

            if cp is not None:
                try:
                    cp.matches(
                        source="jira", account=account,
                        account_id=account_id, canonical_scope=canonical_scope,
                    )
                except ValueError as exc:
                    return SyncResult(
                        scope=canonical_scope, mode=mode,
                        error_code="checkpoint_mismatch", error_detail=str(exc), exit_code=2,
                    )

            # ---------------------------------------------------------- Step 5
            # Freeze target_date; compute query lower bound.
            target_date = datetime.date.today()
            daily_dir = (
                output_dir / "daily"
                / str(target_date.year)
                / f"{target_date.month:02d}"
            )
            target_daily_path = daily_dir / f"{target_date.day:02d}.jsonl"

            old_cursor = cp.cursor if cp else None
            old_last_key = cp.last_key if cp else None
            old_overlap = dict(cp.overlap_snapshot_hashes) if cp else {}

            if full or old_cursor is None:
                since_str = None
            else:
                try:
                    since_str = (
                        datetime.datetime.fromisoformat(old_cursor) - _OVERLAP_WINDOW
                    ).isoformat()
                except ValueError:
                    since_str = None

            # ---- Pre-flight: source.yaml identity check (P2-1).
            # Read-only; must run before any writes so a scope mismatch is caught
            # before records or the checkpoint are modified.
            yaml_preflight = _check_source_yaml_identity(
                output_dir, "jira", account, account_id, canonical_scope,
                migrate=migrate_source,
            )
            if yaml_preflight:
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    error_code="source_yaml_conflict", error_detail=yaml_preflight, exit_code=2,
                )

            # ---------------------------------------------------------- Step 6 (fetch)
            try:
                raw_issues = list(
                    jira_client.scoped_issues(
                        project_key, issue_keys=issue_keys, since=since_str
                    )
                )
            except Exception as exc:  # noqa: BLE001
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    error_code="fetch_failed", error_detail=str(exc), exit_code=2,
                )

            issues_read = len(raw_issues)
            missing_selection = (set(issue_keys or []) - {row.get("key") for row in raw_issues}
                                 if require_selected_first and (cp is None or cp.cursor is None) else set())
            if missing_selection and not raw_issues:
                return SyncResult(scope=canonical_scope, mode=mode, issues_read=0,
                    rejections={key: "Selected issue not returned by the first source read" for key in missing_selection},
                    error_code="selection_incomplete", error_detail="Selected issues unavailable on first read; retry the same scope",
                    checkpoint_result="unchanged", exit_code=1)

            # AG-3: zero Jira results → cursor and last_key unchanged.
            if issues_read == 0:
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    issues_read=0, issues_mapped=0, net_new_records=0,
                    placement=str(target_daily_path),
                    checkpoint_result="unchanged",
                    exit_code=0,
                )

            # ---------------------------------------------------------- Step 6 (map)
            # Fetch changelogs when history is requested (non-fatal if unavailable).
            changelogs = None
            if history:
                keys = [str(i.get("key") or "") for i in raw_issues if i.get("key")]
                try:
                    changelogs = jira_client.issue_changelogs(keys) if keys else None
                except Exception:  # noqa: BLE001
                    changelogs = None

            adapter_result = _jira_to_records(raw_issues, account, changelogs=changelogs)
            rejections = dict(adapter_result.errors)
            rejections.update({key: "Selected issue not returned by the first source read" for key in missing_selection})
            partial_fail = bool(rejections)
            valid_records = list(adapter_result.records)
            issues_mapped = len(valid_records)

            max_updated, last_key_at_max = _max_updated_and_last_key(raw_issues)

            # ---------------------------------------------------------- Step 7 (dedup)
            # Deduplicate against the target daily file and the overlap hash set.
            existing_hashes: set[str] = set(old_overlap.keys())
            if target_daily_path.exists():
                for ln in target_daily_path.read_text(encoding="utf-8").splitlines():
                    ln = ln.strip()
                    if ln:
                        try:
                            existing_hashes.add(_snap_hash(json.loads(ln)))
                        except (json.JSONDecodeError, TypeError):
                            pass

            net_new = [r for r in valid_records if _snap_hash(r) not in existing_hashes]
            net_new_count = len(net_new)

            # Build the new overlap entry map for all valid records in this run.
            new_overlap_entries = {
                _snap_hash(r): str(r.get("updated") or "") for r in valid_records
            }

            # Shortcut: all records already durably represented → skip staging.
            if net_new_count == 0:
                if partial_fail:
                    return SyncResult(
                        scope=canonical_scope, mode=mode,
                        issues_read=issues_read, issues_mapped=issues_mapped,
                        net_new_records=0, placement=str(target_daily_path),
                        checkpoint_result="unchanged", rejections=rejections,
                        error_code="mapping_error",
                        error_detail=f"{len(rejections)} issue(s) failed to map",
                        exit_code=1,
                    )
                if full:
                    # Full run: do NOT advance the incremental checkpoint.
                    src_yaml_err_z: "str | None" = None
                    try:
                        _write_source_yaml_v2(
                            output_dir, "jira", account, account_id, canonical_scope,
                            migrate=migrate_source,
                        )
                    except ValueError as exc:
                        src_yaml_err_z = str(exc)
                    return SyncResult(
                        scope=canonical_scope, mode=mode,
                        issues_read=issues_read, issues_mapped=issues_mapped,
                        net_new_records=0, placement=str(target_daily_path),
                        checkpoint_result="skipped",
                        error_code="source_yaml_conflict" if src_yaml_err_z else None,
                        error_detail=src_yaml_err_z,
                        exit_code=2 if src_yaml_err_z else 0,
                    )
                new_overlap = _prune_and_extend_overlap(old_overlap, max_updated, new_overlap_entries)
                new_cp = JiraCheckpoint(
                    version=_CHECKPOINT_VERSION, source="jira", account=account,
                    authorised_identity={"accountId": account_id},
                    canonical_scope=canonical_scope,
                    cursor=max_updated, last_key=last_key_at_max,
                    commit_time=_jira_now_utc(), overlap_snapshot_hashes=new_overlap,
                )
                try:
                    new_cp.save(cp_path)
                except Exception as exc:  # noqa: BLE001
                    return SyncResult(
                        scope=canonical_scope, mode=mode,
                        issues_read=issues_read, issues_mapped=issues_mapped,
                        net_new_records=0, placement=str(target_daily_path),
                        checkpoint_result="error",
                        error_code="checkpoint_save_failed", error_detail=str(exc), exit_code=2,
                    )
                cp_result = "advanced" if max_updated and max_updated != old_cursor else "unchanged"
                src_yaml_err: "str | None" = None
                try:
                    _write_source_yaml_v2(
                        output_dir, "jira", account, account_id, canonical_scope,
                        migrate=migrate_source,
                    )
                except ValueError as exc:
                    src_yaml_err = str(exc)
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    issues_read=issues_read, issues_mapped=issues_mapped,
                    net_new_records=0, placement=str(target_daily_path),
                    checkpoint_result=cp_result,
                    error_code="source_yaml_conflict" if src_yaml_err else None,
                    error_detail=src_yaml_err,
                    exit_code=2 if src_yaml_err else 0,
                )

            # ---- Two-phase commit: compute candidate checkpoint before any disk writes.
            # For the incremental success path (not full, not partial_fail), the
            # candidate snapshot is embedded in the initial manifest so that Step 3
            # recovery can save it regardless of where a crash occurs.
            candidate_cp: "JiraCheckpoint | None" = None
            candidate_cp_snapshot: "dict | None" = None
            if not full and not partial_fail:
                _candidate_overlap = _prune_and_extend_overlap(
                    old_overlap, max_updated, new_overlap_entries
                )
                candidate_cp = JiraCheckpoint(
                    version=_CHECKPOINT_VERSION, source="jira", account=account,
                    authorised_identity={"accountId": account_id},
                    canonical_scope=canonical_scope,
                    cursor=max_updated, last_key=last_key_at_max,
                    commit_time=_jira_now_utc(), overlap_snapshot_hashes=_candidate_overlap,
                )
                candidate_cp_snapshot = {
                    "version": candidate_cp.version,
                    "source": candidate_cp.source,
                    "account": candidate_cp.account,
                    "authorised_identity": dict(candidate_cp.authorised_identity),
                    "canonical_scope": dict(candidate_cp.canonical_scope),
                    "cursor": candidate_cp.cursor,
                    "last_key": candidate_cp.last_key,
                    "commit_time": candidate_cp.commit_time,
                    "overlap_snapshot_hashes": dict(candidate_cp.overlap_snapshot_hashes),
                }

            # ---------------------------------------------------------- Step 7 (manifest)
            # Phase 1 of the two-phase commit: write manifest with candidate snapshot
            # (records_appended=False).  This must be durable before staging writes begin.
            run_id = str(uuid.uuid4())
            try:
                _write_pending_manifest(
                    pending_p, run_id, old_cursor, old_last_key,
                    str(target_daily_path), staging_p.name, net_new_count,
                    checkpoint_snapshot=candidate_cp_snapshot,
                    records_appended=False,
                )
            except Exception as exc:  # noqa: BLE001
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    error_code="persistence", error_detail=str(exc), exit_code=2,
                )

            # ---------------------------------------------------------- Step 8 (staging)
            try:
                _write_staging_atomic(staging_p, staging_tmp_p, net_new)
            except Exception as exc:  # noqa: BLE001
                pending_p.unlink(missing_ok=True)
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    error_code="persistence", error_detail=str(exc), exit_code=2,
                )

            # ---------------------------------------------------------- Step 9 (append)
            try:
                target_written, n_written = _append_jsonl(
                    net_new, output_dir, keep_versions=True, date=target_date,
                )
            except Exception as exc:  # noqa: BLE001
                # Leave staging + pending in place for recovery on next run.
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    error_code="persistence", error_detail=str(exc), exit_code=2,
                )

            placement = str(target_written)

            # ---------------------------------------------------------- Step 10 (commit)
            # Option B: mapping errors → keep old cursor, clean staging, exit 1.
            if partial_fail:
                staging_p.unlink(missing_ok=True)
                pending_p.unlink(missing_ok=True)
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    issues_read=issues_read, issues_mapped=issues_mapped,
                    net_new_records=n_written, placement=placement,
                    checkpoint_result="unchanged", rejections=rejections,
                    error_code="mapping_error",
                    error_detail=f"{len(rejections)} issue(s) failed to map",
                    exit_code=1,
                )

            # Full run: records written, but do NOT advance the incremental checkpoint.
            if full:
                # ---- Step 9.5-full (mark records as durably written; no checkpoint snapshot)
                # Best-effort: if this write fails we still clean up and return.
                # On a crash, the next run's Step 3 will see records_appended=True +
                # is_full_run=True and clean up without saving a checkpoint.
                try:
                    _write_pending_manifest(
                        pending_p, run_id, old_cursor, old_last_key,
                        str(target_daily_path), staging_p.name, net_new_count,
                        is_full_run=True,
                    )
                except Exception:  # noqa: BLE001
                    pass  # Best-effort; do not block the return.
                staging_p.unlink(missing_ok=True)
                pending_p.unlink(missing_ok=True)
                src_yaml_err_f: "str | None" = None
                try:
                    _write_source_yaml_v2(
                        output_dir, "jira", account, account_id, canonical_scope,
                        migrate=migrate_source,
                    )
                except ValueError as exc:
                    src_yaml_err_f = str(exc)
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    issues_read=issues_read, issues_mapped=issues_mapped,
                    net_new_records=n_written, placement=placement,
                    checkpoint_result="skipped",
                    error_code="source_yaml_conflict" if src_yaml_err_f else None,
                    error_detail=src_yaml_err_f,
                    exit_code=2 if src_yaml_err_f else 0,
                )

            # ---- Step 9.5 (commit bit): mark daily as durably written — hard failure.
            # Phase 2 of the two-phase commit.  If this write fails the next run's
            # Step 3 recovery will see records_appended=False + checkpoint_snapshot
            # and will idempotent re-append + save the checkpoint correctly.
            try:
                _write_pending_manifest(
                    pending_p, run_id, old_cursor, old_last_key,
                    str(target_daily_path), staging_p.name, net_new_count,
                    checkpoint_snapshot=candidate_cp_snapshot,
                    records_appended=True,
                )
            except Exception as exc:  # noqa: BLE001
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    issues_read=issues_read, issues_mapped=issues_mapped,
                    net_new_records=n_written, placement=placement,
                    checkpoint_result="error",
                    error_code="manifest_update_failed", error_detail=str(exc), exit_code=2,
                )

            try:
                candidate_cp.save(cp_path)  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                # Do NOT delete staging+pending: the manifest (Step 9.5) now contains
                # records_appended=True + checkpoint_snapshot, so the next run's Step 3
                # recovery can re-save the checkpoint without re-fetching or re-writing.
                return SyncResult(
                    scope=canonical_scope, mode=mode,
                    issues_read=issues_read, issues_mapped=issues_mapped,
                    net_new_records=n_written, placement=placement,
                    checkpoint_result="error",
                    error_code="checkpoint_save_failed", error_detail=str(exc), exit_code=2,
                )

            staging_p.unlink(missing_ok=True)
            pending_p.unlink(missing_ok=True)
            cp_result = "advanced" if max_updated and max_updated != old_cursor else "unchanged"
            src_yaml_err2: "str | None" = None
            try:
                _write_source_yaml_v2(
                    output_dir, "jira", account, account_id, canonical_scope,
                    migrate=migrate_source,
                )
            except ValueError as exc:
                src_yaml_err2 = str(exc)
            return SyncResult(
                scope=canonical_scope, mode=mode,
                issues_read=issues_read, issues_mapped=issues_mapped,
                net_new_records=n_written, placement=placement,
                checkpoint_result=cp_result,
                error_code="source_yaml_conflict" if src_yaml_err2 else None,
                error_detail=src_yaml_err2,
                exit_code=2 if src_yaml_err2 else 0,
            )

    except RemError as exc:
        return SyncResult(scope=canonical_scope, mode=mode,
                          error_code="lock", error_detail=str(exc), exit_code=2)
    except ValueError as exc:
        if "already running" in str(exc).lower():
            return SyncResult(
                scope=canonical_scope, mode=mode,
                error_code="lock", error_detail=str(exc), exit_code=2,
            )
        return SyncResult(
            scope=canonical_scope, mode=mode,
            error_code="persistence", error_detail=str(exc), exit_code=2,
        )
    except Exception as exc:  # noqa: BLE001
        return SyncResult(
            scope=canonical_scope, mode=mode,
            error_code="internal_error", error_detail=str(exc), exit_code=2,
        )

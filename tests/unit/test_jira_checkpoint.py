"""
Jira checkpoint persistence, scope hash, and scope lock unit tests (F13FCAKE-19, F13FCAKE-1).

Covers: load() / save() roundtrip, validation, atomic write, no-secrets guarantee,
matches() identity checking, _scope_hash() determinism and collision-avoidance, and
_scope_lock() acquire/release/contention behaviour.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from connectonion.useful_tools.jira_checkpoint import (
    JiraCheckpoint,
    _scope_hash,
    _scope_lock,
)

# ------------------------------------------------------------------ fixtures

SCOPE_PROJECT = {"type": "project", "project": "ALPHA"}
SCOPE_PROJECT_KEYS = {"type": "project+keys", "project": "ALPHA", "keys": ["ALPHA-1", "ALPHA-2"]}


def _make_checkpoint(**overrides) -> JiraCheckpoint:
    """Return a minimal valid JiraCheckpoint; any field can be overridden."""
    defaults = dict(
        version=1,
        source="jira",
        account="https://example.atlassian.net",
        authorised_identity={"accountId": "abc123"},
        canonical_scope=SCOPE_PROJECT,
        cursor=None,
        last_key=None,
        commit_time=None,
        overlap_snapshot_hashes={},
    )
    defaults.update(overrides)
    return JiraCheckpoint(**defaults)


def _checkpoint_dict(**overrides) -> dict:
    """Return a dict that load() should accept as valid."""
    base = {
        "version": 1,
        "source": "jira",
        "account": "https://example.atlassian.net",
        "authorised_identity": {"accountId": "abc123"},
        "canonical_scope": SCOPE_PROJECT,
        "cursor": None,
        "last_key": None,
        "commit_time": None,
        "overlap_snapshot_hashes": {},
    }
    base.update(overrides)
    return base


# ================================================================== load() tests

class TestLoad:
    def test_missing_file_returns_none(self, tmp_path):
        """load() returns None when the checkpoint file does not exist (first import)."""
        path = tmp_path / "checkpoint.json"
        result = JiraCheckpoint.load(path)
        assert result is None

    def test_valid_checkpoint_loads(self, tmp_path):
        """A structurally valid checkpoint file round-trips through load()."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(
            cursor="2026-10-01T12:00:00Z",
            last_key="ALPHA-5",
            commit_time="2026-10-01T12:01:00Z",
            overlap_snapshot_hashes={"deadbeef12345678": "2026-10-01T12:00:00Z"},
        )
        path.write_text(json.dumps(data), encoding="utf-8")

        cp = JiraCheckpoint.load(path)

        assert cp is not None
        assert cp.version == 1
        assert cp.source == "jira"
        assert cp.account == "https://example.atlassian.net"
        assert cp.authorised_identity == {"accountId": "abc123"}
        assert cp.canonical_scope == SCOPE_PROJECT
        assert cp.cursor == "2026-10-01T12:00:00Z"
        assert cp.last_key == "ALPHA-5"
        assert cp.commit_time == "2026-10-01T12:01:00Z"
        assert cp.overlap_snapshot_hashes == {"deadbeef12345678": "2026-10-01T12:00:00Z"}

    def test_invalid_json_raises(self, tmp_path):
        """Corrupted JSON raises ValueError with recovery guidance."""
        path = tmp_path / "checkpoint.json"
        path.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(ValueError, match="invalid JSON"):
            JiraCheckpoint.load(path)

    def test_non_object_json_raises(self, tmp_path):
        """A JSON array at the top level raises ValueError."""
        path = tmp_path / "checkpoint.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError, match="not a JSON object"):
            JiraCheckpoint.load(path)

    def test_missing_required_field_raises(self, tmp_path):
        """A checkpoint missing any required field raises ValueError naming that field."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict()
        del data["cursor"]
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="missing required fields"):
            JiraCheckpoint.load(path)

    def test_wrong_version_raises(self, tmp_path):
        """An unsupported version number raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(version=99)
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="unsupported version"):
            JiraCheckpoint.load(path)

    def test_wrong_source_raises(self, tmp_path):
        """A checkpoint with source != 'jira' raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(source="onenote")
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="source="):
            JiraCheckpoint.load(path)

    def test_authorised_identity_missing_account_id_raises(self, tmp_path):
        """authorised_identity without a non-empty accountId string raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(authorised_identity={"displayName": "Alice"})
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="accountId"):
            JiraCheckpoint.load(path)

    def test_authorised_identity_empty_account_id_raises(self, tmp_path):
        """authorised_identity with an empty accountId raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(authorised_identity={"accountId": ""})
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="accountId"):
            JiraCheckpoint.load(path)

    def test_canonical_scope_missing_type_raises(self, tmp_path):
        """canonical_scope without a 'type' key raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(canonical_scope={"project": "ALPHA"})
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="canonical_scope"):
            JiraCheckpoint.load(path)

    def test_overlap_hashes_not_dict_raises(self, tmp_path):
        """overlap_snapshot_hashes that is not a dict raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(overlap_snapshot_hashes=["hash1"])
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="overlap_snapshot_hashes"):
            JiraCheckpoint.load(path)

    def test_credential_field_at_top_level_raises(self, tmp_path):
        """A top-level field named 'token' raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict()
        data["token"] = "should-not-be-here"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="forbidden field"):
            JiraCheckpoint.load(path)

    def test_email_in_authorised_identity_raises(self, tmp_path):
        """An 'email' field inside authorised_identity raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(
            authorised_identity={"accountId": "abc123", "email": "user@example.com"}
        )
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="forbidden field"):
            JiraCheckpoint.load(path)

    def test_recovery_guidance_in_error_messages(self, tmp_path):
        """All load() errors include recovery guidance."""
        path = tmp_path / "checkpoint.json"
        path.write_text("{bad json", encoding="utf-8")

        with pytest.raises(ValueError) as exc_info:
            JiraCheckpoint.load(path)

        message = str(exc_info.value)
        assert "preserve" in message
        assert "separate --state" in message
        assert "delete" not in message.lower()
        assert "--full" not in message
        assert path.read_text() == "{bad json"

    def test_overlap_hashes_absent_defaults_to_empty(self, tmp_path):
        """A checkpoint file without overlap_snapshot_hashes loads with an empty dict."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict()
        del data["overlap_snapshot_hashes"]
        path.write_text(json.dumps(data), encoding="utf-8")

        cp = JiraCheckpoint.load(path)
        assert cp is not None
        assert cp.overlap_snapshot_hashes == {}

    def test_account_non_string_raises(self, tmp_path):
        """'account' that is not a non-empty string raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(account=42)
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="account"):
            JiraCheckpoint.load(path)

    def test_extra_field_in_authorised_identity_raises(self, tmp_path):
        """authorised_identity with extra fields beyond accountId raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(
            authorised_identity={"accountId": "abc123", "displayName": "Alice"}
        )
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="forbidden"):
            JiraCheckpoint.load(path)

    def test_cursor_wrong_type_raises(self, tmp_path):
        """cursor that is neither None nor a string raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(cursor=12345)
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="cursor"):
            JiraCheckpoint.load(path)

    def test_last_key_wrong_type_raises(self, tmp_path):
        """last_key that is neither None nor a string raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(last_key=False)
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="last_key"):
            JiraCheckpoint.load(path)

    def test_commit_time_wrong_type_raises(self, tmp_path):
        """commit_time that is neither None nor a string raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(commit_time={"ts": "2026-01-01"})
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="commit_time"):
            JiraCheckpoint.load(path)

    def test_overlap_hashes_non_string_value_raises(self, tmp_path):
        """overlap_snapshot_hashes with a non-string value raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(overlap_snapshot_hashes={"aabbccdd": 999})
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="overlap_snapshot_hashes"):
            JiraCheckpoint.load(path)

    def test_nested_credential_in_canonical_scope_raises(self, tmp_path):
        """A credential-like field nested inside canonical_scope raises ValueError."""
        path = tmp_path / "checkpoint.json"
        data = _checkpoint_dict(
            canonical_scope={"type": "project", "project": "ALPHA", "token": "secret"}
        )
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="forbidden field"):
            JiraCheckpoint.load(path)

    def test_excessive_nesting_raises_value_error(self, tmp_path):
        """A canonical_scope with more than 8 levels of nesting raises ValueError (fail closed)."""
        path = tmp_path / "checkpoint.json"
        # Build a 10-level deep nested dict inside canonical_scope.
        deep = {}
        cursor = deep
        for _ in range(10):
            cursor["child"] = {}
            cursor = cursor["child"]
        data = _checkpoint_dict(canonical_scope={"type": "project", "project": "ALPHA", "meta": deep})
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="excessive nesting depth"):
            JiraCheckpoint.load(path)


# ================================================================== save() tests

class TestSave:
    def test_save_creates_file(self, tmp_path):
        """save() creates the checkpoint file."""
        cp = _make_checkpoint()
        path = tmp_path / "sub" / "checkpoint.json"

        cp.save(path)

        assert path.exists()

    def test_save_creates_parent_directories(self, tmp_path):
        """save() creates all missing parent directories."""
        cp = _make_checkpoint()
        path = tmp_path / "a" / "b" / "c" / "checkpoint.json"

        cp.save(path)

        assert path.exists()

    def test_save_no_temp_file_left_behind(self, tmp_path):
        """save() leaves no .tmp file after a successful write."""
        cp = _make_checkpoint()
        path = tmp_path / "checkpoint.json"

        cp.save(path)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Unexpected temp files: {tmp_files}"

    def test_save_roundtrip(self, tmp_path):
        """load(save(cp)) produces an equal checkpoint."""
        cp = _make_checkpoint(
            cursor="2026-10-10T09:00:00Z",
            last_key="ALPHA-42",
            commit_time="2026-10-10T09:01:00Z",
            overlap_snapshot_hashes={"aabbccdd11223344": "2026-10-10T09:00:00Z"},
        )
        path = tmp_path / "checkpoint.json"

        cp.save(path)
        loaded = JiraCheckpoint.load(path)

        assert loaded is not None
        assert loaded.version == cp.version
        assert loaded.source == cp.source
        assert loaded.account == cp.account
        assert loaded.authorised_identity == cp.authorised_identity
        assert loaded.canonical_scope == cp.canonical_scope
        assert loaded.cursor == cp.cursor
        assert loaded.last_key == cp.last_key
        assert loaded.commit_time == cp.commit_time
        assert loaded.overlap_snapshot_hashes == cp.overlap_snapshot_hashes

    def test_save_is_valid_json(self, tmp_path):
        """The file written by save() is valid, parseable JSON."""
        cp = _make_checkpoint()
        path = tmp_path / "checkpoint.json"

        cp.save(path)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data["source"] == "jira"

    def test_no_secrets_in_saved_file(self, tmp_path):
        """The saved checkpoint file contains no tokens, passwords, or email addresses."""
        cp = _make_checkpoint(account="https://example.atlassian.net")
        path = tmp_path / "checkpoint.json"

        cp.save(path)

        contents = path.read_text(encoding="utf-8")
        for forbidden in ("token", "password", "secret", "refresh_token",
                          "access_token", "email", "emailAddress"):
            # The key "accountId" is allowed; check that no forbidden key is present as a key
            parsed = json.loads(contents)
            assert forbidden not in parsed, f"Forbidden field {forbidden!r} found in checkpoint"
            if "authorised_identity" in parsed:
                assert forbidden not in parsed["authorised_identity"], (
                    f"Forbidden field {forbidden!r} found in authorised_identity"
                )

    def test_save_overwrites_existing_file(self, tmp_path):
        """save() replaces an existing checkpoint file atomically."""
        cp_old = _make_checkpoint(cursor="2026-09-01T00:00:00Z")
        cp_new = _make_checkpoint(cursor="2026-10-01T00:00:00Z")
        path = tmp_path / "checkpoint.json"

        cp_old.save(path)
        cp_new.save(path)

        loaded = JiraCheckpoint.load(path)
        assert loaded is not None
        assert loaded.cursor == "2026-10-01T00:00:00Z"

    def test_save_rejects_forbidden_field_in_authorised_identity(self, tmp_path):
        """save() raises ValueError when authorised_identity contains a forbidden field."""
        cp = _make_checkpoint(
            authorised_identity={"accountId": "abc123", "email": "user@example.com"}
        )
        path = tmp_path / "checkpoint.json"

        with pytest.raises(ValueError, match="forbidden"):
            cp.save(path)

        assert not path.exists(), "No file should have been written when validation fails"

    def test_save_rejects_cursor_wrong_type(self, tmp_path):
        """save() raises ValueError when cursor is not None or a string."""
        cp = _make_checkpoint(cursor=12345)
        path = tmp_path / "checkpoint.json"

        with pytest.raises(ValueError, match="cursor"):
            cp.save(path)

        assert not path.exists()

    def test_save_rejects_overlap_hashes_non_string_value(self, tmp_path):
        """save() raises ValueError when overlap_snapshot_hashes has a non-string value."""
        cp = _make_checkpoint(overlap_snapshot_hashes={"aabbccdd": 42})
        path = tmp_path / "checkpoint.json"

        with pytest.raises(ValueError, match="overlap_snapshot_hashes"):
            cp.save(path)

        assert not path.exists()

    def test_save_rejects_nested_token_in_canonical_scope(self, tmp_path):
        """save() raises ValueError when a credential-like field appears in canonical_scope."""
        cp = _make_checkpoint(
            canonical_scope={"type": "project", "project": "ALPHA", "token": "secret"}
        )
        path = tmp_path / "checkpoint.json"

        with pytest.raises(ValueError, match="forbidden"):
            cp.save(path)

        assert not path.exists()

    @pytest.mark.skipif(os.name == "nt", reason="directory fsync is POSIX-only")
    def test_save_fsyncs_parent_directory_on_posix(self, tmp_path):
        """On POSIX, save() fsyncs the parent directory after os.replace()."""
        cp = _make_checkpoint()
        path = tmp_path / "checkpoint.json"

        fsync_calls = []
        real_fsync = os.fsync

        def recording_fsync(fd):
            fsync_calls.append(fd)
            return real_fsync(fd)

        with patch("os.fsync", recording_fsync):
            cp.save(path)

        # At least two fsyncs: one for the file content, one for the parent directory.
        assert len(fsync_calls) >= 2, (
            f"Expected at least 2 os.fsync() calls (file + parent dir), got {len(fsync_calls)}"
        )


# ================================================================== matches() tests

class TestMatches:
    def test_matches_valid_identity_passes(self):
        """matches() does not raise when all identity fields match."""
        cp = _make_checkpoint()
        cp.matches(
            source="jira",
            account="https://example.atlassian.net",
            account_id="abc123",
            canonical_scope=SCOPE_PROJECT,
        )

    def test_matches_wrong_source_raises(self):
        """matches() raises ValueError when source differs."""
        cp = _make_checkpoint(source="jira")
        with pytest.raises(ValueError, match="source"):
            cp.matches(
                source="onenote",
                account="https://example.atlassian.net",
                account_id="abc123",
                canonical_scope=SCOPE_PROJECT,
            )

    def test_matches_wrong_account_raises(self):
        """matches() raises ValueError when account URL differs."""
        cp = _make_checkpoint(account="https://example.atlassian.net")
        with pytest.raises(ValueError, match="account"):
            cp.matches(
                source="jira",
                account="https://other.atlassian.net",
                account_id="abc123",
                canonical_scope=SCOPE_PROJECT,
            )

    def test_matches_wrong_account_id_raises(self):
        """matches() raises ValueError when authorised_identity.accountId differs."""
        cp = _make_checkpoint(authorised_identity={"accountId": "abc123"})
        with pytest.raises(ValueError, match="accountId"):
            cp.matches(
                source="jira",
                account="https://example.atlassian.net",
                account_id="xyz789",
                canonical_scope=SCOPE_PROJECT,
            )

    def test_matches_wrong_scope_raises(self):
        """matches() raises ValueError when canonical_scope differs."""
        cp = _make_checkpoint(canonical_scope=SCOPE_PROJECT)
        with pytest.raises(ValueError, match="canonical_scope"):
            cp.matches(
                source="jira",
                account="https://example.atlassian.net",
                account_id="abc123",
                canonical_scope=SCOPE_PROJECT_KEYS,
            )

    def test_matches_error_lists_all_mismatches(self):
        """matches() includes every mismatch in the error message."""
        cp = _make_checkpoint(
            source="jira",
            account="https://example.atlassian.net",
            authorised_identity={"accountId": "abc123"},
            canonical_scope=SCOPE_PROJECT,
        )
        with pytest.raises(ValueError) as exc_info:
            cp.matches(
                source="onenote",
                account="https://other.atlassian.net",
                account_id="xyz789",
                canonical_scope=SCOPE_PROJECT_KEYS,
            )
        msg = str(exc_info.value)
        assert "source" in msg
        assert "account" in msg
        assert "accountId" in msg
        assert "canonical_scope" in msg

    def test_matches_error_includes_recovery_guidance(self):
        """matches() error messages include recovery guidance."""
        cp = _make_checkpoint()
        with pytest.raises(ValueError) as exc_info:
            cp.matches(
                source="onenote",
                account="https://example.atlassian.net",
                account_id="abc123",
                canonical_scope=SCOPE_PROJECT,
            )
        assert "co jira sync" in str(exc_info.value)


# ================================================================== scope_hash() tests

class TestScopeHash:
    def test_scope_hash_length_is_16(self):
        """scope_hash() returns exactly 16 hexadecimal characters."""
        cp = _make_checkpoint()
        h = cp.scope_hash()
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_scope_hash_is_deterministic(self):
        """The same checkpoint identity always produces the same hash."""
        cp1 = _make_checkpoint()
        cp2 = _make_checkpoint()
        assert cp1.scope_hash() == cp2.scope_hash()

    def test_scope_hash_differs_by_source(self):
        """Different sources produce different hashes (no collision)."""
        h1 = _scope_hash("jira", "https://example.atlassian.net", "abc123", SCOPE_PROJECT)
        h2 = _scope_hash("onenote", "https://example.atlassian.net", "abc123", SCOPE_PROJECT)
        assert h1 != h2

    def test_scope_hash_differs_by_account(self):
        """Different account URLs produce different hashes."""
        h1 = _scope_hash("jira", "https://example.atlassian.net", "abc123", SCOPE_PROJECT)
        h2 = _scope_hash("jira", "https://other.atlassian.net", "abc123", SCOPE_PROJECT)
        assert h1 != h2

    def test_scope_hash_differs_by_account_id(self):
        """Different accountIds produce different hashes."""
        h1 = _scope_hash("jira", "https://example.atlassian.net", "abc123", SCOPE_PROJECT)
        h2 = _scope_hash("jira", "https://example.atlassian.net", "xyz789", SCOPE_PROJECT)
        assert h1 != h2

    def test_scope_hash_differs_by_scope(self):
        """Different canonical scopes produce different hashes."""
        h1 = _scope_hash("jira", "https://example.atlassian.net", "abc123", SCOPE_PROJECT)
        h2 = _scope_hash("jira", "https://example.atlassian.net", "abc123", SCOPE_PROJECT_KEYS)
        assert h1 != h2

    def test_scope_hash_scope_key_order_invariant(self):
        """Scope dicts with the same keys in different order produce the same hash."""
        scope_a = {"project": "ALPHA", "type": "project"}
        scope_b = {"type": "project", "project": "ALPHA"}
        h1 = _scope_hash("jira", "https://example.atlassian.net", "abc123", scope_a)
        h2 = _scope_hash("jira", "https://example.atlassian.net", "abc123", scope_b)
        assert h1 == h2

    def test_scope_hash_matches_checkpoint_scope_hash(self):
        """JiraCheckpoint.scope_hash() agrees with the standalone _scope_hash()."""
        cp = _make_checkpoint()
        expected = _scope_hash(
            cp.source,
            cp.account,
            cp.authorised_identity["accountId"],
            cp.canonical_scope,
        )
        assert cp.scope_hash() == expected


# ================================================================== _scope_lock() tests

class TestScopeLock:
    def test_lock_acquires_and_releases(self, tmp_path):
        """_scope_lock() acquires without error and the context block executes."""
        state_dir = tmp_path / ".state"
        ran = []

        with _scope_lock(state_dir, "abcdef1234567890"):
            ran.append(True)

        assert ran == [True]

    def test_lock_creates_lock_file(self, tmp_path):
        """_scope_lock() creates the lock file inside state_dir."""
        state_dir = tmp_path / ".state"
        scope_hash = "abcdef1234567890"

        with _scope_lock(state_dir, scope_hash):
            assert (state_dir / f"{scope_hash}.lock").exists()

    def test_lock_creates_state_dir_if_absent(self, tmp_path):
        """_scope_lock() creates state_dir when it does not exist."""
        state_dir = tmp_path / "nested" / ".state"
        assert not state_dir.exists()

        with _scope_lock(state_dir, "abcdef1234567890"):
            pass

        assert state_dir.exists()

    def test_lock_releases_on_exception(self, tmp_path):
        """_scope_lock() releases the lock even when the body raises."""
        state_dir = tmp_path / ".state"
        scope_hash = "abcdef1234567890"

        with pytest.raises(RuntimeError, match="intentional"):
            with _scope_lock(state_dir, scope_hash):
                raise RuntimeError("intentional")

        # After the exception the lock must be released; verify by acquiring again.
        acquired = []
        with _scope_lock(state_dir, scope_hash):
            acquired.append(True)
        assert acquired == [True]

    def test_lock_contention_raises_value_error(self, tmp_path):
        """A second concurrent process on the same scope raises ValueError immediately."""
        state_dir = tmp_path / ".state"
        scope_hash = "abcdef1234567890"

        # Simulate OS lock contention by patching the low-level call.
        if os.name == "nt":
            import msvcrt
            def _raise_locked(fd, mode, nbytes):
                if mode == msvcrt.LK_NBLCK:
                    raise OSError("locked by another process")
                # Allow LK_UNLCK through so the finally clause doesn't also fail.
                msvcrt.locking(fd, msvcrt.LK_UNLCK, nbytes)

            with patch("msvcrt.locking", _raise_locked):
                with pytest.raises(ValueError, match="already running"):
                    with _scope_lock(state_dir, scope_hash):
                        pass
        else:
            import fcntl
            def _raise_locked(fd, operation):
                if operation & fcntl.LOCK_NB:
                    raise BlockingIOError("locked by another process")
                # Allow LOCK_UN through.

            with patch("fcntl.flock", _raise_locked):
                with pytest.raises(ValueError, match="already running"):
                    with _scope_lock(state_dir, scope_hash):
                        pass

    def test_different_scope_hashes_do_not_contend(self, tmp_path):
        """Two different scope hashes can be locked simultaneously in sequence."""
        state_dir = tmp_path / ".state"
        results = []

        with _scope_lock(state_dir, "aaaaaaaaaaaaaaaa"):
            results.append("first")

        with _scope_lock(state_dir, "bbbbbbbbbbbbbbbb"):
            results.append("second")

        assert results == ["first", "second"]

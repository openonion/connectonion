"""Single-writer review/activation state, stored outside the authored workspace.

State is authenticated with a runtime key. A project may propose build bytes;
it cannot activate an app by writing JSON containing an approved status. The
operator must keep this state root outside author-tool filesystem authority.
"""
import hashlib
import hmac
import json
import math
import os
import secrets
import stat
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .bundle import BundleError, canonical, capture_bundle

MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_HISTORY = 100


class RuntimeErrorState(RuntimeError):
    """The requested activation cannot be performed with trustworthy state."""


@dataclass(frozen=True)
class ReviewResult:
    status: str
    findings: list[dict]
    model: str
    execution_id: str
    cost_usd: float

    def validate(self):
        if (self.status not in {'approved', 'blocked'} or not isinstance(self.findings, list)
                or len(self.findings) > 100 or not isinstance(self.model, str) or not self.model
                or not isinstance(self.execution_id, str) or not self.execution_id
                or not isinstance(self.cost_usd, (int, float))
                or not math.isfinite(self.cost_usd) or self.cost_usd < 0):
            raise RuntimeErrorState('Malformed reviewer result')
        for item in self.findings:
            if (not isinstance(item, dict) or set(item) != {'severity', 'message', 'path'}
                    or item['severity'] not in {'blocker', 'warning', 'info'}
                    or not isinstance(item['message'], str) or not 1 <= len(item['message']) <= 4000
                    or not isinstance(item['path'], str) or len(item['path']) > 512):
                raise RuntimeErrorState('Malformed reviewer finding')
        if len(canonical({'findings': self.findings})) > 128 * 1024:
            raise RuntimeErrorState('Reviewer findings exceed limit')
        return self.status == 'approved' and not any(
            item['severity'] == 'blocker' for item in self.findings)


def _private_directory(path: Path):
    if path.is_symlink():
        raise RuntimeErrorState('Runtime state directory cannot be a symlink')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        os.chmod(path, 0o700)


def _read_private(path: Path, limit: int) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except OSError as exc:
        raise RuntimeErrorState('Runtime state cannot be read') from exc
    with os.fdopen(fd, 'rb') as stream:
        record = os.fstat(stream.fileno())
        if not stat.S_ISREG(record.st_mode) or record.st_size > limit:
            raise RuntimeErrorState('Runtime state is not a bounded regular file')
        if os.name != 'nt' and record.st_mode & 0o077:
            raise RuntimeErrorState('Runtime state permissions must be private')
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise RuntimeErrorState('Runtime state exceeds limit')
    return data


def atomic_private(path: Path, data: bytes):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def writer_lock(state_dir: Path, name: str = 'writer.lock'):
    """An OS lock survives neither crash nor restart; a stale file is harmless."""
    _private_directory(state_dir)
    fd = os.open(state_dir / name, os.O_CREAT | os.O_RDWR |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'r+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b'0')
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeErrorState('Control Center writer is busy') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class ControlCenterRuntime:
    """Review and publish a proposed build, preserving the last approved revision."""

    def __init__(self, state_dir: Path, *, reviewer, uploader, policy: str,
                 available=None, clock=time.time):
        self.state_dir = Path(state_dir)
        self.reviewer, self.uploader = reviewer, uploader
        self.policy, self.clock = policy, clock
        self.available = available or (lambda app: False)
        _private_directory(self.state_dir)
        with writer_lock(self.state_dir):
            key_path = self.state_dir / 'integrity.key'
            if not key_path.exists():
                atomic_private(key_path, secrets.token_bytes(32))
            self._key = _read_private(key_path, 32)
            if len(self._key) != 32:
                raise RuntimeErrorState('Invalid runtime integrity key')

    def _load(self):
        path = self.state_dir / 'state.json'
        if not path.exists():
            return {'schema': 1, 'active': None, 'history': [], 'status': 'empty',
                    'error': None, 'updates': {}}
        try:
            envelope = json.loads(_read_private(path, MAX_STATE_BYTES))
            data, signature = envelope['data'], envelope['mac']
            expected = hmac.new(self._key, canonical(data), hashlib.sha256).hexdigest()
            if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
                raise ValueError('signature')
            if data['schema'] != 1 or not isinstance(data['history'], list):
                raise ValueError('schema')
            return data
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeErrorState('Runtime state integrity verification failed') from exc

    def _save(self, state):
        def removable():
            active = (state.get('active') or {}).get('revision')
            # Keep the newest approval for the active revision and the newest
            # attempt, including a still-running attempt updated by this caller.
            protected = next((i for i in range(len(state['history']) - 1, -1, -1)
                              if state['history'][i].get('revision') == active
                              and state['history'][i].get('status') == 'approved'), None)
            return next((i for i in range(len(state['history']) - 1) if i != protected), None)
        while True:
            mac = hmac.new(self._key, canonical(state), hashlib.sha256).hexdigest()
            data = canonical({'data': state, 'mac': mac})
            if len(data) <= MAX_STATE_BYTES and len(state['history']) <= MAX_HISTORY:
                break
            index = removable()
            if index is None:
                raise RuntimeErrorState('Runtime state exceeds limit')
            state['history'].pop(index)
        atomic_private(self.state_dir / 'state.json', data)

    def snapshot(self) -> dict:
        """Public review/history state contains no runtime authentication key."""
        return self._load()

    def update(self, build_dir: Path, *, entry='index.html', capabilities=(),
               trigger='manual', event_id=None) -> dict:
        """The only code-update path: capture → review → upload → activation."""
        with writer_lock(self.state_dir):
            state = self._load()
            bundle = capture_bundle(build_dir, entry=entry, capabilities=capabilities)
            if (state['active'] and state['active']['revision'] == bundle.revision
                    and state['active']['review'].get('policy') == self.policy):
                return {**state, 'status': 'unchanged'}
            attempt = {'id': str(uuid.uuid4()), 'revision': bundle.revision,
                       'started_at': self.clock(), 'policy': self.policy,
                       'trigger': trigger, 'event_id': event_id, 'status': 'reviewing'}
            state.update(status='reviewing', error=None)
            state['history'].append(attempt)
            self._save(state)
            try:
                result = self.reviewer(bundle)
                if not isinstance(result, ReviewResult):
                    raise RuntimeErrorState('Malformed reviewer result')
                approved = result.validate()
                attempt.update(findings=result.findings, reviewer_model=result.model,
                               reviewer_execution=result.execution_id, cost_usd=result.cost_usd)
                if not approved:
                    return self._block(state, attempt, 'review_blocked', 'Review requires changes')
                current = capture_bundle(build_dir, entry=entry, capabilities=capabilities)
                if current.revision != bundle.revision:
                    return self._block(state, attempt, 'source_changed', 'Build changed during review')
                uploaded = self.uploader(bundle)
                self._validate_upload(uploaded, bundle.revision)
                # An edit during upload must also return to review, even though
                # the already-uploaded snapshot itself remains immutable.
                if capture_bundle(build_dir, entry=entry, capabilities=capabilities).revision != bundle.revision:
                    return self._block(state, attempt, 'source_changed', 'Build changed during upload')
                descriptor = {'schema': 'connectonion.control-app/1', 'sdk_version': '1',
                    'revision': bundle.revision, 'url': uploaded['url'],
                    'capabilities': list(bundle.capabilities),
                    'review': {'status': 'approved', 'review_id': attempt['id'],
                               'reviewed_at': datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(),
                               'policy': self.policy}}
                attempt.update(status='approved', finished_at=self.clock(), app=descriptor,
                               manifest=bundle.manifest)
                state.update(active=descriptor, status='approved', error=None)
                self._save(state)
                return state
            except Exception as exc:
                # Store a bounded error code, never remote response bodies or credentials.
                return self._block(state, attempt, 'update_failed',
                                   f'{type(exc).__name__}: review or upload did not complete')

    def _validate_upload(self, uploaded, revision):
        if not isinstance(uploaded, dict) or uploaded.get('revision') != revision:
            raise RuntimeErrorState('Uploaded revision does not match reviewed bytes')
        url = urlsplit(uploaded.get('url', ''))
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise RuntimeErrorState('Upload did not return an immutable HTTPS URL')

    def _block(self, state, attempt, code, message):
        attempt.update(status='blocked', finished_at=self.clock())
        state.update(status='blocked', error={'code': code, 'message': message})
        self._save(state)
        return state

    def rollback(self, revision: str) -> dict:
        """Only a retained approval under the current policy is eligible."""
        with writer_lock(self.state_dir):
            state = self._load()
            candidates = [record for record in state['history']
                          if record['revision'] == revision and record['status'] == 'approved']
            if not candidates:
                raise RuntimeErrorState('Revision has no retained approval')
            record = candidates[-1]
            if record['policy'] != self.policy:
                raise RuntimeErrorState('Revision requires review under current policy')
            if not self.available(record['app']):
                raise RuntimeErrorState('Approved artifact is unavailable; rollback refused')
            state.update(active=record['app'], status='approved', error=None)
            state['last_rollback'] = {'revision': revision, 'at': self.clock()}
            self._save(state)
            return state

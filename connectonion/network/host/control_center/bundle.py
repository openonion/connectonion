"""Capture complete build output once; review and upload share these exact bytes.

The wire manifest is deliberately independent of archive order, timestamps and
platform MIME databases. Both Core and the static host verify it from scratch.
"""
import base64
import binascii
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

SCHEMA = 'connectonion.control-bundle/1'
MAX_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILES = 256
CAPABILITIES = frozenset({'camera', 'microphone', 'geolocation', 'clipboard-read',
                          'clipboard-write', 'fullscreen'})
TYPES = {'.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
         '.mjs': 'text/javascript', '.json': 'application/json',
         '.wasm': 'application/wasm', '.svg': 'image/svg+xml', '.png': 'image/png',
         '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
         '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff': 'font/woff',
         '.woff2': 'font/woff2', '.txt': 'text/plain', '.map': 'application/json'}


class BundleError(ValueError):
    """The build cannot be represented as a bounded immutable static app."""


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_path(path: str) -> str:
    if (not isinstance(path, str) or len(path) > 512 or not path
            or any(not part or part.startswith('.') or not re.fullmatch(
                r'[A-Za-z0-9_@()\[\] .-]+', part) for part in path.split('/'))):
        raise BundleError('Invalid public bundle path (hidden files are not allowed)')
    return path


def media_type(path: str) -> str:
    return TYPES.get(Path(path).suffix.lower(), 'application/octet-stream')


def _manifest(files, entry, capabilities):
    validate_path(entry)
    if entry not in files or media_type(entry) != 'text/html':
        raise BundleError('The entry must name an included HTML file')
    if (not isinstance(capabilities, (list, tuple))
            or any(not isinstance(c, str) or c not in CAPABILITIES for c in capabilities)):
        raise BundleError('Unsupported browser capability')
    return {'schema': SCHEMA, 'entry': entry, 'capabilities': sorted(set(capabilities)),
            'files': [{'path': path, 'sha256': digest(data), 'bytes': len(data),
                       'media_type': media_type(path)} for path, data in sorted(files.items())]}


@dataclass(frozen=True)
class Bundle:
    """Immutable content captured before review; no later source reads for upload."""
    files: Mapping[str, bytes]
    entry: str = 'index.html'
    capabilities: tuple[str, ...] = ()

    def __post_init__(self):
        copied = dict(self.files)
        if not 1 <= len(copied) <= MAX_FILES:
            raise BundleError('Bundle file count exceeds limit')
        total = 0
        for path, data in copied.items():
            validate_path(path)
            if not isinstance(data, bytes) or len(data) > MAX_FILE_BYTES:
                raise BundleError('Bundle file exceeds byte limit')
            total += len(data)
        if total > MAX_BYTES:
            raise BundleError('Bundle exceeds total byte limit')
        _manifest(copied, self.entry, self.capabilities)
        object.__setattr__(self, 'files', MappingProxyType(copied))
        object.__setattr__(self, 'capabilities', tuple(sorted(set(self.capabilities))))

    @property
    def manifest(self) -> dict:
        return _manifest(self.files, self.entry, self.capabilities)

    @property
    def revision(self) -> str:
        return 'sha256:' + digest(canonical(self.manifest))

    def to_wire(self) -> dict:
        return {'manifest': self.manifest, 'revision': self.revision,
                'files': {path: base64.b64encode(data).decode('ascii')
                          for path, data in self.files.items()}}

    @classmethod
    def from_wire(cls, value: dict) -> 'Bundle':
        if not isinstance(value, dict) or set(value) != {'manifest', 'revision', 'files'}:
            raise BundleError('Invalid bundle envelope')
        manifest, encoded = value['manifest'], value['files']
        if (not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA
                or not isinstance(encoded, dict) or not 1 <= len(encoded) <= MAX_FILES):
            raise BundleError('Invalid bundle manifest or file count')
        files, total = {}, 0
        for path, data in encoded.items():
            validate_path(path)
            if not isinstance(data, str) or len(data) > (MAX_FILE_BYTES + 2) // 3 * 4:
                raise BundleError('Encoded file exceeds byte limit')
            try:
                decoded = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise BundleError('Invalid base64 file') from exc
            total += len(decoded)
            if total > MAX_BYTES:
                raise BundleError('Bundle exceeds total byte limit')
            files[path] = decoded
        bundle = cls(files, manifest.get('entry'), manifest.get('capabilities'))
        if canonical(bundle.manifest) != canonical(manifest) or bundle.revision != value['revision']:
            raise BundleError('Manifest, revision and actual file bytes do not match')
        return bundle


def _read_file(path: Path | str, remaining: int, *, dir_fd=None) -> bytes:
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    try:
        fd = os.open(path, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise BundleError('Bundle file changed or could not be opened') from exc
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise BundleError('Only regular bundle files are supported')
        limit = min(remaining, MAX_FILE_BYTES)
        if before.st_size > limit:
            raise BundleError('Bundle byte limit exceeded')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    stamp = lambda s: (s.st_ino, s.st_dev, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if stamp(before) != stamp(after) or len(data) != before.st_size:
        raise BundleError('Bundle file changed during capture; build again')
    return data


def capture_bundle(root: Path, *, entry: str = 'index.html', capabilities=(),
                   max_bytes: int = MAX_BYTES, max_files: int = MAX_FILES) -> Bundle:
    """Capture a finished static build. Source projects/dependency folders are not builds."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise BundleError('Build root must be a directory, not a symlink')
    files, total = {}, 0
    if os.name != 'nt':
        # Pin every directory before enumerating/opening its children. A rename
        # cannot redirect a later open through an attacker-replaced ancestor.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        absolute = root.absolute()
        fd = os.open(absolute.anchor, flags)
        try:
            for part in absolute.parts[1:]:
                if part in {'.', '..'}:
                    raise BundleError('Build root must have a canonical path')
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            directories = 0
            def walk(directory_fd, prefix='', depth=0):
                nonlocal total, directories
                directories += 1
                if directories > 512 or depth > 32:
                    raise BundleError('Bundle directory limit exceeded')
                before = os.fstat(directory_fd)
                with os.scandir(directory_fd) as entries:
                    names = []
                    for item in entries:
                        names.append(item.name)
                        if len(names) > MAX_FILES + 512:
                            raise BundleError('Bundle directory entry limit exceeded')
                for name in sorted(names):
                    relative = prefix + name
                    validate_path(relative)
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        raise BundleError('Bundle symlinks are not allowed')
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(name, flags, dir_fd=directory_fd)
                        try:
                            walk(child, relative + '/', depth + 1)
                        finally:
                            os.close(child)
                    else:
                        if len(files) >= min(max_files, MAX_FILES):
                            raise BundleError('Bundle file count exceeds limit')
                        data = _read_file(name, min(max_bytes, MAX_BYTES) - total, dir_fd=directory_fd)
                        files[relative] = data
                        total += len(data)
                after = os.fstat(directory_fd)
                if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
                    raise BundleError('Bundle directory changed during capture; build again')
            walk(fd)
        except OSError as exc:
            raise BundleError('Bundle directory changed or contains a symlink') from exc
        finally:
            os.close(fd)
    else:
        # Windows lacks POSIX descriptor-relative directory traversal. Operators
        # must keep build ancestors outside concurrent untrusted write authority.
        for directory, dirs, names in os.walk(root, followlinks=False):
            for name in sorted(dirs + names):
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                if path.is_symlink():
                    raise BundleError('Bundle symlinks are not allowed')
                validate_path(relative)
                if name in dirs:
                    continue
                if len(files) >= min(max_files, MAX_FILES):
                    raise BundleError('Bundle file count exceeds limit')
                data = _read_file(path, min(max_bytes, MAX_BYTES) - total)
                files[relative] = data
                total += len(data)
    return Bundle(files, entry, tuple(capabilities))

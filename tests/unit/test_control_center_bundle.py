"""A revision identifies every served byte, including framework chunks."""
import base64
import json
from pathlib import Path

import pytest

from connectonion.network.host.control_center.bundle import Bundle, BundleError, capture_bundle


def app(root):
    root.mkdir()
    (root / 'index.html').write_text('<script src="assets/app.js"></script>')
    (root / 'assets').mkdir()
    (root / 'assets/app.js').write_text('document.body.dataset.ready = "yes"')
    return root


def test_revision_is_deterministic_and_covers_every_file(tmp_path):
    root = app(tmp_path / 'app')
    first = capture_bundle(root)
    assert first == capture_bundle(root)
    (root / 'assets/app.js').write_text('changed')
    assert capture_bundle(root).revision != first.revision
    assert first.files['assets/app.js'] != b'changed'
    assert Bundle.from_wire(first.to_wire()).revision == first.revision


def test_wire_rejects_changed_bytes_missing_and_extra_files(tmp_path):
    bundle = capture_bundle(app(tmp_path / 'app'))
    for change in ('bytes', 'missing', 'extra', 'revision'):
        wire = bundle.to_wire()
        if change == 'bytes':
            wire['files']['assets/app.js'] = base64.b64encode(b'other').decode()
        elif change == 'missing':
            del wire['files']['assets/app.js']
        elif change == 'extra':
            wire['files']['evil.js'] = base64.b64encode(b'other').decode()
        else:
            wire['revision'] = 'sha256:' + '0' * 64
        with pytest.raises(BundleError):
            Bundle.from_wire(wire)


@pytest.mark.parametrize('path', ['../secret', '/absolute', 'a/../b', 'a//b', 'a\\b', '.env', 'nested/.secret', 'a%2fb', 'a?x', 'a#x'])
def test_manifest_paths_cannot_escape_or_disclose_hidden_files(tmp_path, path):
    wire = capture_bundle(app(tmp_path / 'app')).to_wire()
    wire['manifest']['files'][0]['path'] = path
    with pytest.raises(BundleError):
        Bundle.from_wire(wire)


def test_symlinks_and_private_dotfiles_are_rejected(tmp_path):
    root = app(tmp_path / 'app')
    (root / 'leak').symlink_to(tmp_path / 'outside')
    with pytest.raises(BundleError, match='symlink'):
        capture_bundle(root)
    (root / 'leak').unlink()
    (root / '.env').write_text('SYNTHETIC=test')
    with pytest.raises(BundleError, match='path'):
        capture_bundle(root)


def test_file_and_total_bounds_are_checked_before_read(tmp_path):
    root = app(tmp_path / 'app')
    with pytest.raises(BundleError, match='limit'):
        capture_bundle(root, max_bytes=2)
    with pytest.raises(BundleError, match='limit'):
        capture_bundle(root, max_files=1)


def test_requires_entry_and_rejects_unknown_capabilities(tmp_path):
    root = app(tmp_path / 'app')
    with pytest.raises(BundleError, match='entry'):
        capture_bundle(root, entry='absent.html')
    with pytest.raises(BundleError, match='capabilit'):
        capture_bundle(root, capabilities=['arbitrary'])


def test_capture_fails_if_file_changes_during_read(tmp_path, monkeypatch):
    import os
    root = app(tmp_path / 'app')
    original = os.fstat
    calls = 0
    inode = (root / 'index.html').stat().st_ino
    def changed(fd):
        nonlocal calls
        stat = original(fd)
        if stat.st_ino == inode:
            calls += 1
        if stat.st_ino == inode and calls == 2:
            (root / 'index.html').write_text('a race')
            return original(fd)
        return stat
    monkeypatch.setattr(os, 'fstat', changed)
    with pytest.raises(BundleError, match='changed'):
        capture_bundle(root)


def test_replacing_an_ancestor_with_a_symlink_cannot_capture_outside_bytes(tmp_path, monkeypatch):
    import os
    root = app(tmp_path / 'app')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'app.js').write_text('private synthetic value')
    original = os.open
    replaced = False
    def swap(path, flags, *args, **kwargs):
        nonlocal replaced
        if str(path) in {'assets', str(root / 'assets')} and not replaced:
            replaced = True
            (root / 'assets').rename(root / 'saved')
            (root / 'assets').symlink_to(outside, target_is_directory=True)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', swap)
    with pytest.raises(BundleError):
        capture_bundle(root)
    assert replaced

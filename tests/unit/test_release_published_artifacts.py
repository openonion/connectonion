"""The release retry cannot make GitHub assets disagree with PyPI."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "verify_published_artifacts",
    ROOT / ".github/scripts/verify_published_artifacts.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Response(io.BytesIO):
    pass


def _wheel(path: Path, content: bytes, timestamp=(2024, 1, 1, 0, 0, 0)) -> bytes:
    with zipfile.ZipFile(path, "w") as archive:
        item = zipfile.ZipInfo("connectonion/example.py", timestamp)
        archive.writestr(item, content)
    return path.read_bytes()


def _sdist(path: Path, content: bytes, mtime: int = 1) -> bytes:
    with tarfile.open(path, "w:gz") as archive:
        item = tarfile.TarInfo("connectonion-1.6.0/connectonion/example.py")
        item.size = len(content)
        item.mtime = mtime
        archive.addfile(item, io.BytesIO(content))
    return path.read_bytes()


def test_logical_archive_comparison_ignores_container_timestamps(tmp_path):
    local_wheel = tmp_path / "local.whl"
    remote_wheel = tmp_path / "remote.whl"
    _wheel(local_wheel, b"same", (2024, 1, 1, 0, 0, 0))
    _wheel(remote_wheel, b"same", (2025, 2, 2, 0, 0, 0))

    MODULE.assert_same_archive_contents(local_wheel, remote_wheel)


def test_logical_archive_comparison_rejects_changed_code(tmp_path):
    local_wheel = tmp_path / "local.whl"
    remote_wheel = tmp_path / "remote.whl"
    _wheel(local_wheel, b"reviewed")
    _wheel(remote_wheel, b"different")

    with pytest.raises(MODULE.ArtifactError, match="differs from the reviewed build"):
        MODULE.assert_same_archive_contents(local_wheel, remote_wheel)


def test_recovery_downloads_exact_verified_pypi_bytes(tmp_path):
    version = "1.6.0"
    local_dir = tmp_path / "dist"
    output_dir = tmp_path / "published"
    local_dir.mkdir()
    wheel_name = f"connectonion-{version}-py3-none-any.whl"
    sdist_name = f"connectonion-{version}.tar.gz"
    wheel_bytes = _wheel(local_dir / wheel_name, b"reviewed")
    sdist_bytes = _sdist(local_dir / sdist_name, b"reviewed")
    file_urls = {
        wheel_name: f"https://files.pythonhosted.org/packages/{wheel_name}",
        sdist_name: f"https://files.pythonhosted.org/packages/{sdist_name}",
    }
    blobs = {file_urls[wheel_name]: wheel_bytes, file_urls[sdist_name]: sdist_bytes}
    metadata = {
        "urls": [
            {
                "filename": name,
                "url": url,
                "digests": {"sha256": hashlib.sha256(blobs[url]).hexdigest()},
            }
            for name, url in file_urls.items()
        ]
    }

    def opener(url, timeout):
        del timeout
        if url.endswith("/json"):
            return Response(json.dumps(metadata).encode())
        return Response(blobs[url])

    recovered = MODULE.recover_published_artifacts(
        version,
        local_dir,
        output_dir,
        opener=opener,
    )

    assert {path.name for path in recovered} == {wheel_name, sdist_name}
    assert (output_dir / wheel_name).read_bytes() == wheel_bytes
    assert (output_dir / sdist_name).read_bytes() == sdist_bytes


def test_recovery_rejects_an_extra_or_missing_pypi_file(tmp_path):
    metadata = {"urls": []}

    def opener(url, timeout):
        del url, timeout
        return Response(json.dumps(metadata).encode())

    with pytest.raises(MODULE.ArtifactError, match="expected wheel/sdist pair"):
        MODULE.recover_published_artifacts(
            "1.6.0",
            tmp_path / "dist",
            tmp_path / "published",
            opener=opener,
        )

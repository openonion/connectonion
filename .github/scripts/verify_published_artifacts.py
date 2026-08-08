"""Recover the exact PyPI files and prove they match the reviewed local build."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
PYPI_HOST = "files.pythonhosted.org"


class ArtifactError(RuntimeError):
    """The published artifacts are unsafe or disagree with the reviewed build."""


def _read_url(
    url: str,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ArtifactError(f"refusing non-HTTPS artifact URL: {url}")

    with opener(url, timeout=30) as response:  # type: ignore[attr-defined]
        data = response.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ArtifactError(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes: {url}")
    return data


def _archive_contents(path: Path) -> dict[str, tuple[str, bytes]]:
    """Compare logical archive contents while ignoring zip/tar timestamps."""

    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            contents: dict[str, tuple[str, bytes]] = {}
            seen: set[str] = set()
            for item in archive.infolist():
                if item.filename in seen:
                    raise ArtifactError(
                        f"duplicate archive member {item.filename!r} in {path}"
                    )
                seen.add(item.filename)
                if not item.is_dir():
                    contents[item.filename] = ("file", archive.read(item))
            return contents

    if path.name.endswith(".tar.gz"):
        contents: dict[str, tuple[str, bytes]] = {}
        with tarfile.open(path, "r:gz") as archive:
            seen: set[str] = set()
            for item in archive.getmembers():
                if item.name in seen:
                    raise ArtifactError(
                        f"duplicate archive member {item.name!r} in {path}"
                    )
                seen.add(item.name)
                if item.isfile():
                    extracted = archive.extractfile(item)
                    if extracted is None:
                        raise ArtifactError(f"cannot read {item.name} from {path}")
                    contents[item.name] = ("file", extracted.read())
                elif item.issym() or item.islnk():
                    contents[item.name] = (f"link:{item.linkname}", b"")
        return contents

    raise ArtifactError(f"unsupported release artifact: {path.name}")


def assert_same_archive_contents(local: Path, published: Path) -> None:
    local_contents = _archive_contents(local)
    published_contents = _archive_contents(published)
    if local_contents == published_contents:
        return

    local_names = set(local_contents)
    published_names = set(published_contents)
    added = sorted(published_names - local_names)
    removed = sorted(local_names - published_names)
    changed = sorted(
        name
        for name in local_names & published_names
        if local_contents[name] != published_contents[name]
    )
    raise ArtifactError(
        f"published {published.name} differs from the reviewed build "
        f"(added={added[:5]}, removed={removed[:5]}, changed={changed[:5]})"
    )


def recover_published_artifacts(
    version: str,
    local_dir: Path,
    output_dir: Path,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> list[Path]:
    wheel = f"connectonion-{version}-py3-none-any.whl"
    sdist = f"connectonion-{version}.tar.gz"
    expected = {wheel, sdist}

    metadata_url = f"https://pypi.org/pypi/connectonion/{version}/json"
    try:
        metadata = json.loads(_read_url(metadata_url, opener=opener))
    except (json.JSONDecodeError, urllib.error.URLError) as exc:
        raise ArtifactError(f"cannot read PyPI metadata for {version}: {exc}") from exc

    entries = {entry.get("filename"): entry for entry in metadata.get("urls", [])}
    available = {name for name in entries if isinstance(name, str)}
    if available != expected:
        raise ArtifactError(
            f"PyPI files for {version} are not the expected wheel/sdist pair: {sorted(available)}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    recovered: list[Path] = []
    for name in sorted(expected):
        entry = entries[name]
        url = entry.get("url", "")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != PYPI_HOST:
            raise ArtifactError(f"unexpected PyPI file host for {name}: {url}")

        data = _read_url(url, opener=opener)
        expected_digest = entry.get("digests", {}).get("sha256")
        actual_digest = hashlib.sha256(data).hexdigest()
        if not expected_digest or actual_digest != expected_digest:
            raise ArtifactError(f"PyPI SHA256 mismatch for {name}")

        destination = output_dir / name
        destination.write_bytes(data)
        assert_same_archive_contents(local_dir / name, destination)
        recovered.append(destination)

    return recovered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--local-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    recovered = recover_published_artifacts(
        args.version,
        args.local_dir,
        args.output_dir,
    )
    for path in recovered:
        print(f"verified published artifact: {path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate a release's visual-evidence manifest (#1124).

Usage: python scripts/check_release_visuals.py vX.Y.Z

Exit 0 when docs/releases/assets/vX.Y.Z/manifest.yml is a valid reviewed
set (or a valid explicit exemption); exit 1 with the reason named otherwise.
Absence is a failure on purpose: "we forgot" and "nothing visible changed"
must not look the same — the second one is spelled no_visual_change with a
reviewed reason.

Run by the release checklist (VERSIONING.md), not by CI on every push:
whether a release has user-visible changes is a human judgement this script
checks the *recording* of, not one it can make itself.
"""

import sys
from pathlib import Path

MAX_IMAGE_BYTES = 2_000_000
REQUIRED_IMAGE_FIELDS = ("file", "alt", "caption", "scenario", "viewport",
                         "commit", "source_run")


def fail(reason: str) -> "None":
    print(f"FAIL: {reason}")
    sys.exit(1)


def check(version: str, root: Path = None) -> None:
    import yaml

    root = root or Path(__file__).resolve().parent.parent
    asset_dir = root / "docs" / "releases" / "assets" / version
    manifest_path = asset_dir / "manifest.yml"

    if not manifest_path.exists():
        fail(f"{manifest_path} does not exist. Every release records its "
             f"visual evidence — a backend-only patch records "
             f"no_visual_change with a reviewed reason instead.")

    manifest = yaml.safe_load(manifest_path.read_text()) or {}

    if manifest.get("version") != version:
        fail(f"manifest says version {manifest.get('version')!r}, "
             f"checking {version!r}")

    exemption = manifest.get("no_visual_change")
    images = manifest.get("images")

    if exemption and images:
        fail("manifest claims BOTH no_visual_change and images — pick one")
    if not exemption and not images:
        fail("manifest has neither images nor a no_visual_change reason")

    if exemption:
        if not isinstance(exemption, str) or len(exemption.strip()) < 10:
            fail("no_visual_change must be a real reviewed reason, not a nod")
        print(f"OK: {version} exempt — {exemption.strip()}")
        return

    for entry in images:
        missing = [f for f in REQUIRED_IMAGE_FIELDS if not entry.get(f)]
        if missing:
            fail(f"image entry {entry.get('file', '<unnamed>')!r} missing: "
                 f"{', '.join(missing)}")
        image = asset_dir / entry["file"]
        if not image.exists():
            fail(f"{image} is listed but does not exist")
        size = image.stat().st_size
        if size == 0:
            fail(f"{image} is empty")
        if size > MAX_IMAGE_BYTES:
            fail(f"{image} is {size} bytes; optimize below {MAX_IMAGE_BYTES}")

    print(f"OK: {version} — {len(images)} reviewed image(s)")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].startswith("v"):
        print(__doc__)
        sys.exit(2)
    check(sys.argv[1])

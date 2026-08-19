"""The release-visual manifest check (#1124): a UI release cannot skip
evidence, and a backend-only patch can use the explicit exemption — the
dry-run pair the issue's workflow requirements name.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from check_release_visuals import check  # noqa: E402


def _write_manifest(root: Path, version: str, text: str) -> Path:
    asset_dir = root / "docs" / "releases" / "assets" / version
    asset_dir.mkdir(parents=True)
    (asset_dir / "manifest.yml").write_text(text)
    return asset_dir


def test_a_missing_manifest_fails_instead_of_shrugging(tmp_path, capsys):
    with pytest.raises(SystemExit):
        check("v9.9.9", root=tmp_path)
    assert "does not exist" in capsys.readouterr().out


def test_a_backend_only_patch_uses_the_explicit_exemption(tmp_path):
    _write_manifest(tmp_path, "v9.9.9",
                    'version: v9.9.9\n'
                    'no_visual_change: "backend-only patch: network bounds"\n')
    check("v9.9.9", root=tmp_path)  # must not raise


def test_a_nod_is_not_a_reviewed_exemption(tmp_path, capsys):
    _write_manifest(tmp_path, "v9.9.9",
                    'version: v9.9.9\nno_visual_change: "n/a"\n')
    with pytest.raises(SystemExit):
        check("v9.9.9", root=tmp_path)
    assert "reviewed reason" in capsys.readouterr().out


def test_claiming_both_exemption_and_images_fails(tmp_path, capsys):
    _write_manifest(tmp_path, "v9.9.9",
                    'version: v9.9.9\n'
                    'no_visual_change: "backend-only patch: nothing visible"\n'
                    'images:\n  - file: x.webp\n')
    with pytest.raises(SystemExit):
        check("v9.9.9", root=tmp_path)
    assert "pick one" in capsys.readouterr().out


def test_a_ui_release_needs_every_field_and_a_real_file(tmp_path, capsys):
    asset_dir = _write_manifest(tmp_path, "v9.9.9",
                                'version: v9.9.9\n'
                                'images:\n'
                                '  - file: hero.webp\n'
                                '    alt: "the hero"\n'
                                '    caption: "what changed"\n'
                                '    scenario: "operator opens dashboard"\n'
                                '    viewport: "1440x900, light"\n'
                                '    commit: abc123\n'
                                '    source_run: "https://example.com/run/1"\n')
    # listed but absent
    with pytest.raises(SystemExit):
        check("v9.9.9", root=tmp_path)
    assert "does not exist" in capsys.readouterr().out

    # empty file is as bad as no file
    (asset_dir / "hero.webp").write_bytes(b"")
    with pytest.raises(SystemExit):
        check("v9.9.9", root=tmp_path)
    assert "empty" in capsys.readouterr().out

    # a real file passes
    (asset_dir / "hero.webp").write_bytes(b"RIFF....WEBP")
    check("v9.9.9", root=tmp_path)


def test_missing_metadata_names_the_fields(tmp_path, capsys):
    asset_dir = _write_manifest(tmp_path, "v9.9.9",
                                'version: v9.9.9\n'
                                'images:\n  - file: hero.webp\n')
    (asset_dir / "hero.webp").write_bytes(b"RIFF")
    with pytest.raises(SystemExit):
        check("v9.9.9", root=tmp_path)
    out = capsys.readouterr().out
    for field in ("alt", "caption", "scenario", "viewport", "commit", "source_run"):
        assert field in out


def test_the_version_in_the_manifest_must_match(tmp_path, capsys):
    _write_manifest(tmp_path, "v9.9.9",
                    'version: v1.0.0\nno_visual_change: "backend-only patch"\n')
    with pytest.raises(SystemExit):
        check("v9.9.9", root=tmp_path)
    assert "v1.0.0" in capsys.readouterr().out

"""Unit tests for connectonion.cli.commands.fanout."""

from pathlib import Path

import pytest

from connectonion.cli.commands import fanout


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Redirect fanout.HOME to a tmp dir so tests don't touch the real ~/."""
    monkeypatch.setattr(fanout, "HOME", tmp_path)
    return tmp_path


@pytest.fixture
def bundle(tmp_path):
    """A bundle with two skills, only one has frontmatter."""
    b = tmp_path / "bundle"
    skills = b / "skills"
    (skills / "alpha").mkdir(parents=True)
    (skills / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: Alpha skill\n---\nBody A\n",
        encoding="utf-8",
    )
    (skills / "beta").mkdir(parents=True)
    (skills / "beta" / "SKILL.md").write_text(
        "no frontmatter here\n",
        encoding="utf-8",
    )
    return b


def test_detected_tools_only_lists_existing_dirs(fake_home):
    assert fanout.detected_tools() == []
    (fake_home / ".claude").mkdir()
    (fake_home / ".cursor").mkdir()
    assert set(fanout.detected_tools()) == {"claude", "cursor"}


def test_install_claude_symlinks_whole_bundle(fake_home, bundle):
    n = fanout.install_claude(bundle, "alice")
    plugin = fake_home / ".claude" / "plugins" / "alice"
    assert n == 1
    assert plugin.is_symlink()
    assert plugin.resolve() == bundle.resolve()


def test_install_skill_dirs_creates_per_skill_symlinks(fake_home, bundle):
    n = fanout.install_skill_dirs(bundle, "alice", "codex")
    assert n == 2  # alpha + beta both have SKILL.md
    skills_dir = fake_home / ".codex" / "skills"
    assert (skills_dir / "alice-alpha").is_symlink()
    assert (skills_dir / "alice-beta").is_symlink()
    assert (skills_dir / "alice-alpha").resolve() == (bundle / "skills" / "alpha").resolve()


def test_install_cursor_rewrites_frontmatter_skips_bodies_without_it(fake_home, bundle):
    n = fanout.install_cursor(bundle, "alice")
    rules = fake_home / ".cursor" / "rules"
    assert n == 1  # beta has no frontmatter, skipped
    mdc = rules / "alice-alpha.mdc"
    assert mdc.is_file()
    content = mdc.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "description: Alpha skill" in content
    assert "alwaysApply: false" in content
    assert "Body A" in content
    assert not (rules / "alice-beta.mdc").exists()


def test_install_kiro_copies_flat_md(fake_home, bundle):
    n = fanout.install_kiro(bundle, "alice")
    steering = fake_home / ".kiro" / "steering"
    assert n == 2
    assert (steering / "alice-alpha.md").is_file()
    assert (steering / "alice-beta.md").is_file()
    # Plain copy, not a symlink
    assert not (steering / "alice-alpha.md").is_symlink()


def test_install_all_only_fans_into_detected_tools(fake_home, bundle):
    (fake_home / ".claude").mkdir()
    (fake_home / ".codex").mkdir()
    # No cursor, no kiro, no openclaw

    results = fanout.install_all(bundle, "alice")

    assert set(results.keys()) == {"claude", "codex"}
    assert results["claude"] == 1
    assert results["codex"] == 2


def test_install_is_idempotent(fake_home, bundle):
    (fake_home / ".claude").mkdir()
    fanout.install_all(bundle, "alice")
    fanout.install_all(bundle, "alice")  # second run must not error
    assert (fake_home / ".claude" / "plugins" / "alice").is_symlink()


def test_install_replaces_existing_directory_with_symlink(fake_home, bundle):
    """If a plain directory exists where we want a symlink, we replace it."""
    target = fake_home / ".claude" / "plugins" / "alice"
    target.mkdir(parents=True)
    (target / "stale.txt").write_text("old", encoding="utf-8")

    fanout.install_claude(bundle, "alice")

    assert target.is_symlink()
    assert target.resolve() == bundle.resolve()


def test_uninstall_all_removes_every_per_tool_install(fake_home, bundle):
    for d in (".claude", ".codex", ".openclaw", ".cursor", ".kiro"):
        (fake_home / d).mkdir()
    fanout.install_all(bundle, "alice")

    fanout.uninstall_all("alice")

    assert not (fake_home / ".claude" / "plugins" / "alice").exists()
    assert list((fake_home / ".codex" / "skills").iterdir()) == []
    assert list((fake_home / ".openclaw" / "skills").iterdir()) == []
    assert list((fake_home / ".cursor" / "rules").iterdir()) == []
    assert list((fake_home / ".kiro" / "steering").iterdir()) == []


def test_uninstall_all_with_skill_names_only_removes_listed(fake_home, bundle):
    (fake_home / ".codex").mkdir()
    fanout.install_skill_dirs(bundle, "alice", "codex")
    skills = fake_home / ".codex" / "skills"
    assert (skills / "alice-alpha").exists()
    assert (skills / "alice-beta").exists()

    fanout.uninstall_all("alice", skill_names=["alpha"])

    assert not (skills / "alice-alpha").exists()
    assert (skills / "alice-beta").exists()

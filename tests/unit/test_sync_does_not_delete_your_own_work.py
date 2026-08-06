"""`co sub sync` rmtree's a real directory in its way, without asking.

`_replace` is how every per-tool install lands:

    if dst.is_symlink() or dst.exists():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst.symlink_to(src)

Replacing a symlink this module made is right — that is what a re-sync is. But a
real directory at that path is not ours, and it is deleted with everything in it.
Measured:

    ~/.codex/skills/mapper-candidate-mapping/
        SKILL.md      hand-written
        notes.md      hand-written

    co sub sync 0x…            (alias "mapper", skill "candidate-mapping")

    -> the path is now a symlink into ~/.co/subs/mapper/skills/candidate-mapping
    -> notes.md is gone

No malice needed and no warning given. The `{alias}-{name}` prefix makes a
collision unlikely, not impossible: an alias is the publisher's chosen string, so
two publishers can pick the same one, and a subscriber may have organised their
own skills with the same naming.

A symlink we own is replaced as before. A real directory stops the install for
that skill, says which path and why, and leaves it alone — losing a skill from a
sync is recoverable by re-syncing; losing the notes underneath it is not.
"""

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    from connectonion.cli.commands import fanout

    monkeypatch.setattr(fanout, "HOME", tmp_path)
    return fanout, tmp_path


def _bundle(tmp_path, *names):
    root = tmp_path / "bundle"
    for name in names:
        skill = root / "skills" / name
        skill.mkdir(parents=True)
        # With frontmatter: install_cursor skips a body that has none, so a
        # bundle without it makes the cursor cases pass for the wrong reason.
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: from the relay\n---\n\n"
            f"# {name} from the relay\n", encoding="utf-8")
    return root


class TestARealDirectoryIsNotDeleted:

    def test_the_files_in_it_survive(self, home, tmp_path):
        fanout, root = home
        mine = root / ".codex" / "skills" / "mapper-thing"
        mine.mkdir(parents=True)
        (mine / "notes.md").write_text("hand-written\n", encoding="utf-8")

        fanout.install_skill_dirs(_bundle(tmp_path, "thing"), "mapper", "codex")

        assert (mine / "notes.md").exists(), "a sync deleted work it did not create"

    def test_it_is_not_turned_into_a_symlink(self, home, tmp_path):
        fanout, root = home
        mine = root / ".codex" / "skills" / "mapper-thing"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("# mine\n", encoding="utf-8")

        fanout.install_skill_dirs(_bundle(tmp_path, "thing"), "mapper", "codex")

        assert not mine.is_symlink()

    def test_the_contents_are_still_mine(self, home, tmp_path):
        fanout, root = home
        mine = root / ".codex" / "skills" / "mapper-thing"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("# mine\n", encoding="utf-8")

        fanout.install_skill_dirs(_bundle(tmp_path, "thing"), "mapper", "codex")

        assert (mine / "SKILL.md").read_text() == "# mine\n"

    def test_it_is_not_counted_as_installed(self, home, tmp_path):
        fanout, root = home
        (root / ".codex" / "skills" / "mapper-thing").mkdir(parents=True)

        n = fanout.install_skill_dirs(_bundle(tmp_path, "thing"), "mapper", "codex")

        assert n == 0

    def test_the_operator_is_told_which_path(self, home, tmp_path, capsys):
        fanout, root = home
        (root / ".codex" / "skills" / "mapper-thing").mkdir(parents=True)

        fanout.install_skill_dirs(_bundle(tmp_path, "thing"), "mapper", "codex")

        assert "mapper-thing" in capsys.readouterr().out


class TestTheOtherSkillsStillInstall:
    """One blocked path must not stop the bundle."""

    def test_a_second_skill_lands(self, home, tmp_path):
        fanout, root = home
        (root / ".codex" / "skills" / "mapper-blocked").mkdir(parents=True)

        n = fanout.install_skill_dirs(
            _bundle(tmp_path, "blocked", "fine"), "mapper", "codex"
        )

        assert n == 1
        assert (root / ".codex" / "skills" / "mapper-fine").is_symlink()


class TestOurOwnSymlinkIsStillReplaced:
    """A re-sync has to keep working; that is what _replace is for."""

    def test_a_stale_symlink_is_repointed(self, home, tmp_path):
        fanout, root = home
        old = tmp_path / "old-target"
        old.mkdir()
        dst = root / ".codex" / "skills" / "mapper-thing"
        dst.parent.mkdir(parents=True)
        dst.symlink_to(old)

        bundle = _bundle(tmp_path, "thing")
        fanout.install_skill_dirs(bundle, "mapper", "codex")

        assert dst.resolve() == (bundle / "skills" / "thing").resolve()

    def test_a_broken_symlink_is_replaced(self, home, tmp_path):
        fanout, root = home
        dst = root / ".codex" / "skills" / "mapper-thing"
        dst.parent.mkdir(parents=True)
        dst.symlink_to(tmp_path / "nowhere")

        bundle = _bundle(tmp_path, "thing")
        fanout.install_skill_dirs(bundle, "mapper", "codex")

        assert dst.is_symlink()
        assert dst.exists()

    def test_a_fresh_install_still_works(self, home, tmp_path):
        fanout, root = home
        (root / ".codex" / "skills").mkdir(parents=True)

        n = fanout.install_skill_dirs(_bundle(tmp_path, "thing"), "mapper", "codex")

        assert n == 1


class TestRemoveOnlyRemovesWhatWeInstalled:
    """The same hazard on the way out.

    `uninstall_all` matches by name prefix and rmtree's whatever it finds, so
    `co sub remove` would delete the very directory the install had just refused
    to touch — a user's own work, on a command about someone else's skills.
    """

    def test_a_real_directory_is_left_alone(self, home, tmp_path):
        fanout, root = home
        mine = root / ".codex" / "skills" / "mapper-thing"
        mine.mkdir(parents=True)
        (mine / "notes.md").write_text("hand-written\n", encoding="utf-8")

        fanout.uninstall_all("mapper")

        assert (mine / "notes.md").exists()

    def test_our_symlink_is_removed(self, home, tmp_path):
        fanout, root = home
        target = tmp_path / "bundle-skill"
        target.mkdir()
        link = root / ".codex" / "skills" / "mapper-thing"
        link.parent.mkdir(parents=True)
        link.symlink_to(target)

        fanout.uninstall_all("mapper")

        assert not link.exists() and not link.is_symlink()

    def test_our_generated_files_are_removed(self, home, tmp_path):
        fanout, root = home
        rule = root / ".cursor" / "rules" / "mapper-thing.mdc"
        rule.parent.mkdir(parents=True)
        rule.write_text(f"---\n# {fanout.OURS_MARKER}\n---\n", encoding="utf-8")

        fanout.uninstall_all("mapper")

        assert not rule.exists()

    def test_a_hand_written_rule_with_our_name_survives_removal(self, home):
        """The prefix is a guess about ownership; the marker is not."""
        fanout, root = home
        rule = root / ".cursor" / "rules" / "mapper-thing.mdc"
        rule.parent.mkdir(parents=True)
        rule.write_text("---\ndescription: MY RULE\n---\nmine\n", encoding="utf-8")

        fanout.uninstall_all("mapper")

        assert rule.exists()
        assert "MY RULE" in rule.read_text()

    def test_a_hand_written_kiro_doc_survives_removal(self, home):
        fanout, root = home
        doc = root / ".kiro" / "steering" / "mapper-thing.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("MY STEERING DOC\n", encoding="utf-8")

        fanout.uninstall_all("mapper")

        assert doc.exists()

    def test_a_real_claude_plugin_dir_survives_removal(self, home, tmp_path):
        fanout, root = home
        mine = root / ".claude" / "plugins" / "mapper"
        mine.mkdir(parents=True)
        (mine / "mine.md").write_text("hand-written\n", encoding="utf-8")

        fanout.uninstall_all("mapper")

        assert (mine / "mine.md").exists()


class TestTheMarkerStaysOutOfTheirFormat:
    """The marker has to be recognisable to us and invisible to the tool.

    It first went inside the .mdc frontmatter as `# connectonion:subscription`.
    YAML treats that as a comment so nothing broke — but it is our string inside
    someone else's header, and it only works while Cursor reads that block with a
    YAML parser. The body's first line does the same job without the bet.
    """

    def test_the_frontmatter_is_only_cursors_keys(self, home, tmp_path):
        import yaml

        fanout, root = home
        (root / ".cursor" / "rules").mkdir(parents=True)

        fanout.install_cursor(_bundle(tmp_path, "thing"), "mapper")
        text = (root / ".cursor" / "rules" / "mapper-thing.mdc").read_text()
        front = text.split("---")[1]

        assert set(yaml.safe_load(front)) == {"description", "alwaysApply"}
        assert fanout.OURS_MARKER not in front

    def test_the_marker_is_still_findable(self, home, tmp_path):
        fanout, root = home
        (root / ".cursor" / "rules").mkdir(parents=True)

        fanout.install_cursor(_bundle(tmp_path, "thing"), "mapper")
        text = (root / ".cursor" / "rules" / "mapper-thing.mdc").read_text()

        assert fanout.OURS_MARKER in text

    def test_the_skill_body_survives_intact(self, home, tmp_path):
        fanout, root = home
        (root / ".cursor" / "rules").mkdir(parents=True)

        fanout.install_cursor(_bundle(tmp_path, "thing"), "mapper")
        text = (root / ".cursor" / "rules" / "mapper-thing.mdc").read_text()

        assert "# thing from the relay" in text


class TestEveryInstallPathIsGuarded:
    """Three of five went through _replace; cursor and kiro write files directly.

    Fixing only the symlink paths left the same hole in the two that do not use
    them — `co sub sync` overwrote a hand-written ~/.cursor/rules/<alias>-<name>.mdc
    and ~/.kiro/steering/<alias>-<name>.md with the publisher's content. Measured
    before this: both files lost their contents.
    """

    def test_the_claude_plugin_dir_is_not_destroyed(self, home, tmp_path):
        fanout, root = home
        mine = root / ".claude" / "plugins" / "mapper"
        mine.mkdir(parents=True)
        (mine / "mine.md").write_text("hand-written\n", encoding="utf-8")

        fanout.install_claude(_bundle(tmp_path, "thing"), "mapper")

        assert (mine / "mine.md").exists()

    def test_a_hand_written_cursor_rule_survives(self, home, tmp_path):
        fanout, root = home
        rules = root / ".cursor" / "rules"
        rules.mkdir(parents=True)
        mine = rules / "mapper-thing.mdc"
        mine.write_text("---\ndescription: MY RULE\n---\nmy careful rule\n",
                        encoding="utf-8")

        n = fanout.install_cursor(_bundle(tmp_path, "thing"), "mapper")

        assert "MY RULE" in mine.read_text()
        assert n == 0

    def test_a_hand_written_kiro_doc_survives(self, home, tmp_path):
        fanout, root = home
        steering = root / ".kiro" / "steering"
        steering.mkdir(parents=True)
        mine = steering / "mapper-thing.md"
        mine.write_text("MY STEERING DOC\n", encoding="utf-8")

        n = fanout.install_kiro(_bundle(tmp_path, "thing"), "mapper")

        assert "MY STEERING" in mine.read_text()
        assert n == 0

    def test_a_file_we_wrote_before_is_still_refreshed(self, home, tmp_path):
        """Re-sync must keep working: our own output carries a marker."""
        fanout, root = home
        rules = root / ".cursor" / "rules"
        rules.mkdir(parents=True)

        bundle = _bundle(tmp_path, "thing")
        assert fanout.install_cursor(bundle, "mapper") == 1
        assert fanout.install_cursor(bundle, "mapper") == 1

    def test_kiro_re_sync_still_works(self, home, tmp_path):
        fanout, root = home
        (root / ".kiro" / "steering").mkdir(parents=True)

        bundle = _bundle(tmp_path, "thing")
        assert fanout.install_kiro(bundle, "mapper") == 1
        assert fanout.install_kiro(bundle, "mapper") == 1

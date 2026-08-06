"""`co sub sync` says it installed a skill it did not install.

From the real run that exposed it, an agent announcing one skill it never
published:

    candidate-mapping: skipped — the publisher did not publish its body
    ✓ Subscribed to naturewill-mapping
      mirrored 0 skill(s) → ~/.co/subs/naturewill-mapping
      claude: installed 1 skill(s)          <- there are none
      codex: installed 0 skill(s)
      cursor: installed 0 skill(s)

Zero skills mirrored, and one reported. `install_claude` links the whole bundle
as a single Claude plugin and returns a constant:

    def install_claude(bundle: Path, alias: str) -> int:
        _replace(HOME / ".claude" / "plugins" / alias, bundle)
        return 1

The link is real and correct — that is how a Claude plugin is installed. The
number is a plugin count reported under a heading that says skills, so it reads
as "one skill is now available" when nothing is. The dir it points at is empty:

    ~/.co/subs/naturewill-mapping/skills/     (nothing in it)
    ~/.claude/skills/                          no naturewill entry

Every other tool in the fanout counts skills, so this one line is the odd one
out rather than a different convention.
"""

import pytest


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """A subscription bundle with a controllable number of real skills."""
    from connectonion.cli.commands import fanout

    monkeypatch.setattr(fanout, "HOME", tmp_path / "home")
    (tmp_path / "home" / ".claude").mkdir(parents=True)

    root = tmp_path / "bundle"
    (root / "skills").mkdir(parents=True)
    (root / "agent.json").write_text("{}", encoding="utf-8")

    def add_skill(name):
        skill = root / "skills" / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: d\n---\n\n# {name}\n", encoding="utf-8"
        )

    return fanout, root, add_skill


class TestTheCountIsSkills:

    def test_an_empty_bundle_installs_none(self, bundle):
        fanout, root, _ = bundle

        assert fanout.install_claude(root, "alias") == 0

    def test_one_skill_counts_one(self, bundle):
        fanout, root, add_skill = bundle
        add_skill("alpha")

        assert fanout.install_claude(root, "alias") == 1

    def test_three_skills_count_three(self, bundle):
        fanout, root, add_skill = bundle
        for name in ("alpha", "beta", "gamma"):
            add_skill(name)

        assert fanout.install_claude(root, "alias") == 3

    def test_a_directory_without_a_skill_md_is_not_counted(self, bundle):
        fanout, root, add_skill = bundle
        add_skill("alpha")
        (root / "skills" / "notes").mkdir()

        assert fanout.install_claude(root, "alias") == 1


class TestThePluginIsStillInstalled:
    """The count was wrong; the link was right. It has to stay."""

    def test_the_link_is_made_even_with_no_skills(self, bundle):
        fanout, root, _ = bundle

        fanout.install_claude(root, "alias")

        assert (fanout.HOME / ".claude" / "plugins" / "alias").exists()

    def test_it_points_at_the_bundle(self, bundle):
        fanout, root, add_skill = bundle
        add_skill("alpha")

        fanout.install_claude(root, "alias")
        installed = fanout.HOME / ".claude" / "plugins" / "alias"

        assert (installed / "skills" / "alpha" / "SKILL.md").exists()


class TestItAgreesWithTheOtherTools:
    """codex counts skills; claude reported plugins under the same heading."""

    def test_both_report_the_same_number(self, bundle):
        fanout, root, add_skill = bundle
        for name in ("alpha", "beta"):
            add_skill(name)
        (fanout.HOME / ".codex" / "skills").mkdir(parents=True)

        assert fanout.install_claude(root, "alias") == fanout.install_skill_dirs(
            root, "alias", "codex"
        )

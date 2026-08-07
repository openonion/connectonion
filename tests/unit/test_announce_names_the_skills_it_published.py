"""`co announce` lists every skill right after saying how many have a body.

Real run on this machine:

    Listing linkedin-comment-draft without body: ~/.co/skills/…/SKILL.md not found
    Listing linkedin-comment-generate without body: … not found
    Listing linkedin-thumbup without body: … not found
    ...
      skills: 39 listed, 19 with public body (co-install, ai-language-fix,
    content-quality, deploy-oo-chat, engage-linkedin, frontend-test,
    linkedin-comment-draft, linkedin-comment-generate, linkedin-thumbup, …

`body_count` is right — `sum(1 for s in skills if "body" in s)`. The names in
brackets are all 39, printed immediately after "19 with public body", so the
three the same command just reported as missing appear in the list a reader takes
to be the nineteen. The three do not exist in either location:

    ~/.co/skills/linkedin-thumbup/SKILL.md       absent
    ~/.claude/skills/linkedin-thumbup/SKILL.md   absent

They are in the manifest and nowhere else, which is legitimate — a listed skill
without a body is how you advertise something you have not published. What is
wrong is a list that reads as the published ones and is not.

This is the publisher side of the crash fixed in the previous commit: an agent
announces a skill whose body it never sends, and a subscriber then asks the relay
for that body. Naming the right skills here is what would have made the state
visible before it reached anyone else.
"""

import pytest


@pytest.fixture
def announce(monkeypatch, tmp_path):
    """The announce module with a skills dir under our control."""
    from connectonion.cli.commands import announce_commands

    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setattr(announce_commands, "SKILLS_DIR", skills)
    return announce_commands, skills


def _profile(*entries):
    return {"alias": "me", "skills": [
        {"name": name, "description": "d", "publish": publish}
        for name, publish in entries
    ]}


class TestOnlyPublishedSkillsCarryABody:

    def test_a_present_body_is_included(self, announce):
        module, skills = announce
        (skills / "here").mkdir()
        (skills / "here" / "SKILL.md").write_text("# Body\n", encoding="utf-8")

        built = module._build_listed_skills(_profile(("here", True)))

        assert "body" in built[0]

    def test_a_missing_body_is_omitted(self, announce):
        module, _ = announce

        built = module._build_listed_skills(_profile(("gone", True)))

        assert "body" not in built[0]

    def test_an_unpublished_skill_is_still_listed(self, announce):
        module, _ = announce

        built = module._build_listed_skills(_profile(("private", False)))

        assert built[0]["name"] == "private"
        assert "body" not in built[0]


class TestTheSummaryNamesWhatItCounts:
    """The count was right and the names beside it were everything."""

    def _summary(self, module, skills_out, capsys):
        module.print_announce_summary("me", skills_out)
        return capsys.readouterr().out

    def test_only_the_ones_with_a_body_are_named(self, announce, capsys):
        module, _ = announce
        skills_out = [
            {"name": "published", "body": "# b"},
            {"name": "listed-only"},
        ]

        out = self._summary(module, skills_out, capsys)

        assert "published" in out
        assert "listed-only" not in out.split("with public body")[1]

    def test_the_count_still_matches_the_names(self, announce, capsys):
        module, _ = announce
        skills_out = [
            {"name": "one", "body": "# b"},
            {"name": "two", "body": "# b"},
            {"name": "three"},
        ]

        out = self._summary(module, skills_out, capsys)

        assert "3 listed" in out
        assert "2 with public body" in out
        assert out.count("one") >= 1 and "two" in out

    def test_the_listed_only_total_is_still_reported(self, announce, capsys):
        """Dropping them from the names must not hide that they exist."""
        module, _ = announce
        out = self._summary(module, [{"name": "a"}, {"name": "b"}], capsys)

        assert "2 listed" in out
        assert "0 with public body" in out

    def test_no_skills_at_all_says_so_without_brackets(self, announce, capsys):
        module, _ = announce
        out = self._summary(module, [], capsys)

        assert "0 listed" in out
        assert "(" not in out.split("public body")[1]

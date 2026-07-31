"""What `co deploy` puts in the tarball, and what it leaves out.

The rules for a project and the rules for a skill are not the same, and using
one for the other loses files quietly — which is the worst way to lose them,
because the deploy still reports success.
"""

from pathlib import Path

import pytest

from connectonion.cli.commands import deploy_commands as dc


class TestASkillIsNotAProject:
    """A skill's `build/` is a compiled helper it shells out to; its `todo.md`
    may be a document it reads. The project ignore defaults call both noise, so
    a skill bundled with them lost files silently — the deploy succeeded and the
    skill failed later, on the server, reaching for something never sent.
    openonion/connectonion#380
    """

    def test_a_skills_build_directory_is_not_ignored(self, tmp_path):
        patterns = dc._load_skill_ignore_patterns(tmp_path)

        assert not any(p.startswith("build") for p in patterns)
        assert not any("node_modules" in p for p in patterns)
        assert not any("todo" in p.lower() for p in patterns)

    def test_the_project_defaults_still_ignore_those(self, tmp_path):
        """The contrast is the point: a project wants them gone, a skill does not."""
        patterns = dc._load_deploy_ignore_patterns(tmp_path)

        assert any(p.startswith("build") for p in patterns)

    def test_caches_are_still_left_out(self, tmp_path):
        patterns = dc._load_skill_ignore_patterns(tmp_path)

        assert "__pycache__/" in patterns
        assert ".git/" in patterns

    def test_a_skill_author_can_still_say_what_to_leave_out(self, tmp_path):
        (tmp_path / ".gitignore").write_text("secrets.env\n# a comment\n\nscratch/\n")

        patterns = dc._load_skill_ignore_patterns(tmp_path)

        assert "secrets.env" in patterns
        assert "scratch/" in patterns
        assert not any(p.startswith("#") for p in patterns)


class TestASkillStillKeepsItsSecrets:
    """Letting a skill ship its own files must not let it ship its own keys.

    The first cut of #380 dropped the project defaults wholesale, and `.env.local`
    — which those defaults had been excluding — started travelling to the server
    inside the tarball. That is a worse bug than the one being fixed.
    """

    def test_env_files_never_travel(self, tmp_path):
        patterns = dc._load_skill_ignore_patterns(tmp_path)

        assert ".env*" in patterns

    def test_private_keys_never_travel(self, tmp_path):
        patterns = dc._load_skill_ignore_patterns(tmp_path)

        for name in ("*.pem", "id_rsa", "id_ed25519", ".co/keys/"):
            assert name in patterns, name

    def test_the_files_the_fix_was_about_still_travel(self, tmp_path):
        patterns = dc._load_skill_ignore_patterns(tmp_path)

        assert not any(p.startswith("build") for p in patterns)
        assert not any("node_modules" in p for p in patterns)

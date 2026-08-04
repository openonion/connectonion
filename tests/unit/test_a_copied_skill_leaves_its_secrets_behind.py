"""`co skills copy` takes the skill's files and leaves its credentials.

VERSIONING.md says so, in the entry that introduced the command:

    skills carry their own files but never their secrets, and
    `co skills copy --to-project` puts one where a deploy will find it

`_copy_entry` copies the directory whole:

    for item in src_path.parent.iterdir():
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

Measured on a skill directory holding a credential:

    src/leaky/.env                 ->  copied
    src/leaky/credentials.json     ->  copied
    src/leaky/keys/id_rsa          ->  copied

Nothing in skills_commands.py, useful_plugins/skills.py, the co_ai loader or the
fanout mentions `.env` or a secret at all, so the sentence was never true of any
skills path.

It matters most where the command is pointed: `--to-project` puts the skill
where `co deploy` will find it, and a deploy rsyncs the project tree to a server.
A credential that a skill kept beside itself on a laptop then lands on the box.

Skipping is not silent. A skill that really did keep something here would
otherwise lose it without a word, and finding that out later is worse than being
told now.
"""

from pathlib import Path

import pytest

from connectonion.cli.commands.skills_commands import _copy_entry


@pytest.fixture
def a_skill_with_secrets(tmp_path):
    src = tmp_path / "src" / "leaky"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: leaky\ndescription: d\n---\n\nDo it.\n")

    # what a skill legitimately carries
    (src / "helper.py").write_text("print('hi')\n")
    (src / "reference.md").write_text("notes\n")
    (src / "data").mkdir()
    (src / "data" / "table.csv").write_text("a,b\n1,2\n")
    (src / ".env.example").write_text("API_TOKEN=\n")

    # what it must not
    (src / ".env").write_text("API_TOKEN=super-secret\n")
    (src / "credentials.json").write_text('{"aws": "key"}')
    (src / "server.pem").write_text("-----BEGIN PRIVATE KEY-----\n")
    (src / "keys").mkdir()
    (src / "keys" / "id_rsa").write_text("PRIVATE\n")

    return src, tmp_path / "dest"


def _copy(a_skill_with_secrets):
    src, dest_root = a_skill_with_secrets
    entry = {"name": "leaky", "path": str(src / "SKILL.md"), "source": "test"}
    _copy_entry(entry, force=True, skills_dir=dest_root)
    return dest_root / "leaky"


class TestTheSecretsStayBehind:

    @pytest.mark.parametrize("secret", [
        ".env",
        "credentials.json",
        "server.pem",
        "keys/id_rsa",
    ])
    def test_it_is_not_copied(self, a_skill_with_secrets, secret):
        dest = _copy(a_skill_with_secrets)

        assert not (dest / secret).exists(), f"{secret} travelled with the skill"


class TestTheSkillStillArrives:
    """Filtering that eats the skill is worse than the leak."""

    @pytest.mark.parametrize("kept", [
        "SKILL.md",
        "helper.py",
        "reference.md",
        "data/table.csv",
        ".env.example",
    ])
    def test_it_is_copied(self, a_skill_with_secrets, kept):
        dest = _copy(a_skill_with_secrets)

        assert (dest / kept).exists(), f"{kept} was dropped; it is not a secret"

    def test_the_body_is_intact(self, a_skill_with_secrets):
        dest = _copy(a_skill_with_secrets)

        assert "Do it." in (dest / "SKILL.md").read_text()


class TestItSaysWhatItLeft:
    """A skill that really did keep something here loses it otherwise, silently."""

    def test_the_skipped_files_are_named(self, a_skill_with_secrets, capsys):
        _copy(a_skill_with_secrets)

        printed = capsys.readouterr().out
        assert ".env" in printed

    def test_a_skill_with_no_secrets_says_nothing_about_them(self, tmp_path, capsys):
        src = tmp_path / "src" / "clean"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("---\nname: clean\n---\n\nGo.\n")

        _copy_entry({"name": "clean", "path": str(src / "SKILL.md"), "source": "t"},
                    force=True, skills_dir=tmp_path / "dest")

        assert "skipped" not in capsys.readouterr().out.lower()


class TestASingleFileSkill:
    """`<name>.md` with no directory of its own — the other shape."""

    def test_it_still_copies(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "solo.md").write_text("---\nname: solo\n---\n\nGo.\n")

        _copy_entry({"name": "solo", "path": str(src / "solo.md"), "source": "t"},
                    force=True, skills_dir=tmp_path / "dest")

        assert (tmp_path / "dest" / "solo" / "SKILL.md").exists()


class TestTheShapesTheFirstPassMissed:
    """Step 7 on #657: assume the fix was incomplete, and it was.

    Matching one filename at a time missed two kinds of thing —

        token.json, auth.json, service_account.json, .git-credentials,
        secrets.yaml                      common names that were simply not listed

        .ssh/id_ecdsa, .aws/credentials   a credential *directory*, where guessing
                                          each filename is the wrong shape of rule

    The second is why the directory rule exists: a skill carrying `.ssh/` should
    leave all of it, not the two key names someone thought of.
    """

    @pytest.mark.parametrize("name", [
        "token.json", "auth.json", "service_account.json",
        ".git-credentials", "secrets.yaml", "secrets.yml",
    ])
    def test_a_credential_file_is_skipped(self, tmp_path, name):
        from connectonion.cli.commands.skills_commands import _is_secret

        assert _is_secret(tmp_path / name), f"{name} would travel"

    @pytest.mark.parametrize("directory", [".ssh", ".aws", ".gnupg", ".kube"])
    def test_a_credential_directory_is_skipped_whole(self, tmp_path, directory):
        from connectonion.cli.commands.skills_commands import _is_secret

        assert _is_secret(tmp_path / directory)

    def test_everything_inside_such_a_directory_stays(self, tmp_path):
        """The point of the directory rule: no guessing at the names inside."""
        src = tmp_path / "src" / "s"
        (src / ".ssh").mkdir(parents=True)
        (src / "SKILL.md").write_text("---\nname: s\n---\n\nGo.\n")
        (src / ".ssh" / "id_ecdsa").write_text("PRIVATE\n")
        (src / ".ssh" / "known_hosts").write_text("host\n")

        _copy_entry({"name": "s", "path": str(src / "SKILL.md"), "source": "t"},
                    force=True, skills_dir=tmp_path / "dest")

        assert not (tmp_path / "dest" / "s" / ".ssh").exists()
        assert (tmp_path / "dest" / "s" / "SKILL.md").exists()

    @pytest.mark.parametrize("innocent", [
        "config.json", "package.json", "data.yaml", "README.md",
        "tokens.md", "secrets.md",
    ])
    def test_an_ordinary_file_is_not_mistaken_for_one(self, tmp_path, innocent):
        """A rule that eats documentation is a rule nobody keeps."""
        from connectonion.cli.commands.skills_commands import _is_secret

        assert not _is_secret(tmp_path / innocent)

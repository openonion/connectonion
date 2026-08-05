"""A credential at the project root travels to the server as ordinary source.

The deploy already knows `.env` is not source, and says so:

    # `.env` is a secret, not source. It reaches the server through
    # _sync_env(), as a root-owned 0600 file systemd reads — not as a
    # world-readable file that happens to land in the working directory.
    "--exclude", ".env",
    "--exclude", ".env.*",

and it is careful in the same way elsewhere: `umask 077` around
`chmod 600 .co/keys/agent.key`, `~/.ssh` at 700, `authorized_keys` at 600, the
env file root-owned.

`RSYNC_FILTERS` stops there. It does not exclude the other shapes a credential
takes — `credentials.json`, `token.json`, `service_account.json`,
`secrets.yaml`, `*.pem`, `*.key`, or an `.ssh/` `.aws/` `.gnupg/` directory
sitting in the project. Those go up as ordinary source and land at 644 in a 755
tree.

This project already decided what a credential looks like. #657 and #658 built
that list for `co skills copy`, after the same question — a skill's directory
travelling whole, secrets included:

    SECRET_NAMES, SECRET_SUFFIXES, SECRET_DIRS, _is_secret()

and #658 widened it once the first pass proved too narrow: `token.json`,
`auth.json`, `.git-credentials`, `secrets.yaml`, and whole directories rather
than guessing at the filenames inside them.

Two copies of "what is a secret" would drift, and the one that drifts is the one
nobody is looking at. The deploy uses that list.

Not a hypothetical for a deployed agent: #683 measured that a hosted agent
publishes its sessions to anyone who can reach the port, and a credential in the
tree beside it is the next thing worth having.
"""

import pytest

from connectonion.cli.commands.deploy_to_server import RSYNC_FILTERS


def _excluded(pattern: str) -> bool:
    """Is this pattern in the rsync filter list, as an --exclude?"""
    return any(RSYNC_FILTERS[i] == "--exclude" and RSYNC_FILTERS[i + 1] == pattern
               for i in range(len(RSYNC_FILTERS) - 1))


class TestTheShapesACredentialTakes:

    @pytest.mark.parametrize("name", [
        "credentials.json", "service-account.json", "service_account.json",
        "token.json", "auth.json", "secrets.json", "secrets.yaml", "secrets.yml",
        ".netrc", ".npmrc", ".pypirc", "keys.env", ".git-credentials",
    ])
    def test_a_credential_file_is_excluded(self, name):
        assert _excluded(name), f"{name} would travel to the server"

    @pytest.mark.parametrize("pattern", ["*.pem", "*.key", "*.p12", "*.pfx"])
    def test_a_key_file_is_excluded(self, pattern):
        assert _excluded(pattern), f"{pattern} would travel to the server"

    @pytest.mark.parametrize("directory", [
        ".ssh/", ".aws/", ".gnupg/", ".kube/", ".docker/", ".azure/",
    ])
    def test_a_credential_directory_is_excluded_whole(self, directory):
        assert _excluded(directory), f"{directory} would travel to the server"

    def test_an_ssh_private_key_is_excluded(self):
        assert _excluded("id_rsa") or _excluded("id_*"), "an ssh key would travel"


class TestItAgreesWithTheSkillsRule:
    """One definition of "secret", not two that drift apart."""

    def test_every_name_the_skills_rule_knows_is_excluded_here(self):
        from connectonion.cli.commands.skills_commands import SECRET_NAMES

        missing = sorted(n for n in SECRET_NAMES if not _excluded(n))

        assert missing == [], f"the deploy would carry what a skill copy leaves behind: {missing}"

    def test_every_directory_the_skills_rule_knows_is_excluded_here(self):
        from connectonion.cli.commands.skills_commands import SECRET_DIRS

        missing = sorted(d for d in SECRET_DIRS if not _excluded(d + "/"))

        assert missing == [], f"the deploy would carry: {missing}"

    def test_every_suffix_the_skills_rule_knows_is_excluded_here(self):
        from connectonion.cli.commands.skills_commands import SECRET_SUFFIXES

        missing = sorted(s for s in SECRET_SUFFIXES if not _excluded("*" + s))

        assert missing == [], f"the deploy would carry: {missing}"


class TestWhatMustStillTravel:
    """A filter that eats the agent is worse than the leak."""

    @pytest.mark.parametrize("name", [
        "agent.py", "main.py", "requirements.txt", "config.json",
        "package.json", "data.yaml", "README.md", ".env.example",
    ])
    def test_ordinary_source_is_not_excluded(self, name):
        assert not _excluded(name), f"{name} is not a credential"

    def test_the_env_rules_are_still_there(self):
        assert _excluded(".env") and _excluded(".env.*")


class TestWhatRsyncActuallyDoes:
    """Pattern presence is not the same question as what travels.

    The class above asks whether a pattern is in the list. rsync decides by
    matching, and the two answers differ: `.env.example` is not in the list and
    still does not travel, because `--exclude .env.*` matches it. A test that
    only reads the list would report that file as safe to carry when it is not.

    So this runs rsync.
    """

    import shutil as _shutil

    @pytest.fixture
    def tree(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        (src / ".aws").mkdir(parents=True)
        dst.mkdir()
        for name in ("agent.py", "requirements.txt", "config.json",
                     "credentials.json", "server.pem", "token.json",
                     ".env", "id_rsa"):
            (src / name).write_text("x\n")
        (src / ".aws" / "credentials").write_text("x\n")
        return src, dst

    def _transferred(self, src, dst) -> set:
        import subprocess

        result = subprocess.run(
            ["rsync", "-a", "--dry-run", "--itemize-changes", *RSYNC_FILTERS,
             str(src) + "/", str(dst) + "/"],
            capture_output=True, text=True, timeout=120,
        )
        return {line.split()[1] for line in result.stdout.splitlines()
                if len(line.split()) > 1 and not line.split()[1].endswith("/")}

    @pytest.mark.skipif(not _shutil.which("rsync"), reason="rsync not installed")
    def test_the_source_travels(self, tree):
        assert {"agent.py", "requirements.txt", "config.json"} <= self._transferred(*tree)

    @pytest.mark.skipif(not _shutil.which("rsync"), reason="rsync not installed")
    @pytest.mark.parametrize("secret", [
        "credentials.json", "server.pem", "token.json", ".env",
        "id_rsa", ".aws/credentials",
    ])
    def test_the_credential_does_not(self, tree, secret):
        assert secret not in self._transferred(*tree), f"{secret} reached the server"

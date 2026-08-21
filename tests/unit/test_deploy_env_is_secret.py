"""`.env` is a secret on both deploy paths, or it is a secret on neither.

`co deploy` parses `.env`, uploads the pairs as secrets, and keeps the file out
of the tarball. `co deploy --to` had no notion of a secret at all: `.env` was
ordinary source, so it rsynced to the server as a world-readable file — and
because `co init` copies the whole of `~/.co/keys.env` into a new project's
`.env`, what travelled was the operator's Google and Microsoft refresh tokens.
"""

import shutil
import subprocess
from unittest.mock import patch

import pytest

from connectonion.cli.commands import deploy_to_server as dts
from connectonion.cli.commands.deploy_to_server import RSYNC_FILTERS


def _ok():
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


needs_rsync = pytest.mark.skipif(
    shutil.which("rsync") is None, reason="needs rsync on PATH"
)


@needs_rsync
@pytest.mark.parametrize("name", [".env", ".env.local", ".env.production"])
def test_env_files_never_reach_the_server_as_source(tmp_path, name):
    local, server = tmp_path / "local", tmp_path / "server"
    (local / ".co").mkdir(parents=True)
    server.mkdir()
    (local / name).write_text("GOOGLE_REFRESH_TOKEN=1//secret\n")
    (local / "agent.py").write_text("print('hi')\n")

    subprocess.run(
        ["rsync", "-a", "--delete", *RSYNC_FILTERS, f"{local}/", f"{server}/"],
        check=True, capture_output=True,
    )

    assert (server / "agent.py").exists(), "code should still ship"
    assert not (server / name).exists(), f"{name} was rsynced as source"


def test_the_unit_reads_the_env_file_systemd_owns():
    """Secrets reach the process through systemd, not by happening to sit in
    the working directory.

    The `-` prefix is deliberate: a project with no `.env` has no file to read,
    and that must not be a boot failure.
    """
    unit = dts._unit_text("myagent", "agent.py")
    env_file = dts.ENV_FILE_TEMPLATE.format(agent="myagent")
    assert f"EnvironmentFile=-{env_file}" in unit
    assert f"Environment=CONNECTONION_ENV_FILE={env_file}" in unit


def test_the_env_file_lives_outside_the_rsync_root(tmp_path):
    """/srv/<agent>/ is the rsync destination, and `--delete` owns it. A secret
    stored there could never be rotated on the server: the next deploy would
    overwrite it with the laptop's copy."""
    path = dts.ENV_FILE_TEMPLATE.format(agent="myagent")
    assert not path.startswith(f"{dts.SRV}/myagent/"), path


def test_local_config_path_is_rewritten_for_the_server():
    """AGENT_CONFIG_PATH in a project .env is an absolute macOS path. Shipped
    verbatim it points at a directory that cannot exist on Linux, and the OAuth
    tools that build their keys.env path from it fail there."""
    out = dts._env_for_server({"AGENT_CONFIG_PATH": "/Users/someone/.co",
                               "GEMINI_API_KEY": "AIza"}, "myagent")

    assert out["AGENT_CONFIG_PATH"] == f"{dts.SRV}/myagent/.co"
    # Everything that is not identity passes through untouched. The identity
    # keys are withheld deliberately — see test_a_deploy_runs_as_the_agent.py.
    assert out["GEMINI_API_KEY"] == "AIza"


def test_a_project_without_config_path_gains_nothing():
    """Only rewrite what is there — do not invent the variable."""
    assert "AGENT_CONFIG_PATH" not in dts._env_for_server({"X": "1"}, "myagent")


class TestAValueIsNeverShellSyntax:
    """A `.env` value is attacker-influenced input in the general case, and it
    is written to the server under sudo. The first version of this sent it in a
    heredoc, so a value equal to the delimiter would close the heredoc early and
    hand the rest of the file to the shell — as root.
    """

    @staticmethod
    def _ssh_script(project, env_text):
        (project / ".env").write_text(env_text)
        with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
            dts._sync_env("user@host", "myagent", project)
        return ssh.call_args.args[1] if ssh.call_args else ""

    def test_a_value_equal_to_a_heredoc_delimiter_is_inert(self, tmp_path):
        script = self._ssh_script(tmp_path, "K=CO_ENV_EOF\n")
        assert "K=CO_ENV_EOF" not in script, "the value reached the shell verbatim"

    def test_a_value_with_a_command_substitution_is_inert(self, tmp_path):
        script = self._ssh_script(tmp_path, "K=$(touch /tmp/pwned)\n")
        assert "touch /tmp/pwned" not in script

    def test_the_values_still_arrive(self, tmp_path):
        """Inert must not mean lost — decode what the server would decode."""
        import base64
        import re

        script = self._ssh_script(tmp_path, "A=1\nB=two words\n")
        payload = re.search(r"printf %s \'?([A-Za-z0-9+/=]+)\'?", script).group(1)
        assert base64.b64decode(payload).decode() == "A=1\nB=two words\n"


def test_a_multiline_value_is_skipped_not_silently_mangled(tmp_path):
    """A newline inside a value ends the KEY=VALUE line, so the remainder
    becomes junk entries. systemd would read the file without complaint."""
    import base64
    import re

    (tmp_path / ".env").write_text('PEM="line1\nline2"\nOK=fine\n')
    with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
        dts._sync_env("user@host", "myagent", tmp_path)

    payload = re.search(r"printf %s \'?([A-Za-z0-9+/=]+)\'?", ssh.call_args.args[1]).group(1)
    written = base64.b64decode(payload).decode()
    assert "OK=fine" in written
    assert "PEM" not in written

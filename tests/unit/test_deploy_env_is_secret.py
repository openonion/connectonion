"""`.env` is a secret on both deploy paths, or it is a secret on neither.

`co deploy` parses `.env`, uploads the pairs as secrets, and keeps the file out
of the tarball. `co deploy --to` had no notion of a secret at all: `.env` was
ordinary source, so it rsynced to the server as a world-readable file — and
because `co init` copies the whole of `~/.co/keys.env` into a new project's
`.env`, what travelled was the operator's Google and Microsoft refresh tokens.
"""

import shutil
import subprocess

import pytest

from connectonion.cli.commands import deploy_to_server as dts
from connectonion.cli.commands.deploy_to_server import RSYNC_FILTERS


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
    assert f"EnvironmentFile=-{dts.ENV_FILE_TEMPLATE.format(agent='myagent')}" in unit


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
                               "OPENONION_API_KEY": "jwt"}, "myagent")

    assert out["AGENT_CONFIG_PATH"] == f"{dts.SRV}/myagent/.co"
    assert out["OPENONION_API_KEY"] == "jwt"


def test_a_project_without_config_path_gains_nothing():
    """Only rewrite what is there — do not invent the variable."""
    assert "AGENT_CONFIG_PATH" not in dts._env_for_server({"X": "1"}, "myagent")

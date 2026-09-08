"""`co env` is the one place to see, set and repair the selected env file.

Before it existed, the selected file could only be edited by hand, `co doctor`
told people to "set OPENAI_API_KEY in global keys.env" without naming a command,
and a single broken line in ~/.co/keys.env made every `co` command exit 2 with
"Next: co --help" — a tip that cannot repair anything.
"""

import os
import shlex
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from connectonion import environment
from connectonion.cli.main import app


def run(args, home, *, env_file=None, environ=None):
    """Invoke `co` in-process with an isolated home; never the developer's own keys.env."""
    process = {"HOME": str(home), "USERPROFILE": str(home), **(environ or {})}
    with patch.dict(os.environ, process, clear=True), \
         patch.object(Path, "home", return_value=home), \
         patch.object(environment, "_loaded", {}), \
         patch.object(environment, "_selected", None), \
         patch.object(environment, "_selection_error", None):
        argv = (["--env-file", str(env_file)] if env_file else []) + args
        return CliRunner().invoke(app, argv, prog_name="co")


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    return home


@pytest.fixture
def keys_env(home):
    path = home / ".co" / "keys.env"
    path.write_text("# Managed keys\nOPENONION_API_KEY=sk-secret-1234567890abcdef\nMODEL=co/gemini-3.7-flash\n")
    return path


class TestShow:
    def test_bare_env_names_the_file_and_masks_secrets(self, home, keys_env):
        result = run(["env"], home)
        assert result.exit_code == 0, result.output
        assert "keys.env" in result.output
        assert "MODEL" in result.output and "co/gemini-3.7-flash" in result.output
        assert "sk-secret-1234567890abcdef" not in result.output
        assert "Next: co env set" in result.output

    def test_reveal_prints_full_values(self, home, keys_env):
        result = run(["env", "show", "--reveal"], home)
        assert result.exit_code == 0, result.output
        assert "sk-secret-1234567890abcdef" in result.output

    def test_process_override_is_labelled(self, home, keys_env):
        result = run(["env"], home, environ={"MODEL": "from-shell"})
        assert result.exit_code == 0, result.output
        assert "overrides" in result.output

    def test_missing_global_file_points_at_init(self, home):
        result = run(["env"], home)
        assert result.exit_code == 0, result.output
        assert "not found" in result.output.lower()
        assert "Next: co init" in result.output

    def test_help_lists_every_subcommand(self, home):
        result = run(["env", "--help"], home)
        assert result.exit_code == 0
        for name in ("show", "path", "get", "set", "unset"):
            assert name in result.output


class TestPathAndGet:
    def test_path_prints_only_the_path(self, home, keys_env):
        result = run(["env", "path"], home)
        assert result.exit_code == 0
        assert result.output.strip() == str(keys_env.resolve())

    def test_get_prints_only_the_value(self, home, keys_env):
        result = run(["env", "get", "MODEL"], home)
        assert result.exit_code == 0
        assert result.output.strip() == "co/gemini-3.7-flash"

    def test_get_prefers_the_process_value(self, home, keys_env):
        result = run(["env", "get", "MODEL"], home, environ={"MODEL": "from-shell"})
        assert result.output.strip() == "from-shell"

    def test_get_missing_exits_1_and_names_set(self, home, keys_env):
        result = run(["env", "get", "NOPE"], home)
        assert result.exit_code == 1
        assert "Next: co env set NOPE <value>" in result.output


class TestSet:
    def test_set_appends_and_preserves_comments(self, home, keys_env):
        result = run(["env", "set", "OPENAI_API_KEY", "sk-new"], home)
        assert result.exit_code == 0, result.output
        text = keys_env.read_text()
        assert text.startswith("# Managed keys\n")
        assert "OPENAI_API_KEY=sk-new\n" in text
        assert "MODEL=co/gemini-3.7-flash\n" in text
        assert "Next: co env get OPENAI_API_KEY" in result.output

    def test_set_replaces_in_place(self, home, keys_env):
        run(["env", "set", "MODEL", "co/other"], home)
        lines = keys_env.read_text().splitlines()
        assert lines.count("MODEL=co/other") == 1
        assert not any(line.startswith("MODEL=co/gemini") for line in lines)

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    def test_set_creates_the_global_file_owner_only(self, home):
        result = run(["env", "set", "MODEL", "co/x"], home)
        assert result.exit_code == 0, result.output
        path = home / ".co" / "keys.env"
        assert path.read_text() == "MODEL=co/x\n"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_set_quotes_values_with_spaces(self, home, keys_env):
        run(["env", "set", "GREETING", "hello world"], home)
        assert run(["env", "get", "GREETING"], home).output.strip() == "hello world"

    def test_set_rejects_a_bad_name(self, home, keys_env):
        result = run(["env", "set", "not-a-name", "x"], home)
        assert result.exit_code == 2
        assert "Next: co env set <KEY> <value>" in result.output
        assert "not-a-name" not in keys_env.read_text()

    def test_set_refuses_agent_config_path(self, home, keys_env):
        result = run(["env", "set", "AGENT_CONFIG_PATH", "/elsewhere"], home)
        assert result.exit_code == 2
        assert "export AGENT_CONFIG_PATH" in result.output
        assert "AGENT_CONFIG_PATH" not in keys_env.read_text()

    @pytest.mark.parametrize("key,auth", [("GOOGLE_ACCESS_TOKEN", "co auth google"),
                                          ("MICROSOFT_EMAIL", "co auth microsoft")])
    def test_set_refuses_provider_record_fields(self, home, keys_env, key, auth):
        result = run(["env", "set", key, "x"], home)
        assert result.exit_code == 2
        assert f"Next: {auth}" in result.output
        assert key not in keys_env.read_text()

    def test_set_warns_when_the_shell_overrides_it(self, home, keys_env):
        result = run(["env", "set", "MODEL", "co/other"], home, environ={"MODEL": "from-shell"})
        assert result.exit_code == 0, result.output
        assert "MODEL=co/other" in keys_env.read_text()
        assert "unset MODEL" in result.output


class TestUnset:
    def test_unset_removes_the_line(self, home, keys_env):
        result = run(["env", "unset", "MODEL"], home)
        assert result.exit_code == 0, result.output
        assert "MODEL" not in keys_env.read_text()
        assert "OPENONION_API_KEY" in keys_env.read_text()
        assert "Next: co env" in result.output

    def test_unset_missing_exits_1(self, home, keys_env):
        result = run(["env", "unset", "NOPE"], home)
        assert result.exit_code == 1
        assert "Next: co env" in result.output

    def test_unset_a_provider_field_removes_the_whole_record(self, home, keys_env):
        keys_env.write_text("GOOGLE_API_KEY=gemini\nGOOGLE_ACCESS_TOKEN=a\nGOOGLE_REFRESH_TOKEN=r\n"
                            "GOOGLE_EMAIL=me@example.test\nGOOGLE_SCOPES=gmail\n")
        result = run(["env", "unset", "GOOGLE_EMAIL"], home)
        assert result.exit_code == 0, result.output
        text = keys_env.read_text()
        assert text == "GOOGLE_API_KEY=gemini\n"
        assert "Next: co auth google" in result.output


class TestExplicitFile:
    def test_missing_selected_file_env_names_set(self, home, tmp_path):
        target = tmp_path / "project.env"
        result = run(["env"], home, env_file=target)
        assert result.exit_code == 2, result.output
        assert f"Next: co --env-file {shlex.quote(str(target.resolve()))} env set" in result.output

    def test_set_creates_the_selected_file(self, home, tmp_path):
        target = tmp_path / "project.env"
        result = run(["env", "set", "MODEL", "co/x"], home, env_file=target)
        assert result.exit_code == 0, result.output
        assert target.read_text() == "MODEL=co/x\n"
        assert f"Next: co --env-file {shlex.quote(str(target.resolve()))} env get MODEL" in result.output

    def test_set_never_touches_the_global_file(self, home, keys_env, tmp_path):
        target = tmp_path / "project.env"
        before = keys_env.read_text()
        run(["env", "set", "MODEL", "co/x"], home, env_file=target)
        assert keys_env.read_text() == before

    def test_path_prints_the_selected_file(self, home, keys_env, tmp_path):
        target = tmp_path / "project.env"
        target.write_text("A=1\n")
        assert run(["env", "path"], home, env_file=target).output.strip() == str(target.resolve())


class TestBrokenFile:
    @pytest.fixture
    def broken(self, home):
        path = home / ".co" / "keys.env"
        path.write_text("A=1\nthis line is broken\nB=2\n")
        return path

    def test_env_names_the_broken_line(self, home, broken):
        result = run(["env"], home)
        assert result.exit_code == 2, result.output
        assert "line 2" in result.output
        assert "keys.env" in result.output
        assert "Next: co env" in result.output
        assert "this line is broken" not in result.output

    def test_other_commands_exit_2_and_name_co_env(self, home, broken):
        result = run(["keys"], home)
        assert result.exit_code == 2, result.output
        assert "line 2" in result.output
        assert "Next: co env" in result.output

    def test_set_refuses_to_rewrite_a_broken_file(self, home, broken):
        before = broken.read_text()
        result = run(["env", "set", "C", "3"], home)
        assert result.exit_code == 2
        assert broken.read_text() == before


class TestProviderFailuresPointAtEnv:
    """`co gmail` / `co outlook` used to say only "not connected" — and people
    re-authorized an account that was connected all along, in the other file."""

    def failure(self, home, environ=None) -> str:
        """The message a Google client raises, resolved and checked inside the isolated home."""
        from connectonion.provider_credentials import resolve_provider_credentials
        process = {"HOME": str(home), "USERPROFILE": str(home), **(environ or {})}
        with patch.dict(os.environ, process, clear=True), \
             patch.object(Path, "home", return_value=home), \
             patch.object(environment, "_loaded", {}), \
             patch.object(environment, "_selected", None):
            with pytest.raises(ValueError) as exc:
                resolve_provider_credentials("google").require_configured()
            return str(exc.value)

    def test_a_file_without_a_token_names_the_file_and_co_env(self, home, keys_env):
        keys_env.write_text("GOOGLE_EMAIL=me@example.test\n")
        text = self.failure(home)
        assert "Google account not connected in ~/.co/keys.env" in text
        assert "co env" in text
        assert text.endswith("Next: co auth google")

    def test_a_partial_process_record_says_so(self, home, keys_env):
        text = self.failure(home, environ={"GOOGLE_EMAIL": "shell@example.test"})
        assert "process environment" in text
        assert "co env" in text


def test_doctor_actions_all_name_a_command():
    from connectonion.cli.commands.doctor_commands import CREDENTIAL_ACTIONS
    for credential, action in CREDENTIAL_ACTIONS.items():
        assert action.startswith("co "), f"{credential}: {action!r} names no command"

"""Tests for CLI project helpers — upsert_env credential writing."""

import sys

from connectonion.cli.commands.project_cmd_lib import upsert_env


class TestUpsertEnv:
    """upsert_env replaces, appends, and creates .env files safely."""

    def test_creates_file_with_new_keys(self, tmp_path):
        env_file = tmp_path / "keys.env"
        upsert_env(env_file, {"A": "1", "B": "2"})

        assert env_file.read_text() == "A=1\nB=2\n"

    def test_replaces_existing_key_and_keeps_the_rest(self, tmp_path):
        env_file = tmp_path / "keys.env"
        env_file.write_text("# comment\nA=old\nOTHER=keep\n")

        upsert_env(env_file, {"A": "new"})

        assert env_file.read_text() == "# comment\nA=new\nOTHER=keep\n"

    def test_appends_to_file_without_trailing_newline(self, tmp_path):
        env_file = tmp_path / "keys.env"
        env_file.write_text("A=1")

        upsert_env(env_file, {"B": "2"})

        assert env_file.read_text() == "A=1\nB=2\n"

    def test_skips_none_values(self, tmp_path):
        env_file = tmp_path / "keys.env"
        env_file.write_text("A=1\n")

        upsert_env(env_file, {"A": None, "B": "2"})

        assert env_file.read_text() == "A=1\nB=2\n"

    def test_strip_prefix_drops_stale_credentials(self, tmp_path):
        env_file = tmp_path / "keys.env"
        env_file.write_text("MICROSOFT_OLD=x\nMICROSOFT_EMAIL=a@b.com\nKEEP=1\n")

        upsert_env(env_file, {"MICROSOFT_EMAIL": "c@d.com"}, strip_prefix="MICROSOFT_")

        assert env_file.read_text() == "KEEP=1\nMICROSOFT_EMAIL=c@d.com\n"

    def test_written_file_is_owner_only(self, tmp_path):
        env_file = tmp_path / "keys.env"
        upsert_env(env_file, {"TOKEN": "secret"})

        if sys.platform != "win32":
            assert env_file.stat().st_mode & 0o777 == 0o600

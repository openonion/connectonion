"""CLI smoke tests for `co sub`."""

from .argparse_runner import ArgparseCliRunner


class TestSubCommand:
    """Test the sub command for managing subscriptions."""

    def setup_method(self):
        self.runner = ArgparseCliRunner()

    def test_sub_help_lists_subcommands(self):
        from connectonion.cli.main import app

        result = self.runner.invoke(app, ["sub", "--help"])

        assert result.exit_code == 0
        assert "sync" in result.output
        assert "list" in result.output
        assert "remove" in result.output

    def test_sub_sync_help_advertises_target(self):
        from connectonion.cli.main import app

        result = self.runner.invoke(app, ["sub", "sync", "--help"])

        assert result.exit_code == 0
        assert "0x address" in result.output
        assert "--relay" in result.output

    def test_sub_remove_help(self):
        from connectonion.cli.main import app

        result = self.runner.invoke(app, ["sub", "remove", "--help"])

        assert result.exit_code == 0
        assert "Alias or 0x address" in result.output

    def test_sub_sync_rejects_bare_alias(self):
        """Aliases are mutable/dangerous; only 0x addresses are accepted at first subscribe."""
        from connectonion.cli.main import app

        result = self.runner.invoke(app, ["sub", "sync", "alice"])

        assert result.exit_code != 0
        assert "not a 0x address" in result.output

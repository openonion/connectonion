"""CLI smoke tests for `co sub` — mirror tests/cli/test_cli_trust.py style.

No real network. Address-based subscribe/unsubscribe paths are covered in
tests/unit/test_sub_commands.py; here we only verify CLI surface area.
"""

from .argparse_runner import ArgparseCliRunner


class TestSubCommand:
    """Test the sub command for managing subscriptions."""

    def setup_method(self):
        self.runner = ArgparseCliRunner()

    def test_sub_help(self):
        from connectonion.cli.main import app

        result = self.runner.invoke(app, ["sub", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "sub" in result.output
        assert "add" in result.output
        assert "list" in result.output
        assert "remove" in result.output

    def test_sub_add_help_advertises_address_argument(self):
        from connectonion.cli.main import app

        result = self.runner.invoke(app, ["sub", "add", "--help"])

        assert result.exit_code == 0
        assert "0x address" in result.output
        assert "--relay" in result.output

    def test_sub_remove_help(self):
        from connectonion.cli.main import app

        result = self.runner.invoke(app, ["sub", "remove", "--help"])

        assert result.exit_code == 0
        assert "Alias or 0x address" in result.output

    def test_sub_add_rejects_bare_alias(self):
        """Aliases are mutable/dangerous; only 0x addresses are accepted at first subscribe."""
        from connectonion.cli.main import app

        result = self.runner.invoke(app, ["sub", "add", "alice"])

        assert result.exit_code != 0
        assert "not a 0x address" in result.output

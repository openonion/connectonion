"""Test runner for Typer-based CLIs - wraps typer.testing.CliRunner."""

import os
import tempfile
import shutil
from contextlib import contextmanager
from pathlib import Path

from typer.testing import CliRunner as TyperCliRunner
from connectonion.cli.main import app


class Result:
    """Result object compatible with old ArgparseCliRunner."""

    def __init__(self, typer_result):
        self.exit_code = typer_result.exit_code
        self.output = typer_result.stdout or ""
        self.stdout = typer_result.stdout or ""
        self.stderr = typer_result.stderr or ""
        self.exception = typer_result.exception


class ArgparseCliRunner:
    """Test runner for Typer CLIs, backwards compatible with old interface."""

    def __init__(self):
        self._runner = TyperCliRunner(mix_stderr=False)

    @contextmanager
    def isolated_filesystem(self, temp_dir=None):
        """Create isolated filesystem for testing."""
        if temp_dir is None:
            temp_dir = tempfile.mkdtemp()

        try:
            original_dir = os.getcwd()
        except FileNotFoundError:
            original_dir = os.path.expanduser("~")

        try:
            os.chdir(temp_dir)
            yield temp_dir
        finally:
            try:
                os.chdir(original_dir)
            except (FileNotFoundError, OSError):
                os.chdir(os.path.expanduser("~"))

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def invoke(self, cli_func, args=None, input=None, env=None, catch_exceptions=True):
        """
        Invoke CLI with given arguments.

        Args:
            cli_func: Ignored (uses global app) for backwards compatibility
            args: List of command-line arguments
            input: String to pass as stdin
            env: Environment variables to set
            catch_exceptions: Whether to catch exceptions

        Returns:
            Result object with exit_code, output, stdout, stderr
        """
        if args is None:
            args = []

        # Set environment variables
        original_env = os.environ.copy()
        if env:
            os.environ.update(env)

        try:
            typer_result = self._runner.invoke(
                app,
                args,
                input=input,
                catch_exceptions=catch_exceptions,
            )
            return Result(typer_result)
        finally:
            os.environ.clear()
            os.environ.update(original_env)

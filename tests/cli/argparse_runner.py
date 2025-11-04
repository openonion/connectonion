"""Test runner for argparse-based CLIs - mimics Click's CliRunner interface."""

import sys
import os
import tempfile
import shutil
from io import StringIO
from contextlib import contextmanager
from pathlib import Path


class Result:
    """Mimics Click's Result object."""

    def __init__(self, exit_code, stdout, stderr):
        self.exit_code = exit_code
        self.output = stdout
        self.stdout = stdout
        self.stderr = stderr
        self.exception = None


class ArgparseCliRunner:
    """Test runner for argparse-based CLIs, mimics Click's CliRunner."""

    def __init__(self):
        self.mix_stderr = True

    @contextmanager
    def isolated_filesystem(self, temp_dir=None):
        """Create isolated filesystem for testing."""
        if temp_dir is None:
            temp_dir = tempfile.mkdtemp()

        original_dir = os.getcwd()
        try:
            os.chdir(temp_dir)
            yield temp_dir
        finally:
            os.chdir(original_dir)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def invoke(self, cli_func, args=None, input=None, env=None, catch_exceptions=True):
        """
        Invoke CLI function with given arguments.

        Args:
            cli_func: The CLI function to invoke (should use argparse)
            args: List of command-line arguments
            input: String to pass as stdin
            env: Environment variables to set
            catch_exceptions: Whether to catch exceptions

        Returns:
            Result object with exit_code, output, stdout, stderr
        """
        if args is None:
            args = []

        # Save original state
        original_argv = sys.argv
        original_stdin = sys.stdin
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        original_env = os.environ.copy()

        # Prepare new state
        sys.argv = ['cli'] + args
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        if input:
            sys.stdin = StringIO(input)

        if env:
            os.environ.update(env)

        exit_code = 0
        exception = None

        try:
            cli_func()
        except SystemExit as e:
            exit_code = e.code if e.code is not None else 0
        except Exception as e:
            if not catch_exceptions:
                raise
            exception = e
            exit_code = 1
        finally:
            # Restore original state
            sys.argv = original_argv
            sys.stdin = original_stdin
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            os.environ.clear()
            os.environ.update(original_env)

        stdout_value = stdout_capture.getvalue()
        stderr_value = stderr_capture.getvalue()

        result = Result(exit_code, stdout_value, stderr_value)
        result.exception = exception

        return result

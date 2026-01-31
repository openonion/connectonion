"""
Shell tool for executing terminal commands (cross-platform).

Usage:
    from connectonion import Agent, Shell

    shell = Shell()
    agent = Agent("coder", tools=[shell])

    # Agent can now use:
    # - run(command) - Execute shell command, returns output
    # - run_in_dir(command, directory) - Execute in specific directory

Note: Uses system default shell (bash/sh on Unix, cmd on Windows).
For Unix-specific bash, use the `bash` function from bash.py instead.
"""

import subprocess


class Shell:
    """Shell command execution tool (cross-platform)."""

    def __init__(self, cwd: str = "."):
        """Initialize Shell tool.

        Args:
            cwd: Default working directory
        """
        self.cwd = cwd

    def run(self, command: str, timeout: int = 120) -> str:
        """Execute a shell command, returns output.

        Args:
            command: Shell command to execute (e.g., "ls -la", "git status")
            timeout: Seconds before timeout (default: 120, max: 600)

        Returns:
            Command output (stdout + stderr)
        """
        timeout = min(timeout, 600)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"

        return self._format_output(result)

    def run_in_dir(self, command: str, directory: str, timeout: int = 120) -> str:
        """Execute command in a specific directory.

        Args:
            command: Shell command to execute
            directory: Directory to run the command in
            timeout: Seconds before timeout (default: 120, max: 600)

        Returns:
            Command output (stdout + stderr)
        """
        timeout = min(timeout, 600)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=directory,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"

        return self._format_output(result)

    def _format_output(self, result: subprocess.CompletedProcess) -> str:
        """Format subprocess result into readable output."""
        parts = []
        if result.stdout:
            parts.append(result.stdout.rstrip())
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr.rstrip()}")
        if result.returncode != 0:
            parts.append(f"\nExit code: {result.returncode}")

        output = "\n".join(parts) if parts else "(no output)"

        # Truncate large outputs
        max_chars = 10000
        if len(output) > max_chars:
            output = output[:max_chars] + f"\n... (truncated, {len(output):,} total chars)"

        return output

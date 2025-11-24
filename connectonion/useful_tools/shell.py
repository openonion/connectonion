"""
Shell tool for executing terminal commands.

Usage:
    from connectonion import Agent, Shell

    shell = Shell()
    agent = Agent("coder", tools=[shell])

    # Agent can now use:
    # - run(command) - Execute shell command, returns output
    # - run_in_dir(command, directory) - Execute in specific directory
"""

import subprocess


class Shell:
    """Shell command execution tool."""

    def __init__(self, cwd: str = "."):
        """Initialize Shell tool.

        Args:
            cwd: Default working directory
        """
        self.cwd = cwd

    def run(self, command: str) -> str:
        """Execute a shell command, returns output.

        Args:
            command: Shell command to execute (e.g., "ls -la", "git status")

        Returns:
            Command output (stdout + stderr)
        """
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=self.cwd
        )

        parts = []
        if result.stdout:
            parts.append(result.stdout.rstrip())
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr.rstrip()}")
        if result.returncode != 0:
            parts.append(f"\nExit code: {result.returncode}")

        return "\n".join(parts) if parts else "(no output)"

    def run_in_dir(self, command: str, directory: str) -> str:
        """Execute command in a specific directory.

        Args:
            command: Shell command to execute
            directory: Directory to run the command in

        Returns:
            Command output (stdout + stderr)
        """
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=directory
        )

        parts = []
        if result.stdout:
            parts.append(result.stdout.rstrip())
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr.rstrip()}")
        if result.returncode != 0:
            parts.append(f"\nExit code: {result.returncode}")

        return "\n".join(parts) if parts else "(no output)"

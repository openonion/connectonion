"""
Purpose: Cross-platform shell command execution with directory control and output formatting
LLM-Note:
  Dependencies: imports from [subprocess] | imported by [useful_tools/__init__.py] | tested by command execution
  Data flow: Shell() creates instance → .run(command, timeout) or .run_in_dir(command, directory, timeout) → subprocess.run(shell=True) in cwd → captures stdout+stderr → _format_output() truncates if >10000 chars → returns formatted output: str
  State/Effects: executes system commands via subprocess.run(shell=True) | stores default cwd in self.cwd | no file persistence | side effects depend on executed commands (file I/O, network calls, etc.)
  Integration: exposes Shell class with .run(command, timeout), .run_in_dir(command, directory, timeout) | used as agent tool | class methods extracted to tools via extract_methods_from_instance() | instance accessible via agent.tools.shell
  Performance: timeout default 120s, max 600s | truncates output >10000 chars to prevent token overflow | synchronous execution (blocks until command completes) | uses system default shell (bash/sh on Unix, cmd.exe on Windows)
  Errors: returns "Error: Command timed out" on TimeoutExpired | includes stderr in output | includes exit code for non-zero returns | handles empty output gracefully

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

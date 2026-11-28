"""
Purpose: Cross-platform shell command execution with directory control and output formatting
LLM-Note:
  Dependencies: imports from [subprocess] | imported by [useful_tools/__init__.py] | tested by command execution
  Data flow: Shell() creates instance → .run(command, timeout) or .run_in_dir(command, directory, timeout) → subprocess.run(shell=True) in cwd → captures stdout+stderr → _format_output() truncates if >10000 chars → returns formatted output: str
  State/Effects: executes system commands via subprocess.run(shell=True) | stores default cwd in self.cwd | no file persistence | side effects depend on executed commands (file I/O, network calls, etc.)
  Integration: exposes Shell class with .run(command, timeout), .run_in_dir(command, directory, timeout) | used as agent tool | class methods extracted to tools via extract_methods_from_instance() | instance accessible via agent.tools.shell
  Performance: timeout default 120s; explicit caller values are honored | truncates output >10000 chars to prevent token overflow, keeping stderr and the exit code | synchronous execution (blocks until command completes) | uses system default shell (bash/sh on Unix, cmd.exe on Windows)
  Errors: propagates subprocess.TimeoutExpired so callers can distinguish timeout from success | includes stderr in output | includes exit code for non-zero returns | handles empty output gracefully

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

import os
import subprocess

# Output cap for one command. The tool's own lines (stderr and the exit code)
# are never cut: dropping the exit code makes a failed command read as a
# truncated success, and dropping stderr hides the error that explains it.
MAX_OUTPUT_CHARS = 10_000

# Room for one "... (stream truncated, N total chars)" note. When both streams
# overflow, each keeps this much back so neither can be dropped without saying
# so -- a stderr that filled the whole cap used to erase stdout entirely.
TRUNCATION_NOTE_RESERVE = 64


def _utf8_env() -> dict:
    """Child env that forces UTF-8 I/O regardless of the console codepage.

    On non-UTF-8 Windows locales (Chinese GBK/cp936, Japanese cp932, ...) a child
    Python process would otherwise encode its stdout with the legacy codepage and
    crash on emoji/non-local characters. PYTHONUTF8/PYTHONIOENCODING make it emit
    UTF-8, which pairs with our UTF-8 decoding of the pipe below.
    """
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


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
            timeout: Seconds before timeout (default: 120)

        Returns:
            Command output (stdout + stderr)

        Raises:
            subprocess.TimeoutExpired: If the command exceeds ``timeout``.
        """
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=self.cwd,
            timeout=timeout,
            env=_utf8_env(),
        )

        return self._format_output(result)

    def run_in_dir(self, command: str, directory: str, timeout: int = 120) -> str:
        """Execute command in a specific directory.

        Args:
            command: Shell command to execute
            directory: Directory to run the command in
            timeout: Seconds before timeout (default: 120)

        Returns:
            Command output (stdout + stderr)

        Raises:
            subprocess.TimeoutExpired: If the command exceeds ``timeout``.
        """
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=directory,
            timeout=timeout,
            env=_utf8_env(),
        )

        return self._format_output(result)

    def _format_output(self, result: subprocess.CompletedProcess) -> str:
        """Format subprocess result into readable output."""
        status = f"Exit code: {result.returncode}" if result.returncode != 0 else ""
        stderr = f"STDERR:\n{result.stderr.rstrip()}" if result.stderr else ""
        stdout = result.stdout.rstrip() if result.stdout else ""

        # Truncate the command's streams, never the lines this tool adds.
        # Stderr gets the space first because it is the part a caller acts on,
        # but it cannot spend the last note's worth of budget when stdout also
        # has something to say, or a huge stderr would silently erase stdout.
        remaining = MAX_OUTPUT_CHARS - (len(status) + 1 if status else 0)
        if stderr:
            stderr_budget = remaining - 1
            if stdout:
                stderr_budget -= TRUNCATION_NOTE_RESERVE
            stderr = _fit(stderr, max(0, stderr_budget), "stderr")
            remaining -= len(stderr) + 1
        if stdout:
            stdout = _fit(stdout, remaining, "stdout")

        output = "\n".join(part for part in (stdout, stderr, status) if part)
        return output or "(no output)"


def _fit(text: str, budget: int, label: str) -> str:
    """Cut ``text`` to ``budget`` characters, keeping a note of what was dropped."""
    if len(text) <= budget:
        return text
    note = f"\n... ({label} truncated, {len(text):,} total chars)"
    if len(note) >= budget:
        return text[:max(0, budget)]
    return text[: budget - len(note)] + note

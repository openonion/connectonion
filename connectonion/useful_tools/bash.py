"""
Purpose: Execute bash commands (Git Bash on Windows, else cmd) with timeout and output truncation
LLM-Note:
  Dependencies: imports from [subprocess, shutil, platform] | imported by [useful_tools/__init__.py, useful_prompts/coding_agent/assembler.py] | tested by command execution
  Data flow: receives command: str, description: str, cwd: str, timeout: int → subprocess.run() locally or cancellable Popen in hosted mode → captures stdout+stderr → truncates if >10000 chars → returns formatted output: str
  State/Effects: executes shell commands | hosted runs use an isolated process group so OIP Stop terminates descendants | no persistent state | reads/writes filesystem based on command | can have any side effect depending on command (network calls, file operations, etc.)
  Integration: exposes bash(command, description="", cwd, timeout) function | used as agent tool | description is OPTIONAL (defaults "") — an LLM is prompted to fill it for the approval UI, but direct/programmatic callers (remote.call, co call, scripts) can pass command alone | not passed to shell | on Windows runs Git Bash, or cmd /c when there is none
  Performance: timeout default 120s; explicit caller values are honored | truncates output >10000 chars to prevent token overflow | synchronous execution (blocks until command completes)
  Errors: propagates subprocess.TimeoutExpired so callers can distinguish timeout from success | non-zero exit codes included in output | stderr merged with stdout

Bash tool for executing terminal commands.

Usage:
    from connectonion import Agent, bash

    agent = Agent("coder", tools=[bash])

    # Agent can now use:
    # - bash(command) - Execute bash command, returns output
    # - bash(command, cwd="/path") - Execute in specific directory
    # - bash(command, timeout=60) - Execute with custom timeout

On Windows it runs Git Bash when installed and falls back to `cmd /c`, so a
`co call <address> co status` works against a Windows host (#3123).
"""

import os
import platform
import shutil
import signal
import subprocess
import time

from ..core.interrupt import UserInterrupt


def bash(
    command: str,
    description: str = "",
    cwd: str = ".",
    timeout: int = 120,
    agent=None,
) -> str:
    """Execute a bash command, returns output.

    Args:
        command: Bash command to execute (e.g., "ls -la", "git status")
        description: What this command does (e.g., "Install dependencies"). Optional
            — an LLM should fill it in so the approval UI can show intent, but direct
            callers (scripts, remote.call, co call) may pass just the command.
        cwd: Working directory (default: current directory)
        timeout: Seconds before timeout (default: 120)
        agent: Runtime-injected Agent used only for hosted cancellation.

    Returns:
        Command output (stdout + stderr)

    Raises:
        subprocess.TimeoutExpired: If the command exceeds ``timeout``.
    """
    cancelled = getattr(getattr(agent, "io", None), "is_cancelled", None)
    try:
        if callable(cancelled):
            result = _run_cancellable(command, cwd, timeout, cancelled)
        else:
            result = subprocess.run(
                _argv(command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                timeout=timeout,
            )
    except FileNotFoundError:
        return f"Error: {_argv(command)[0]} not found. This tool requires a bash shell."

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


def _argv(command: str) -> list:
    """The shell that runs `command`, as an argv list (no shell=True).

    On Windows `executable=` with `shell=True` still builds a `cmd.exe /c`
    line, so the list form is the only way to choose the shell there."""
    if platform.system() != "Windows":
        return ["/bin/bash", "-c", command]
    bash_exe = _windows_bash()
    return [bash_exe, "-c", command] if bash_exe else ["cmd", "/c", command]


def _windows_bash():
    """Git Bash, or None. System32\\bash.exe is the WSL launcher: it runs the
    command inside Linux, where this machine's `co` and files are not."""
    git = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe")
    if os.path.isfile(git):
        return git
    found = shutil.which("bash")
    return found if found and "system32" not in found.lower() else None


def _run_cancellable(command, cwd, timeout, cancelled):
    process = subprocess.Popen(
        _argv(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout
    while True:
        if cancelled():
            _terminate_process_group(process)
            raise UserInterrupt()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _terminate_process_group(process)
            raise subprocess.TimeoutExpired(command, timeout)
        try:
            stdout, stderr = process.communicate(timeout=min(0.05, remaining))
            return subprocess.CompletedProcess(
                command, process.returncode, stdout, stderr
            )
        except subprocess.TimeoutExpired:
            continue


def _terminate_process_group(process):
    if process.poll() is not None:
        return
    if not hasattr(os, "killpg"):  # Windows: no process groups to signal
        process.kill()
        process.wait(timeout=1)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=0.5)
        return
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    process.wait(timeout=1)

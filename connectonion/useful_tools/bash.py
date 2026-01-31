"""
Bash tool for executing terminal commands (Unix/Mac only).

Usage:
    from connectonion import Agent, bash

    agent = Agent("coder", tools=[bash])

    # Agent can now use:
    # - bash(command) - Execute bash command, returns output
    # - bash(command, cwd="/path") - Execute in specific directory
    # - bash(command, timeout=60) - Execute with custom timeout

Note: This tool is for Unix/Mac systems. For cross-platform usage, use Shell class instead.
"""

import subprocess
import platform


def bash(command: str, cwd: str = ".", timeout: int = 120) -> str:
    """Execute a bash command, returns output (Unix/Mac only).

    Args:
        command: Bash command to execute (e.g., "ls -la", "git status")
        cwd: Working directory (default: current directory)
        timeout: Seconds before timeout (default: 120, max: 600)

    Returns:
        Command output (stdout + stderr)
    """
    # Check platform
    if platform.system() == "Windows":
        return "Error: bash tool is for Unix/Mac only. Use Shell class for Windows."

    # Cap timeout at 10 minutes
    timeout = min(timeout, 600)

    try:
        result = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds"
    except FileNotFoundError:
        return "Error: /bin/bash not found. This tool requires bash shell."

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

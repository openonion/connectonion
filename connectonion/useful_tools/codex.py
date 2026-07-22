"""
Purpose: Run OpenAI Codex CLI headless as an agent tool, with session resume
LLM-Note:
  Dependencies: imports from [subprocess, json, shutil] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_codex_tool.py]
  Data flow: receives prompt: str, session_id: str, cwd: str, sandbox: str, model: str, timeout: int → builds `codex exec --json` argv (resume subcommand when session_id given) → subprocess.run() → parses JSONL events from stdout (thread.started, item.completed, turn.completed) → returns JSON envelope: str
  State/Effects: executes codex CLI via subprocess | no persistent state in this module | Codex itself persists sessions under ~/.codex/sessions | file writes depend on sandbox level
  Integration: exposes codex(prompt, session_id, cwd, sandbox, model, timeout) function | used as agent tool | session_id from a previous call resumes that Codex session | envelope includes resumed flag so callers can detect silent new-thread fallback
  Performance: timeout default 600s (Codex tasks can run minutes) | synchronous, blocks until CLI exits
  Errors: returns JSON envelope with error field on missing CLI, timeout, bad sandbox value, or non-zero exit | never raises to the agent loop

Codex tool for delegating coding tasks to the OpenAI Codex CLI (headless).

Usage:
    from connectonion import Agent
    from connectonion.useful_tools import codex

    agent = Agent("architect", tools=[codex])
    agent.input("Ask Codex to fix the failing tests in ./myrepo")

    # First call returns a session_id in its JSON result.
    # Passing that session_id back resumes the same Codex session:
    # plan -> implement -> fix review comments, all with full context.

Notes:
    - Requires the `codex` CLI installed and authenticated.
    - Always runs with --json internally: the thread.started event is the
      only reliable source of the session id.
    - Codex exec mode has no interactive approval, so the sandbox level is
      the only safety knob. Default is read-only; escalation is explicit.
"""

import json
import shutil
import subprocess

SANDBOX_LEVELS = ("read-only", "workspace-write", "danger-full-access")


def codex(prompt: str, session_id: str = "", cwd: str = "",
          sandbox: str = "read-only", model: str = "", timeout: int = 600) -> str:
    """Run Codex CLI headless. Pass session_id to resume a previous session.

    Args:
        prompt: Task for Codex (e.g., "fix the failing tests")
        session_id: Session id returned by a previous call, to resume it
        cwd: Directory Codex works in (default: current directory)
        sandbox: "read-only" (default), "workspace-write", or "danger-full-access"
        model: Codex model override (e.g., "gpt-5-codex"); empty uses CLI default
        timeout: Seconds before timeout (default: 600)

    Returns:
        JSON string with provider, session_id, resumed, last_message,
        usage, exit_code — and error when something went wrong.
    """
    if sandbox not in SANDBOX_LEVELS:
        return _envelope(session_id, error=f"Invalid sandbox {sandbox!r}. Use one of: {', '.join(SANDBOX_LEVELS)}")

    if shutil.which("codex") is None:
        return _envelope(session_id, error="codex CLI not found. Install it (npm install -g @openai/codex) and authenticate first.")

    cmd = ["codex", "exec"]
    if session_id:
        cmd += ["resume", session_id]
    cmd += ["--json", "--sandbox", sandbox, "--skip-git-repo-check"]
    if cwd:
        cmd += ["--cd", cwd]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _envelope(session_id, error=f"Codex timed out after {timeout} seconds")

    thread_id, last_message, usage = _parse_events(result.stdout)

    if result.returncode != 0:
        stderr_tail = result.stderr.strip()[-2000:]
        return _envelope(thread_id or session_id, exit_code=result.returncode,
                         error=f"codex exited with code {result.returncode}: {stderr_tail}")

    return _envelope(thread_id, resumed=bool(session_id) and thread_id == session_id,
                     last_message=last_message, usage=usage, exit_code=result.returncode)


def _parse_events(stdout: str):
    """Extract thread id, final agent message, and token usage from JSONL events."""
    thread_id, last_message, usage = "", "", {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id", "")
        elif event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                last_message = item.get("text", "")
        elif event.get("type") == "turn.completed":
            usage = event.get("usage", {})
    return thread_id, last_message, usage


def _envelope(session_id: str, resumed: bool = False, last_message: str = "",
              usage: dict = None, exit_code: int = -1, error: str = "") -> str:
    """Build the JSON result envelope returned to the calling agent."""
    result = {
        "provider": "codex",
        "session_id": session_id,
        "resumed": resumed,
        "last_message": last_message,
        "usage": usage or {},
        "exit_code": exit_code,
    }
    if error:
        result["error"] = error
    return json.dumps(result)

"""
Purpose: Run OpenAI Codex CLI headless as an agent tool, streaming its internal steps to the frontend, with session resume
LLM-Note:
  Dependencies: imports from [subprocess, json, shutil, threading] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_codex_tool.py]
  Data flow: receives prompt: str, session_id: str, cwd: str, sandbox: str, model: str, timeout: int, agent (injected) → builds `codex exec --json` argv (resume subcommand when session_id given) → subprocess.Popen() → reads stdout JSONL line by line as it arrives → forwards each event to agent.io.log("codex_event", ...) when io present → tracks thread.started/item.completed/turn.completed → returns JSON envelope: str
  State/Effects: executes codex CLI via subprocess | streams live events to agent.io | no persistent state in this module | Codex itself persists sessions under ~/.codex/sessions | file writes depend on sandbox level
  Integration: exposes codex(prompt, session_id, cwd, sandbox, model, timeout, agent) function | used as agent tool | agent parameter injected by tool_executor (hidden from LLM) so codex's inner tool calls stream to the client live | session_id from a previous call resumes that Codex session | envelope includes resumed flag so callers can detect silent new-thread fallback
  Performance: timeout default 600s (Codex tasks can run minutes) | streams incrementally so the frontend sees progress instead of waiting for a final blob | watchdog thread kills the process on timeout
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
      only reliable source of the session id, and JSONL lets us stream each
      of Codex's inner steps (command runs, file edits, MCP tool calls, web
      searches) to a watching frontend via agent.io as they happen.
    - Codex exec mode has no interactive approval, so the sandbox level is
      the only safety knob. Default is read-only; escalation is explicit.
"""

import json
import shutil
import subprocess
import threading

SANDBOX_LEVELS = ("read-only", "workspace-write", "danger-full-access")


def codex(prompt: str, session_id: str = "", cwd: str = "",
          sandbox: str = "read-only", model: str = "", timeout: int = 600,
          agent=None) -> str:
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

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Drain stderr in a thread so a full stderr pipe can't deadlock stdout reads.
    stderr_chunks = []
    stderr_thread = threading.Thread(target=lambda: stderr_chunks.append(proc.stderr.read()))
    stderr_thread.start()

    # Watchdog: kill the process if it outlives the timeout.
    state = {"timed_out": False}
    timer = threading.Timer(timeout, lambda: (state.__setitem__("timed_out", True), proc.kill()))
    timer.start()

    thread_id, last_message, usage = "", "", {}
    try:
        for line in proc.stdout:
            event = _parse_line(line)
            if event is None:
                continue
            _forward(agent, event)
            etype = event.get("type")
            if etype == "thread.started":
                thread_id = event.get("thread_id", "")
            elif etype == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    last_message = item.get("text", "")
            elif etype == "turn.completed":
                usage = event.get("usage", {})
        proc.wait()
    finally:
        timer.cancel()
        stderr_thread.join()

    if state["timed_out"]:
        return _envelope(thread_id or session_id, error=f"Codex timed out after {timeout} seconds")

    if proc.returncode != 0:
        stderr_tail = "".join(stderr_chunks).strip()[-2000:]
        return _envelope(thread_id or session_id, exit_code=proc.returncode,
                         error=f"codex exited with code {proc.returncode}: {stderr_tail}")

    return _envelope(thread_id, resumed=bool(session_id) and thread_id == session_id,
                     last_message=last_message, usage=usage, exit_code=proc.returncode)


def _parse_line(line: str):
    """Parse one JSONL line into an event dict, or None if blank/not JSON."""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _forward(agent, event: dict) -> None:
    """Stream one Codex event to a watching frontend, if io is available.

    Lets the client render Codex's inner steps (command runs, file edits,
    MCP tool calls, web searches) live instead of waiting for the final blob.
    """
    if agent is None or getattr(agent, "io", None) is None:
        return
    item = event.get("item", {})
    agent.io.log(
        "codex_event",
        event_type=event.get("type", ""),
        item_type=item.get("type", ""),
        event=event,
    )


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

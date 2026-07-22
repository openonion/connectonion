"""
Purpose: Run OpenAI Codex CLI headless as an agent tool, streaming its internal steps to the frontend, with session resume
LLM-Note:
  Dependencies: imports from [subprocess, json, shutil, threading] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_codex_tool.py]
  Data flow: receives prompt: str, session_id: str, cwd: str, sandbox: str, model: str, timeout: int, approval: str, agent (injected) → approval gate resolves the effective sandbox (manual asks agent.io.request_approval, auto trusts, read-only free) → builds `codex exec --json` argv (resume subcommand when session_id given) → subprocess.Popen() → reads stdout JSONL line by line as it arrives → forwards each event to agent.io.log("codex_event", ...) when io present → tracks thread.started/item.completed/turn.completed → returns JSON envelope: str
  State/Effects: executes codex CLI via subprocess | streams live events to agent.io | no persistent state in this module | Codex itself persists sessions under ~/.codex/sessions | file writes depend on sandbox level
  Integration: exposes codex(prompt, session_id, cwd, sandbox, model, timeout, approval, agent) function | used as agent tool | agent parameter injected by tool_executor (hidden from LLM) so codex's inner tool calls stream to the client live and write access is approved via agent.io.request_approval | session_id from a previous call resumes that Codex session | envelope includes resumed flag so callers can detect silent new-thread fallback
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
    - Requires the `codex` CLI installed and authenticated (backend="cli"),
      or the codex-acp adapter (backend="acp", see codex_acp.py).
    - Always runs with --json internally: the thread.started event is the
      only reliable source of the session id, and JSONL lets us stream each
      of Codex's inner steps (command runs, file edits, MCP tool calls, web
      searches) to a watching frontend via agent.io as they happen.
    - Default sandbox is workspace-write, gated by approval: write access is
      authorized once before launch (manual → asked via agent.io, auto →
      trusted) since codex exec has no interactive approval of its own. With
      no frontend to ask, a write sandbox downgrades to read-only rather than
      escalating silently. The acp backend approves per action instead.
"""

import json
import shutil
import subprocess
import threading

SANDBOX_LEVELS = ("read-only", "workspace-write", "danger-full-access")
APPROVAL_MODES = ("manual", "auto")


BACKENDS = ("cli", "acp")


def codex(prompt: str, session_id: str = "", cwd: str = "",
          sandbox: str = "workspace-write", model: str = "", timeout: int = 600,
          approval: str = "manual", backend: str = "cli", agent=None) -> str:
    """Run Codex and (optionally) resume a previous session.

    Two transports, one signature:
      - backend="cli" (default): drives `codex exec --json` as a one-shot
        subprocess. Approval is coarse — the sandbox is authorized once before
        launch (Codex exec has no interactive approval of its own).
      - backend="acp": drives the codex-acp adapter over the Agent Client
        Protocol (a long-lived JSON-RPC session). Approval is per-action:
        Codex asks before each sensitive step via session/request_permission,
        which maps to agent.io.request_approval.

    Args:
        prompt: Task for Codex (e.g., "fix the failing tests")
        session_id: Session id returned by a previous call, to resume it
        cwd: Directory Codex works in (default: current directory)
        sandbox: "read-only", "workspace-write" (default, lets Codex edit files
            in cwd), or "danger-full-access"
        model: Codex model override (e.g., "gpt-5-codex"); empty uses CLI default
        timeout: Seconds before timeout (default: 600)
        approval: How write access is authorized — "manual" (default: ask the
            human via the frontend) or "auto" (the calling agent approves it
            itself). "read-only" never needs approval.
        backend: "cli" (default) or "acp".

    Returns:
        JSON string with provider, session_id, resumed, last_message,
        usage, exit_code — plus note when the sandbox was adjusted, and
        error when something went wrong.
    """
    if sandbox not in SANDBOX_LEVELS:
        return _envelope(session_id, error=f"Invalid sandbox {sandbox!r}. Use one of: {', '.join(SANDBOX_LEVELS)}")
    if approval not in APPROVAL_MODES:
        return _envelope(session_id, error=f"Invalid approval {approval!r}. Use 'manual' or 'auto'.")
    if backend not in BACKENDS:
        return _envelope(session_id, error=f"Invalid backend {backend!r}. Use 'cli' or 'acp'.")

    if backend == "acp":
        from .codex_acp import run_codex_acp
        return run_codex_acp(prompt, session_id=session_id, cwd=cwd, sandbox=sandbox,
                             model=model, timeout=timeout, approval=approval, agent=agent)

    if shutil.which("codex") is None:
        return _envelope(session_id, error="codex CLI not found. Install it (npm install -g @openai/codex) and authenticate first.")

    sandbox, gate_error, note = _gate_sandbox(sandbox, approval, agent, prompt, cwd)
    if gate_error:
        return _envelope(session_id, error=gate_error)

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
        # errors="replace": never let a stray non-UTF-8 byte crash the read loop.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        return _envelope(session_id, error=f"failed to launch codex: {e}")

    # Drain stderr in a thread so a full stderr pipe can't deadlock stdout reads.
    stderr_chunks = []
    stderr_thread = threading.Thread(target=lambda: stderr_chunks.append(proc.stderr.read()))
    stderr_thread.start()

    # Watchdog: kill the process if it outlives the timeout.
    state = {"timed_out": False}
    timer = threading.Timer(timeout, lambda: (state.__setitem__("timed_out", True), proc.kill()))
    timer.start()

    thread_id, last_message, usage, turn_error = "", "", {}, ""
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
            elif etype == "turn.failed":
                err = event.get("error")
                msg = err.get("message", "") if isinstance(err, dict) else (str(err) if err else "")
                turn_error = msg or turn_error
            elif etype == "error":
                turn_error = event.get("message", "") or turn_error
        proc.wait()
    finally:
        timer.cancel()
        stderr_thread.join()

    if state["timed_out"]:
        return _envelope(thread_id or session_id, error=f"Codex timed out after {timeout} seconds")

    if proc.returncode != 0:
        # Prefer the structured error Codex emits in the JSONL stream over the
        # noisy stderr transport spam; fall back to stderr when none was seen.
        detail = turn_error or "".join(stderr_chunks).strip()[-2000:]
        return _envelope(thread_id or session_id, exit_code=proc.returncode,
                         error=f"codex exited with code {proc.returncode}: {detail}")

    return _envelope(thread_id, resumed=bool(session_id) and thread_id == session_id,
                     last_message=last_message, usage=usage, exit_code=proc.returncode, note=note)


def _gate_sandbox(sandbox, approval, agent, prompt, cwd):
    """Resolve the effective sandbox after the approval gate.

    read-only needs no approval. A write-capable sandbox runs only if the
    calling agent auto-approves, or a human approves via io. With no io to
    ask, it downgrades to read-only rather than silently escalating.

    Returns (effective_sandbox, error, note): error set means reject the run.
    """
    if sandbox == "read-only" or approval == "auto":
        return sandbox, "", ""
    io = getattr(agent, "io", None) if agent is not None else None
    if io is None:
        return "read-only", "", f"downgraded to read-only: {sandbox} needs approval but no interactive client is available"
    approved = io.request_approval("codex", {"sandbox": sandbox, "cwd": cwd or ".", "prompt": prompt})
    if not approved:
        return sandbox, f"Codex run rejected: user denied {sandbox} access", ""
    return sandbox, "", ""


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
    # NB: io.log(event_type, **data) — the first positional IS the event type,
    # so the Codex event's own type must go under a different key ("codex_type"),
    # not "event_type", or it collides with that positional parameter.
    agent.io.log(
        "codex_event",
        codex_type=event.get("type", ""),
        item_type=item.get("type", ""),
        event=event,
    )


def _envelope(session_id: str, resumed: bool = False, last_message: str = "",
              usage: dict = None, exit_code: int = -1, error: str = "", note: str = "") -> str:
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
    if note:
        result["note"] = note
    return json.dumps(result)

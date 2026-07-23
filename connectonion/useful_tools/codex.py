"""
Purpose: Run Codex via its native app-server protocol (our own Python client), streaming steps to the frontend with per-action approval, and resume sessions
LLM-Note:
  Dependencies: imports from [json, os, shutil, subprocess, threading] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_codex_tool.py, tests/e2e/real_api/test_real_codex.py]
  Data flow: codex(prompt, session_id, cwd, sandbox, model, timeout, approval, agent) → spawns `codex app-server` → CodexAppServer speaks newline-delimited JSON-RPC 2.0 → initialize/initialized → thread/start or thread/resume → turn/start → item/started+item/completed notifications converted to the FRONTEND's native events (tool_call / tool_result) via agent.io.log → server-initiated approval requests (item/*/requestApproval, execCommandApproval, applyPatchApproval) answered by the approval gate (manual→agent.io.request_approval, auto→approved, no io→denied) → waits for turn/completed → returns JSON envelope: str
  State/Effects: spawns `codex app-server` subprocess | reader thread parses stdout | streams live events to agent.io using the tool_call/tool_result/approval_needed events the connectonion-ts SDK already renders (NO frontend changes) | Codex persists threads under ~/.codex; file writes depend on sandbox + granted approvals
  Integration: exposes codex(...) and CodexAppServer | this IS the adapter — ConnectOnion's own Python client drives the codex CLI's native app-server (no external codex-acp Node binary) | agent injected by tool_executor (hidden from LLM) | codex binary overridable via $CODEX_CMD | session_id resumes via thread/resume; envelope's resumed flag reports it
  Performance: long-lived process per call | streams incrementally | requests + turn wait have timeouts so a hung server can't block forever
  Errors: returns envelope with error on missing binary, JSON-RPC failure/timeout, or exception | never raises to the agent loop

Codex tool. ConnectOnion drives the codex CLI's built-in `app-server` (OpenAI's
native JSON-RPC 2.0 protocol) directly from Python — our own client is the
adapter, so the only dependency is the `codex` binary itself (no external
codex-acp Node adapter).

Why app-server: session + resume (thread/start, thread/resume), live streaming
of Codex's inner steps (item/* events), and PER-ACTION approval — the server
asks before each sensitive step, which maps onto agent.io.request_approval.

Frontend contract: Codex's steps are streamed as the SAME events the
connectonion-ts SDK already maps to ChatItems — `tool_call` (stable tool_id)
and `tool_result` — so no frontend or SDK change is needed.

Usage:
    from connectonion import Agent
    from connectonion.useful_tools import codex

    agent = Agent("architect", tools=[codex])
    agent.input("Ask Codex to fix the failing tests in ./myrepo")

Requires the `codex` CLI (npm install -g @openai/codex) and Codex auth. Set
$CODEX_CMD to override the binary path/command.
"""

import json
import os
import shutil
import subprocess
import threading

SANDBOX_LEVELS = ("read-only", "workspace-write", "danger-full-access")
APPROVAL_MODES = ("manual", "auto")

# Server-initiated approval requests (v2 item/* and legacy names).
_APPROVAL_METHODS = (
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "execCommandApproval",
    "applyPatchApproval",
)
# Thread items that represent a discrete step worth showing as a tool card.
_TOOL_ITEM_TYPES = ("commandExecution", "fileChange", "mcpToolCall", "webSearch")


def codex(prompt: str, session_id: str = "", cwd: str = "",
          sandbox: str = "workspace-write", model: str = "", timeout: int = 600,
          approval: str = "manual", agent=None) -> str:
    """Run Codex (via `codex app-server`) and optionally resume a session.

    Args:
        prompt: Task for Codex (e.g., "fix the failing tests")
        session_id: Thread id returned by a previous call, to resume it
        cwd: Directory Codex works in (default: current directory)
        sandbox: "read-only", "workspace-write" (default), or "danger-full-access"
        model: Codex model override (e.g., "gpt-5-codex"); empty uses the default
        timeout: Seconds before timeout (default: 600)
        approval: How Codex's per-action approval requests are answered —
            "manual" (default: ask the human via agent.io, rendered as an
            approval card) or "auto" (approve automatically). With no frontend
            to ask, manual denies each request rather than escalating.

    Returns:
        JSON string with provider, session_id, resumed, last_message,
        usage, exit_code — and error when something went wrong.
    """
    if sandbox not in SANDBOX_LEVELS:
        return _envelope(session_id, error=f"Invalid sandbox {sandbox!r}. Use one of: {', '.join(SANDBOX_LEVELS)}")
    if approval not in APPROVAL_MODES:
        return _envelope(session_id, error=f"Invalid approval {approval!r}. Use 'manual' or 'auto'.")

    command = _base_command()
    if command is None:
        return _envelope(session_id, error="codex CLI not found. Install it (npm install -g @openai/codex) or set $CODEX_CMD.")

    chunks = []

    def on_event(event):
        if event.get("kind") == "agent_message":
            chunks.append(event.get("text", ""))
        _forward_ui(agent, event)

    def on_approval(params):
        return _decide_approval(params, approval, agent)

    client = CodexAppServer(command=command, cwd=cwd or ".",
                            on_event=on_event, on_approval=on_approval)
    try:
        client.start()
        client.initialize(timeout=timeout)
        if session_id:
            sid = client.resume_thread(session_id, timeout=timeout)
            resumed = True
        else:
            sid = client.start_thread(sandbox=sandbox, model=model, timeout=timeout)
            resumed = False
        turn = client.run_turn(sid, prompt, cwd=cwd, timeout=timeout)
    except Exception as e:
        return _envelope(session_id, error=f"codex app-server: {e}")
    finally:
        client.close()

    turn = turn or {}
    status = turn.get("status", "")
    if status in ("", "completed", "success", "ok"):
        return _envelope(sid, resumed=resumed, last_message="".join(chunks),
                         usage=turn.get("usage", {}), exit_code=0)
    return _envelope(sid, resumed=resumed, last_message="".join(chunks),
                     usage=turn.get("usage", {}), exit_code=1, error=f"turn {status}: {_turn_error(turn)}")


def _turn_error(turn):
    """Best-effort error text from a failed turn/completed|turn/failed payload."""
    err = turn.get("error")
    if isinstance(err, dict):
        return err.get("message", "") or json.dumps(err)[:300]
    return str(err) if err else "no details"


def _base_command():
    """codex launch argv: $CODEX_CMD (space-split) else PATH lookup, + app-server."""
    env = os.environ.get("CODEX_CMD")
    if env:
        return env.split() + ["app-server"]
    found = shutil.which("codex")
    return [found, "app-server"] if found else None


def _forward_ui(agent, event):
    """Convert one Codex thread event into the frontend's native event stream.

    The connectonion-ts SDK maps `tool_call` (stable tool_id) → a running tool
    card and `tool_result` (same id) → its completion, so Codex's inner command
    runs / file edits render live with no frontend change.
    """
    if agent is None or getattr(agent, "io", None) is None:
        return
    kind = event.get("kind", "")
    if kind == "tool_start":
        agent.io.log("tool_call", tool_id=event.get("id", ""),
                     name=event.get("name", "codex"), args={})
    elif kind == "tool_end":
        agent.io.log("tool_result", tool_id=event.get("id", ""),
                     status="error" if event.get("failed") else "done",
                     result=event.get("name", ""))


def _decide_approval(params, approval, agent):
    """Answer a server approval request: auto approves; manual asks the human via
    io.request_approval (rendered as an approval card); no io denies."""
    if approval == "auto":
        return "approved"
    io = getattr(agent, "io", None) if agent is not None else None
    if io is None:
        return "denied"
    action = _approval_summary(params)
    return "approved" if io.request_approval("codex", {"action": action}) else "denied"


def _approval_summary(params):
    """Human-readable summary of what Codex wants to do."""
    cmd = params.get("command")
    if isinstance(cmd, list):
        return " ".join(cmd)
    return params.get("reason") or params.get("cwd") or "codex action"


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


class CodexAppServer:
    """Minimal client for `codex app-server`: JSON-RPC 2.0 over stdio."""

    def __init__(self, command, cwd=None, on_event=None, on_approval=None):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event or (lambda e: None)
        self.on_approval = on_approval or (lambda p: "approved")
        self.proc = None
        self._next_id = 0
        self._pending = {}
        self._lock = threading.Lock()
        self._turn_done = threading.Event()
        self._turn_result = {}

    # ── lifecycle ────────────────────────────────────────────────

    def start(self):
        self.proc = subprocess.Popen(
            self.command, cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        threading.Thread(target=self._read_loop, daemon=True).start()

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    # ── high-level flow ──────────────────────────────────────────

    def initialize(self, timeout=60):
        self.request("initialize", {
            "clientInfo": {"name": "connectonion", "title": "ConnectOnion", "version": "1"},
            "capabilities": {"experimentalApi": False,
                             "optOutNotificationMethods": ["item/agentMessage/delta",
                                                            "item/reasoning/textDelta"]},
        }, timeout=timeout)
        self._notify("initialized", {})

    def start_thread(self, sandbox="workspace-write", model="", timeout=60):
        params = {"cwd": self.cwd or ".", "sandbox": sandbox,
                  "approvalPolicy": "on-request", "approvalsReviewer": "user"}
        if model:
            params["model"] = model
        result = self.request("thread/start", params, timeout=timeout)
        return result["thread"]["id"]

    def resume_thread(self, thread_id, timeout=60):
        self.request("thread/resume", {"threadId": thread_id, "cwd": self.cwd or "."},
                     timeout=timeout)
        return thread_id

    def run_turn(self, thread_id, prompt, cwd="", timeout=600):
        self._turn_done.clear()
        self._turn_result = {}
        self.request("turn/start", {
            "threadId": thread_id, "cwd": cwd or self.cwd or ".",
            "input": [{"type": "text", "text": prompt}],
        }, timeout=timeout)
        if not self._turn_done.wait(timeout):
            raise TimeoutError(f"turn timed out after {timeout}s")
        return self._turn_result

    # ── JSON-RPC plumbing ────────────────────────────────────────

    def request(self, method, params, timeout=60):
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            slot = {"event": threading.Event(), "result": None, "error": None}
            self._pending[req_id] = slot
        self._send({"id": req_id, "method": method, "params": params})
        if not slot["event"].wait(timeout):
            self._pending.pop(req_id, None)
            raise TimeoutError(f"{method} timed out after {timeout}s")
        if slot["error"] is not None:
            raise RuntimeError(f"{method} failed: {slot['error']}")
        return slot["result"]

    def _notify(self, method, params):
        self._send({"method": method, "params": params})

    def _send(self, message):
        message.setdefault("jsonrpc", "2.0")
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def _read_loop(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            # A raised callback must not kill the reader thread — that would
            # strand every pending request until it times out.
            try:
                self._dispatch(message)
            except Exception:
                continue

    def _dispatch(self, message):
        method = message.get("method")
        if method is None and "id" in message:                 # response to our request
            slot = self._pending.pop(message["id"], None)
            if slot:
                slot["result"] = message.get("result")
                slot["error"] = message.get("error")
                slot["event"].set()
            return
        if "id" in message:                                    # server -> client request
            self._handle_server_request(message["id"], method, message.get("params", {}))
        else:                                                  # notification
            self._handle_notification(method, message.get("params", {}))

    def _handle_server_request(self, req_id, method, params):
        if method in _APPROVAL_METHODS:
            try:
                decision = self.on_approval(params)
            except Exception:
                decision = "denied"      # fail safe: never leave it hanging
            self._send({"id": req_id, "result": {"decision": decision}})
        else:
            self._send({"id": req_id,
                        "error": {"code": -32601, "message": f"method not supported: {method}"}})

    def _handle_notification(self, method, params):
        if method == "turn/completed":
            self._turn_result = params.get("turn", params)
            self._turn_done.set()
        elif method == "turn/failed":
            self._turn_result = {"status": "failed", **params}
            self._turn_done.set()
        elif method == "item/started":
            self.on_event(self._item_event(params.get("item", {}), start=True))
        elif method == "item/completed":
            self.on_event(self._item_event(params.get("item", {}), start=False))

    @staticmethod
    def _item_event(item, start):
        """Normalize a thread item into a flat event for forwarding."""
        itype = item.get("type", "")
        if itype == "agentMessage":
            return {"kind": "agent_message", "text": item.get("text") or item.get("content", "")}
        if itype in _TOOL_ITEM_TYPES:
            name = item.get("command") or item.get("title") or item.get("path") or itype
            if isinstance(name, list):
                name = " ".join(name)
            failed = item.get("status") in ("failed", "error") or item.get("exitCode") not in (None, 0)
            return {"kind": "tool_start" if start else "tool_end",
                    "id": item.get("id", ""), "name": name, "failed": failed}
        return {"kind": itype, "id": item.get("id", "")}

"""
Purpose: ACP (Agent Client Protocol) transport for the codex tool — drive codex-acp over JSON-RPC with per-action approval
LLM-Note:
  Dependencies: imports from [json, os, shutil, subprocess, threading] and [.codex._envelope] | imported lazily by [.codex.codex when backend="acp"] | tested by [tests/unit/test_codex_acp.py, tests/e2e/real_api/test_real_codex.py]
  Data flow: run_codex_acp(prompt, session_id, cwd, sandbox, model, timeout, approval, agent) → spawns codex-acp with `-c sandbox_mode=...`/`-c model=...` overrides → ACPClient speaks newline-delimited JSON-RPC → initialize → session/new or session/load(resume) → session/prompt → session/update notifications normalized and forwarded to agent.io.log("codex_event", ...) → session/request_permission answered via approval gate (manual→agent.io.request_approval, auto→allow) → returns the same JSON envelope as the cli backend
  State/Effects: spawns codex-acp subprocess | reader thread parses stdout | forwards live events to agent.io | Codex persists sessions under ~/.codex; file writes depend on sandbox + granted permissions
  Integration: exposes run_codex_acp(...) and ACPClient | ACP Client role (ConnectOnion drives codex-acp the Agent) | permission is per-action, unlike the coarse pre-launch gate of the cli backend | command overridable via $CODEX_ACP_CMD for tests / npx
  Performance: long-lived process per call | streams incrementally | request() has a timeout so a hung agent can't block forever
  Errors: returns envelope with error on missing binary, ACP request failure/timeout, or agent exception | never raises to the agent loop

ACP transport for `codex(..., backend="acp")`. ConnectOnion plays the ACP
Client; codex-acp is the Agent. Transport is JSON-RPC 2.0 as newline-delimited
JSON over stdio (protocol on stdout, logs on stderr) — same framing as MCP.

Stdlib only.
"""

import json
import os
import shutil
import subprocess
import threading

from .codex import _envelope


def run_codex_acp(prompt, session_id="", cwd="", sandbox="workspace-write",
                  model="", timeout=600, approval="manual", agent=None):
    """Drive codex-acp for one prompt turn and return the codex envelope."""
    base = _base_command()
    if base is None:
        return _envelope(session_id, error="codex-acp not found. Install it (npm install -g @zed-industries/codex-acp) or set $CODEX_ACP_CMD.")

    command = list(base) + ["-c", f'sandbox_mode="{sandbox}"']
    if model:
        command += ["-c", f'model="{model}"']

    chunks = []

    def on_event(event):
        # Only the assistant's message is the result; agent_thought_chunk is
        # reasoning and must NOT leak into last_message (it is still streamed
        # to the frontend below for display).
        if event.get("acp_update") == "agent_message_chunk":
            chunks.append(event.get("text", ""))
        _forward_acp(agent, event)

    def on_permission(tool_call, options):
        return _decide_permission(tool_call, options, approval, agent)

    client = ACPClient(command=command, cwd=cwd or ".",
                       on_event=on_event, on_permission=on_permission)
    try:
        client.start()
        client.initialize(timeout=timeout)
        if session_id:
            sid = client.load_session(session_id, timeout=timeout)
            resumed = True
        else:
            sid = client.new_session(timeout=timeout)
            resumed = False
        stop = client.prompt(sid, prompt, timeout=timeout)
    except Exception as e:
        return _envelope(session_id, error=f"codex-acp: {e}")
    finally:
        client.close()

    exit_code = 0 if stop and stop != "error" else 1
    return _envelope(sid, resumed=resumed, last_message="".join(chunks),
                     exit_code=exit_code)


def _base_command():
    """codex-acp launch argv: $CODEX_ACP_CMD (space-split), else PATH lookup."""
    env = os.environ.get("CODEX_ACP_CMD")
    if env:
        return env.split()
    found = shutil.which("codex-acp")
    return [found] if found else None


def _forward_acp(agent, event):
    """Stream a normalized ACP update to the frontend, mirroring the cli
    backend's codex_event shape so a client renders both the same way."""
    if agent is None or getattr(agent, "io", None) is None:
        return
    agent.io.log("codex_event", codex_type=event.get("acp_update", ""),
                 item_type=event.get("tool_kind", ""), event=event)


def _decide_permission(tool_call, options, approval, agent):
    """Answer a session/request_permission: auto allows; manual asks the human
    via io.request_approval; with no io to ask, deny (never silently allow)."""
    if approval == "auto":
        return _option_id(options, "allow")
    io = getattr(agent, "io", None) if agent is not None else None
    if io is None:
        return _option_id(options, "reject")
    approved = io.request_approval("codex", {"action": tool_call.get("title", "")})
    return _option_id(options, "allow" if approved else "reject")


def _option_id(options, want):
    """Pick the option whose kind starts with want ('allow'/'reject')."""
    for opt in options:
        if opt.get("kind", "").startswith(want):
            return opt.get("optionId")
    return options[0].get("optionId") if options else want


class ACPClient:
    """Minimal ACP Client: JSON-RPC 2.0 over newline-delimited stdio."""

    def __init__(self, command, cwd=None, on_event=None, on_permission=None):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event or (lambda e: None)
        self.on_permission = on_permission or (lambda tc, opts: _option_id(opts, "allow"))
        self.proc = None
        self._next_id = 0
        self._pending = {}
        self._lock = threading.Lock()

    # ── lifecycle ────────────────────────────────────────────────

    def start(self):
        self.proc = subprocess.Popen(
            self.command, cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        threading.Thread(target=self._read_loop, daemon=True).start()

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    # ── high-level ACP flow ──────────────────────────────────────

    def initialize(self, timeout=60):
        return self.request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
            "clientInfo": {"name": "connectonion", "version": "1"},
        }, timeout=timeout)

    def new_session(self, timeout=60):
        return self.request("session/new", {"cwd": self.cwd or ".", "mcpServers": []},
                            timeout=timeout)["sessionId"]

    def load_session(self, session_id, timeout=60):
        self.request("session/load",
                     {"sessionId": session_id, "cwd": self.cwd or ".", "mcpServers": []},
                     timeout=timeout)
        return session_id

    def prompt(self, session_id, text, timeout=600):
        result = self.request("session/prompt",
                              {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
                              timeout=timeout)
        return result.get("stopReason", "")

    # ── JSON-RPC plumbing ────────────────────────────────────────

    def request(self, method, params, timeout=60):
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            slot = {"event": threading.Event(), "result": None, "error": None}
            self._pending[req_id] = slot
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        if not slot["event"].wait(timeout):
            self._pending.pop(req_id, None)
            raise TimeoutError(f"{method} timed out after {timeout}s")
        if slot["error"] is not None:
            raise RuntimeError(f"{method} failed: {slot['error']}")
        return slot["result"]

    def _send(self, message):
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
            # A raised callback (on_event/on_permission) must not kill the reader
            # thread — that would strand every pending request until it times out.
            try:
                self._dispatch(message)
            except Exception:
                continue

    def _dispatch(self, message):
        if "method" not in message and "id" in message:      # response to our request
            slot = self._pending.pop(message["id"], None)
            if slot:
                slot["result"] = message.get("result")
                slot["error"] = message.get("error")
                slot["event"].set()
            return
        method = message.get("method")
        if "id" in message:                                   # agent -> client request
            self._handle_server_request(message["id"], method, message.get("params", {}))
        elif method == "session/update":                      # agent -> client notification
            self._handle_update(message.get("params", {}))

    def _handle_server_request(self, req_id, method, params):
        if method == "session/request_permission":
            options = params.get("options", [])
            try:
                option_id = self.on_permission(params.get("toolCall", {}), options)
            except Exception:
                # Never leave the agent's permission request unanswered (it would
                # hang the turn). On handler failure, fail safe: deny.
                option_id = _option_id(options, "reject")
            self._send({"jsonrpc": "2.0", "id": req_id,
                        "result": {"outcome": {"outcome": "selected", "optionId": option_id}}})
        else:
            self._send({"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32601, "message": f"method not supported: {method}"}})

    def _handle_update(self, params):
        update = params.get("update", {})
        kind = update.get("sessionUpdate", "")
        event = {"acp_update": kind, "session_id": params.get("sessionId", "")}
        if kind in ("agent_message_chunk", "agent_thought_chunk"):
            event["text"] = update.get("content", {}).get("text", "")
        elif kind in ("tool_call", "tool_call_update"):
            event["tool_call_id"] = update.get("toolCallId", "")
            event["title"] = update.get("title", "")
            event["tool_kind"] = update.get("kind", "")
            event["status"] = update.get("status", "")
        elif kind == "plan":
            event["entries"] = update.get("entries", [])
        self.on_event(event)

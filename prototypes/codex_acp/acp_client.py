"""
PROTOTYPE — minimal Agent Client Protocol (ACP) client for driving codex-acp.

This is a spike, not a shipped tool. It exists to validate that ConnectOnion
can play the ACP *Client* role: spawn an ACP *Agent* (codex-acp) as a
subprocess, speak JSON-RPC 2.0 over newline-delimited stdio, and turn the
agent's `session/update` notifications into ConnectOnion-style io events —
including the `session/request_permission` round-trip that headless
`codex exec` cannot do.

Transport (same as MCP): one JSON-RPC object per line on stdio, no embedded
newlines; protocol on stdout, logs on stderr.

Message directions we handle:
  - client -> agent request:      initialize, session/new, session/load, session/prompt
  - agent  -> client notification: session/update  (streamed progress)
  - agent  -> client request:      session/request_permission, fs/*  (we must reply)

Stdlib only — ACP is just JSON-RPC over pipes, so no dependency is needed.
"""

import json
import subprocess
import threading


class ACPClient:
    def __init__(self, command, cwd=None, on_event=None, on_permission=None):
        """
        Args:
            command: argv to launch the ACP agent, e.g. ["codex-acp"] or
                     ["npx", "-y", "@zed-industries/codex-acp"]
            cwd: working directory the agent operates in
            on_event: callback(dict) for normalized session/update events —
                      the ConnectOnion side would forward these to agent.io.log
            on_permission: callback(tool_call, options) -> option_id, deciding
                      how to answer session/request_permission. Defaults to
                      auto-approving the first option (prototype only).
        """
        self.command = command
        self.cwd = cwd
        self.on_event = on_event or (lambda e: None)
        self.on_permission = on_permission or self._auto_approve
        self.proc = None
        self._next_id = 0
        self._pending = {}            # id -> {"event": Event, "result": ..., "error": ...}
        self._lock = threading.Lock()
        self._reader = None

    # ── lifecycle ────────────────────────────────────────────────

    def start(self):
        self.proc = subprocess.Popen(
            self.command, cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    # ── high-level ACP flow ──────────────────────────────────────

    def initialize(self):
        return self.request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
            "clientInfo": {"name": "connectonion", "version": "prototype"},
        })

    def new_session(self):
        result = self.request("session/new", {"cwd": self.cwd or ".", "mcpServers": []})
        return result["sessionId"]

    def load_session(self, session_id):
        """Resume a previous session (the ACP equivalent of `codex exec resume`)."""
        self.request("session/load", {"sessionId": session_id, "cwd": self.cwd or ".", "mcpServers": []})
        return session_id

    def prompt(self, session_id, text):
        """Send one user turn. Blocks until the turn ends; updates stream via on_event."""
        result = self.request("session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": text}],
        })
        return result.get("stopReason", "")

    # ── JSON-RPC plumbing ────────────────────────────────────────

    def request(self, method, params):
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            slot = {"event": threading.Event(), "result": None, "error": None}
            self._pending[req_id] = slot
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        slot["event"].wait()
        if slot["error"] is not None:
            raise RuntimeError(f"ACP {method} failed: {slot['error']}")
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
            self._dispatch(message)

    def _dispatch(self, message):
        # Response to one of our requests: has id, no method.
        if "method" not in message and "id" in message:
            slot = self._pending.pop(message["id"], None)
            if slot:
                slot["result"] = message.get("result")
                slot["error"] = message.get("error")
                slot["event"].set()
            return

        method = message.get("method")
        # Agent -> client request (needs a reply): has method + id.
        if "id" in message:
            self._handle_server_request(message["id"], method, message.get("params", {}))
            return

        # Agent -> client notification: has method, no id.
        if method == "session/update":
            self._handle_update(message.get("params", {}))

    def _handle_server_request(self, req_id, method, params):
        if method == "session/request_permission":
            tool_call = params.get("toolCall", {})
            options = params.get("options", [])
            option_id = self.on_permission(tool_call, options)
            self._send({"jsonrpc": "2.0", "id": req_id, "result": {
                "outcome": {"outcome": "selected", "optionId": option_id},
            }})
        else:
            # Unknown request (e.g. fs/* we didn't advertise) — reply with error.
            self._send({"jsonrpc": "2.0", "id": req_id, "error": {
                "code": -32601, "message": f"method not supported: {method}",
            }})

    def _handle_update(self, params):
        """Normalize an ACP session/update into a flat ConnectOnion-style event."""
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

    @staticmethod
    def _auto_approve(tool_call, options):
        """Prototype default: pick the first 'allow'-ish option, else the first."""
        for opt in options:
            if opt.get("kind", "").startswith("allow"):
                return opt.get("optionId")
        return options[0].get("optionId") if options else "allow"

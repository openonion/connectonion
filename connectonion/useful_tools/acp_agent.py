"""
Purpose: Drive any ACP-speaking coding agent (Claude Code, Codex, Gemini CLI, …) as a sub-agent, streaming its inner steps to the frontend
LLM-Note:
  Dependencies: imports from [json, os, shutil, subprocess, threading, pathlib] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_acp_agent.py]
  Data flow: acp_agent(prompt, engine, session_id, cwd, timeout, approval, agent) → resolves engine command from ENGINES (or explicit command) → spawns the ACP agent subprocess → JSON-RPC 2.0 over newline-delimited stdio → initialize → session/new or session/load → session/prompt → session/update notifications converted to the frontend's native events (tool_call / tool_result) via agent.io.log → session/request_permission answered through the approval gate → returns JSON envelope: str
  State/Effects: spawns one subprocess per call | reader thread parses stdout | streams live events to agent.io using the tool_call/tool_result/approval_needed events that @connectonion/react already renders (NO frontend changes) | session persistence is the engine's own (e.g. codex threads under ~/.codex)
  Integration: exposes acp_agent(...), engine_status(), ENGINES | ConnectOnion plays the ACP *Client* role — the engine is the ACP Agent | agent injected by tool_executor (hidden from LLM) | escape hatch: command="..." drives any ACP agent
  Performance: one subprocess per call | streams incrementally | request timeouts so a hung agent cannot block forever
  Errors: returns envelope with error on missing binary, JSON-RPC failure/timeout, or exception | never raises to the agent loop

One ACP client, every ACP engine. Claude Code and Codex do not speak ACP
natively — both route through adapters maintained by the ACP org — while
Gemini CLI speaks it natively. The engine table captures that; the protocol
handling below is identical for all of them. That is the point: written once,
this tool gains every agent in the ACP registry.

Deliberately NOT the ``acp`` SDK's client side: that API is asyncio-based, and
tools run as plain synchronous functions on the agent's worker thread with no
event loop to join. JSON-RPC over pipes is small enough to speak directly —
the same choice ``codex.py`` made for the app-server protocol.

Approval semantics (differs from codex.py's, deliberately): codex negotiates a
sandbox up front, so an unexpected callback there fails closed even on "auto".
ACP has no sandbox negotiation — permission requests are the *only* boundary —
so "auto" here answers them with the allow option. "manual" asks the operator
through the same approval UI as every other tool; "deny" rejects every request.

Usage:
    from connectonion import Agent
    from connectonion.useful_tools import acp_agent

    agent = Agent("architect", tools=[acp_agent])
    agent.input("Use acp_agent with engine claude-code to fix the tests")
"""

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

APPROVAL_MODES = ("manual", "auto", "deny")

# Engine table. Command is how to start the ACP agent; auth_hint is a local
# file whose presence usually means the underlying CLI is logged in — a cheap,
# honest heuristic (reported as such), not proof.
ENGINES = {
    "claude-code": {
        "command": ["npx", "-y", "@agentclientprotocol/claude-agent-acp"],
        "requires": "npx",
        "auth_hint": "~/.claude/.credentials.json",
    },
    "codex": {
        "command": ["npx", "-y", "@agentclientprotocol/codex-acp"],
        "requires": "npx",
        "auth_hint": "~/.codex/auth.json",
    },
    "gemini": {
        "command": ["gemini", "--experimental-acp"],
        "requires": "gemini",
        "auth_hint": "~/.gemini/oauth_creds.json",
    },
}


def engine_status() -> str:
    """Report which ACP engines are ready on this machine.

    For each engine: is the launcher installed, and does the underlying CLI
    look authenticated (credential file present — a heuristic, not proof).
    Lets the delegating agent prefer a ready engine instead of failing
    mid-task, and lets the UI show "Codex ✓ logged in · Gemini ✗ not found".
    """
    rows = []
    for name, spec in ENGINES.items():
        installed = shutil.which(spec["requires"]) is not None
        authenticated = Path(spec["auth_hint"]).expanduser().exists()
        rows.append({
            "engine": name,
            "installed": installed,
            "authenticated": authenticated if installed else False,
            "auth_check": "credential file (heuristic)",
        })
    return json.dumps({"engines": rows})


def acp_agent(prompt: str, engine: str = "", session_id: str = "",
              cwd: str = "", timeout: int = 600, approval: str = "manual",
              command: str = "", agent=None) -> str:
    """Run a prompt on an ACP coding agent and return its result.

    Args:
        prompt: The task for the engine.
        engine: Which engine to use: 'claude-code', 'codex', or 'gemini'.
            Check engine_status() first to pick one that is ready.
        session_id: Resume this engine session (from a previous envelope).
        cwd: Working directory the engine operates in (default: current).
        timeout: Seconds to wait for the turn to complete.
        approval: 'manual' asks the operator for each permission request;
            'auto' answers with the allow option; 'deny' rejects every request.
        command: Escape hatch — full command line of any ACP agent to drive
            instead of a named engine (e.g. "my-acp-agent --flag").

    Returns:
        JSON envelope: engine, session_id (pass back to resume), resumed,
        stop_reason, result text, and error if the run failed.
    """
    if approval not in APPROVAL_MODES:
        return _envelope(engine, error=(
            f"Invalid approval {approval!r}. Use 'manual', 'auto', or 'deny'."))

    if command:
        argv, engine = command.split(), engine or "custom"
    else:
        engine = engine or "claude-code"
        spec = ENGINES.get(engine)
        if spec is None:
            return _envelope(engine, error=(
                f"Unknown engine {engine!r}. Use one of {sorted(ENGINES)} "
                "or pass command=..."))
        if shutil.which(spec["requires"]) is None:
            return _envelope(engine, error=(
                f"{spec['requires']!r} not found on PATH — {engine} cannot "
                "start. Check engine_status()."))
        argv = spec["command"]

    client = _ACPClient(
        argv, cwd=cwd or os.getcwd(),
        on_event=lambda event: _forward_ui(agent, event),
        on_permission=lambda tool_call, options: _pick_option(
            tool_call, options, approval, agent),
    )
    try:
        client.start()
        client.initialize()
        resumed = False
        if session_id:
            resumed = client.load_session(session_id)
        if not resumed:
            session_id = client.new_session()
        stop_reason = client.prompt(session_id, prompt, timeout=timeout)
        return _envelope(engine, session_id=session_id, resumed=resumed,
                         stop_reason=stop_reason,
                         result=client.message_text())
    except Exception as error:
        return _envelope(engine, session_id=session_id, error=str(error))
    finally:
        client.close()


def _envelope(engine, session_id="", resumed=False, stop_reason="",
              result="", error=None) -> str:
    payload = {"engine": engine, "session_id": session_id, "resumed": resumed,
               "stop_reason": stop_reason, "result": result}
    if error:
        payload["error"] = error
    return json.dumps(payload)


def _forward_ui(agent, event):
    """Convert one ACP session/update into the frontend's native event stream.

    The @connectonion/react package maps `tool_call` (stable tool_id) → a
    running tool card and `tool_result` (same id) → its completion, so the
    engine's inner command runs / file edits render live with no oo-chat
    change — the same contract codex.py already ships.
    """
    if agent is None or getattr(agent, "io", None) is None:
        return
    kind = event.get("acp_update", "")
    status = event.get("status", "")
    if kind == "tool_call" or (kind == "tool_call_update"
                               and status in ("", "pending", "in_progress")):
        agent.io.log("tool_call", tool_id=event.get("tool_call_id", ""),
                     name=event.get("title", "") or "acp", args={},
                     status="in_progress")
    elif kind == "tool_call_update" and status in ("completed", "failed"):
        agent.io.log("tool_result", tool_id=event.get("tool_call_id", ""),
                     status=status, result=event.get("title", ""))


def _pick_option(tool_call, options, approval, agent):
    """Answer one session/request_permission.

    Returns the chosen optionId, or None for "grant nothing" — the client
    then answers with ACP's ``cancelled`` outcome, which needs no optionId.
    A refusal must never fall back to whatever option happens to be first:
    on a malformed option list that could *be* the allow option.
    """
    allow = _first_option(options, "allow")
    reject = _first_option(options, "reject")
    if approval == "deny":
        return reject
    if approval == "auto":
        return allow
    # manual — same authority rules as codex.py: hosted dialogs belong to the
    # operator; a non-admin requester cannot approve an expansion of power.
    requester = (getattr(agent, "current_session", {}).get("requester")
                 if agent is not None else None)
    if requester and requester.get("level") != "admin":
        return reject
    io = getattr(agent, "io", None) if agent is not None else None
    if io is None:
        return reject
    details = {"title": tool_call.get("title", ""),
               "tool_call_id": tool_call.get("toolCallId", "")}
    return allow if io.request_approval("acp_agent", details) else reject


def _first_option(options, kind_prefix):
    for opt in options:
        if opt.get("kind", "").startswith(kind_prefix):
            return opt.get("optionId")
    return None


class _ACPClient:
    """Minimal ACP client: JSON-RPC 2.0 over newline-delimited stdio.

    Message directions:
      - client -> agent request:       initialize, session/new, session/load,
                                       session/prompt
      - agent  -> client notification: session/update (streamed progress)
      - agent  -> client request:      session/request_permission (we reply)
    """

    def __init__(self, command, cwd, on_event, on_permission):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event
        self.on_permission = on_permission
        self.proc = None
        self._next_id = 0
        self._pending = {}            # id -> {"event", "result", "error"}
        self._lock = threading.Lock()
        self._chunks = []             # accumulated agent_message_chunk text

    # ── lifecycle ────────────────────────────────────────────────

    def start(self):
        self.proc = subprocess.Popen(
            self.command, cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        threading.Thread(target=self._read_loop, daemon=True).start()

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    # ── high-level ACP flow ──────────────────────────────────────

    def initialize(self):
        return self._request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {"fs": {"readTextFile": False,
                                          "writeTextFile": False}},
            "clientInfo": {"name": "connectonion", "version": "1"},
        })

    def new_session(self):
        result = self._request("session/new",
                               {"cwd": self.cwd, "mcpServers": []})
        return result["sessionId"]

    def load_session(self, session_id) -> bool:
        """Resume; False when the engine does not know the session."""
        try:
            self._request("session/load", {"sessionId": session_id,
                                           "cwd": self.cwd, "mcpServers": []})
            return True
        except RuntimeError:
            return False

    def prompt(self, session_id, text, timeout):
        result = self._request("session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": text}],
        }, timeout=timeout)
        return result.get("stopReason", "")

    def message_text(self) -> str:
        return "".join(self._chunks)

    # ── JSON-RPC plumbing ────────────────────────────────────────

    def _request(self, method, params, timeout=60):
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            slot = {"event": threading.Event(), "result": None, "error": None}
            self._pending[req_id] = slot
        self._send({"jsonrpc": "2.0", "id": req_id,
                    "method": method, "params": params})
        if not slot["event"].wait(timeout):
            self._pending.pop(req_id, None)
            raise TimeoutError(f"ACP {method} timed out after {timeout}s")
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
                continue                      # stray non-protocol output
            self._dispatch(message)
        # EOF: the agent died. Fail every waiter instead of letting them
        # sit out their full timeout against a process that cannot answer.
        with self._lock:
            pending, self._pending = self._pending, {}
        for slot in pending.values():
            slot["error"] = "agent process exited"
            slot["event"].set()

    def _dispatch(self, message):
        if "method" not in message and "id" in message:
            slot = self._pending.pop(message["id"], None)
            if slot:
                slot["result"] = message.get("result")
                slot["error"] = message.get("error")
                slot["event"].set()
            return

        method = message.get("method")
        if "id" in message:                   # agent -> client request
            self._handle_agent_request(message["id"], method,
                                       message.get("params", {}))
            return
        if method == "session/update":        # notification
            self._handle_update(message.get("params", {}))

    def _handle_agent_request(self, req_id, method, params):
        if method == "session/request_permission":
            option_id = self.on_permission(params.get("toolCall", {}),
                                           params.get("options", []))
            outcome = ({"outcome": "selected", "optionId": option_id}
                       if option_id else {"outcome": "cancelled"})
            self._send({"jsonrpc": "2.0", "id": req_id,
                        "result": {"outcome": outcome}})
        else:
            # e.g. fs/* we did not advertise — refuse, do not hang the agent.
            self._send({"jsonrpc": "2.0", "id": req_id, "error": {
                "code": -32601, "message": f"method not supported: {method}",
            }})

    def _handle_update(self, params):
        update = params.get("update", {})
        kind = update.get("sessionUpdate", "")
        event = {"acp_update": kind}
        if kind == "agent_message_chunk":
            self._chunks.append(update.get("content", {}).get("text", ""))
            return                            # accumulated, not a UI card
        if kind in ("tool_call", "tool_call_update"):
            event["tool_call_id"] = update.get("toolCallId", "")
            event["title"] = update.get("title", "")
            event["status"] = update.get("status", "")
        self.on_event(event)

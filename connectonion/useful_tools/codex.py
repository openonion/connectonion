"""
Purpose: Run Codex via its native app-server protocol, stream steps and permission requests to the frontend, and resume sessions
LLM-Note:
  Dependencies: imports from [json, os, shutil, subprocess, threading, time] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_codex_tool.py, tests/e2e/real_api/test_real_codex.py]
  Data flow: codex(prompt, session_id, cwd, sandbox, model, timeout, approval, agent) → spawns `codex app-server` → CodexAppServer speaks newline-delimited JSON-RPC 2.0 → initialize/initialized → thread/start or thread/resume with the requested policy reapplied → turn/start → item/started+item/completed notifications converted to the FRONTEND's native events (tool_call / tool_result) via agent.io.log → method-specific approval responses are answered by the approval gate → waits for turn/completed → returns JSON envelope: str
  State/Effects: spawns `codex app-server` subprocess | reader thread parses stdout | streams live events to agent.io using the tool_call/tool_result/approval_needed events the connectonion-ts SDK already renders (NO frontend changes) | Codex persists threads under ~/.codex; file writes depend on sandbox + granted approvals
  Integration: exposes codex(...) and CodexAppServer | this IS the adapter — ConnectOnion's own Python client drives the codex CLI's native app-server (no external codex-acp Node binary) | agent injected by tool_executor (hidden from LLM) | codex binary overridable via $CODEX_CMD | session_id resumes via thread/resume; envelope's resumed flag reports it
  Performance: long-lived process per call | streams incrementally | requests + turn wait have timeouts so a hung server can't block forever
  Errors: returns envelope with error on missing binary, JSON-RPC failure/timeout, or exception | never raises to the agent loop

Codex tool. ConnectOnion drives the codex CLI's built-in `app-server` (OpenAI's
native JSON-RPC 2.0 protocol) directly from Python — our own client is the
adapter, so the only dependency is the `codex` binary itself (no external
codex-acp Node adapter).

Why app-server: session + resume (thread/start, thread/resume), live streaming
of Codex's inner steps (item/* events), and interactive permission callbacks
when the selected policy requires them. Those callbacks map onto
agent.io.request_approval.

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
import signal
import subprocess
import threading
import time

SANDBOX_LEVELS = ("read-only", "workspace-write", "danger-full-access")
APPROVAL_MODES = ("manual", "auto", "deny")

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
        approval: "manual" asks the operator when Codex requests permission;
            "auto" runs commands without prompts inside the selected sandbox
            but refuses permission-profile escalation; "deny" refuses every
            unexpected permission request. With no frontend, or in a hosted
            session whose requester is not an admin, manual fails closed. The
            policy is reapplied on resume.

    Returns:
        JSON string with provider, session_id, resumed, last_message,
        usage, exit_code — and error when something went wrong.
    """
    if sandbox not in SANDBOX_LEVELS:
        return _envelope(session_id, error=f"Invalid sandbox {sandbox!r}. Use one of: {', '.join(SANDBOX_LEVELS)}")
    if approval not in APPROVAL_MODES:
        return _envelope(
            session_id,
            error=(
                f"Invalid approval {approval!r}. Use 'manual', 'auto', or 'deny'."
            ),
        )
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        return _envelope(session_id, error="Timeout must be a positive integer.")

    command = _base_command()
    if command is None:
        return _envelope(session_id, error="codex CLI not found. Install it (npm install -g @openai/codex) or set $CODEX_CMD.")

    chunks = []

    def on_event(event):
        if event.get("kind") == "agent_message":
            chunks.append(event.get("text", ""))
        _forward_ui(agent, event)

    def on_approval(method, params):
        return _approval_allowed(method, params, approval, agent)

    client = CodexAppServer(command=command, cwd=cwd or ".",
                            on_event=on_event, on_approval=on_approval)
    deadline = time.monotonic() + timeout
    try:
        client.start()
        client.initialize(timeout=_remaining(deadline))
        approval_policy = "untrusted" if approval == "manual" else "never"
        if session_id:
            sid = client.resume_thread(
                session_id,
                sandbox=sandbox,
                model=model,
                approval_policy=approval_policy,
                timeout=_remaining(deadline),
            )
            resumed = True
        else:
            sid = client.start_thread(
                sandbox=sandbox,
                model=model,
                approval_policy=approval_policy,
                timeout=_remaining(deadline),
            )
            resumed = False
        turn = client.run_turn(
            sid,
            prompt,
            cwd=cwd,
            timeout=_remaining(deadline),
        )
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


def _remaining(deadline):
    """Seconds left in one end-to-end tool-call budget."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("operation timed out")
    return remaining


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


def _approval_allowed(method, params, approval, agent):
    """Whether one server approval request may proceed."""
    if approval == "auto":
        # A permissions request can expand the selected sandbox (for example,
        # by granting network or an additional filesystem root). ``auto`` is
        # intentionally automatic *inside* the sandbox, not permission to
        # redefine it.
        return method != "item/permissions/requestApproval"
    if approval == "deny":
        return False
    requester = (
        getattr(agent, "current_session", {}).get("requester")
        if agent is not None
        else None
    )
    # Hosted approval dialogs belong to the operator. A local run has no
    # requester record and keeps the existing interactive behaviour.
    if requester and requester.get("level") != "admin":
        return False
    io = getattr(agent, "io", None) if agent is not None else None
    if io is None:
        return False
    return bool(io.request_approval("codex", _approval_details(method, params)))


def _approval_response(method, params, allowed):
    """Build the response shape required by each app-server protocol method."""
    if method in (
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
    ):
        return {"decision": "accept" if allowed else "decline"}
    if method == "item/permissions/requestApproval":
        return {
            "permissions": params.get("permissions", {}) if allowed else {},
            "scope": "turn",
        }
    if allowed:
        return {"decision": "approved"}
    return {
        "decision": {
            "denied": {"rejection": "Denied by ConnectOnion approval policy."}
        }
    }


def _approval_details(method, params):
    """Show the concrete scope of one Codex permission request."""
    cmd = params.get("command")
    if isinstance(cmd, list):
        cmd = " ".join(cmd)
    if isinstance(cmd, str) and cmd.strip():
        return {
            "action": cmd,
            "command": cmd,
            "cwd": params.get("cwd", ""),
            "reason": params.get("reason", ""),
        }
    if method in {"item/fileChange/requestApproval", "applyPatchApproval"}:
        root = params.get("grantRoot") or params.get("cwd") or "unknown path"
        file_changes = params.get("fileChanges", {})
        files = list(file_changes) if isinstance(file_changes, dict) else []
        scope = f" under {root}"
        if files:
            scope += f" ({', '.join(files)})"
        return {
            "action": f"Allow file changes{scope}",
            "grant_root": root,
            "files": files,
            "reason": params.get("reason", ""),
        }
    if method == "item/permissions/requestApproval":
        permissions = params.get("permissions", {})
        return {
            "action": f"Grant permissions: {json.dumps(permissions, sort_keys=True)}",
            "permissions": permissions,
            "cwd": params.get("cwd", ""),
            "reason": params.get("reason", ""),
        }
    action = params.get("reason") or params.get("cwd") or "codex action"
    return {"action": action, "reason": params.get("reason", "")}


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


def _terminate_process_tree(process):
    """Bounded best-effort cleanup of the app-server and its descendants."""
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                shell=False,
            )
            if result.returncode != 0:
                process.kill()
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, 0)
    except OSError:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


class CodexAppServer:
    """Minimal client for `codex app-server`: JSON-RPC 2.0 over stdio."""

    def __init__(self, command, cwd=None, on_event=None, on_approval=None):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event or (lambda e: None)
        self.on_approval = on_approval or (lambda method, params: False)
        self.proc = None
        self._next_id = 0
        self._pending = {}
        self._lock = threading.Lock()
        self._turn_done = threading.Event()
        self._turn_result = {}
        self._stderr_tail = ""
        self._stderr_thread = None
        self._exit_error = None

    # ── lifecycle ────────────────────────────────────────────────

    def start(self):
        with self._lock:
            self._exit_error = None
        self._stderr_tail = ""
        platform_options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        self.proc = subprocess.Popen(
            self.command, cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            shell=False,
            **platform_options,
        )
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()
        threading.Thread(target=self._read_loop, daemon=True).start()

    def close(self):
        if not self.proc:
            return
        _terminate_process_tree(self.proc)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _read_stderr(self):
        """Drain stderr without allowing diagnostics to grow without bound."""
        try:
            for chunk in iter(lambda: self.proc.stderr.read(1024), ""):
                self._stderr_tail = (self._stderr_tail + chunk)[-4000:]
        except (OSError, ValueError):
            pass

    # ── high-level flow ──────────────────────────────────────────

    def initialize(self, timeout=60):
        self.request("initialize", {
            "clientInfo": {"name": "connectonion", "title": "ConnectOnion", "version": "1"},
            "capabilities": {"experimentalApi": False,
                             "optOutNotificationMethods": ["item/agentMessage/delta",
                                                            "item/reasoning/textDelta"]},
        }, timeout=timeout)
        self._notify("initialized", {})

    def start_thread(
        self,
        sandbox="workspace-write",
        model="",
        approval_policy="on-request",
        timeout=60,
    ):
        params = {"cwd": self.cwd or ".", "sandbox": sandbox,
                  "approvalPolicy": approval_policy, "approvalsReviewer": "user"}
        if model:
            params["model"] = model
        result = self.request("thread/start", params, timeout=timeout)
        return result["thread"]["id"]

    def resume_thread(
        self,
        thread_id,
        sandbox="workspace-write",
        model="",
        approval_policy="on-request",
        timeout=60,
    ):
        params = {
            "threadId": thread_id,
            "cwd": self.cwd or ".",
            "sandbox": sandbox,
            "approvalPolicy": approval_policy,
            "approvalsReviewer": "user",
        }
        if model:
            params["model"] = model
        result = self.request("thread/resume", params, timeout=timeout)
        returned_id = (result or {}).get("thread", {}).get("id")
        if returned_id != thread_id:
            raise RuntimeError(
                f"thread/resume returned {returned_id!r}, expected {thread_id!r}"
            )
        return returned_id

    def run_turn(self, thread_id, prompt, cwd="", timeout=600):
        deadline = time.monotonic() + timeout
        self._turn_done.clear()
        self._turn_result = {}
        self.request("turn/start", {
            "threadId": thread_id, "cwd": cwd or self.cwd or ".",
            "input": [{"type": "text", "text": prompt}],
        }, timeout=_remaining(deadline))
        if not self._turn_done.wait(_remaining(deadline)):
            raise TimeoutError(f"turn timed out after {timeout}s")
        return self._turn_result

    # ── JSON-RPC plumbing ────────────────────────────────────────

    def request(self, method, params, timeout=60):
        with self._lock:
            if self._exit_error is not None:
                raise RuntimeError(self._exit_error)
            self._next_id += 1
            req_id = self._next_id
            slot = {"event": threading.Event(), "result": None, "error": None}
            self._pending[req_id] = slot
        try:
            self._send({"id": req_id, "method": method, "params": params})
        except (OSError, ValueError) as exc:
            with self._lock:
                self._pending.pop(req_id, None)
                error = self._exit_error
            raise RuntimeError(error or f"{method} could not be sent: {exc}") from exc
        if not slot["event"].wait(timeout):
            with self._lock:
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
        try:
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
        except (OSError, ValueError):
            pass
        finally:
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=0.1)
            self._fail_pending(self._server_exit_error())

    def _server_exit_error(self):
        code = self.proc.poll()
        message = f"app-server exited unexpectedly (code {code})"
        detail = self._stderr_tail.strip().replace("\n", " ")[-1000:]
        return f"{message}: {detail}" if detail else message

    def _fail_pending(self, error):
        with self._lock:
            self._exit_error = self._exit_error or error
            pending = list(self._pending.values())
            self._pending.clear()
        for slot in pending:
            slot["error"] = error
            slot["event"].set()
        if not self._turn_done.is_set():
            self._turn_result = {"status": "failed", "error": error}
            self._turn_done.set()

    def _dispatch(self, message):
        method = message.get("method")
        if method is None and "id" in message:                 # response to our request
            with self._lock:
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
                allowed = bool(self.on_approval(method, params))
            except Exception:
                allowed = False
            self._send(
                {
                    "id": req_id,
                    "result": _approval_response(method, params, allowed),
                }
            )
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

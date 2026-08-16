"""
Purpose: Run Codex via its native app-server protocol, stream steps and permission requests to the frontend, and resume sessions
LLM-Note:
  Dependencies: imports from [atexit, json, os, shutil, subprocess, threading, time] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_codex_tool.py, tests/e2e/real_api/test_real_codex.py]
  Data flow: codex(prompt, session_id, cwd, sandbox, model, timeout, approval, agent) → spawns `codex app-server` → CodexAppServer speaks newline-delimited JSON-RPC 2.0 → initialize/initialized → thread/start or thread/resume with the requested policy reapplied → turn/start → item/started+item/completed notifications converted to OIP-aligned frontend events via agent.io.log → method-specific approval responses are answered by the approval gate → waits for turn/completed → returns JSON envelope: str
  State/Effects: spawns `codex app-server` subprocess | reader thread parses stdout | open-only threads remain in a process-local registry for at most 15 minutes (maximum 8) until their first turn persists the rollout | streams live events to agent.io using the tool_call/tool_result/approval_needed events that @connectonion/react already renders (NO frontend changes) | Codex persists threads under ~/.codex; file writes depend on sandbox + granted approvals
  Integration: exposes codex(...) and CodexAppServer | this is the native adapter: ConnectOnion's Python client drives Codex app-server directly | agent injected by tool_executor (hidden from LLM) | codex binary overridable via $CODEX_CMD | session_id resumes via thread/resume; envelope's resumed flag reports it
  Performance: one process per active call; open-only keeps its initialized process until first follow-up/expiry | streams incrementally | requests + turn wait have timeouts so a hung server can't block forever
  Errors: returns envelope with error on missing binary, JSON-RPC failure/timeout, or exception | never raises to the agent loop

Codex tool. ConnectOnion drives the codex CLI's built-in `app-server` (OpenAI's
native JSON-RPC 2.0 protocol) directly from Python — our own client is the
adapter, so the only dependency is the `codex` binary itself (no external
third-party protocol bridge).

Why app-server: session + resume (thread/start, thread/resume), live streaming
of Codex's inner steps (item/* events), and interactive permission callbacks
when the selected policy requires them. Those callbacks map onto
agent.io.request_approval.

Frontend contract: Codex's steps are streamed as the SAME events the
`@connectonion/react` package already maps to ChatItems — `tool_call` (stable
tool_id) and `tool_result` — so no oo-chat change is needed.

Usage:
    from connectonion import Agent
    from connectonion.useful_tools import codex

    agent = Agent("architect", tools=[codex])
    agent.input("Ask Codex to fix the failing tests in ./myrepo")

Requires the `codex` CLI (npm install -g @openai/codex) and Codex auth. Set
$CODEX_CMD to override the binary path/command.
"""

import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time

from ..core.provider_events import (
    command_phase,
    provider_activity_event,
    provider_status_summary,
    remember_provider_activity,
)

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

# A newly started Codex thread is not written to ~/.codex until its first turn.
# Keep an open-only app-server alive so the Work Room's first message can use
# the exact provider thread id that was shown to the user.  Once that first
# turn completes, Codex has persisted the rollout and ordinary thread/resume
# works across later tool calls and Host restarts.
_OPEN_THREAD_TTL_SECONDS = 15 * 60
_MAX_OPEN_THREADS = 8
_open_threads = {}
_open_threads_lock = threading.Lock()


def codex(prompt: str = "", session_id: str = "", cwd: str = "",
          sandbox: str = "workspace-write", model: str = "", timeout: int = 600,
          approval: str = "manual", agent=None) -> str:
    """Run Codex (via `codex app-server`) and optionally resume a session.

    Args:
        prompt: Task for Codex (e.g., "fix the failing tests"). Omit it to
            create or resume a provider thread without submitting a turn.
        session_id: Thread id returned by a previous call, to resume it
        cwd: Directory Codex works in (default: current directory)
        sandbox: "read-only", "workspace-write" (default), or "danger-full-access"
        model: Codex model override (e.g., "gpt-5-codex"); empty uses the default
        timeout: Seconds before timeout (default: 600)
        approval: "manual" asks the operator when Codex requests permission;
            "auto" runs without prompts inside the selected sandbox and fails
            closed on unexpected approval callbacks; "deny" also refuses every
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
        return _approval_allowed(
            method,
            params,
            approval,
            agent,
            fallback_cwd=working_directory,
        )

    cancelled = _provider_cancellation_check(agent)
    working_directory = cwd or "."
    cancellation_check = cancelled if callable(cancelled) else None
    client = None
    deadline = time.monotonic() + timeout
    force_close = False
    keep_open = False
    try:
        has_prompt = bool(prompt.strip())
        approval_policy = "untrusted" if approval == "manual" else "never"
        if session_id and has_prompt:
            client = _take_open_thread(
                session_id,
                cwd=working_directory,
                sandbox=sandbox,
                model=model,
                approval_policy=approval_policy,
            )
        reused_open_thread = client is not None
        if client is not None:
            client.on_event = on_event
            client.on_approval = on_approval
            client.cancelled = cancellation_check or (lambda: False)
            client.refresh_account(timeout=_remaining(deadline))
            sid = session_id
            resumed = True
        else:
            client = CodexAppServer(
                command=command,
                cwd=working_directory,
                on_event=on_event,
                on_approval=on_approval,
                cancelled=cancellation_check,
            )
            client.start()
            client.initialize(timeout=_remaining(deadline))
            if has_prompt:
                client.refresh_account(timeout=_remaining(deadline))
        if not reused_open_thread:
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
        if not has_prompt:
            if not session_id:
                _store_open_thread(
                    sid,
                    client,
                    cwd=working_directory,
                    sandbox=sandbox,
                    model=model,
                    approval_policy=approval_policy,
                )
                keep_open = True
            return _envelope(
                sid, resumed=resumed, exit_code=0, opened=True
            )
        turn = client.run_turn(
            sid, prompt, cwd=cwd, timeout=_remaining(deadline)
        )
    except _ProviderCancelled as e:
        force_close = True
        return _envelope(session_id, error=f"codex app-server: {e}")
    except Exception as e:
        return _envelope(session_id, error=f"codex app-server: {e}")
    finally:
        if client is not None and not keep_open:
            if force_close:
                client.close(force=True)
            else:
                client.close()

    turn = turn or {}
    status = turn.get("status", "")
    if status in ("", "completed", "success", "ok"):
        return _envelope(sid, resumed=resumed, last_message="".join(chunks),
                         usage=turn.get("usage", {}), exit_code=0)
    return _envelope(sid, resumed=resumed, last_message="".join(chunks),
                     usage=turn.get("usage", {}), exit_code=1, error=f"turn {status}: {_turn_error(turn)}")


def _thread_config(cwd, sandbox, model, approval_policy):
    return cwd, sandbox, model, approval_policy


def _store_open_thread(
    thread_id, client, *, cwd, sandbox, model, approval_policy
):
    """Keep a no-turn thread alive until its first Work Room message."""
    record = {
        "client": client,
        "config": _thread_config(cwd, sandbox, model, approval_policy),
        "opened_at": time.monotonic(),
    }
    timer = threading.Timer(
        _OPEN_THREAD_TTL_SECONDS, _expire_open_thread, (thread_id, client)
    )
    timer.daemon = True
    record["timer"] = timer
    with _open_threads_lock:
        previous = _open_threads.pop(thread_id, None)
        _open_threads[thread_id] = record
        evicted = []
        while len(_open_threads) > _MAX_OPEN_THREADS:
            oldest = min(
                _open_threads,
                key=lambda key: _open_threads[key]["opened_at"],
            )
            evicted.append(_open_threads.pop(oldest))
    _close_thread_records([previous] if previous is not None else [])
    _close_thread_records(evicted)
    timer.start()


def _take_open_thread(
    thread_id, *, cwd, sandbox, model, approval_policy
):
    """Claim a matching live open-only thread for its first provider turn."""
    _close_expired_open_threads()
    expected = _thread_config(cwd, sandbox, model, approval_policy)
    with _open_threads_lock:
        record = _open_threads.get(thread_id)
        if record is None:
            return None
        _open_threads.pop(thread_id, None)
    record["timer"].cancel()
    if record["config"] != expected:
        record["client"].close()
        return None
    return record["client"]


def _close_expired_open_threads(now=None):
    now = time.monotonic() if now is None else now
    with _open_threads_lock:
        expired = [
            thread_id
            for thread_id, record in _open_threads.items()
            if now - record["opened_at"] >= _OPEN_THREAD_TTL_SECONDS
        ]
        records = [_open_threads.pop(thread_id) for thread_id in expired]
    _close_thread_records(records)


def _expire_open_thread(thread_id, client):
    with _open_threads_lock:
        record = _open_threads.get(thread_id)
        if record is None or record["client"] is not client:
            return
        _open_threads.pop(thread_id, None)
    record["client"].close()


def _close_thread_records(records):
    for record in records:
        record["timer"].cancel()
        record["client"].close()


def _close_open_threads():
    """Reap open-only app-servers when the Host process exits."""
    with _open_threads_lock:
        records = list(_open_threads.values())
        _open_threads.clear()
    _close_thread_records(records)


atexit.register(_close_open_threads)


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

    The @connectonion/react package maps `tool_call` (stable tool_id) → a
    running tool card and `tool_result` (same id) → its completion, so Codex's
    inner command runs / file edits render live with no oo-chat change.
    """
    if agent is None or getattr(agent, "io", None) is None:
        return
    kind = event.get("kind", "")
    parent_id = _active_parent_tool_call_id(agent)
    correlation = ({"invocationId": f"codex:{parent_id}",
                    "parentToolCallId": parent_id} if parent_id else {})
    if kind == "tool_start":
        _emit_safe_provider_activity(agent, event, "running", correlation)
        _emit_provider_event(agent, "tool_call", tool_id=event.get("id", ""),
                             name=event.get("name", "codex"),
                             args=event.get("args", {}),
                             status="in_progress", provider="codex",
                             **correlation)
    elif kind == "tool_end":
        _emit_safe_provider_activity(
            agent,
            event,
            "failed" if event.get("failed") else "completed",
            correlation,
        )
        _emit_provider_event(agent, "tool_result", tool_id=event.get("id", ""),
                             name=event.get("name", "codex"),
                             args=event.get("args", {}),
                             status="failed" if event.get("failed") else "completed",
                             result=event.get("result", ""), provider="codex",
                             **correlation)


def _emit_safe_provider_activity(agent, event, status, correlation):
    """Send a redacted OIP activity before the legacy generic compatibility event."""
    activity_id = event.get("id")
    invocation_id = correlation.get("invocationId")
    if not isinstance(activity_id, str) or not activity_id or not invocation_id:
        return
    details = event.get("args")
    fields = provider_activity_event(
        provider="codex",
        activity_id=activity_id,
        sequence=_provider_activity_sequence(agent, invocation_id, activity_id),
        native_kind=event.get("native_kind", event.get("name", "")),
        status=status,
        name=event.get("name", ""),
        details=details if isinstance(details, dict) else {},
    )
    fields.pop("type")
    remember_provider_activity(agent, invocation_id, fields)
    _emit_provider_event(agent, "provider_activity", **fields, **correlation)


def _provider_activity_sequence(agent, invocation_id, activity_id):
    """Keep start/result updates on one stable sequence number for replay."""
    sequences = getattr(agent, "_provider_activity_sequences", None)
    if not isinstance(sequences, dict):
        sequences = {}
        setattr(agent, "_provider_activity_sequences", sequences)
    key = (invocation_id, activity_id)
    if key not in sequences:
        sequences[key] = 1 + max(
            (value for (known_invocation, _), value in sequences.items()
             if known_invocation == invocation_id),
            default=0,
        )
    return sequences[key]


def _active_parent_tool_call_id(agent):
    session = getattr(agent, "current_session", None)
    value = session.get("_active_tool_call_id") if isinstance(session, dict) else None
    return value if isinstance(value, str) and value else None


def _provider_cancellation_check(agent):
    """Scope a Work Room Stop to this Codex invocation when the IO supports it."""
    io = getattr(agent, "io", None)
    parent_id = _active_parent_tool_call_id(agent)
    invocation_id = f"codex:{parent_id}" if parent_id else ""
    targeted = getattr(io, "is_provider_cancelled", None)
    global_cancelled = getattr(io, "is_cancelled", None)

    def cancelled():
        if callable(global_cancelled) and global_cancelled():
            return True
        return bool(invocation_id and callable(targeted) and targeted(invocation_id))

    return cancelled


def _emit_provider_event(agent, event_type, **fields):
    entry = {"type": event_type, **fields}
    record = getattr(agent, "_record_trace", None)
    if callable(record) and isinstance(getattr(agent, "current_session", None), dict):
        record(entry)
        stream_live = getattr(getattr(agent, "io", None), "send_live_trace", None)
        if callable(stream_live):
            stream_live(entry)
    else:
        if event_type == "tool_result":
            fields.pop("name", None)
            fields.pop("args", None)
        agent.io.log(event_type, **fields)


def _approval_allowed(method, params, approval, agent, *, fallback_cwd=""):
    """Whether one server approval request may proceed."""
    if approval == "auto":
        # ``approvalPolicy=never`` already permits work inside the selected
        # sandbox without callbacks. Any callback here is therefore an
        # unexpected request to expand that boundary (including legacy command
        # or file requests), so fail closed.
        return False
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
    context = _approval_context(agent, params)
    presentation = _provider_approval_presentation(method, params, fallback_cwd=fallback_cwd)
    if context:
        context["providerApproval"] = presentation
    if context:
        _emit_provider_event(
            agent,
            "provider_invocation",
            invocationId=context["invocationId"],
            parentToolCallId=context["parentToolCallId"],
            provider="codex",
            providerDisplayName="Codex",
            status="awaiting_approval",
            currentSummary=provider_status_summary("awaiting_approval"),
        )
    try:
        approved = bool(
            io.request_approval(
                "codex",
                _approval_details(
                    method,
                    params,
                    fallback_cwd=fallback_cwd,
                    presentation=presentation,
                ),
                context=context or None,
            )
        )
        # A client response is never sufficient to expand a Work Room's verified
        # boundary. The provider still receives a normal decline for an elevated
        # request, even if a stale or custom client sends `approved: true`.
        return approved and presentation["allowOnce"]
    finally:
        if context:
            _emit_provider_event(
                agent,
                "provider_invocation",
                invocationId=context["invocationId"],
                parentToolCallId=context["parentToolCallId"],
                provider="codex",
                providerDisplayName="Codex",
                status="running",
                currentSummary=provider_status_summary("running"),
            )


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


def _approval_context(agent, params):
    parent_id = _active_parent_tool_call_id(agent)
    if not parent_id:
        return {}
    context = {
        "provider": "codex",
        "invocationId": f"codex:{parent_id}",
        "parentToolCallId": parent_id,
    }
    for key in ("itemId", "item_id", "id"):
        value = params.get(key)
        if isinstance(value, str) and value:
            context["activityId"] = value
            break
    return context


def _approval_details(method, params, *, fallback_cwd="", presentation=None):
    """Return the safe legacy presentation fields for one Codex approval."""
    presentation = presentation or _provider_approval_presentation(
        method, params, fallback_cwd=fallback_cwd
    )
    return {
        "action": presentation["action"],
        "scope": presentation["scope"],
        "reason": presentation["reason"],
    }


def _provider_approval_presentation(method, params, *, fallback_cwd=""):
    """Describe verified approval scope without exposing provider transport data."""
    is_file_change = method in {"item/fileChange/requestApproval", "applyPatchApproval"}
    command = params.get("command")
    if isinstance(command, list):
        command = " ".join(str(part) for part in command)
    if isinstance(command, str) and command.strip():
        action, reason = _command_approval_copy(command)
    elif is_file_change:
        action = "Make workspace file changes"
        reason = "Apply the requested workspace file changes"
    elif method == "item/permissions/requestApproval":
        action = "Expand provider permissions"
        reason = "Review the requested permission expansion"
    else:
        action = "Perform a provider action"
        reason = "Codex requested approval to continue"
    requested_root = params.get("grantRoot") if is_file_change else params.get("cwd")
    if not isinstance(requested_root, str) or not requested_root:
        requested_root = params.get("cwd") if is_file_change else requested_root
    scope_classification = _approval_scope_classification(requested_root, fallback_cwd)
    if isinstance(command, str) and _requests_external_effect(command):
        # A Work Room directory is not authority to publish, fetch, or contact
        # another machine. Keep the command hidden, but require a broader
        # policy rather than allowing it through the filesystem label.
        scope_classification = "elevated"
    scope = {
        "workroom": "This Work Room only",
        "elevated": "Outside this Work Room",
        "unknown": "Boundary could not be verified",
    }[scope_classification]
    presentation = {
        "action": action,
        "scope": scope,
        "reason": reason,
        "scopeClassification": scope_classification,
        # Only a positively verified Work Room boundary may be approved. An
        # omitted or malformed scope is not a smaller request; it is unknown.
        "allowOnce": scope_classification == "workroom",
        # Native Codex approvals are one request at a time. Calling this a
        # session trust grant would promise authority this adapter does not have.
        "allowSession": False,
    }
    files = _approval_file_names(
        params,
        fallback_cwd=fallback_cwd,
        include_command=bool(isinstance(command, str) and command.strip()),
    )
    if files:
        presentation["files"] = files
    return presentation


def _command_approval_copy(command):
    """Return a finite, decision-useful command label without disclosing it."""
    phase = command_phase(details={"command": command})
    return {
        "compile_c11": (
            "Compile the requested C11 program",
            "Compile the requested workspace files before continuing",
        ),
        "compile_c": (
            "Compile the requested C program",
            "Compile the requested workspace files before continuing",
        ),
        "compile_and_test": (
            "Compile and run the requested tests",
            "Verify the requested workspace changes before continuing",
        ),
        "test": (
            "Run the requested tests",
            "Verify the requested workspace changes before continuing",
        ),
        "run": (
            "Run the requested program",
            "Verify the requested program before continuing",
        ),
        "inspect": (
            "Inspect the workspace",
            "Check the requested workspace result before continuing",
        ),
        "command": (
            "Run a workspace command",
            "Codex requested approval to continue",
        ),
    }[phase]


def _requests_external_effect(command):
    return bool(re.search(
        r"(?:^|\s)(?:curl|wget|ssh|scp|rsync|nc)(?:\s|$)"
        r"|(?:^|\s)git\s+(?:push|fetch|pull|clone)(?:\s|$)"
        r"|(?:^|\s)(?:npm|pnpm)\s+(?:publish|install)(?:\s|$)"
        r"|(?:^|\s)pip(?:3)?\s+install(?:\s|$)",
        command.lower(),
    ))


def _approval_scope_classification(requested_root, fallback_cwd):
    if not isinstance(fallback_cwd, str) or not fallback_cwd:
        return "unknown"
    if not isinstance(requested_root, str) or not requested_root:
        return "workroom"
    if not os.path.isabs(requested_root):
        return "elevated" if ".." in requested_root.replace("\\", "/").split("/") else "workroom"
    try:
        workroom = os.path.realpath(fallback_cwd)
        requested = os.path.realpath(requested_root)
        return "workroom" if os.path.commonpath((workroom, requested)) == workroom else "elevated"
    except (OSError, ValueError):
        return "unknown"


def _approval_file_names(params, *, fallback_cwd="", include_command=False):
    """Return only verified basenames, never raw paths or arbitrary arguments."""
    file_changes = params.get("fileChanges", {})
    candidates = list(file_changes) if isinstance(file_changes, dict) else []
    names = []
    for candidate in candidates[:8]:
        if not _is_inside_workroom(candidate, fallback_cwd):
            continue
        name = candidate.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        if name and name not in {".", ".."} and name not in names:
            names.append(name[:128])
    if include_command:
        command = params.get("command")
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        if isinstance(command, str):
            # Bare C source/header names resolve inside the already verified
            # command cwd. We intentionally never extract a path, flag, URL,
            # variable, or provider-controlled free-form token for the UI.
            for name in re.findall(r"(?<![\w./-])([A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.(?:c|h))(?![\w.-])", command):
                if name not in names:
                    names.append(name)
                if len(names) == 8:
                    break
    return names


def _is_inside_workroom(candidate, fallback_cwd):
    if not isinstance(candidate, str) or not candidate:
        return False
    if not isinstance(fallback_cwd, str) or not fallback_cwd:
        return False
    try:
        workroom = os.path.realpath(fallback_cwd)
        path = os.path.realpath(candidate)
        return os.path.commonpath((workroom, path)) == workroom
    except (OSError, ValueError):
        return False


def _display_cwd(value):
    """Keep approval context useful without exposing an operator's full path."""
    if not isinstance(value, str) or not value:
        return ""
    if not os.path.isabs(value):
        return value
    normalized = value.rstrip("/\\")
    return os.path.basename(normalized) or "."


def _envelope(session_id: str, resumed: bool = False, last_message: str = "",
              usage: dict = None, exit_code: int = -1, error: str = "",
              opened: bool = False) -> str:
    """Build the JSON result envelope returned to the calling agent."""
    result = {
        "provider": "codex",
        "session_id": session_id,
        "resumed": resumed,
        "last_message": last_message,
        "usage": usage or {},
        "exit_code": exit_code,
    }
    if opened:
        result["opened"] = True
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
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.terminate()
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
        except OSError:
            pass
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


def _kill_process_tree(process):
    """Immediately stop a revoked provider; no post-interrupt grace window."""
    if os.name == "nt":
        _terminate_process_tree(process)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.kill()
        except OSError:
            return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


class _ProviderCancelled(Exception):
    """The enclosing agent revoked this provider invocation."""


class CodexAppServer:
    """Minimal client for `codex app-server`: JSON-RPC 2.0 over stdio."""

    def __init__(
        self,
        command,
        cwd=None,
        on_event=None,
        on_approval=None,
        cancelled=None,
    ):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event or (lambda e: None)
        self.on_approval = on_approval or (lambda method, params: False)
        self.cancelled = cancelled or (lambda: False)
        self.proc = None
        self._next_id = 0
        self._pending = {}
        self._lock = threading.Lock()
        self._turn_done = threading.Event()
        self._turn_result = {}
        self._stderr_tail = ""
        self._stderr_thread = None
        self._exit_error = None
        # A human deciding on a nested approval is not active Codex execution.
        # Keep that wall time separate from the bounded turn budget so a careful
        # review cannot make the next provider step time out immediately.
        self._approval_lock = threading.Lock()
        self._approval_wait_seconds = 0.0
        self._approval_started_at = None

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

    def close(self, force=False):
        if not self.proc:
            return
        if force:
            _kill_process_tree(self.proc)
        else:
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

    def refresh_account(self, timeout=60):
        """Let Codex refresh its managed auth without exposing credentials."""
        return self.request("account/read", {"refreshToken": True}, timeout=timeout)

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
        approval_pause_mark = self._approval_pause_mark()
        self._turn_done.clear()
        self._turn_result = {}
        self.request("turn/start", {
            "threadId": thread_id, "cwd": cwd or self.cwd or ".",
            "input": [{"type": "text", "text": prompt}],
        }, timeout=_remaining(deadline))
        self._wait_for_turn(
            self._turn_done,
            deadline,
            approval_pause_mark,
            "turn",
            timeout,
        )
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
        try:
            self._wait_for(
                slot["event"], time.monotonic() + timeout, method, timeout
            )
        except (TimeoutError, _ProviderCancelled):
            with self._lock:
                self._pending.pop(req_id, None)
            raise
        if slot["error"] is not None:
            raise RuntimeError(f"{method} failed: {slot['error']}")
        return slot["result"]

    def _wait_for(self, event, deadline, operation, timeout):
        """Wait within one budget while honoring the worker's revoked lease."""
        while True:
            if self.cancelled():
                raise _ProviderCancelled(f"{operation} interrupted")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{operation} timed out after {timeout}s")
            if event.wait(min(0.1, remaining)):
                return

    def _approval_pause_mark(self):
        with self._approval_lock:
            return self._approval_wait_seconds

    def _approval_pause_since(self, mark, now):
        with self._approval_lock:
            paused = self._approval_wait_seconds - mark
            if self._approval_started_at is not None:
                paused += now - self._approval_started_at
        return max(0.0, paused)

    def _wait_for_turn(self, event, deadline, approval_pause_mark, operation, timeout):
        """Wait for a turn without charging an operator's approval review time."""
        while True:
            if self.cancelled():
                raise _ProviderCancelled(f"{operation} interrupted")
            now = time.monotonic()
            remaining = deadline + self._approval_pause_since(approval_pause_mark, now) - now
            if remaining <= 0:
                raise TimeoutError(f"{operation} timed out after {timeout}s")
            if event.wait(min(0.1, remaining)):
                return

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
            started_at = time.monotonic()
            with self._approval_lock:
                self._approval_started_at = started_at
            try:
                allowed = bool(self.on_approval(method, params))
            except Exception:
                allowed = False
            finally:
                finished_at = time.monotonic()
                with self._approval_lock:
                    self._approval_wait_seconds += max(0.0, finished_at - started_at)
                    self._approval_started_at = None
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
            args = {}
            if itype == "commandExecution" and item.get("command"):
                command = item["command"]
                args["command"] = " ".join(command) if isinstance(command, list) else str(command)
            elif itype == "fileChange":
                path = item.get("path") or item.get("filePath")
                if isinstance(path, str) and path:
                    args["path"] = path
            elif itype == "webSearch" and item.get("query"):
                args["query"] = str(item["query"])
            return {
                "kind": "tool_start" if start else "tool_end",
                "id": item.get("id", ""),
                "name": name,
                "native_kind": itype,
                "args": args,
                "result": "Failed" if failed else "Completed",
                "failed": failed,
            }
        return {"kind": itype, "id": item.get("id", "")}

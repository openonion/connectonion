"""Own one native Claude terminal session and its OIP Work Room history."""

from __future__ import annotations

import hashlib
import secrets
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from connectonion import Agent, ClaudeCodePlugin, address
from connectonion.core.provider_events import (
    provider_activity_event,
    provider_message_event,
    provider_session_event,
)
from connectonion.network.host.server import host
from connectonion.network.host.session.storage import Session, SessionStorage, session_owner
from connectonion.network.trust import TrustAgent
from connectonion.useful_tools.claude_code import run_interactive_claude


class ClaudeStation:
    """A terminal owner whose durable OIP session can be claimed by one browser."""

    def __init__(self, workspace: Path, storage: SessionStorage, model: str = ""):
        self.workspace = workspace.resolve(strict=True)
        self.storage = storage
        self.model = model
        self.session_id = str(uuid.uuid4())
        self._unpaired_owner = f"station:{self.session_id}"
        self.invocation_id = f"claude_code:station:{self.session_id}"
        self.parent_id = f"claude_station:{self.session_id}"
        self.claude_session_id = ""
        self.pairing_code = secrets.token_urlsafe(24)
        self._pairing_hash = hashlib.sha256(self.pairing_code.encode()).digest()
        self._condition = threading.Condition()
        self._stop_local = threading.Event()
        self._resume_local = threading.Event()
        self._phase = "local_starting"
        self._revision = 1
        self._activity_ids: dict[str, tuple[str, int]] = {}
        self._activity_sequence = 0
        self.storage.save(Session(
            session_id=self.session_id,
            status="running",
            prompt="Claude Code terminal Work Room",
            session={"messages": [], "trace": [self._session_event()],
                     "requester": {"address": self._unpaired_owner, "level": "admin"}},
            created=time.time(),
        ))

    def _session_event(self) -> dict:
        return provider_session_event(
            invocation_id=self.invocation_id,
            parent_tool_call_id=self.parent_id,
            session_id=self.claude_session_id,
            owner="terminal" if self._phase.startswith("local") else "browser",
            phase=self._phase,
            state_revision=self._revision,
        )

    def _append(self, event: dict, *, status: str | None = None) -> None:
        def update(record: Session | None) -> Session:
            if record is None:
                raise RuntimeError("Claude Station session disappeared")
            session = dict(record.session or {})
            trace = list(session.get("trace") or [])
            trace.append(event)
            session["trace"] = trace
            return record.model_copy(update={
                "session": session,
                "status": status if status is not None else record.status,
            })

        self.storage.atomic_update(self.session_id, update)

    def _transition(self, phase: str, *, status: str | None = None) -> None:
        with self._condition:
            self._phase = phase
            self._revision += 1
            self._append(self._session_event(), status=status)
            self._condition.notify_all()

    def _invocation(self, status: str) -> dict:
        if status == "running":
            summary = "Running in the terminal" if self._phase.startswith("local") else "Claude Code is working"
        else:
            summary = "Ready for a browser message" if self._phase == "remote_controlling" else "Session ready in the terminal"
        return {
            "type": "provider_invocation",
            "provider": "claude_code",
            "providerDisplayName": "Claude Code",
            "invocationId": self.invocation_id,
            "parentToolCallId": self.parent_id,
            "workroomId": self.invocation_id,
            "sessionId": self.claude_session_id,
            "taskTitle": "Claude Code session",
            "status": status,
            "currentSummary": summary,
            "stateRevision": self._revision,
        }

    def _on_fact(self, fact: dict) -> None:
        kind = fact["hook_event_name"]
        if kind == "SessionStart":
            with self._condition:
                self.claude_session_id = fact["session_id"]
                self._transition("local_observing")
                self._append(self._invocation("running"))
        elif kind == "UserPromptSubmit":
            with self._condition:
                self._revision += 1
                self._append(self._invocation("running"))
        elif kind == "Stop":
            with self._condition:
                self._revision += 1
                self._append(self._invocation("completed"))
        elif kind in {"PreToolUse", "PostToolUse", "PostToolUseFailure", "SubagentStart", "SubagentStop"}:
            self._on_activity(fact)

    def _on_activity(self, fact: dict) -> None:
        kind = fact["hook_event_name"]
        native_id = fact.get("tool_use_id") or fact.get("agent_id") or str(uuid.uuid4())
        if native_id not in self._activity_ids:
            self._activity_sequence += 1
            self._activity_ids[native_id] = (f"claude:{uuid.uuid4().hex}", self._activity_sequence)
        activity_id, sequence = self._activity_ids[native_id]
        status = (
            "failed" if kind == "PostToolUseFailure"
            else "completed" if kind in {"PostToolUse", "SubagentStop"}
            else "running"
        )
        activity = provider_activity_event(
            provider="claude_code",
            activity_id=activity_id,
            sequence=sequence,
            native_kind="tool",
            status=status,
            name=fact.get("tool_name") or ("Subagent" if "Subagent" in kind else "Tool"),
        )
        activity.update({
            "invocationId": self.invocation_id,
            "parentToolCallId": self.parent_id,
        })
        self._append(activity)
        if status != "running":
            self._activity_ids.pop(native_id, None)

    def _on_message(self, message: dict) -> None:
        event = provider_message_event(
            provider="claude_code",
            invocation_id=self.invocation_id,
            parent_tool_call_id=self.parent_id,
            message_id=message["message_id"],
            role=message["role"],
            text=message["text"],
            workroom_id=self.invocation_id,
        )
        self._append(event)

    def attach(self, owner: str, pairing_code: str) -> dict:
        if not isinstance(pairing_code, str) or not secrets.compare_digest(
            hashlib.sha256(pairing_code.encode()).digest(), self._pairing_hash
        ):
            return {"accepted": False, "reason": "invalid_pairing_code"}

        def claim(record: Session | None) -> Session:
            if record is None or session_owner(record) not in (self._unpaired_owner, owner):
                raise ValueError("Claude Station belongs to another browser")
            session = dict(record.session or {})
            session["requester"] = {"address": owner, "level": "admin"}
            return record.model_copy(update={"session": session})

        self.storage.atomic_update(self.session_id, claim)
        return {"accepted": True, "sessionId": self.session_id}

    def take_control(self, owner: str, observed_revision: int) -> dict:
        with self._condition:
            record = self.storage.get(self.session_id)
            if session_owner(record) != owner or observed_revision != self._revision:
                return {"accepted": False, "reason": "stale_or_unowned"}
            if self._phase != "local_observing" or not self.claude_session_id:
                return {"accepted": False, "reason": "not_ready"}
            self._transition("handover_to_remote")
            self._stop_local.set()
            completed = self._condition.wait_for(
                lambda: self._phase in {"remote_controlling", "failed"}, timeout=10,
            )
            return {
                "accepted": completed and self._phase == "remote_controlling",
                "stateRevision": self._revision,
                "reason": None if completed else "handover_timeout",
            }

    def release_control(self, owner: str, observed_revision: int) -> dict:
        with self._condition:
            record = self.storage.get(self.session_id)
            if session_owner(record) != owner or observed_revision != self._revision:
                return {"accepted": False, "reason": "stale_or_unowned"}
            if self._phase != "remote_controlling":
                return {"accepted": False, "reason": "provider_busy"}
            deadline = time.monotonic() + 10
            while record.status != "done" and time.monotonic() < deadline:
                time.sleep(0.1)
                record = self.storage.get(self.session_id)
            if record.status != "done":
                return {"accepted": False, "reason": "provider_busy"}
            latest = next((event for event in reversed(record.session.get("trace", []))
                           if event.get("type") == "provider_invocation"
                           and event.get("provider") == "claude_code"
                           and event.get("sessionId")), None)
            if latest:
                self.claude_session_id = latest["sessionId"]
            self._transition("handover_to_local")
            self._resume_local.set()
            return {"accepted": True, "stateRevision": self._revision}

    def can_continue(self, owner: str | None, session_id: str | None) -> bool:
        with self._condition:
            record = self.storage.get(self.session_id)
            return (
                session_id == self.session_id
                and bool(owner)
                and session_owner(record) == owner
                and self._phase == "remote_controlling"
            )

    def run(self) -> int:
        """Run the TUI on the foreground thread; remote turns use Host workers."""
        while True:
            self._stop_local.clear()
            self._resume_local.clear()
            self._transition("local_starting", status="running")
            try:
                code, session_id = run_interactive_claude(
                    cwd=str(self.workspace),
                    session_id=self.claude_session_id,
                    model=self.model,
                    on_private_fact=self._on_fact,
                    on_message=self._on_message,
                    stop_event=self._stop_local,
                )
            except (OSError, ValueError) as exc:
                self._transition("failed", status="done")
                raise RuntimeError("Claude Station terminal failed") from exc
            with self._condition:
                self.claude_session_id = session_id
            if not self._stop_local.is_set():
                self._transition("completed" if code == 0 else "failed", status="done")
                return code
            with self._condition:
                self._revision += 1
                self._append(self._invocation("completed"), status="done")
            self._transition("remote_controlling", status="done")
            self._resume_local.wait()


class _StationOutput:
    """Keep Host diagnostics out of Claude's foreground terminal."""

    def __init__(self, terminal, log):
        self.terminal = terminal
        self.log = log

    def _target(self):
        return self.log if threading.current_thread().name == "co-claude-station-host" else self.terminal

    def write(self, value):
        return self._target().write(value)

    def flush(self):
        return self._target().flush()

    def isatty(self):
        return self._target().isatty()

    def __getattr__(self, name):
        return getattr(self.terminal, name)


def launch_claude_station(workspace: Path, session_id: str, model: str) -> tuple[int, str]:
    """Serve one private OIP identity while Claude owns the foreground terminal."""
    workspace = workspace.resolve(strict=True)
    name = hashlib.sha256(str(workspace).encode()).hexdigest()[:24]
    state_dir = Path.home() / ".co" / "claude-stations" / name
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = address.load(state_dir)
    if identity is None:
        identity = address.generate()
        address.save(identity, state_dir)
    storage = SessionStorage(state_dir / "session_results.jsonl")
    storage.reconcile_interrupted()
    station = ClaudeStation(workspace, storage, model)
    station.claude_session_id = session_id

    def create_agent() -> Agent:
        return Agent(
            "Claude Code Station",
            llm=SimpleNamespace(model="claude-code"),
            tools=[],
            plugins=[ClaudeCodePlugin(workspace=workspace, use_host_permissions=True)],
            co_dir=state_dir,
            quiet=True,
        )

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    trust = TrustAgent("careful", co_dir=state_dir, invite_code=station.pairing_code)
    server = threading.Thread(
        target=host,
        kwargs={
            "create_agent": create_agent,
            "port": port,
            "trust": trust,
            "co_dir": state_dir,
            "provider_station": station,
            "summary": "Claude Code terminal Work Room",
        },
        name="co-claude-station-host",
        daemon=True,
    )
    print(f"Claude Work Room: https://o.openonion.ai/{identity['address']}")
    print(f"Pairing code: {station.pairing_code}")
    original_stdout, original_stderr = sys.stdout, sys.stderr
    with (state_dir / "station-host.log").open("a", encoding="utf-8") as log:
        sys.stdout = _StationOutput(original_stdout, log)
        sys.stderr = _StationOutput(original_stderr, log)
        try:
            server.start()
            code = station.run()
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
    return code, station.claude_session_id

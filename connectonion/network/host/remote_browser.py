"""Owner-bound Remote Browser lifecycle over the existing browser daemon.

This module owns no browser driver. It records OIP session authority and maps
each session to one named tab in the already-shared daemon. Navigation is
deliberately absent until the public-destination policy can cover redirects and
subresources as well as the first URL.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shlex
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from .proxy_channel import ProxyChannelRegistry

SCHEMA_VERSION = "1"
REQUEST_ID = re.compile(r"[\x21-\x7e]{1,128}")
SESSION_ID = re.compile(r"rb_[0-9a-f]{32}")
COMMANDS = frozenset({"start", "status", "sessions", "stop", "diagnose"})


def _success(request_id: str, command: str, *, result=None, state=None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "command": f"remote-browser.{command}",
        "request_id": request_id,
        "summary": {
            "start": "Remote browser session started.",
            "status": "Remote browser session status loaded.",
            "sessions": "Remote browser sessions loaded.",
            "stop": "Remote browser session stopped.",
            "diagnose": "Remote browser diagnosis completed.",
        }[command],
        "result": result or {},
        "state": state or {},
        "tips": [],
        "warnings": [],
        "next_actions": [],
    }


def _failure(
    request_id: str,
    command: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    state=None,
    next_actions=None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "command": f"remote-browser.{command}" if command else "remote-browser",
        "request_id": request_id,
        "code": code,
        "message": message,
        "retryable": retryable,
        "retry_after_seconds": None,
        "state": state or {},
        "tips": [],
        "warnings": [],
        "next_actions": next_actions or [],
    }


class RemoteBrowserService:
    """Persistent authority registry delegating lifecycle to BrowserDaemon."""

    def __init__(
        self,
        state_path: Path,
        daemon_request: Callable | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.state_path = Path(state_path)
        self.clock = clock
        self._lock = threading.RLock()
        self.daemon_target = None
        if daemon_request is None:
            from ...cli.browser_agent.client import request_target_as
            from .private_browser_runtime import PrivateBrowserTarget

            self.daemon_target = PrivateBrowserTarget.from_state_path(self.state_path)

            def daemon_request(line, **identity):
                return request_target_as(self.daemon_target, line, **identity)
        self.daemon_request = daemon_request
        # Laptops that are lending this host their connection right now,
        # keyed by their address. The WS session that carried PROXY_ATTACH
        # registers and, in its finally, detaches; `start` with
        # `proxy: shared` only reads it.
        self.proxy_channels = ProxyChannelRegistry()

    @staticmethod
    def _share_binding(endpoint) -> str:
        identity = json.dumps(
            {
                "host": endpoint.host,
                "port": endpoint.port,
                "username": endpoint.username,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        # The random Proxy credential is a key, not a user password to verify.
        # HMAC gives this private registry a purpose-separated, non-reversible
        # binding without persisting the bearer credential itself.
        return hmac.new(
            endpoint.password.encode("ascii"),
            b"connectonion:remote-browser:proxy-binding:v1\x00" + identity,
            hashlib.sha256,
        ).hexdigest()

    def _load(self) -> dict:
        if not self.state_path.exists():
            return {"version": 1, "sessions": {}}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("remote browser session registry is unreadable") from exc
        if value.get("version") != 1 or not isinstance(value.get("sessions"), dict):
            raise RuntimeError("remote browser session registry has an unknown format")
        return value

    def _save(self, value: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.", dir=self.state_path.parent
        )
        path = Path(temporary)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            path.chmod(0o600)
            path.replace(self.state_path)
        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def _public(session: dict) -> dict:
        return {
            key: session[key]
            for key in (
                "session_id",
                "status",
                "proxy_mode",
                "created_at",
                "updated_at",
            )
        }

    def _owned(self, state: dict, session_id: str, owner: str) -> dict | None:
        session = state["sessions"].get(session_id)
        return session if session and session.get("owner") == owner else None

    def handle(self, request: dict, *, owner: str, transport: str) -> dict:
        request_id = request.get("request_id")
        command = request.get("command")
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            return _failure(
                "",
                str(command or ""),
                "INVALID_ARGUMENT",
                "request_id must be 1-128 visible ASCII characters.",
            )
        if command not in COMMANDS:
            return _failure(
                request_id,
                str(command or ""),
                "INVALID_ARGUMENT",
                "Unknown Remote Browser command.",
            )
        if not owner:
            return _failure(
                request_id,
                command,
                "AUTH_REQUIRED",
                "Remote Browser requires an authenticated caller.",
            )
        if transport != "direct":
            return _failure(
                request_id,
                command,
                "SECURE_CHANNEL_UNAVAILABLE",
                "Relay Remote Browser control is unavailable until the reviewed OIP secure channel is negotiated.",
                state={"fallback_applied": False},
                next_actions=[
                    {
                        "id": "use_direct_endpoint",
                        "command": "co remote-browser <address> status",
                        "requires_user_approval": False,
                    }
                ],
            )
        try:
            if command == "start":
                return self._start(request_id, request.get("args", {}), owner)
            if command == "sessions":
                return self._sessions(request_id, owner)
            session_id = request.get("session_id")
            if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
                return _failure(
                    request_id,
                    command,
                    "INVALID_ARGUMENT",
                    "A canonical rb_ session_id is required.",
                )
            if command == "status":
                return self._status(request_id, session_id, owner)
            if command == "stop":
                return self._stop(request_id, session_id, owner)
            return self._diagnose(request_id, session_id, owner)
        except (OSError, RuntimeError) as exc:
            return _failure(
                request_id,
                command,
                "REMOTE_BROWSER_UNAVAILABLE",
                str(exc),
                retryable=True,
                state={"fallback_applied": False},
            )

    def _start(self, request_id: str, args: dict, owner: str) -> dict:
        if not isinstance(args, dict):
            return _failure(
                request_id, "start", "INVALID_ARGUMENT", "args must be an object."
            )
        proxy_mode = args.get("proxy", "direct")
        if proxy_mode not in {"direct", "shared"}:
            return _failure(
                request_id,
                "start",
                "REMOTE_SESSION_PROXY_LOCKED",
                "Egress is either direct or shared from the caller's own connection.",
                state={"fallback_applied": False},
            )
        # `shared` sends this session's egress out through the caller's machine,
        # so pages see the caller's address rather than this host's. The caller
        # lends it by staying attached (`co proxy share`); the exit is the
        # channel that same identity attached, never one this host guessed.
        share_endpoint = None
        share_binding = None
        if proxy_mode == "shared":
            share_endpoint = self.proxy_channels.endpoint_for(owner)
            if share_endpoint is None:
                return _failure(
                    request_id,
                    "start",
                    "REMOTE_SESSION_PROXY_NOT_ATTACHED",
                    "Shared egress needs your computer attached to this host. "
                    "On your computer run: co proxy share",
                    state={"fallback_applied": False},
                    next_actions=[
                        {
                            "id": "attach_share",
                            "command": "co proxy share",
                            "requires_user_approval": False,
                        }
                    ],
                )
            share_binding = self._share_binding(share_endpoint)
        headless = args.get("headless", False)
        if not isinstance(headless, bool):
            return _failure(
                request_id, "start", "INVALID_ARGUMENT", "headless must be boolean."
            )
        with self._lock:
            state = self._load()
            for session in state["sessions"].values():
                if (
                    session.get("owner") == owner
                    and session.get("start_request_id") == request_id
                ):
                    return _success(
                        request_id,
                        "start",
                        result=self._public(session),
                        state={"session": session["status"], "fallback_applied": False},
                    )
            active = [
                session
                for session in state["sessions"].values()
                if session.get("status") == "active"
            ]
            runtime_already_active = bool(active)
            if any(
                session.get("proxy_mode") != proxy_mode
                or (
                    proxy_mode == "shared"
                    and session.get("proxy_binding") != share_binding
                )
                for session in active
            ):
                return _failure(
                    request_id,
                    "start",
                    "REMOTE_SESSION_PROXY_LOCKED",
                    "The running WTF Browser is already pinned to another proxy.",
                    state={"fallback_applied": False},
                )
            if share_endpoint is not None and self.daemon_target is not None:
                from .private_browser_runtime import write_shared_proxy_file

                write_shared_proxy_file(
                    self.daemon_target.shared_proxy_path, share_endpoint
                )
            session_id = f"rb_{uuid.uuid4().hex}"
            tab = f"remote-{session_id[3:19]}"
            line = shlex.join(
                ["tab", "open", tab, "--who", owner, "--for", "remote-browser"]
            )
            try:
                code, payload = self.daemon_request(
                    line, caller=owner, account=owner, headless=headless
                )
                if code:
                    raise RuntimeError(
                        payload or "browser daemon rejected session start"
                    )
                if payload.strip() != tab:
                    raise RuntimeError(
                        "browser daemon returned an unexpected tab identity"
                    )
            except Exception:
                if (
                    not runtime_already_active
                    and self.daemon_target is not None
                    and self.daemon_target.shared_proxy_path is not None
                ):
                    self.daemon_target.shared_proxy_path.unlink(missing_ok=True)
                raise
            now = int(self.clock())
            session = {
                "session_id": session_id,
                "owner": owner,
                "tab": tab,
                "status": "active",
                "proxy_mode": proxy_mode,
                "proxy_binding": share_binding,
                "headless": headless,
                "start_request_id": request_id,
                "created_at": now,
                "updated_at": now,
            }
            state["sessions"][session_id] = session
            try:
                self._save(state)
            except OSError:
                # Opening the daemon tab precedes the durable commit. If that
                # commit fails, release the unowned tab before reporting failure
                # so a retry cannot accumulate invisible browser sessions.
                try:
                    self.daemon_request(
                        shlex.join(["tab", "close", tab]),
                        caller=owner,
                        account=owner,
                        headless=headless,
                    )
                except Exception:
                    pass
                if not runtime_already_active:
                    try:
                        self.daemon_request(
                            "close",
                            caller=owner,
                            account=owner,
                            headless=headless,
                        )
                    except Exception:
                        pass
                    if (
                        self.daemon_target is not None
                        and self.daemon_target.shared_proxy_path is not None
                    ):
                        self.daemon_target.shared_proxy_path.unlink(missing_ok=True)
                raise
        return _success(
            request_id,
            "start",
            result=self._public(session),
            state={"session": "active", "fallback_applied": False},
        )

    def _sessions(self, request_id: str, owner: str) -> dict:
        with self._lock:
            state = self._load()
            sessions = [
                self._public(session)
                for session in state["sessions"].values()
                if session.get("owner") == owner
            ]
        sessions.sort(key=lambda item: (item["created_at"], item["session_id"]))
        return _success(request_id, "sessions", result={"sessions": sessions})

    def _status(self, request_id: str, session_id: str, owner: str) -> dict:
        with self._lock:
            session = self._owned(self._load(), session_id, owner)
            if session is None:
                return _failure(
                    request_id,
                    "status",
                    "REMOTE_SESSION_NOT_FOUND",
                    "Remote browser session was not found.",
                )
            public = self._public(session)
        return _success(
            request_id,
            "status",
            result=public,
            state={"session": session["status"], "fallback_applied": False},
        )

    def _stop(self, request_id: str, session_id: str, owner: str) -> dict:
        with self._lock:
            state = self._load()
            session = self._owned(state, session_id, owner)
            if session is None:
                return _failure(
                    request_id,
                    "stop",
                    "REMOTE_SESSION_NOT_FOUND",
                    "Remote browser session was not found.",
                )
            if session["status"] != "stopped":
                code, payload = self.daemon_request(
                    shlex.join(["tab", "close", session["tab"]]),
                    caller=owner,
                    account=owner,
                    headless=session["headless"],
                )
                if code not in (0, 3):
                    raise RuntimeError(
                        payload or "browser daemon rejected session stop"
                    )
                session["status"] = "stopped"
                session["updated_at"] = int(self.clock())
            if not any(
                candidate.get("status") == "active"
                for candidate in state["sessions"].values()
            ):
                close_code, close_payload = self.daemon_request(
                    "close",
                    caller=owner,
                    account=owner,
                    headless=session["headless"],
                )
                if close_code not in (0, 3):
                    raise RuntimeError(
                        close_payload or "browser daemon rejected runtime stop"
                    )
                if self.daemon_target is not None:
                    self.daemon_target.shared_proxy_path.unlink(missing_ok=True)
            self._save(state)
            public = self._public(session)
        return _success(
            request_id,
            "stop",
            result=public,
            state={"session": "stopped", "fallback_applied": False},
        )

    def _diagnose(self, request_id: str, session_id: str, owner: str) -> dict:
        status = self._status(request_id, session_id, owner)
        if not status["ok"]:
            return status
        status["command"] = "remote-browser.diagnose"
        status["summary"] = "Remote browser diagnosis completed."
        status["result"] = {
            **status["result"],
            "checks": {
                "authenticated_owner": "ok",
                "session_registry": "ok",
                "transport": "direct",
                "proxy_mode": "direct",
                "egress_gateway": "ready",
                "dns_boundary": (
                    "laptop" if status["result"]["proxy_mode"] == "shared" else "host"
                ),
                "navigation_policy": "not_enabled",
            },
        }
        status["result"]["checks"]["proxy_mode"] = status["result"]["proxy_mode"]
        status["warnings"] = [
            "The WTF Browser egress boundary is ready; remote page commands remain disabled."
        ]
        return status

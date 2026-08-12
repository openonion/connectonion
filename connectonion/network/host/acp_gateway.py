"""Authenticated ACP v1 WebSocket gateway for hosted agents.

ACP defines the agent/client conversation.  ConnectOnion still owns admission:
caller signatures, recipient binding, replay protection, trust policy, and
browser-origin checks all run before an ACP Agent is constructed.

The first remote profile is deliberately WebSocket-only.  Uvicorn does not
serve the HTTP/2 required by ACP Streamable HTTP, while ACP's remote transport
allows a server to offer WebSocket alone.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import ipaddress
import json
import logging
import math
import secrets
import time
import uuid
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from acp import PROTOCOL_VERSION
from acp.agent.connection import AgentSideConnection
from acp.schema import InitializeRequest
from pydantic import ValidationError

from .auth import _authenticate_signed, request_from_http_headers
from .replay import ReplayProtectionError

logger = logging.getLogger(__name__)

ACP_PATH = "/acp"
ACP_AUTHORIZE_PATH = "/acp/authorize"
ACP_SUBPROTOCOL = "acp"
TICKET_SUBPROTOCOL_PREFIX = "connectonion.ticket."
DEFAULT_ACP_ORIGINS = ("https://chat.openonion.ai",)
DEFAULT_TICKET_TTL_SECONDS = 60
DEFAULT_INITIALIZE_TIMEOUT_SECONDS = 10
DEFAULT_MAX_CONNECTIONS = 16
DEFAULT_MAX_CONNECTIONS_PER_PRINCIPAL = 2
DEFAULT_ADMISSIONS_PER_MINUTE = 30
DEFAULT_RATE_LIMIT_PRINCIPALS = 1024
ACP_QUEUE_MESSAGES = 8
MAX_AUTHORIZATION_BODY_BYTES = 16 * 1024
MAX_ACP_MESSAGE_BYTES = 1024 * 1024
MAX_INVITE_CODE_LENGTH = 512

_CORS_REQUEST_HEADERS = "content-type,x-co-from,x-co-signature,x-co-timestamp,x-co-to,x-co-request-id"
_CORS_REQUEST_HEADER_NAMES = frozenset(_CORS_REQUEST_HEADERS.split(","))
_UNIQUE_SECURITY_HEADERS = _CORS_REQUEST_HEADER_NAMES | frozenset(
    {
        "origin",
        "host",
        "content-type",
        "access-control-request-method",
        "access-control-request-headers",
        "access-control-request-private-network",
    }
)
_IGNORED_WEBSOCKET_FRAME = object()


def acp_transport_descriptor() -> dict[str, Any]:
    """Return the public, non-authoritative discovery shape for this gateway."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "type": "websocket",
        "path": ACP_PATH,
        "authorization": {
            "type": "connectonion-ticket",
            "path": ACP_AUTHORIZE_PATH,
        },
    }


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _payment_is_valid(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


@dataclass(frozen=True)
class ACPPrincipal:
    """Verified identity attached to one admitted ACP connection."""

    address: str
    level: str
    recipient: str
    origin: str | None
    auth_method: str
    authenticated_at: float


@dataclass(frozen=True)
class _TicketRecord:
    principal: ACPPrincipal
    expires_at: float


class ACPTicketRegistry:
    """Short-lived, single-use browser tickets stored only as SHA-256 digests."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_TICKET_TTL_SECONDS,
        max_pending: int = 256,
        max_pending_per_principal: int = 8,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_pending = max_pending
        self.max_pending_per_principal = max_pending_per_principal
        self._clock = clock
        self._records: dict[bytes, _TicketRecord] = {}

    @staticmethod
    def _digest(ticket: str) -> bytes:
        return hashlib.sha256(ticket.encode("utf-8")).digest()

    def _drop_expired(self, now: float) -> None:
        for digest in [digest for digest, record in self._records.items() if record.expires_at <= now]:
            del self._records[digest]

    def issue(self, principal: ACPPrincipal) -> str:
        now = self._clock()
        self._drop_expired(now)
        if len(self._records) >= self.max_pending:
            raise RuntimeError("too many pending ACP authorization tickets")
        owner = (
            principal.recipient,
            principal.address,
            principal.origin,
            principal.auth_method,
        )
        if (
            sum(
                (
                    record.principal.recipient,
                    record.principal.address,
                    record.principal.origin,
                    record.principal.auth_method,
                )
                == owner
                for record in self._records.values()
            )
            >= self.max_pending_per_principal
        ):
            raise RuntimeError("too many pending ACP authorization tickets")
        ticket = secrets.token_urlsafe(32)
        self._records[self._digest(ticket)] = _TicketRecord(
            principal=principal,
            expires_at=now + self.ttl_seconds,
        )
        return ticket

    def consume(self, ticket: str, *, origin: str | None) -> ACPPrincipal | None:
        """Consume once.  A mismatched-origin attempt also burns the ticket."""

        now = self._clock()
        self._drop_expired(now)
        record = self._records.pop(self._digest(ticket), None)
        if record is None or record.expires_at <= now:
            return None
        if record.principal.origin != origin:
            return None
        return record.principal


class ACPAdmissionRateLimiter:
    """Bound verified admission attempts without retaining unbounded identities."""

    def __init__(
        self,
        *,
        limit: int = DEFAULT_ADMISSIONS_PER_MINUTE,
        window_seconds: float = 60.0,
        max_principals: int = DEFAULT_RATE_LIMIT_PRINCIPALS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_principals = max_principals
        self._clock = clock
        self._attempts: dict[
            tuple[str, str, str | None, str],
            deque[float],
        ] = {}

    @staticmethod
    def _key(principal: ACPPrincipal) -> tuple[str, str, str | None, str]:
        return (
            principal.recipient,
            principal.address,
            principal.origin,
            principal.auth_method,
        )

    def allow(self, principal: ACPPrincipal) -> bool:
        now = self._clock()
        cutoff = now - self.window_seconds
        for key in list(self._attempts):
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                del self._attempts[key]

        key = self._key(principal)
        attempts = self._attempts.get(key)
        if attempts is None:
            if len(self._attempts) >= self.max_principals:
                return False
            attempts = deque()
            self._attempts[key] = attempts
        if len(attempts) >= self.limit:
            return False
        attempts.append(now)
        return True


class _ACPTransport:
    """Message transport joining AgentSideConnection to one ASGI WebSocket."""

    def __init__(self) -> None:
        self._to_agent: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=ACP_QUEUE_MESSAGES)
        self._to_client: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=ACP_QUEUE_MESSAGES)
        self._closed = False

    async def send(self, message: dict[str, Any]) -> None:
        if self._closed:
            raise ConnectionError("ACP WebSocket transport is closed")
        await self._to_client.put(dict(message))

    async def receive(self) -> dict[str, Any] | None:
        return await self._to_agent.get()

    async def feed(self, message: dict[str, Any]) -> None:
        if self._closed:
            raise ConnectionError("ACP WebSocket transport is closed")
        await self._to_agent.put(message)

    async def next_outgoing(self) -> dict[str, Any] | None:
        return await self._to_client.get()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._put_eof(self._to_agent)
        self._put_eof(self._to_client)

    @staticmethod
    def _put_eof(queue: asyncio.Queue) -> None:
        while True:
            try:
                queue.put_nowait(None)
                return
            except asyncio.QueueFull:
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()


ACPAgentFactory = Callable[[ACPPrincipal], Any]
ReplayCheck = Callable[[dict[str, Any]], bool]


class AuthenticatedACPApp:
    """ASGI sub-application for signed ACP admission and WebSocket transport."""

    def __init__(
        self,
        agent_factory: ACPAgentFactory,
        *,
        trust_agent: Any,
        recipient_address: str,
        replay_check: ReplayCheck,
        allowed_origins: Iterable[str] = DEFAULT_ACP_ORIGINS,
        blacklist: Iterable[str] | None = None,
        whitelist: Iterable[str] | None = None,
        tickets: ACPTicketRegistry | None = None,
        rate_limiter: ACPAdmissionRateLimiter | None = None,
        initialize_timeout_seconds: float = DEFAULT_INITIALIZE_TIMEOUT_SECONDS,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        max_connections_per_principal: int = DEFAULT_MAX_CONNECTIONS_PER_PRINCIPAL,
    ) -> None:
        self._agent_factory = agent_factory
        self._trust_agent = trust_agent
        self._recipient_address = recipient_address
        self._replay_check = replay_check
        self._allowed_origins = frozenset(allowed_origins)
        self._blacklist = set(blacklist or ())
        self._whitelist = set(whitelist or ())
        self._tickets = tickets or ACPTicketRegistry()
        self._rate_limiter = rate_limiter or ACPAdmissionRateLimiter()
        self._initialize_timeout_seconds = initialize_timeout_seconds
        self._max_connections = max_connections
        self._max_connections_per_principal = max_connections_per_principal
        self._connection_tasks: set[asyncio.Task] = set()
        self._active_principals: dict[tuple[str, str, str | None, str], int] = {}

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
            return
        if scope["type"] != "http":
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if path == ACP_AUTHORIZE_PATH:
            if method == "OPTIONS":
                await self._handle_options(scope, send)
            elif method == "POST":
                await self._handle_authorize(scope, receive, send)
            else:
                await self._send_json(send, 405, {"error": "Method not allowed"})
            return

        # This release advertises only the transport Uvicorn can serve without
        # pretending HTTP/1.1 is ACP's HTTP/2 Streamable HTTP profile.
        await self._send_json(
            send,
            426,
            {
                "error": "ACP Streamable HTTP is not enabled",
                "transport": "websocket",
                "path": ACP_PATH,
            },
            extra_headers=[(b"upgrade", b"websocket")],
        )

    async def close(self) -> None:
        """Cancel active ACP sockets during the host lifespan shutdown."""

        current = asyncio.current_task()
        tasks = [task for task in self._connection_tasks if task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_options(self, scope: dict, send: Callable) -> None:
        if self._has_ambiguous_security_headers(scope):
            await self._send_json(send, 400, {"error": "Ambiguous security headers"})
            return
        origin = self._origin(scope)
        if not self._origin_allowed(origin):
            await self._send_json(send, 403, {"error": "Origin not allowed"})
            return
        headers = self._headers(scope)
        requested_method = headers.get("access-control-request-method", "").upper()
        if requested_method != "POST":
            await self._send_json(
                send,
                400,
                {"error": "CORS preflight must request POST"},
                origin=origin,
            )
            return
        requested_headers = {
            item.strip().lower()
            for item in headers.get("access-control-request-headers", "").split(",")
            if item.strip()
        }
        if not requested_headers.issubset(_CORS_REQUEST_HEADER_NAMES):
            await self._send_json(
                send,
                400,
                {"error": "CORS preflight requested unsupported headers"},
                origin=origin,
            )
            return
        response_headers = self._cors_headers(origin)
        if headers.get("access-control-request-private-network", "").lower() == "true":
            response_headers.append((b"access-control-allow-private-network", b"true"))
        await send(
            {
                "type": "http.response.start",
                "status": 204,
                "headers": response_headers,
            }
        )
        await send({"type": "http.response.body", "body": b""})

    async def _handle_authorize(
        self,
        scope: dict,
        receive: Callable,
        send: Callable,
    ) -> None:
        if self._has_ambiguous_security_headers(scope):
            await self._send_json(send, 400, {"error": "Ambiguous security headers"})
            return
        origin = self._origin(scope)
        if not self._origin_allowed(origin):
            await self._send_json(send, 403, {"error": "Origin not allowed"})
            return
        if not self._transport_is_secure(scope):
            await self._send_json(
                send,
                403,
                {"error": "Secure transport is required for non-loopback ACP"},
                origin=origin,
            )
            return
        content_type = self._headers(scope).get("content-type", "")
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type != "application/json":
            await self._send_json(
                send,
                415,
                {"error": "Content-Type must be application/json"},
                origin=origin,
            )
            return

        body, too_large = await self._read_body(receive)
        if too_large:
            await self._send_json(
                send,
                413,
                {"error": "Authorization request is too large"},
                origin=origin,
            )
            return
        try:
            options = (
                json.loads(
                    body,
                    parse_constant=_reject_json_constant,
                )
                if body
                else {}
            )
        except (ValueError, RecursionError):
            await self._send_json(send, 400, {"error": "Invalid JSON"}, origin=origin)
            return
        if not isinstance(options, dict):
            await self._send_json(send, 400, {"error": "JSON object required"}, origin=origin)
            return
        invite_code = options.get("invite_code")
        payment = options.get("payment", 0)
        if invite_code is not None and (not isinstance(invite_code, str) or len(invite_code) > MAX_INVITE_CODE_LENGTH):
            await self._send_json(send, 400, {"error": "Invalid invite_code"}, origin=origin)
            return
        if not _payment_is_valid(payment):
            await self._send_json(send, 400, {"error": "Invalid payment"}, origin=origin)
            return

        principal, error, status = self._admit_signed(
            scope,
            method="POST",
            path=ACP_AUTHORIZE_PATH,
            body=body,
            origin=origin,
            request_data={
                "prompt": "Open an ACP WebSocket connection",
                "invite_code": invite_code,
                "payment": payment,
            },
        )
        if error:
            await self._send_json(send, status, {"error": error}, origin=origin)
            return

        try:
            ticket = self._tickets.issue(principal)
        except RuntimeError:
            await self._send_json(
                send,
                503,
                {"error": "ACP authorization is temporarily busy"},
                origin=origin,
            )
            return
        await self._send_json(
            send,
            201,
            {
                "ticket": ticket,
                "expires_in": self._tickets.ttl_seconds,
                "websocket_path": ACP_PATH,
                "protocols": [
                    ACP_SUBPROTOCOL,
                    f"{TICKET_SUBPROTOCOL_PREFIX}{ticket}",
                ],
            },
            origin=origin,
            extra_headers=[(b"cache-control", b"no-store")],
        )

    async def _handle_websocket(
        self,
        scope: dict,
        receive: Callable,
        send: Callable,
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._connection_tasks.add(task)
        agent = None
        connection = None
        transport = None
        pump_tasks: set[asyncio.Task] = set()
        principal_key = None
        principal_counted = False
        try:
            event = await receive()
            if event.get("type") != "websocket.connect":
                return
            if scope.get("path") != ACP_PATH:
                await send(
                    {
                        "type": "websocket.close",
                        "code": 4404,
                        "reason": "ACP WebSocket path not found",
                    }
                )
                return
            if self._has_ambiguous_security_headers(scope):
                await send(
                    {
                        "type": "websocket.close",
                        "code": 4400,
                        "reason": "Ambiguous ACP security headers",
                    }
                )
                return
            if len(self._connection_tasks) > self._max_connections:
                await send(
                    {
                        "type": "websocket.close",
                        "code": 4429,
                        "reason": "ACP connection limit reached",
                    }
                )
                return
            if not self._transport_is_secure(scope):
                await send(
                    {
                        "type": "websocket.close",
                        "code": 4403,
                        "reason": "Secure transport is required",
                    }
                )
                return
            principal, error, status = self._admit_websocket(scope)
            if error:
                close_code = 4403 if status == 403 else 4429 if status == 429 else 4401
                await send(
                    {
                        "type": "websocket.close",
                        "code": close_code,
                        "reason": "ACP admission refused",
                    }
                )
                return
            principal_key = self._principal_key(principal)
            active_for_principal = self._active_principals.get(principal_key, 0)
            if active_for_principal >= self._max_connections_per_principal:
                await send(
                    {
                        "type": "websocket.close",
                        "code": 4429,
                        "reason": "ACP principal connection limit reached",
                    }
                )
                return
            self._active_principals[principal_key] = active_for_principal + 1
            principal_counted = True

            connection_id = str(uuid.uuid4())
            accept: dict[str, Any] = {
                "type": "websocket.accept",
                "headers": [
                    (b"acp-connection-id", connection_id.encode("ascii")),
                ],
            }
            if ACP_SUBPROTOCOL in scope.get("subprotocols", ()):
                accept["subprotocol"] = ACP_SUBPROTOCOL
            await send(accept)

            deadline = asyncio.get_running_loop().time() + self._initialize_timeout_seconds
            while True:
                try:
                    first = await asyncio.wait_for(
                        receive(),
                        timeout=max(0, deadline - asyncio.get_running_loop().time()),
                    )
                except asyncio.TimeoutError:
                    await send(
                        {
                            "type": "websocket.close",
                            "code": 4408,
                            "reason": "ACP initialize timed out",
                        }
                    )
                    return
                payload = await self._decode_websocket_message(first, send)
                if payload is _IGNORED_WEBSOCKET_FRAME:
                    continue
                if payload is None:
                    return
                break
            if not self._is_initialize_request(payload):
                await send(
                    {
                        "type": "websocket.close",
                        "code": 4400,
                        "reason": "First ACP message must be initialize",
                    }
                )
                return

            # Authentication and the mandatory initialize frame have both
            # succeeded before any coding Agent or session state exists.
            agent = self._agent_factory(principal)
            with suppress(AttributeError):
                agent.connection_principal = principal
            transport = _ACPTransport()
            connection = AgentSideConnection(
                agent,
                transport,
                listening=True,
                use_unstable_protocol=True,
            )
            await transport.feed(payload)
            pump_tasks = {
                asyncio.create_task(
                    self._pump_inbound(transport, receive, send),
                    name="connectonion.acp.websocket.inbound",
                ),
                asyncio.create_task(
                    self._pump_outbound(transport, send),
                    name="connectonion.acp.websocket.outbound",
                ),
            }
            done, pending = await asyncio.wait(
                pump_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for pending_task in pending:
                pending_task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for completed_task in done:
                completed_task.result()
        finally:
            if agent is not None:
                cancel_all = getattr(agent, "cancel_all", None)
                if callable(cancel_all):
                    try:
                        cancel_all()
                    except Exception:
                        logger.exception("ACP Agent cancellation cleanup failed")
            if transport is not None:
                await transport.close()
            if connection is not None:
                try:
                    await connection.close()
                except Exception:
                    logger.exception("ACP connection cleanup failed")
            for pump_task in pump_tasks:
                pump_task.cancel()
            if pump_tasks:
                await asyncio.gather(*pump_tasks, return_exceptions=True)
            if agent is not None:
                close_all = getattr(agent, "close_all", None)
                if callable(close_all):
                    try:
                        result = close_all()
                        if inspect.isawaitable(result):
                            await result
                    except Exception:
                        logger.exception("ACP Agent session cleanup failed")
            if task is not None:
                self._connection_tasks.discard(task)
            if principal_counted:
                remaining = self._active_principals.get(principal_key, 1) - 1
                if remaining > 0:
                    self._active_principals[principal_key] = remaining
                else:
                    self._active_principals.pop(principal_key, None)

    def _admit_websocket(
        self,
        scope: dict,
    ) -> tuple[ACPPrincipal | None, str | None, int]:
        origin = self._origin(scope)
        if origin is not None and not self._origin_allowed(origin):
            return None, "Origin not allowed", 403

        tickets = self._tickets_from_subprotocols(scope.get("subprotocols", ()))
        if len(tickets) > 1:
            return None, "Ambiguous ACP ticket protocols", 401
        if tickets:
            if ACP_SUBPROTOCOL not in scope.get("subprotocols", ()):
                return None, "ACP subprotocol is required with a browser ticket", 401
            principal = self._tickets.consume(tickets[0], origin=origin)
            if principal is None:
                return None, "Invalid or expired ACP ticket", 401
            return replace(principal, auth_method="browser_ticket"), None, 200

        return self._admit_signed(
            scope,
            method="GET",
            path=ACP_PATH,
            body=b"",
            origin=origin,
            request_data={"prompt": "Open an ACP WebSocket connection"},
        )

    def _admit_signed(
        self,
        scope: dict,
        *,
        method: str,
        path: str,
        body: bytes,
        origin: str | None,
        request_data: dict[str, Any],
    ) -> tuple[ACPPrincipal | None, str | None, int]:
        data = request_from_http_headers(
            self._headers(scope),
            method,
            path,
            query=scope.get("query_string", b""),
            body=body,
        )
        _, caller, error = _authenticate_signed(
            data,
            blacklist=self._blacklist,
            recipient_address=self._recipient_address,
        )
        if error:
            return None, error, self._status_for_auth_error(error)
        try:
            if self._replay_check(data):
                return None, "unauthorized: signed request already used", 401
        except ReplayProtectionError:
            return None, "misconfigured: replay protection unavailable", 503

        if caller not in self._whitelist:
            try:
                decision = self._trust_agent.should_allow(caller, request_data)
            except (OSError, UnicodeDecodeError) as exc:
                return None, f"misconfigured: {exc}", 503
            if not decision.allow:
                return None, f"forbidden: {decision.reason}", 403

        try:
            level = "admin" if self._trust_agent.is_admin(caller) else self._trust_agent.get_level(caller)
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"misconfigured: {exc}", 503
        principal = ACPPrincipal(
            address=caller,
            level=level,
            recipient=self._recipient_address,
            origin=origin,
            auth_method="signed_headers",
            authenticated_at=time.time(),
        )
        if not self._rate_limiter.allow(principal):
            return None, "too many ACP admission attempts", 429
        return principal, None, 200

    async def _pump_inbound(
        self,
        transport: _ACPTransport,
        receive: Callable,
        send: Callable,
    ) -> None:
        while True:
            event = await receive()
            payload = await self._decode_websocket_message(event, send)
            if payload is _IGNORED_WEBSOCKET_FRAME:
                continue
            if payload is None:
                return
            await transport.feed(payload)

    @staticmethod
    async def _pump_outbound(
        transport: _ACPTransport,
        send: Callable,
    ) -> None:
        while True:
            message = await transport.next_outgoing()
            if message is None:
                return
            try:
                text = json.dumps(
                    message,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            except (TypeError, ValueError, RecursionError):
                logger.exception("ACP response could not be serialized")
                await send(
                    {
                        "type": "websocket.close",
                        "code": 1011,
                        "reason": "ACP response could not be serialized",
                    }
                )
                return
            if len(text.encode("utf-8")) > MAX_ACP_MESSAGE_BYTES:
                await send(
                    {
                        "type": "websocket.close",
                        "code": 1009,
                        "reason": "ACP response is too large",
                    }
                )
                return
            await send(
                {
                    "type": "websocket.send",
                    "text": text,
                }
            )

    async def _decode_websocket_message(
        self,
        event: dict,
        send: Callable,
    ) -> dict[str, Any] | object | None:
        if event.get("type") == "websocket.disconnect":
            return None
        if event.get("type") != "websocket.receive":
            return None
        text = event.get("text")
        if text is None:
            binary = event.get("bytes")
            if binary is not None and len(binary) > MAX_ACP_MESSAGE_BYTES:
                await send(
                    {
                        "type": "websocket.close",
                        "code": 1009,
                        "reason": "ACP message is too large",
                    }
                )
                return None
            return _IGNORED_WEBSOCKET_FRAME
        if len(text.encode("utf-8")) > MAX_ACP_MESSAGE_BYTES:
            await send(
                {
                    "type": "websocket.close",
                    "code": 1009,
                    "reason": "ACP message is too large",
                }
            )
            return None
        try:
            payload = json.loads(text, parse_constant=_reject_json_constant)
        except (ValueError, RecursionError):
            payload = None
        if not isinstance(payload, dict):
            await send(
                {
                    "type": "websocket.close",
                    "code": 1007,
                    "reason": "Invalid ACP JSON-RPC message",
                }
            )
            return None
        return payload

    async def _read_body(self, receive: Callable) -> tuple[bytes, bool]:
        chunks: list[bytes] = []
        size = 0
        while True:
            event = await receive()
            if event.get("type") == "http.disconnect":
                break
            if event.get("type") != "http.request":
                continue
            chunk = event.get("body", b"")
            size += len(chunk)
            if size > MAX_AUTHORIZATION_BODY_BYTES:
                return b"", True
            chunks.append(chunk)
            if not event.get("more_body", False):
                break
        return b"".join(chunks), False

    @staticmethod
    def _headers(scope: dict) -> dict[str, str]:
        return {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", ())}

    @staticmethod
    def _has_ambiguous_security_headers(scope: dict) -> bool:
        seen: set[str] = set()
        for raw_name, _ in scope.get("headers", ()):
            name = raw_name.decode("latin-1").lower()
            if name not in _UNIQUE_SECURITY_HEADERS:
                continue
            if name in seen:
                return True
            seen.add(name)
        return False

    def _origin(self, scope: dict) -> str | None:
        return self._headers(scope).get("origin")

    def _origin_allowed(self, origin: str | None) -> bool:
        return origin is not None and origin in self._allowed_origins

    @staticmethod
    def _principal_key(
        principal: ACPPrincipal,
    ) -> tuple[str, str, str | None, str]:
        return (
            principal.recipient,
            principal.address,
            principal.origin,
            principal.auth_method,
        )

    @staticmethod
    def _is_initialize_request(payload: dict[str, Any]) -> bool:
        request_id = payload.get("id")
        envelope_valid = (
            payload.get("jsonrpc") == "2.0"
            and payload.get("method") == "initialize"
            and isinstance(payload.get("params"), dict)
            and (isinstance(request_id, str) or (isinstance(request_id, int) and not isinstance(request_id, bool)))
        )
        if not envelope_valid:
            return False
        protocol_version = payload["params"].get("protocolVersion")
        if (
            isinstance(protocol_version, bool)
            or not isinstance(protocol_version, int)
            or not 0 <= protocol_version <= 65535
        ):
            return False
        try:
            InitializeRequest.model_validate(payload["params"])
        except ValidationError:
            return False
        return True

    @staticmethod
    def _transport_is_secure(scope: dict) -> bool:
        if scope.get("scheme") in {"https", "wss"}:
            return True
        client = scope.get("client")
        if not client:
            return False
        host = str(client[0]).split("%", 1)[0]
        try:
            peer_is_loopback = host.lower() == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
        if not peer_is_loopback:
            return False

        # A local reverse proxy is also a loopback peer. Plaintext is local-only
        # only when the request authority is local too; a public authority must
        # arrive with a trusted HTTPS/WSS scheme from the proxy.
        authority = AuthenticatedACPApp._headers(scope).get("host", "")
        try:
            hostname = urlsplit(f"//{authority}").hostname or ""
        except ValueError:
            return False
        if hostname.lower() == "localhost" or hostname.lower().endswith(".localhost"):
            return True
        try:
            return ipaddress.ip_address(hostname.split("%", 1)[0]).is_loopback
        except ValueError:
            return False

    @staticmethod
    def _tickets_from_subprotocols(protocols: Iterable[str]) -> list[str]:
        return [
            ticket
            for protocol in protocols
            if protocol.startswith(TICKET_SUBPROTOCOL_PREFIX)
            for ticket in [protocol[len(TICKET_SUBPROTOCOL_PREFIX) :]]
            if ticket
        ]

    @staticmethod
    def _status_for_auth_error(error: str) -> int:
        if error.startswith("forbidden:"):
            return 403
        if error.startswith("misconfigured:"):
            return 503
        return 401

    def _cors_headers(self, origin: str) -> list[tuple[bytes, bytes]]:
        return [
            (b"access-control-allow-origin", origin.encode("latin-1")),
            (b"access-control-allow-methods", b"POST, OPTIONS"),
            (b"access-control-allow-headers", _CORS_REQUEST_HEADERS.encode()),
            (b"access-control-max-age", b"600"),
            (
                b"vary",
                b"Origin, Access-Control-Request-Method, "
                b"Access-Control-Request-Headers, "
                b"Access-Control-Request-Private-Network",
            ),
        ]

    async def _send_json(
        self,
        send: Callable,
        status: int,
        body: dict[str, Any],
        *,
        origin: str | None = None,
        extra_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        headers = [(b"content-type", b"application/json")]
        if origin is not None and self._origin_allowed(origin):
            headers.extend(self._cors_headers(origin))
        if extra_headers:
            headers.extend(extra_headers)
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(body, separators=(",", ":")).encode(),
            }
        )


def create_authenticated_acp_app(
    agent_factory: ACPAgentFactory,
    **kwargs: Any,
) -> AuthenticatedACPApp:
    return AuthenticatedACPApp(agent_factory, **kwargs)


__all__ = [
    "ACP_AUTHORIZE_PATH",
    "ACP_PATH",
    "ACP_SUBPROTOCOL",
    "ACPPrincipal",
    "ACPAdmissionRateLimiter",
    "ACPTicketRegistry",
    "AuthenticatedACPApp",
    "DEFAULT_ACP_ORIGINS",
    "DEFAULT_INITIALIZE_TIMEOUT_SECONDS",
    "TICKET_SUBPROTOCOL_PREFIX",
    "acp_transport_descriptor",
    "create_authenticated_acp_app",
]

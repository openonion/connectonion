"""Bounded loopback egress gateway for future Remote Browser navigation.

The gateway owns hostname resolution and numeric socket selection.  A private
launch policy can request this proxy, but Remote Browser page commands remain
unavailable until the credential-enabled paid artifact and native preflight
both pass their installed-artifact acceptance suite.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hmac
import ipaddress
import math
import re
import secrets
import socket
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit

from .destination_policy import (
    ADDRESS_DENIED,
    DNS_FAILED,
    HOST_DENIED,
    INVALID,
    PORT_DENIED,
    SCHEME_DENIED,
    DestinationAuthority,
    DestinationPolicyError,
    decide_destination,
    normalize_web_destination,
)

HEADER_TIMEOUT = "EGRESS_HEADER_TIMEOUT"
HEADER_TOO_LARGE = "EGRESS_HEADER_TOO_LARGE"
AUTH_REQUIRED = "EGRESS_AUTH_REQUIRED"
OVERLOADED = "EGRESS_OVERLOADED"
CONNECT_FAILED = "EGRESS_CONNECT_FAILED"
TRANSFER_LIMIT = "EGRESS_TRANSFER_LIMIT"
GATEWAY_STOPPING = "EGRESS_GATEWAY_STOPPING"
RESOLVE_UNAVAILABLE = "EGRESS_RESOLVE_UNAVAILABLE"

_HEADER_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_METHOD = re.compile(rb"[A-Z][A-Z0-9!#$%&'*+.^_`|~-]{0,31}")
_ERROR_STATUS = {
    INVALID: (400, "Bad Request"),
    SCHEME_DENIED: (403, "Forbidden"),
    PORT_DENIED: (403, "Forbidden"),
    ADDRESS_DENIED: (403, "Forbidden"),
    HOST_DENIED: (403, "Forbidden"),
    DNS_FAILED: (502, "Bad Gateway"),
    HEADER_TIMEOUT: (408, "Request Timeout"),
    HEADER_TOO_LARGE: (431, "Request Header Fields Too Large"),
    AUTH_REQUIRED: (407, "Proxy Authentication Required"),
    OVERLOADED: (429, "Too Many Requests"),
    CONNECT_FAILED: (502, "Bad Gateway"),
    TRANSFER_LIMIT: (413, "Content Too Large"),
    GATEWAY_STOPPING: (503, "Service Unavailable"),
    RESOLVE_UNAVAILABLE: (403, "Forbidden"),
}


@dataclass
class _Admission:
    """Whether this connection has converted a pending slot into a served one."""

    promoted: bool = False


class GatewayRefusal(Exception):
    """Stable internal refusal containing no caller-controlled value."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class GatewayLimits:
    """Hard per-instance and per-connection limits."""

    header_bytes: int = 16 * 1024
    request_line_bytes: int = 4 * 1024
    header_count: int = 100
    header_timeout: float = 5.0
    resolve_timeout: float = 5.0
    connect_timeout: float = 10.0
    idle_timeout: float = 60.0
    bytes_per_direction: int = 128 * 1024 * 1024
    max_connections: int = 32
    max_dns_answers: int = 32
    # Sockets waiting to prove they hold the credential are counted separately.
    # Sharing one budget lets any local process that connects and says nothing
    # hold slots for the whole header timeout, and the browser's only route to
    # the internet is this gateway.
    max_pending_connections: int = 128

    def __post_init__(self) -> None:
        integer_values = (
            self.header_bytes,
            self.request_line_bytes,
            self.header_count,
            self.bytes_per_direction,
            self.max_connections,
            self.max_dns_answers,
            self.max_pending_connections,
        )
        durations = (
            self.header_timeout,
            self.resolve_timeout,
            self.connect_timeout,
            self.idle_timeout,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in integer_values
        ) or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in durations
        ):
            raise ValueError("gateway limits must be positive")
        if self.request_line_bytes > self.header_bytes:
            raise ValueError("request line limit exceeds header limit")
        if self.max_pending_connections < self.max_connections:
            raise ValueError("pending budget is smaller than the connection limit")


@dataclass(frozen=True)
class ProxyEndpoint:
    host: str
    port: int
    username: str
    # Kept out of the repr so a traceback, a debug line, or a structured dump of
    # this object cannot publish the credential. The rule that nothing logs it
    # is easier to keep when there is nothing to log.
    password: str = field(repr=False)


@dataclass(frozen=True)
class NumericEndpoint:
    family: int
    address: str
    port: int

    def __post_init__(self) -> None:
        try:
            address = ipaddress.ip_address(self.address)
        except (TypeError, ValueError):
            raise ValueError("numeric endpoint address is invalid") from None
        expected = socket.AF_INET if address.version == 4 else socket.AF_INET6
        if (
            self.family != expected
            or str(address) != self.address
            or isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65535
        ):
            raise ValueError("numeric endpoint is not canonical")

    @property
    def sockaddr(self) -> tuple:
        if self.family == socket.AF_INET:
            return (self.address, self.port)
        return (self.address, self.port, 0, 0)


@dataclass(frozen=True)
class ProxyRequest:
    method: str
    target: str
    headers: tuple[tuple[str, str], ...]

    def values(self, name: str) -> tuple[str, ...]:
        lowered = name.lower()
        return tuple(value for key, value in self.headers if key == lowered)


Resolver = Callable[[str, int], Awaitable[Sequence[str]]]
Dialer = Callable[
    [NumericEndpoint, float],
    Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]],
]


async def resolve_system(host: str, port: int) -> Sequence[str]:
    """Resolve one hostname once; callers own timeout and answer bounds."""
    loop = asyncio.get_running_loop()
    answers = await loop.getaddrinfo(
        host,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return tuple(answer[4][0] for answer in answers)


async def dial_numeric(
    endpoint: NumericEndpoint, timeout: float
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect an already-numeric sockaddr without invoking name resolution."""
    sock = socket.socket(endpoint.family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    sock.setblocking(False)
    try:
        await asyncio.wait_for(
            asyncio.get_running_loop().sock_connect(sock, endpoint.sockaddr),
            timeout=timeout,
        )
        return await asyncio.open_connection(sock=sock)
    except BaseException:
        sock.close()
        raise


class EgressGateway:
    """Authenticated single-destination HTTP/CONNECT proxy on IPv4 loopback."""

    def __init__(
        self,
        *,
        resolver: Resolver = resolve_system,
        dialer: Dialer = dial_numeric,
        allowed_ports: Iterable[int] = (80, 443, 8080, 8443),
        deny_networks: Iterable[str] = (),
        limits: GatewayLimits | None = None,
        username: str = "connectonion",
        password: str | None = None,
        bind_host: str = "127.0.0.1",
        allow_remote_resolution: bool = False,
    ):
        # Loopback is the default and the only address a browser-private
        # gateway may use. `co proxy share` runs the same request machinery on
        # a reachable address so a remote agent can egress through this
        # machine, and that is the only reason this is a parameter.
        self.bind_host = bind_host
        self.allow_remote_resolution = bool(allow_remote_resolution)
        self.resolver = resolver
        self.dialer = dialer
        try:
            self.allowed_ports = frozenset(allowed_ports)
            self.deny_networks = tuple(deny_networks)
        except TypeError:
            raise ValueError("gateway destination policy is invalid") from None
        self.limits = limits or GatewayLimits()
        self.username = username
        self.password = secrets.token_urlsafe(32) if password is None else password
        if (
            not isinstance(self.username, str)
            or not isinstance(self.password, str)
            or not self.username
            or not self.password
            or len(self.username) > 256
            or len(self.password) > 256
            or ":" in self.username
            or any(ord(char) < 0x21 or ord(char) > 0x7E for char in self.username)
            or any(ord(char) < 0x21 or ord(char) > 0x7E for char in self.password)
        ):
            raise ValueError("proxy credentials must be nonempty visible ASCII")
        raw = f"{self.username}:{self.password}".encode("ascii")
        self._authorization = b"Basic " + base64.b64encode(raw)
        if any(
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 1 <= port <= 65535
            for port in self.allowed_ports
        ):
            raise ValueError("gateway destination policy is invalid")
        # Validate operator CIDRs at construction rather than on a live request.
        try:
            decide_destination(
                DestinationAuthority(
                    "https", "8.8.8.8", 443, ipaddress.ip_address("8.8.8.8")
                ),
                deny_networks=self.deny_networks,
            )
        except DestinationPolicyError as exc:
            raise ValueError("gateway destination policy is invalid") from exc
        self._server: asyncio.AbstractServer | None = None
        self._port: int | None = None
        self._closing = False
        self._active = 0
        self._pending = 0
        self._lifecycle_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._client_tasks: set[asyncio.Task] = set()
        self._handled = 0

    @property
    def endpoint(self) -> ProxyEndpoint:
        if self._port is None:
            raise RuntimeError("egress gateway is not started")
        return ProxyEndpoint(self.bind_host, self._port, self.username, self.password)

    @property
    def is_running(self) -> bool:
        """Whether this instance still owns a serving listener."""
        return self._server is not None and self._server.is_serving()

    @property
    def handled_requests(self) -> int:
        """How many authenticated requests this gateway has decided.

        The positive control for anything asserting an absence: "the sentinel
        saw no sockets" and "the browser never made the request" produce the
        same zero, and a proof built on the first needs this to tell them
        apart.
        """
        return self._handled

    async def start(self) -> ProxyEndpoint:
        async with self._lifecycle_lock:
            if self._server is not None:
                return self.endpoint
            self._closing = False
            listener = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP
            )
            try:
                listener.bind((self.bind_host, 0))
                listener.listen()
                listener.setblocking(False)
                self._server = await asyncio.start_server(
                    self._accept,
                    sock=listener,
                    limit=self.limits.header_bytes + 1,
                )
            except BaseException:
                listener.close()
                raise
            sockets = self._server.sockets or ()
            host, port = (
                sockets[0].getsockname()[:2] if len(sockets) == 1 else (None, 0)
            )
            if host != self.bind_host:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
                raise RuntimeError("egress gateway did not bind the address it asked for")
            self._port = int(port)
            return self.endpoint

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            self._closing = True
            server, self._server = self._server, None
            if server is not None:
                server.close()
            tasks = tuple(task for task in self._client_tasks if not task.done())
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if server is not None:
                # Python 3.14 wait_closed() waits for accepted connections too.
                # Cancel owned handlers first so shutdown cannot wait on the very
                # resolver/tunnel that shutdown is responsible for stopping.
                await server.wait_closed()
            self._client_tasks.clear()
            self._port = None

    async def __aenter__(self) -> EgressGateway:
        await self.start()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.stop()

    async def _promote(self, admission: _Admission) -> None:
        """Take a served-connection slot, now that the credential is proven."""
        async with self._state_lock:
            if self._closing:
                raise GatewayRefusal(GATEWAY_STOPPING)
            if self._active >= self.limits.max_connections:
                raise GatewayRefusal(OVERLOADED)
            self._active += 1
            admission.promoted = True

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._client_tasks.add(task)
        admitted = False
        admission = _Admission()
        try:
            async with self._state_lock:
                if (
                    not self._closing
                    and self._pending < self.limits.max_pending_connections
                ):
                    self._pending += 1
                    admitted = True
            if not admitted:
                await self._send_error(
                    writer, OVERLOADED if not self._closing else GATEWAY_STOPPING
                )
                # macOS resets a TCP close with unread peer bytes, which can erase
                # the already-written 429/503. Consume at most one bounded request
                # buffer without parsing, authenticating, resolving, or dialing.
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(
                        reader.read(self.limits.header_bytes + 1), timeout=0.05
                    )
                return
            await self._serve_connection(reader, writer, admission)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Every expected refusal is translated inside _serve_connection.
            # An unexpected failure closes silently because a response may have
            # already started; appending a second response is request smuggling.
            pass
        finally:
            if admitted:
                async with self._state_lock:
                    self._pending -= 1
                    if admission.promoted:
                        self._active -= 1
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            if task is not None:
                self._client_tasks.discard(task)

    async def _serve_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        admission: _Admission,
    ) -> None:
        try:
            request = await self._read_request(reader)
            self._authenticate(request)
            # Counted the moment the credential is proven, which is the point
            # this gateway has definitely seen the request, whatever the policy
            # decides next.
            self._handled += 1
            await self._promote(admission)
            if request.method == "CORESOLVE":
                await self._serve_resolution(request, writer)
                return
            authority, origin_target, upgrade = self._request_destination(request)
            endpoints = await self._approved_endpoints(authority)
            upstream_reader, upstream_writer = await self._connect(endpoints)
        except GatewayRefusal as refusal:
            await self._send_error(writer, refusal.code)
            return
        except DestinationPolicyError as refusal:
            await self._send_error(writer, refusal.code)
            return

        try:
            if request.method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await self._drain(writer)
                await self._tunnel(reader, writer, upstream_reader, upstream_writer)
                return

            assert origin_target is not None
            content_length = self._content_length(request)
            outgoing = self._rewrite_headers(request, authority, origin_target, upgrade)
            upstream_writer.write(outgoing)
            await self._drain(upstream_writer)
            if upgrade:
                await self._tunnel(reader, writer, upstream_reader, upstream_writer)
                return
            if content_length:
                await self._stream_body(reader, upstream_writer, content_length)
            with contextlib.suppress(NotImplementedError, OSError):
                upstream_writer.write_eof()
            await self._relay_response_head(upstream_reader, writer)
            await self._copy(upstream_reader, writer)
        except (GatewayRefusal, ConnectionError, OSError):
            # Upstream establishment succeeded, so either side may already have
            # observed bytes. Close instead of appending a second HTTP response.
            pass
        finally:
            upstream_writer.close()
            with contextlib.suppress(Exception):
                await upstream_writer.wait_closed()

    async def _serve_resolution(
        self, request: ProxyRequest, writer: asyncio.StreamWriter
    ) -> None:
        """Resolve one authority on the egress machine for a shared browser.

        Chromium never calls this method.  The remote host-private gateway uses
        it before asking this same service to CONNECT one returned numeric
        address.  Keeping resolution here makes the Laptop the DNS boundary;
        keeping the ordinary destination decision here means sharing an exit
        never shares the Laptop's LAN.
        """
        if not self.allow_remote_resolution:
            raise GatewayRefusal(RESOLVE_UNAVAILABLE)
        if request.values("host"):
            raise GatewayRefusal(INVALID)
        try:
            encoded, raw_port = request.target.rsplit(":", 1)
            padding = "=" * (-len(encoded) % 4)
            host = base64.urlsafe_b64decode((encoded + padding).encode("ascii")).decode(
                "utf-8"
            )
            port = int(raw_port)
        except (ValueError, UnicodeError, binascii.Error):
            raise GatewayRefusal(INVALID) from None
        if not host or isinstance(port, bool) or not 1 <= port <= 65535:
            raise GatewayRefusal(INVALID)
        endpoints = await self.resolve_destination(host, port)
        body = ("\n".join(endpoint.address for endpoint in endpoints) + "\n").encode(
            "ascii"
        )
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Connection: close\r\n"
            b"Content-Type: text/plain; charset=us-ascii\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        await self._drain(writer)

    async def resolve_destination(
        self, host: str, port: int
    ) -> tuple[NumericEndpoint, ...]:
        """This gateway's destination policy applied to one name, no socket.

        The laptop end of a share answers the browser host's `resolve` with
        this: the same resolver, the same bounds, the same frozen classifier
        that decides what its own listener would connect to.
        """
        bracketed = f"[{host}]" if ":" in host else host
        try:
            authority = normalize_web_destination(f"https://{bracketed}:{port}")
            return await self._approved_endpoints(authority)
        except DestinationPolicyError as refusal:
            raise GatewayRefusal(refusal.code) from refusal

    async def connect_destination(
        self, address: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Classify one numeric address again, then dial it.

        A share connects only what it has just approved itself; the peer's
        earlier resolve answer is not a decision it gets to keep.
        """
        bracketed = f"[{address}]" if ":" in address else address
        try:
            authority = normalize_web_destination(
                f"https://{bracketed}:{port}/", allowed_ports=self.allowed_ports
            )
        except DestinationPolicyError as refusal:
            raise GatewayRefusal(refusal.code) from refusal
        if authority.literal is None:
            raise GatewayRefusal(INVALID)
        return await self._connect(await self._approved_endpoints(authority))

    async def _read_request(self, reader: asyncio.StreamReader) -> ProxyRequest:
        refusal_code = None
        try:
            block = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), timeout=self.limits.header_timeout
            )
        except asyncio.TimeoutError:
            refusal_code = HEADER_TIMEOUT
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            refusal_code = HEADER_TOO_LARGE
        if refusal_code is not None:
            raise GatewayRefusal(refusal_code)
        if len(block) > self.limits.header_bytes:
            raise GatewayRefusal(HEADER_TOO_LARGE)
        lines = block[:-4].split(b"\r\n")
        if not lines or len(lines[0]) > self.limits.request_line_bytes:
            raise GatewayRefusal(HEADER_TOO_LARGE)
        parts = lines[0].split(b" ")
        if (
            len(parts) != 3
            or not _METHOD.fullmatch(parts[0])
            or parts[2] != b"HTTP/1.1"
        ):
            raise GatewayRefusal(INVALID)
        try:
            method = parts[0].decode("ascii")
            target = parts[1].decode("ascii")
        except UnicodeDecodeError:
            raise GatewayRefusal(INVALID)
        if not target or len(lines) - 1 > self.limits.header_count:
            raise GatewayRefusal(INVALID)
        headers: list[tuple[str, str]] = []
        for line in lines[1:]:
            if not line or line[:1] in {b" ", b"\t"} or b":" not in line:
                raise GatewayRefusal(INVALID)
            raw_name, raw_value = line.split(b":", 1)
            if not _HEADER_NAME.fullmatch(raw_name):
                raise GatewayRefusal(INVALID)
            value = raw_value.strip(b" ")
            if any(byte < 0x20 or byte > 0x7E for byte in value):
                raise GatewayRefusal(INVALID)
            headers.append((raw_name.decode("ascii").lower(), value.decode("ascii")))
        return ProxyRequest(method, target, tuple(headers))

    def _authenticate(self, request: ProxyRequest) -> None:
        values = request.values("proxy-authorization")
        if len(values) != 1:
            raise GatewayRefusal(AUTH_REQUIRED)
        supplied = values[0].encode("ascii")
        if not hmac.compare_digest(supplied, self._authorization):
            raise GatewayRefusal(AUTH_REQUIRED)

    def _request_destination(
        self, request: ProxyRequest
    ) -> tuple[DestinationAuthority, str | None, bool]:
        hosts = request.values("host")
        if len(hosts) > 1:
            raise GatewayRefusal(INVALID)
        if request.method == "CONNECT":
            if any(char in request.target for char in "/?#@"):
                raise GatewayRefusal(INVALID)
            split = self._safe_split(f"https://{request.target}/")
            explicit_port = None
            port_invalid = False
            try:
                explicit_port = split.port
            except ValueError:
                port_invalid = True
            if port_invalid:
                raise GatewayRefusal(INVALID)
            if explicit_port is None:
                raise GatewayRefusal(PORT_DENIED)
            authority = normalize_web_destination(
                f"https://{request.target}/", allowed_ports=self.allowed_ports
            )
            if hosts:
                self._require_matching_host(hosts[0], authority)
            if request.values("content-length") or request.values("transfer-encoding"):
                raise GatewayRefusal(INVALID)
            return authority, None, False

        split = self._safe_split(request.target)
        # A fragment is never sent on the wire, so a target carrying one is a
        # malformed request rather than a scheme this gateway declines. The
        # distinction only shows up when someone reads the code and goes looking
        # at scheme policy for a target whose scheme was fine.
        if split.fragment:
            raise GatewayRefusal(INVALID)
        if split.scheme.lower() not in {"http", "ws"}:
            raise GatewayRefusal(SCHEME_DENIED if split.scheme else INVALID)
        authority = normalize_web_destination(
            request.target, allowed_ports=self.allowed_ports
        )
        if len(hosts) != 1:
            raise GatewayRefusal(INVALID)
        self._require_matching_host(hosts[0], authority)
        origin = urlunsplit(("", "", split.path or "/", split.query, ""))
        connection = request.values("connection")
        upgrades = request.values("upgrade")
        if len(connection) > 1 or len(upgrades) > 1:
            raise GatewayRefusal(INVALID)
        tokens = {
            token.strip().lower()
            for value in connection
            for token in value.split(",")
            if token.strip()
        }
        if tokens & {
            "host",
            "content-length",
            "transfer-encoding",
            "proxy-authorization",
        }:
            raise GatewayRefusal(INVALID)
        upgrade = bool(upgrades and "upgrade" in tokens)
        if bool(upgrades) != ("upgrade" in tokens) or (
            upgrade and request.method != "GET"
        ):
            raise GatewayRefusal(INVALID)
        self._content_length(request)
        return authority, origin, upgrade

    @staticmethod
    def _safe_split(value: str):
        split = None
        try:
            split = urlsplit(value)
        except ValueError:
            pass
        if split is None:
            raise GatewayRefusal(INVALID)
        return split

    def _require_matching_host(
        self, header_value: str, authority: DestinationAuthority
    ) -> None:
        if any(character in header_value for character in "/?#@"):
            raise GatewayRefusal(INVALID)
        candidate = normalize_web_destination(
            f"{authority.scheme}://{header_value}/", allowed_ports=self.allowed_ports
        )
        if (candidate.host, candidate.port) != (authority.host, authority.port):
            raise GatewayRefusal(INVALID)

    def _content_length(self, request: ProxyRequest) -> int:
        lengths = request.values("content-length")
        transfers = request.values("transfer-encoding")
        if len(lengths) > 1 or len(transfers) > 0 or request.values("expect"):
            raise GatewayRefusal(INVALID)
        if not lengths:
            return 0
        if not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 20:
            raise GatewayRefusal(INVALID)
        length = int(lengths[0])
        if length > self.limits.bytes_per_direction:
            raise GatewayRefusal(TRANSFER_LIMIT)
        return length

    async def _approved_endpoints(
        self, authority: DestinationAuthority
    ) -> tuple[NumericEndpoint, ...]:
        if authority.literal is not None:
            answers = (str(authority.literal),)
        else:
            resolution_failed = False
            try:
                answers = tuple(
                    await asyncio.wait_for(
                        self.resolver(authority.host, authority.port),
                        timeout=self.limits.resolve_timeout,
                    )
                )
            except (asyncio.TimeoutError, OSError):
                resolution_failed = True
                answers = ()
            except Exception:
                # Resolver is pluggable. Whatever a custom one raises, the
                # caller gets the same refusal — a resolver failure that closed
                # the connection with no response at all left the operator
                # nothing to read and the client nothing to distinguish.
                resolution_failed = True
                answers = ()
            if resolution_failed:
                raise GatewayRefusal(DNS_FAILED)
        if not answers or len(answers) > self.limits.max_dns_answers:
            raise GatewayRefusal(DNS_FAILED)
        decision = decide_destination(
            authority, answers, deny_networks=self.deny_networks
        )
        if not decision.ok:
            raise GatewayRefusal(decision.code)
        endpoints = []
        for value in decision.addresses:
            address = ipaddress.ip_address(value)
            family = socket.AF_INET if address.version == 4 else socket.AF_INET6
            endpoints.append(NumericEndpoint(family, str(address), authority.port))
        return tuple(endpoints)

    async def _connect(
        self, endpoints: Sequence[NumericEndpoint]
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.limits.connect_timeout
        for endpoint in endpoints:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                return await asyncio.wait_for(
                    self.dialer(endpoint, remaining), timeout=remaining
                )
            except (asyncio.TimeoutError, OSError):
                continue
        raise GatewayRefusal(CONNECT_FAILED)

    def _rewrite_headers(
        self,
        request: ProxyRequest,
        authority: DestinationAuthority,
        origin_target: str,
        upgrade: bool,
    ) -> bytes:
        connection_tokens = {
            token.strip().lower()
            for value in request.values("connection")
            for token in value.split(",")
            if token.strip()
        }
        remove = {
            "host",
            "proxy-authorization",
            "proxy-connection",
            "connection",
            "keep-alive",
            "te",
            "trailer",
        }
        remove.update(connection_tokens - ({"upgrade"} if upgrade else set()))
        lines = [f"{request.method} {origin_target} HTTP/1.1"]
        host = authority.host
        if ":" in host:
            host = f"[{host}]"
        default_port = 80 if authority.scheme in {"http", "ws"} else 443
        suffix = "" if authority.port == default_port else f":{authority.port}"
        lines.append(f"Host: {host}{suffix}")
        for name, value in request.headers:
            if name not in remove and (name != "upgrade" or upgrade):
                lines.append(f"{name}: {value}")
        lines.append("Connection: Upgrade" if upgrade else "Connection: close")
        return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")

    async def _relay_response_head(
        self, upstream: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Forward the response head with connection reuse taken away.

        The gateway answers exactly one request per connection and then stops
        reading. An origin that replies `Connection: keep-alive` would leave the
        client believing otherwise — and a second response queued behind the
        first would already be in the client's receive buffer, waiting to be
        matched against whatever it sends next. Rewriting the hop-by-hop
        headers here is what makes the one-request-per-connection rule visible
        to the client instead of only true inside the gateway.
        """
        head = None
        try:
            head = await asyncio.wait_for(
                upstream.readuntil(b"\r\n\r\n"), timeout=self.limits.idle_timeout
            )
        except (
            asyncio.TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            pass
        if head is None or len(head) > self.limits.header_bytes:
            # An unparseable or oversized head cannot be made safe, and passing
            # it through is what this function exists to prevent.
            raise GatewayRefusal(TRANSFER_LIMIT)

        lines = head.decode("latin-1").split("\r\n")
        rewritten = [lines[0]]
        for line in lines[1:]:
            name, separator, _ = line.partition(":")
            if not separator:
                continue
            if name.strip().lower() in {"connection", "keep-alive", "proxy-connection"}:
                continue
            rewritten.append(line)
        rewritten.append("Connection: close")
        writer.write(("\r\n".join(rewritten) + "\r\n\r\n").encode("latin-1"))
        await self._drain(writer)

    async def _stream_body(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        count: int,
    ) -> None:
        """Forward a declared body in bounded chunks.

        `Content-Length` is caller-controlled, so reading it in one call sizes a
        resident buffer from a number a stranger chose: one connection declaring
        the transfer limit holds that many bytes in RAM, times the connection
        cap. Chunks bound the memory to the chunk size regardless of the
        declaration; the transfer limit still bounds the total.
        """
        if count > self.limits.bytes_per_direction:
            raise GatewayRefusal(TRANSFER_LIMIT)
        remaining = count
        while remaining:
            chunk = None
            try:
                chunk = await asyncio.wait_for(
                    reader.read(min(remaining, 64 * 1024)),
                    timeout=self.limits.idle_timeout,
                )
            except asyncio.TimeoutError:
                pass
            if not chunk:
                raise GatewayRefusal(TRANSFER_LIMIT)
            remaining -= len(chunk)
            writer.write(chunk)
            await self._drain(writer)

    async def _copy(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        total = 0
        while True:
            timed_out = False
            try:
                data = await asyncio.wait_for(
                    reader.read(64 * 1024), timeout=self.limits.idle_timeout
                )
            except asyncio.TimeoutError:
                timed_out = True
                data = b""
            if timed_out:
                raise GatewayRefusal(TRANSFER_LIMIT)
            if not data:
                with contextlib.suppress(NotImplementedError, OSError):
                    writer.write_eof()
                return
            total += len(data)
            if total > self.limits.bytes_per_direction:
                raise GatewayRefusal(TRANSFER_LIMIT)
            writer.write(data)
            await self._drain(writer)

    async def _tunnel(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        tasks = (
            asyncio.create_task(self._copy(client_reader, upstream_writer)),
            asyncio.create_task(self._copy(upstream_reader, client_writer)),
        )
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _drain(self, writer: asyncio.StreamWriter) -> None:
        failed = False
        try:
            await asyncio.wait_for(writer.drain(), timeout=self.limits.idle_timeout)
        except (asyncio.TimeoutError, ConnectionError, OSError):
            failed = True
        if failed:
            raise GatewayRefusal(TRANSFER_LIMIT)

    async def _send_error(self, writer: asyncio.StreamWriter, code: str) -> None:
        if writer.is_closing():
            return
        status, reason = _ERROR_STATUS.get(code, _ERROR_STATUS[CONNECT_FAILED])
        authenticate = (
            'Proxy-Authenticate: Basic realm="ConnectOnion Remote Browser"\r\n'
            if code == AUTH_REQUIRED
            else ""
        )
        # A refusal carries a body because Chromium will not commit a bodyless
        # 4xx/5xx main-frame navigation: it reports ERR_HTTP_RESPONSE_CODE_FAILURE
        # instead, so `page.goto` raises rather than returning the status. The
        # native preflight has to read this refusal as evidence that the browser
        # reached this gateway, and with no body it never sees one. The body
        # holds the stable code and nothing caller-controlled.
        body = f"{code}\n".encode("ascii")
        response = (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Connection: close\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"X-ConnectOnion-Error: {code}\r\n"
            f"{authenticate}\r\n"
        ).encode("ascii") + body
        writer.write(response)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(writer.drain(), timeout=1.0)

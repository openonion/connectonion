"""Share this computer's internet connection with an authorized remote agent.

A browser running on a server reaches the internet from a data-centre address.
Many sites treat that differently from an ordinary home connection, so the
Remote Browser product lets the caller lend its own connection instead:

    browser on the host  ──▶  this machine  ──▶  the internet (your IP)

This module is the middle box. It is deliberately the same request machinery as
the host-private egress gateway — same parser, same authentication, same
destination policy, same limits — bound to a reachable address instead of
loopback. Sharing a connection must not mean sharing the network behind it, and
the policy that keeps a remote caller off the host's private network is exactly
the one that keeps it off yours.

The grant issued by `connectonion.network.proxy` is the credential. Nothing
here reads a browser profile, a cookie, or a file: the tunnel carries bytes the
remote browser already decided to send, and TLS inside it stays end to end.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import socket
from dataclasses import dataclass

from .host.egress_gateway import (
    EgressGateway,
    GatewayLimits,
    NumericEndpoint,
    ProxyEndpoint,
)

# Ranges a shared connection must never reach on the sharer's behalf. The
# gateway's frozen table already denies these; naming them here is what makes
# the intent legible when someone widens the policy later.
SHARED_DENY_NETWORKS: tuple[str, ...] = ()

DEFAULT_SHARE_PORT = 0
_REMOTE_HEADER_LIMIT = 16 * 1024
_REMOTE_IO_TIMEOUT = 10.0


@dataclass(frozen=True)
class ShareEndpoint:
    """Where an authorized agent connects, and what it must present."""

    host: str
    port: int
    username: str
    password: str

    @property
    def url(self) -> str:
        """The address to hand the remote host; carries no credential."""
        return f"http://{self.host}:{self.port}"


def local_egress_address() -> str:
    """The address on this machine a remote agent can actually reach.

    Not `gethostname()`: on a laptop that frequently resolves to loopback, and
    a service bound there is reachable by nothing. Asking the routing table
    which address it would use to reach the internet gives the interface a
    remote peer arrives on.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    finally:
        probe.close()


class ProxyEgressService:
    """This machine's internet connection, lent to one authorized agent."""

    def __init__(
        self,
        *,
        bind_host: str | None = None,
        credential: str | None = None,
        allowed_ports=(80, 443, 8080, 8443),
        deny_networks=SHARED_DENY_NETWORKS,
        limits: GatewayLimits | None = None,
        resolver=None,
        dialer=None,
    ):
        overrides = {}
        if resolver is not None:
            overrides["resolver"] = resolver
        if dialer is not None:
            overrides["dialer"] = dialer
        self._gateway = EgressGateway(
            allowed_ports=allowed_ports,
            deny_networks=deny_networks,
            limits=limits,
            **overrides,
            username="connectonion-proxy",
            password=credential,
            bind_host=bind_host or local_egress_address(),
            allow_remote_resolution=True,
        )

    @property
    def endpoint(self) -> ShareEndpoint:
        inner = self._gateway.endpoint
        return ShareEndpoint(inner.host, inner.port, inner.username, inner.password)

    @property
    def is_running(self) -> bool:
        return self._gateway.is_running

    @property
    def handled_requests(self) -> int:
        """Requests this share has decided; the evidence `co proxy status` shows."""
        return self._gateway.handled_requests

    async def start(self) -> ShareEndpoint:
        await self._gateway.start()
        return self.endpoint

    async def stop(self) -> None:
        await self._gateway.stop()

    async def __aenter__(self) -> "ProxyEgressService":
        await self.start()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.stop()


def remote_proxy_dialer(share: ShareEndpoint):
    """Dial approved destinations through a shared connection, not directly.

    Returned in the shape `EgressGateway` expects for its `dialer`, which is
    the whole integration: the host still resolves, classifies and pins a
    numeric address itself, and only the last hop changes. The host asks the
    sharer for that exact numeric address — never a hostname — so lending a
    connection cannot widen what the host was willing to reach.
    """

    async def dial(endpoint: NumericEndpoint, timeout: float):
        authority = (
            f"[{endpoint.address}]:{endpoint.port}"
            if endpoint.family == socket.AF_INET6
            else f"{endpoint.address}:{endpoint.port}"
        )
        token = base64.b64encode(
            f"{share.username}:{share.password}".encode("ascii")
        ).decode("ascii")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                share.host, share.port, limit=_REMOTE_HEADER_LIMIT + 1
            ),
            timeout=timeout,
        )
        try:
            writer.write(
                (
                    f"CONNECT {authority} HTTP/1.1\r\n"
                    f"Host: {authority}\r\n"
                    f"Proxy-Authorization: Basic {token}\r\n\r\n"
                ).encode("ascii")
            )
            await asyncio.wait_for(writer.drain(), timeout=timeout)
            head = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), timeout=timeout
            )
            if len(head) > _REMOTE_HEADER_LIMIT:
                raise OSError("shared connection returned an invalid response")
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            asyncio.TimeoutError,
        ) as exc:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            raise OSError("shared connection returned an invalid response") from exc
        except BaseException:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            raise
        status = head.split(b" ")[1:2]
        if status != [b"200"]:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            # The sharer refused. Its reason is its own business — surfacing it
            # would let a remote caller probe someone else's network policy.
            raise OSError("shared connection refused this destination")
        return reader, writer

    return dial


def remote_proxy_resolver(share: ShareEndpoint):
    """Resolve browser destinations on the Laptop that owns the shared exit.

    The server-side browser and operating system never resolve the target.  A
    small authenticated request asks the Laptop's already-bounded egress
    service for its complete answer set; the server classifies that set again
    before selecting one numeric address, and the Laptop classifies the chosen
    address once more when CONNECT arrives.
    """

    async def resolve(host: str, port: int):
        encoded = base64.urlsafe_b64encode(host.encode("utf-8")).decode("ascii").rstrip(
            "="
        )
        token = base64.b64encode(
            f"{share.username}:{share.password}".encode("ascii")
        ).decode("ascii")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                share.host, share.port, limit=_REMOTE_HEADER_LIMIT + 1
            ),
            timeout=_REMOTE_IO_TIMEOUT,
        )
        try:
            writer.write(
                (
                    f"CORESOLVE {encoded}:{port} HTTP/1.1\r\n"
                    f"Proxy-Authorization: Basic {token}\r\n\r\n"
                ).encode("ascii")
            )
            await asyncio.wait_for(writer.drain(), timeout=_REMOTE_IO_TIMEOUT)
            head = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), timeout=_REMOTE_IO_TIMEOUT
            )
            if len(head) > _REMOTE_HEADER_LIMIT:
                raise OSError("shared connection returned invalid DNS response")
            status = head.split(b" ")[1:2]
            if status != [b"200"]:
                raise OSError("shared connection refused remote DNS")
            length = None
            for line in head.split(b"\r\n")[1:]:
                name, separator, value = line.partition(b":")
                if separator and name.lower() == b"content-length":
                    length = int(value.strip())
                    break
            if length is None or not 0 < length <= 4096:
                raise OSError("shared connection returned invalid DNS response")
            body = await asyncio.wait_for(
                reader.readexactly(length), timeout=_REMOTE_IO_TIMEOUT
            )
            answers = tuple(line for line in body.decode("ascii").splitlines() if line)
            if not answers:
                raise OSError("shared connection returned no DNS answers")
            # Canonicalize before returning into EgressGateway's independent
            # frozen classifier.  A malformed Laptop response cannot reach a
            # dial call or turn into a second hostname lookup.
            return tuple(str(ipaddress.ip_address(answer)) for answer in answers)
        except (
            ValueError,
            UnicodeError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            asyncio.TimeoutError,
        ) as exc:
            raise OSError("shared connection returned invalid DNS response") from exc
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    return resolve


def shared_egress_gateway(
    share: ShareEndpoint,
    **kwargs,
) -> EgressGateway:
    """A host-private gateway whose last hop is the caller's own connection."""
    if "resolver" in kwargs or "dialer" in kwargs:
        raise ValueError("shared egress owns its resolver and dialer")
    return EgressGateway(
        resolver=remote_proxy_resolver(share),
        dialer=remote_proxy_dialer(share),
        **kwargs,
    )


__all__ = [
    "DEFAULT_SHARE_PORT",
    "ProxyEgressService",
    "ProxyEndpoint",
    "ShareEndpoint",
    "local_egress_address",
    "remote_proxy_dialer",
    "remote_proxy_resolver",
    "shared_egress_gateway",
]

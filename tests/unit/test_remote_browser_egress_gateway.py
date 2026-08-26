"""Protocol and zero-dial contracts for the Remote Browser egress gateway."""

import asyncio
import base64
import contextlib
import socket
import time

import pytest

from connectonion.network.host.destination_policy import normalize_web_destination
from connectonion.network.host.egress_gateway import (
    AUTH_REQUIRED,
    HEADER_TIMEOUT,
    HEADER_TOO_LARGE,
    OVERLOADED,
    EgressGateway,
    GatewayLimits,
    GatewayRefusal,
    NumericEndpoint,
    dial_numeric,
)


def _authorization(endpoint) -> str:
    value = f"{endpoint.username}:{endpoint.password}".encode("ascii")
    return "Basic " + base64.b64encode(value).decode("ascii")


def _connect_request(endpoint, target="example.com:443", *, extra_headers=()) -> bytes:
    headers = [
        f"CONNECT {target} HTTP/1.1",
        f"Host: {target}",
        f"Proxy-Authorization: {_authorization(endpoint)}",
        *extra_headers,
        "",
        "",
    ]
    return "\r\n".join(headers).encode("ascii")


async def _exchange(endpoint, payload: bytes) -> bytes:
    reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
    writer.write(payload)
    await writer.drain()
    with contextlib.suppress(NotImplementedError):
        writer.write_eof()
    response = await asyncio.wait_for(reader.read(), timeout=2)
    writer.close()
    await writer.wait_closed()
    return response


class RecordingResolver:
    def __init__(self, answers=("8.8.8.8",)):
        self.answers = answers
        self.calls = []

    async def __call__(self, host, port):
        self.calls.append((host, port))
        return self.answers


class RecordingDialer:
    def __init__(self, redirect_port=None):
        self.redirect_port = redirect_port
        self.calls = []

    async def __call__(self, endpoint, timeout):
        self.calls.append((endpoint, timeout))
        if self.redirect_port is None:
            raise OSError("test dial refused")
        return await asyncio.open_connection("127.0.0.1", self.redirect_port)


@pytest.mark.asyncio
async def test_gateway_binds_only_ephemeral_ipv4_loopback_and_rotates_credentials():
    first = EgressGateway()
    second = EgressGateway()
    async with first, second:
        assert first.endpoint.host == second.endpoint.host == "127.0.0.1"
        assert first.endpoint.port > 0
        assert second.endpoint.port > 0
        assert first.endpoint.password != second.endpoint.password


@pytest.mark.asyncio
async def test_concurrent_start_and_stop_share_one_listener_and_cleanup_once():
    gateway = EgressGateway()
    endpoints = await asyncio.gather(*(gateway.start() for _ in range(10)))

    assert len({(endpoint.host, endpoint.port) for endpoint in endpoints}) == 1
    assert gateway.is_running is True
    await asyncio.gather(*(gateway.stop() for _ in range(10)))
    assert gateway.is_running is False
    assert gateway._server is None
    assert gateway._client_tasks == set()
    with pytest.raises(RuntimeError):
        _ = gateway.endpoint


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [None, "Basic wrong", "Basic one\r\nProxy-Authorization: Basic two"],
)
async def test_auth_failure_never_resolves_or_dials(authorization):
    resolver = RecordingResolver()
    dialer = RecordingDialer()
    gateway = EgressGateway(resolver=resolver, dialer=dialer, password="test-secret")
    async with gateway:
        headers = ["CONNECT example.com:443 HTTP/1.1", "Host: example.com:443"]
        if authorization is not None:
            headers.append(f"Proxy-Authorization: {authorization}")
        response = await _exchange(
            gateway.endpoint, ("\r\n".join([*headers, "", ""])).encode("ascii")
        )

    assert b"407 Proxy Authentication Required" in response
    assert f"X-ConnectOnion-Error: {AUTH_REQUIRED}".encode() in response
    assert resolver.calls == []
    assert dialer.calls == []
    assert b"test-secret" not in response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "status"),
    [
        ("127.1:443", b"403 Forbidden"),
        ("2130706433:443", b"403 Forbidden"),
        ("169.254.169.254:80", b"403 Forbidden"),
        ("example.com:22", b"403 Forbidden"),
        ("localhost:443", b"403 Forbidden"),
    ],
)
async def test_literal_and_authority_denials_are_zero_dial(target, status):
    resolver = RecordingResolver()
    dialer = RecordingDialer()
    gateway = EgressGateway(resolver=resolver, dialer=dialer, password="secret")
    async with gateway:
        response = await _exchange(
            gateway.endpoint, _connect_request(gateway.endpoint, target)
        )

    assert status in response
    assert dialer.calls == []
    if target[0].isdigit():
        assert resolver.calls == []


@pytest.mark.asyncio
async def test_mixed_dns_answer_set_is_denied_before_any_dial():
    resolver = RecordingResolver(("8.8.8.8", "127.0.0.1"))
    dialer = RecordingDialer()
    gateway = EgressGateway(resolver=resolver, dialer=dialer, password="secret")
    async with gateway:
        response = await _exchange(gateway.endpoint, _connect_request(gateway.endpoint))

    assert b"403 Forbidden" in response
    assert resolver.calls == [("example.com", 443)]
    assert dialer.calls == []


@pytest.mark.asyncio
async def test_hostname_resolves_once_and_only_numeric_candidates_reach_the_dialer():
    resolver = RecordingResolver(("2001:4860:4860::8888", "8.8.8.8"))
    dialer = RecordingDialer()
    gateway = EgressGateway(resolver=resolver, dialer=dialer, password="secret")
    async with gateway:
        response = await _exchange(gateway.endpoint, _connect_request(gateway.endpoint))

    assert b"502 Bad Gateway" in response
    assert resolver.calls == [("example.com", 443)]
    assert [call[0].address for call in dialer.calls] == [
        "8.8.8.8",
        "2001:4860:4860::8888",
    ]
    assert [call[0].family for call in dialer.calls] == [
        socket.AF_INET,
        socket.AF_INET6,
    ]
    assert all(call[0].address != "example.com" for call in dialer.calls)


@pytest.mark.asyncio
async def test_dial_failure_retries_only_the_frozen_approved_answer_set():
    upstream_connected = asyncio.Event()

    async def upstream_handler(_reader, writer):
        upstream_connected.set()
        writer.close()
        await writer.wait_closed()

    upstream = await asyncio.start_server(upstream_handler, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    calls = []

    async def fallback_dialer(endpoint, _timeout):
        calls.append(endpoint)
        if len(calls) == 1:
            raise OSError("first approved peer unavailable")
        return await asyncio.open_connection("127.0.0.1", port)

    resolver = RecordingResolver(("2001:4860:4860::8888", "8.8.8.8"))
    gateway = EgressGateway(
        resolver=resolver, dialer=fallback_dialer, password="secret"
    )
    try:
        async with gateway:
            response = await _exchange(
                gateway.endpoint, _connect_request(gateway.endpoint)
            )
            await asyncio.wait_for(upstream_connected.wait(), timeout=1)
    finally:
        await gateway.stop()
        upstream.close()
        await upstream.wait_closed()

    assert response.startswith(b"HTTP/1.1 200 Connection Established")
    assert [endpoint.address for endpoint in calls] == [
        "8.8.8.8",
        "2001:4860:4860::8888",
    ]
    assert resolver.calls == [("example.com", 443)]


@pytest.mark.asyncio
async def test_connect_timeout_bounds_the_complete_answer_set():
    calls = []

    async def stalled_dialer(endpoint, timeout):
        calls.append((endpoint, timeout))
        await asyncio.Event().wait()

    answers = (
        "1.0.0.1",
        "1.1.1.1",
        "8.8.4.4",
        "8.8.8.8",
        "9.9.9.9",
        "2001:4860:4860::8844",
        "2001:4860:4860::8888",
        "2606:4700:4700::1111",
    )
    gateway = EgressGateway(
        resolver=RecordingResolver(answers),
        dialer=stalled_dialer,
        limits=GatewayLimits(connect_timeout=0.2),
        password="secret",
    )
    started = time.perf_counter()
    async with gateway:
        response = await _exchange(gateway.endpoint, _connect_request(gateway.endpoint))
    elapsed = time.perf_counter() - started

    assert b"502 Bad Gateway" in response
    assert calls
    assert all(0 < timeout < 0.201 for _, timeout in calls)
    assert elapsed < 0.75


@pytest.mark.asyncio
async def test_connect_tunnels_bytes_only_after_policy_and_numeric_dial():
    received = bytearray()

    async def echo(reader, writer):
        try:
            while data := await reader.read(1024):
                received.extend(data)
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    resolver = RecordingResolver()
    dialer = RecordingDialer(port)
    gateway = EgressGateway(resolver=resolver, dialer=dialer, password="secret")
    try:
        async with gateway:
            reader, writer = await asyncio.open_connection(
                gateway.endpoint.host, gateway.endpoint.port
            )
            writer.write(_connect_request(gateway.endpoint))
            await writer.drain()
            assert await reader.readuntil(b"\r\n\r\n") == (
                b"HTTP/1.1 200 Connection Established\r\n\r\n"
            )
            assert received == b""
            writer.write(b"tls-client-hello")
            await writer.drain()
            assert (
                await reader.readexactly(len(b"tls-client-hello"))
                == b"tls-client-hello"
            )
            writer.close()
            await writer.wait_closed()
    finally:
        await gateway.stop()
        upstream.close()
        await upstream.wait_closed()

    assert received == b"tls-client-hello"
    assert dialer.calls[0][0] == NumericEndpoint(socket.AF_INET, "8.8.8.8", 443)


@pytest.mark.asyncio
async def test_absolute_http_is_rewritten_and_proxy_credentials_are_stripped():
    captured = bytearray()

    async def http_server(reader, writer):
        captured.extend(await reader.read())
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    upstream = await asyncio.start_server(http_server, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    dialer = RecordingDialer(port)
    gateway = EgressGateway(
        resolver=RecordingResolver(), dialer=dialer, password="strip-me"
    )
    try:
        async with gateway:
            request = (
                "GET http://example.com/private?q=secret HTTP/1.1\r\n"
                "Host: example.com\r\n"
                f"Proxy-Authorization: {_authorization(gateway.endpoint)}\r\n"
                "Proxy-Connection: keep-alive\r\n"
                "Connection: keep-alive\r\n"
                "X-Public: yes\r\n\r\n"
            ).encode("ascii")
            response = await _exchange(gateway.endpoint, request)
    finally:
        await gateway.stop()
        upstream.close()
        await upstream.wait_closed()

    assert response.endswith(b"\r\n\r\nok")
    assert captured.startswith(b"GET /private?q=secret HTTP/1.1\r\n")
    assert b"Host: example.com\r\n" in captured
    assert b"Connection: close\r\n" in captured
    assert b"proxy-authorization" not in captured.lower()
    assert b"proxy-connection" not in captured.lower()
    assert b"strip-me" not in captured


@pytest.mark.asyncio
async def test_plain_http_forwards_only_the_declared_body_not_a_pipelined_request():
    captured = bytearray()

    async def http_server(reader, writer):
        captured.extend(await reader.read())
        writer.write(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    upstream = await asyncio.start_server(http_server, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    gateway = EgressGateway(
        resolver=RecordingResolver(), dialer=RecordingDialer(port), password="secret"
    )
    try:
        async with gateway:
            request = (
                "POST http://example.com/form HTTP/1.1\r\n"
                "Host: example.com\r\n"
                f"Proxy-Authorization: {_authorization(gateway.endpoint)}\r\n"
                "Content-Length: 4\r\n\r\n"
                "body"
                "GET http://other.example/ HTTP/1.1\r\nHost: other.example\r\n\r\n"
            ).encode("ascii")
            await _exchange(gateway.endpoint, request)
    finally:
        await gateway.stop()
        upstream.close()
        await upstream.wait_closed()

    assert captured.endswith(b"\r\n\r\nbody")
    assert b"other.example" not in captured


@pytest.mark.asyncio
async def test_websocket_upgrade_stays_on_the_pinned_peer():
    captured_headers = bytearray()

    async def websocket_server(reader, writer):
        captured_headers.extend(await reader.readuntil(b"\r\n\r\n"))
        writer.write(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Connection: Upgrade\r\nUpgrade: websocket\r\n\r\n"
        )
        await writer.drain()
        while data := await reader.read(1024):
            writer.write(data)
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    upstream = await asyncio.start_server(websocket_server, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    gateway = EgressGateway(
        resolver=RecordingResolver(), dialer=RecordingDialer(port), password="secret"
    )
    try:
        async with gateway:
            reader, writer = await asyncio.open_connection(
                gateway.endpoint.host, gateway.endpoint.port
            )
            request = (
                "GET ws://example.com/socket HTTP/1.1\r\n"
                "Host: example.com\r\n"
                f"Proxy-Authorization: {_authorization(gateway.endpoint)}\r\n"
                "Connection: keep-alive, Upgrade\r\n"
                "Upgrade: websocket\r\n\r\n"
            ).encode("ascii")
            writer.write(request)
            await writer.drain()
            response = await reader.readuntil(b"\r\n\r\n")
            assert b"101 Switching Protocols" in response
            writer.write(b"frame")
            await writer.drain()
            assert await reader.readexactly(5) == b"frame"
            writer.close()
            await writer.wait_closed()
    finally:
        await gateway.stop()
        upstream.close()
        await upstream.wait_closed()

    assert captured_headers.startswith(b"GET /socket HTTP/1.1\r\n")
    assert b"Connection: Upgrade\r\n" in captured_headers
    assert b"proxy-authorization" not in captured_headers.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_request",
    [
        b"GET /origin-form HTTP/1.1\r\nHost: example.com\r\n",
        b"CONNECT [broken:443 HTTP/1.1\r\nHost: [broken:443\r\n",
        b"GET ftp://example.com/file HTTP/1.1\r\nHost: example.com\r\n",
        b"GET http://example.com/ HTTP/1.1\r\nHost: other.example\r\n",
        b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\nConnection: content-length\r\nContent-Length: 1\r\n",
        b"POST http://example.com/ HTTP/1.1\r\nHost: example.com\r\nTransfer-Encoding: chunked\r\n",
    ],
)
async def test_malformed_or_ambiguous_requests_never_resolve_or_dial(raw_request):
    resolver = RecordingResolver()
    dialer = RecordingDialer()
    gateway = EgressGateway(resolver=resolver, dialer=dialer, password="secret")
    async with gateway:
        payload = (
            raw_request
            + f"Proxy-Authorization: {_authorization(gateway.endpoint)}\r\n\r\n".encode()
        )
        response = await _exchange(gateway.endpoint, payload)

    assert response.startswith((b"HTTP/1.1 400", b"HTTP/1.1 403"))
    assert resolver.calls == []
    assert dialer.calls == []


@pytest.mark.asyncio
async def test_header_timeout_and_size_limits_are_bounded_and_zero_dial():
    resolver = RecordingResolver()
    dialer = RecordingDialer()
    limits = GatewayLimits(
        header_bytes=128,
        request_line_bytes=64,
        header_timeout=0.02,
    )
    gateway = EgressGateway(
        resolver=resolver, dialer=dialer, limits=limits, password="secret"
    )
    async with gateway:
        reader, writer = await asyncio.open_connection(
            gateway.endpoint.host, gateway.endpoint.port
        )
        timeout_response = await asyncio.wait_for(reader.read(), timeout=1)
        writer.close()
        await writer.wait_closed()
        oversized = await _exchange(gateway.endpoint, b"X" * 256 + b"\r\n\r\n")

    assert f"X-ConnectOnion-Error: {HEADER_TIMEOUT}".encode() in timeout_response
    assert f"X-ConnectOnion-Error: {HEADER_TOO_LARGE}".encode() in oversized
    assert resolver.calls == []
    assert dialer.calls == []


@pytest.mark.asyncio
async def test_dns_timeout_empty_and_answer_limit_are_zero_dial():
    async def timeout_resolver(_host, _port):
        await asyncio.Event().wait()

    for resolver in (
        timeout_resolver,
        RecordingResolver(()),
        RecordingResolver(tuple(f"8.8.8.{index}" for index in range(1, 34))),
    ):
        dialer = RecordingDialer()
        gateway = EgressGateway(
            resolver=resolver,
            dialer=dialer,
            limits=GatewayLimits(resolve_timeout=0.02),
            password="secret",
        )
        async with gateway:
            response = await _exchange(
                gateway.endpoint, _connect_request(gateway.endpoint)
            )
        assert b"502 Bad Gateway" in response
        assert dialer.calls == []


@pytest.mark.asyncio
async def test_overload_is_rejected_without_read_resolve_or_dial():
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def held_dialer(endpoint, timeout):
        calls.append((endpoint, timeout))
        entered.set()
        await release.wait()
        raise OSError("released")

    resolver = RecordingResolver()
    gateway = EgressGateway(
        resolver=resolver,
        dialer=held_dialer,
        limits=GatewayLimits(max_connections=1),
        password="secret",
    )
    try:
        async with gateway:
            first_reader, first_writer = await asyncio.open_connection(
                gateway.endpoint.host, gateway.endpoint.port
            )
            first_writer.write(_connect_request(gateway.endpoint))
            await first_writer.drain()
            await asyncio.wait_for(entered.wait(), timeout=1)
            second = await _exchange(gateway.endpoint, b"not-even-read")
            assert f"X-ConnectOnion-Error: {OVERLOADED}".encode() in second
            assert resolver.calls == [("example.com", 443)]
            assert len(calls) == 1
            release.set()
            await asyncio.wait_for(first_reader.read(), timeout=1)
            first_writer.close()
            await first_writer.wait_closed()
    finally:
        release.set()
        await gateway.stop()


@pytest.mark.asyncio
async def test_numeric_dialer_never_calls_getaddrinfo(monkeypatch):
    async def accept_then_close(_reader, writer):
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept_then_close, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    loop = asyncio.get_running_loop()

    async def forbidden_getaddrinfo(*_args, **_kwargs):
        raise AssertionError("numeric dial attempted hostname resolution")

    monkeypatch.setattr(loop, "getaddrinfo", forbidden_getaddrinfo)
    try:
        _reader, writer = await dial_numeric(
            NumericEndpoint(socket.AF_INET, "127.0.0.1", port), 1
        )
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_tunnel_byte_limit_closes_before_an_oversized_chunk_reaches_upstream():
    received = bytearray()

    async def collect(reader, writer):
        received.extend(await reader.read())
        writer.close()
        await writer.wait_closed()

    upstream = await asyncio.start_server(collect, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    gateway = EgressGateway(
        resolver=RecordingResolver(),
        dialer=RecordingDialer(port),
        limits=GatewayLimits(bytes_per_direction=4),
        password="secret",
    )
    try:
        async with gateway:
            reader, writer = await asyncio.open_connection(
                gateway.endpoint.host, gateway.endpoint.port
            )
            writer.write(_connect_request(gateway.endpoint))
            await writer.drain()
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"12345")
            await writer.drain()
            assert await asyncio.wait_for(reader.read(), timeout=1) == b""
            writer.close()
            await writer.wait_closed()
    finally:
        await gateway.stop()
        upstream.close()
        await upstream.wait_closed()

    assert received == b""


@pytest.mark.asyncio
async def test_stopping_during_resolution_cancels_owned_work_without_dialing():
    resolver_entered = asyncio.Event()
    resolver_cancelled = asyncio.Event()

    async def held_resolver(_host, _port):
        resolver_entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            resolver_cancelled.set()

    dialer = RecordingDialer()
    gateway = EgressGateway(resolver=held_resolver, dialer=dialer, password="secret")
    await gateway.start()
    reader, writer = await asyncio.open_connection(
        gateway.endpoint.host, gateway.endpoint.port
    )
    writer.write(_connect_request(gateway.endpoint))
    await writer.drain()
    await asyncio.wait_for(resolver_entered.wait(), timeout=1)

    await asyncio.wait_for(gateway.stop(), timeout=1)

    assert await asyncio.wait_for(reader.read(), timeout=1) == b""
    assert resolver_cancelled.is_set()
    assert dialer.calls == []
    assert gateway._active == 0
    assert gateway._client_tasks == set()
    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_refusal_response_never_echoes_target_or_header_secrets():
    gateway = EgressGateway(password="proxy-secret")
    async with gateway:
        request = (
            "GET http://localhost/private/customer?token=url-secret HTTP/1.1\r\n"
            "Host: localhost\r\n"
            f"Proxy-Authorization: {_authorization(gateway.endpoint)}\r\n"
            "Cookie: cookie-secret\r\n\r\n"
        ).encode("ascii")
        response = await _exchange(gateway.endpoint, request)

    assert b"403 Forbidden" in response
    for secret in (
        b"localhost",
        b"customer",
        b"url-secret",
        b"cookie-secret",
        b"proxy-secret",
    ):
        assert secret not in response


@pytest.mark.asyncio
async def test_gateway_refusals_do_not_retain_parser_dns_or_body_payloads():
    reader = asyncio.StreamReader(limit=64)
    reader.feed_data(b"secret-incomplete-header")
    reader.feed_eof()
    gateway = EgressGateway(password="secret")

    with pytest.raises(GatewayRefusal) as header_refusal:
        await gateway._read_request(reader)
    assert header_refusal.value.__context__ is None
    assert b"secret" not in repr(header_refusal.value).encode()

    async def failed_resolver(_host, _port):
        raise OSError("secret-dns-payload")

    gateway = EgressGateway(resolver=failed_resolver, password="secret")
    authority = normalize_web_destination("https://example.com/")
    with pytest.raises(GatewayRefusal) as dns_refusal:
        await gateway._approved_endpoints(authority)
    assert dns_refusal.value.__context__ is None
    assert "secret-dns" not in repr(dns_refusal.value)

    body_reader = asyncio.StreamReader()
    body_reader.feed_data(b"secret-partial-body")
    body_reader.feed_eof()
    with pytest.raises(GatewayRefusal) as body_refusal:
        await gateway._read_exactly(body_reader, 100)
    assert body_refusal.value.__context__ is None
    assert "secret-partial" not in repr(body_refusal.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        (socket.AF_INET, "example.com", 443),
        (socket.AF_INET6, "8.8.8.8", 443),
        (socket.AF_INET, "127.1", 443),
        (socket.AF_INET, "8.8.8.8", 0),
    ],
)
def test_numeric_endpoint_rejects_every_nonnumeric_or_noncanonical_form(endpoint):
    with pytest.raises(ValueError):
        NumericEndpoint(*endpoint)


def test_invalid_limits_credentials_and_operator_policy_fail_at_construction():
    with pytest.raises(ValueError):
        GatewayLimits(max_connections=0)
    with pytest.raises(ValueError):
        GatewayLimits(idle_timeout=float("nan"))
    with pytest.raises(ValueError):
        GatewayLimits(header_count=1.5)
    with pytest.raises(ValueError):
        EgressGateway(username="bad:name")
    with pytest.raises(ValueError):
        EgressGateway(password="")
    with pytest.raises(ValueError):
        EgressGateway(username=1)
    with pytest.raises(ValueError):
        EgressGateway(allowed_ports={True})
    with pytest.raises(ValueError):
        EgressGateway(deny_networks={"not-a-network"})

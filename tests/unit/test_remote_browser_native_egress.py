"""Unit contracts for the effective native egress preflight."""

import asyncio

import pytest

from connectonion.useful_tools.browser_tools.native_egress import (
    NativeEgressPreflightError,
    run_native_egress_preflight,
)


class FakeResponse:
    def __init__(self, status=403, witness="DESTINATION_HOST_DENIED"):
        self.status = status
        # The real gateway stamps this on every refusal, and it is what the
        # preflight matches on. A fake that omits it models a response no
        # gateway produces.
        self.headers = {"x-connectonion-error": witness} if witness else {}


class FakeGateway:
    """Counts decisions the way EgressGateway does, for the positive control."""

    def __init__(self, per_probe=1):
        self.handled_requests = 0
        self.per_probe = per_probe

    def saw_request(self):
        self.handled_requests += 1


class FakePage:
    def __init__(self, *, status=403, witness_status=403, error=None,
                 witness=True, gateway=None, evaluate_hits=1):
        self.status = status
        self.witness_status = witness_status
        self.error = error
        self.witness = witness
        self.gateway = gateway
        self.evaluate_hits = evaluate_hits
        self.calls = []
        self.closed = False

    async def goto(self, url, **options):
        self.calls.append(("goto", url, options))
        if self.error is not None:
            raise self.error
        if self.gateway is not None:
            self.gateway.saw_request()
        status = self.witness_status if url.endswith(".invalid/") else self.status
        code = "DESTINATION_HOST_DENIED" if self.witness else None
        return FakeResponse(status, code)

    async def set_content(self, html):
        self.calls.append(("set_content", html))

    async def evaluate(self, script, origin):
        self.calls.append(("evaluate", script, origin))
        # A real subresource probe reaches the gateway; a neutered one does not,
        # and that difference is what the positive control detects.
        if self.gateway is not None:
            for _ in range(self.evaluate_hits):
                self.gateway.saw_request()

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page


def sentinel_factory(*, connections=0, byte_count=0):
    class FakeSentinel:
        origin = "http://127.0.0.1:43123"
        accepted_connections = connections
        accepted_bytes = byte_count

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

    return FakeSentinel


@pytest.mark.asyncio
async def test_preflight_requires_gateway_403_and_exercises_native_paths():
    page = FakePage()
    context = FakeContext(page)

    await run_native_egress_preflight(
        "remote-egress-v1",
        context,
        sentinel_factory=sentinel_factory(),
    )

    assert page.calls[0][0] == "goto"
    assert page.calls[0][1] == "http://remote-browser-preflight.invalid/"
    assert page.calls[1][1].endswith("/main-frame")
    assert [call[0] for call in page.calls] == [
        "goto",
        "goto",
        "set_content",
        "evaluate",
    ]
    assert page.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "connections", "byte_count"),
    ((204, 1, 20), (407, 0, 0), (502, 0, 0), (403, 1, 0)),
)
async def test_preflight_fails_closed_for_direct_auth_or_gateway_uncertainty(
    status, connections, byte_count
):
    page = FakePage(status=status)

    with pytest.raises(
        NativeEgressPreflightError,
        match="^EGRESS_PREFLIGHT_FAILED: native browser egress boundary could not be proven$",
    ):
        await run_native_egress_preflight(
            "remote-egress-v1",
            FakeContext(page),
            sentinel_factory=sentinel_factory(
                connections=connections,
                byte_count=byte_count,
            ),
        )

    assert page.closed is True


@pytest.mark.asyncio
async def test_preflight_requires_the_gateway_dns_witness():
    page = FakePage(witness_status=407)

    with pytest.raises(NativeEgressPreflightError, match="EGRESS_PREFLIGHT_FAILED"):
        await run_native_egress_preflight(
            "remote-egress-v1",
            FakeContext(page),
            sentinel_factory=sentinel_factory(),
        )

    assert len(page.calls) == 1


@pytest.mark.asyncio
async def test_preflight_collapses_internal_errors_without_leaking_details():
    page = FakePage(error=RuntimeError("proxy-password=never-print-this"))

    with pytest.raises(NativeEgressPreflightError) as raised:
        await run_native_egress_preflight(
            "remote-egress-v1",
            FakeContext(page),
            sentinel_factory=sentinel_factory(),
        )

    assert str(raised.value) == (
        "EGRESS_PREFLIGHT_FAILED: native browser egress boundary could not be proven"
    )
    assert "password" not in str(raised.value)
    assert page.closed is True


@pytest.mark.asyncio
async def test_preflight_preserves_cancellation_and_closes_probe_page():
    page = FakePage(error=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await run_native_egress_preflight(
            "remote-egress-v1",
            FakeContext(page),
            sentinel_factory=sentinel_factory(),
        )

    assert page.closed is True


@pytest.mark.asyncio
async def test_unknown_preflight_version_fails_closed_before_opening_a_page():
    page = FakePage()

    with pytest.raises(NativeEgressPreflightError, match="EGRESS_PREFLIGHT_FAILED"):
        await run_native_egress_preflight(
            "remote-egress-v2",
            FakeContext(page),
            sentinel_factory=sentinel_factory(),
        )

    assert page.calls == []


@pytest.mark.asyncio
async def test_a_subresource_probe_that_does_nothing_fails_the_preflight():
    """Absence is only evidence once the thing that makes presence has run.

    The subresource probes swallow their own errors inside a bounded race, so
    a probe that silently no-ops leaves exactly the zero-socket reading that a
    correctly proxied probe leaves. Neutering the probe must be detectable.
    """
    gateway = FakeGateway()
    # evaluate_hits=0 models a probe that ran but reached nothing: a wrong URL,
    # a blocked API, an await that resolved on the timer.
    page = FakePage(gateway=gateway, evaluate_hits=0)
    context = FakeContext(page)

    with pytest.raises(NativeEgressPreflightError, match="EGRESS_PREFLIGHT_FAILED"):
        await run_native_egress_preflight(
            "remote-egress-v1",
            context,
            sentinel_factory=sentinel_factory(),
            gateway=gateway,
        )


@pytest.mark.asyncio
async def test_a_response_without_the_gateway_witness_fails_the_preflight():
    """A 403 from something other than this gateway proves nothing."""
    gateway = FakeGateway()
    page = FakePage(gateway=gateway, witness=False)
    context = FakeContext(page)

    with pytest.raises(NativeEgressPreflightError, match="EGRESS_PREFLIGHT_FAILED"):
        await run_native_egress_preflight(
            "remote-egress-v1",
            context,
            sentinel_factory=sentinel_factory(),
            gateway=gateway,
        )


@pytest.mark.asyncio
async def test_the_preflight_passes_when_every_probe_reaches_the_gateway():
    """The positive case, so the tests above prove a difference, not a floor."""
    gateway = FakeGateway()
    page = FakePage(gateway=gateway, evaluate_hits=4)
    context = FakeContext(page)

    await run_native_egress_preflight(
        "remote-egress-v1",
        context,
        sentinel_factory=sentinel_factory(),
        gateway=gateway,
    )
    assert gateway.handled_requests >= 6

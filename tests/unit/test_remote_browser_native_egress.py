"""Unit contracts for the effective native egress preflight."""

import asyncio

import pytest

from connectonion.useful_tools.browser_tools.native_egress import (
    NativeEgressPreflightError,
    run_native_egress_preflight,
)


class FakeResponse:
    def __init__(self, status=403):
        self.status = status


class FakePage:
    def __init__(self, *, status=403, witness_status=502, error=None):
        self.status = status
        self.witness_status = witness_status
        self.error = error
        self.calls = []
        self.closed = False

    async def goto(self, url, **options):
        self.calls.append(("goto", url, options))
        if self.error is not None:
            raise self.error
        status = self.witness_status if url.endswith(".invalid/") else self.status
        return FakeResponse(status)

    async def set_content(self, html):
        self.calls.append(("set_content", html))

    async def evaluate(self, script, origin):
        self.calls.append(("evaluate", script, origin))

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

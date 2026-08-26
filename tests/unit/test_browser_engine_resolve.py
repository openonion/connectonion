from types import SimpleNamespace

import pytest

from connectonion.useful_tools.browser_tools import engine


def ready_resolution():
    prepared = SimpleNamespace(
        ready=True,
        capability=SimpleNamespace(
            reason="ready",
            next_action="start",
            artifact=SimpleNamespace(artifact_id="chrome/150/linux-x86_64.tar.zst"),
        ),
    )
    client = SimpleNamespace(
        client_version=engine.MIN_ONIONWRIGHT_VERSION,
        prepare=lambda revision: prepared,
    )
    return engine.resolve(
        engine.ONION,
        token_loader=lambda: "token",
        client_factory=lambda token, home: client,
    )


def test_launch_passes_the_same_prepared_result_to_onionwright(monkeypatch):
    result = ready_resolution()
    calls = []

    def fake_launch(playwright, client, revision, key, **kwargs):
        calls.append((playwright, client, revision, key, kwargs))
        return "paid-run"

    monkeypatch.setitem(
        __import__("sys").modules,
        "onionwright",
        SimpleNamespace(launch_paid=fake_launch),
    )
    launched = engine.launch(
        result,
        "playwright",
        "stable-idempotency-key",
        user_data_dir=True,
        headless=True,
    )
    assert launched == "paid-run"
    assert calls == [(
        "playwright",
        result.client,
        engine.BROWSER_REVISION,
        "stable-idempotency-key",
        {"prepared": result.prepared, "user_data_dir": True, "headless": True},
    )]


@pytest.mark.asyncio
async def test_async_launch_passes_same_prepared_result_to_onionwright(monkeypatch):
    result = ready_resolution()
    calls = []

    async def fake_launch(playwright, client, revision, key, **kwargs):
        calls.append((playwright, client, revision, key, kwargs))
        return "async-paid-run"

    monkeypatch.setitem(
        __import__("sys").modules,
        "onionwright",
        SimpleNamespace(launch_paid_async=fake_launch),
    )
    launched = await engine.launch_async(
        result,
        "async-playwright",
        "stable-idempotency-key",
        user_data_dir=True,
        headless=True,
    )
    assert launched == "async-paid-run"
    assert calls == [(
        "async-playwright",
        result.client,
        engine.BROWSER_REVISION,
        "stable-idempotency-key",
        {"prepared": result.prepared, "user_data_dir": True, "headless": True},
    )]


def test_system_resolution_cannot_cross_the_billing_boundary():
    result = engine.resolve(engine.SYSTEM)
    with pytest.raises(engine.BrowserEngineError):
        engine.launch(result, "playwright", "key")


def test_client_constructor_import_failure_is_auto_fallback():
    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: "token",
        client_factory=lambda token, home: (_ for _ in ()).throw(
            ModuleNotFoundError("No module named 'onionwright'")
        ),
    )
    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.ONIONWRIGHT_MISSING


def test_prepare_exception_is_typed_and_explicit_onion_fails():
    class FailedClient:
        client_version = engine.MIN_ONIONWRIGHT_VERSION

        def prepare(self, revision):
            exc = RuntimeError("offline")
            exc.code = "api_unavailable"
            exc.message = "retry later"
            raise exc

    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve(
            engine.ONION,
            token_loader=lambda: "token",
            client_factory=lambda token, home: FailedClient(),
        )
    assert caught.value.reason == "api_unavailable"
    assert caught.value.next_action == "retry later"

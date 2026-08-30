from types import SimpleNamespace

import pytest

from connectonion.useful_tools.browser_tools import engine


def prepared(
    *, ready=True, reason="ready", action="start", artifact_id="chrome/150/linux"
):
    artifact = SimpleNamespace(artifact_id=artifact_id)
    capability = SimpleNamespace(reason=reason, next_action=action, artifact=artifact)
    return SimpleNamespace(ready=ready, capability=capability)


class Client:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.client_version = engine.MIN_ONIONWRIGHT_VERSION
        self.release_channel = engine.ONIONWRIGHT_RELEASE_CHANNEL

    def prepare(self, revision):
        self.calls.append(revision)
        return self.result


def test_system_resolver_does_not_invoke_paid_token_loader_or_onionwright():
    def forbidden(*args):
        pytest.fail("system mode touched the paid path")

    result = engine.resolve(
        engine.SYSTEM,
        token_loader=forbidden,
        client_factory=forbidden,
    )
    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.SYSTEM_REQUESTED
    assert not result.fallback


def test_omitted_engine_defaults_to_nonbilling_system():
    def forbidden(*args):
        pytest.fail("the omitted engine invoked its paid token loader or paid code")

    result = engine.resolve(
        token_loader=forbidden,
        client_factory=forbidden,
    )

    assert result.requested == engine.SYSTEM
    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.SYSTEM_REQUESTED


def test_auto_ready_selects_exact_prepared_onion_artifact(tmp_path):
    client = Client(prepared(artifact_id="chrome/150.0/linux-x86_64.tar.zst"))
    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: "token",
        client_factory=lambda token, home: client,
        home=tmp_path,
    )
    assert result.resolved == engine.ONION
    assert result.client is client
    assert result.artifact_id == "chrome/150.0/linux-x86_64.tar.zst"
    assert client.calls == [engine.BROWSER_REVISION]


@pytest.mark.parametrize(
    "reason",
    [
        "unsupported_platform",
        "unsupported_arch",
        "unsupported_os_version",
        "artifact_unavailable",
        "download_failed",
        "checksum_mismatch",
        "insufficient_balance",
    ],
)
def test_auto_preflight_failure_falls_back_before_billing(reason, tmp_path):
    client = Client(prepared(ready=False, reason=reason, action="use system"))
    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: "token",
        client_factory=lambda token, home: client,
        home=tmp_path,
    )
    assert result.resolved == engine.SYSTEM
    assert result.fallback
    assert result.reason == reason
    assert result.client is None


def test_explicit_onion_never_falls_back(tmp_path):
    client = Client(
        prepared(ready=False, reason="insufficient_balance", action="top up")
    )
    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve(
            engine.ONION,
            token_loader=lambda: "token",
            client_factory=lambda token, home: client,
            home=tmp_path,
        )
    assert caught.value.reason == "insufficient_balance"
    assert caught.value.next_action == "top up"


def test_auto_without_credentials_is_typed_system_fallback():
    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: (_ for _ in ()).throw(RuntimeError("no token")),
    )
    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.LICENSE_UNAVAILABLE


def test_invalid_mode_is_never_guessed():
    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve("default")
    assert caught.value.reason == engine.Reason.INVALID_MODE


def test_installed_old_onionwright_is_typed_incompatible_before_preflight():
    client = Client(prepared())
    client.client_version = "0.0.10"
    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: "token",
        client_factory=lambda token, home: client,
    )
    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.ONIONWRIGHT_INCOMPATIBLE
    assert client.calls == []


@pytest.mark.parametrize(
    "version", ["0.0.13.dev1", "0.0.13.dev2", "0.0.13", "0.0.14"]
)
def test_a_different_version_is_not_preview_compatible(version):
    client = Client(prepared())
    client.client_version = version

    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: "token",
        client_factory=lambda token, home: client,
    )

    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.ONIONWRIGHT_INCOMPATIBLE
    assert client.calls == []


def test_a_production_channel_client_is_rejected_before_preflight():
    client = Client(prepared())
    client.release_channel = "production"

    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: "token",
        client_factory=lambda token, home: client,
    )

    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.ONIONWRIGHT_INCOMPATIBLE
    assert client.calls == []


def test_installed_sync_only_onionwright_is_rejected_before_client_or_preflight(
    monkeypatch,
):
    constructed = []

    def paid_client(**kwargs):
        constructed.append(kwargs)
        return Client(prepared())

    monkeypatch.setitem(
        __import__("sys").modules,
        "onionwright",
        SimpleNamespace(PaidSessionClient=paid_client),
    )
    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: "token",
    )
    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.ONIONWRIGHT_INCOMPATIBLE
    assert constructed == []


def test_default_client_binds_exact_preview_origin_and_channel(monkeypatch, tmp_path):
    constructed = []

    def paid_client(**kwargs):
        constructed.append(kwargs)
        return Client(prepared())

    monkeypatch.setenv("OO_API_URL", "https://production-override.invalid")
    monkeypatch.setattr(engine, "api_url", lambda: "https://preview.test")
    monkeypatch.setitem(
        __import__("sys").modules,
        "onionwright",
        SimpleNamespace(
            PaidSessionClient=paid_client,
            launch_paid_async=lambda *args, **kwargs: None,
        ),
    )

    client = engine._default_client("token", tmp_path)

    assert isinstance(client, Client)
    assert constructed == [
        {
            "token": "token",
            "home": tmp_path,
            "api": "https://preview.test",
            "release_channel": "preview",
        }
    ]


def test_public_status_contains_no_client_token_or_local_path(tmp_path):
    client = Client(prepared())
    result = engine.resolve(
        engine.AUTO,
        token_loader=lambda: "super-secret",
        client_factory=lambda token, home: client,
        home=tmp_path,
    )
    status = result.public_status()
    assert status["resolved_engine"] == engine.ONION
    assert status["onionwright_version"] == engine.MIN_ONIONWRIGHT_VERSION
    assert status["release_channel"] == engine.ONIONWRIGHT_RELEASE_CHANNEL
    assert "super-secret" not in repr(status)
    assert str(tmp_path) not in repr(status)


@pytest.mark.parametrize("wire_price", ["0.025", 0.025])
def test_public_status_normalizes_the_real_onionwright_interval_price(wire_price):
    paid = prepared()
    paid.capability.interval_usd = wire_price
    result = engine.Resolution(
        requested=engine.AUTO,
        resolved=engine.ONION,
        reason=engine.Reason.ONION_READY,
        next_action="start",
        prepared=paid,
    )

    assert result.interval_usd == 0.025
    assert result.public_status()["interval_usd"] == 0.025


@pytest.mark.parametrize(
    "wire_price",
    [None, True, 0, -0.025, float("nan"), float("inf"), " 0.025", "2.5e-2"],
)
def test_public_status_rejects_noncanonical_or_unsafe_interval_prices(wire_price):
    paid = prepared()
    paid.capability.interval_usd = wire_price
    result = engine.Resolution(
        requested=engine.ONION,
        resolved=engine.ONION,
        reason=engine.Reason.ONION_READY,
        next_action="start",
        prepared=paid,
    )

    assert result.interval_usd is None

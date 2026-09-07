from types import SimpleNamespace

import pytest

from connectonion.useful_tools.browser_tools import engine


def prepared(*, ready=True, reason="ready", action="start", artifact_id="chrome/150/linux"):
    artifact = SimpleNamespace(artifact_id=artifact_id)
    capability = SimpleNamespace(reason=reason, next_action=action, artifact=artifact)
    return SimpleNamespace(ready=ready, capability=capability)


class Client:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.client_version = engine.MIN_ONIONWRIGHT_VERSION

    def prepare(self, revision):
        self.calls.append(revision)
        return self.result


def test_system_returns_before_token_or_onionwright():
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


def test_explicit_onion_selects_exact_prepared_artifact(tmp_path):
    client = Client(prepared(artifact_id="chrome/150.0/linux-x86_64.tar.zst"))
    result = engine.resolve(
        engine.ONION,
        token_loader=lambda: "token",
        client_factory=lambda token, home: client,
        home=tmp_path,
    )
    assert result.resolved == engine.ONION
    assert result.client is client
    assert result.artifact_id == "chrome/150.0/linux-x86_64.tar.zst"
    assert client.calls == [engine.BROWSER_REVISION]


def test_default_engine_cannot_reach_the_paid_path_even_when_it_would_succeed(tmp_path):
    """The default must not spend money on a machine that merely could.

    A ready paid client is offered and must go untouched: `auto` is what every
    ordinary `co browser ...` sends, and it resolves to system Chrome without
    a token, an Onionwright import, or a preflight call.
    """
    def forbidden(*args):
        pytest.fail("the default engine touched the paid path")

    result = engine.resolve(
        engine.AUTO,
        token_loader=forbidden,
        client_factory=forbidden,
        home=tmp_path,
    )
    assert result.resolved == engine.SYSTEM
    assert result.reason == engine.Reason.SYSTEM_DEFAULT
    assert result.client is None
    assert result.interval_usd is None
    assert not result.fallback


@pytest.mark.parametrize("reason", [
    "unsupported_platform",
    "unsupported_arch",
    "unsupported_os_version",
    "artifact_unavailable",
    "download_failed",
    "checksum_mismatch",
    "insufficient_balance",
])
def test_explicit_onion_preflight_failure_is_typed_before_billing(reason, tmp_path):
    client = Client(prepared(ready=False, reason=reason, action="use system"))
    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve(
            engine.ONION,
            token_loader=lambda: "token",
            client_factory=lambda token, home: client,
            home=tmp_path,
        )
    assert caught.value.reason == reason


def test_explicit_onion_never_falls_back(tmp_path):
    client = Client(prepared(ready=False, reason="insufficient_balance", action="top up"))
    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve(
            engine.ONION,
            token_loader=lambda: "token",
            client_factory=lambda token, home: client,
            home=tmp_path,
        )
    assert caught.value.reason == "insufficient_balance"
    assert caught.value.next_action == "top up"


def test_explicit_onion_without_credentials_is_typed_and_explicit():
    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve(
            engine.ONION,
            token_loader=lambda: (_ for _ in ()).throw(RuntimeError("no token")),
        )
    assert caught.value.reason == engine.Reason.LICENSE_UNAVAILABLE


def test_invalid_mode_is_never_guessed():
    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve("default")
    assert caught.value.reason == engine.Reason.INVALID_MODE


def test_installed_old_onionwright_is_typed_incompatible_before_preflight():
    client = Client(prepared())
    client.client_version = "0.0.10"
    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve(
            engine.ONION,
            token_loader=lambda: "token",
            client_factory=lambda token, home: client,
        )
    assert caught.value.reason == engine.Reason.ONIONWRIGHT_INCOMPATIBLE
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
    with pytest.raises(engine.BrowserEngineError) as caught:
        engine.resolve(
            engine.ONION,
            token_loader=lambda: "token",
        )
    assert caught.value.reason == engine.Reason.ONIONWRIGHT_INCOMPATIBLE
    assert constructed == []


def test_public_status_contains_no_client_token_or_local_path(tmp_path):
    client = Client(prepared())
    result = engine.resolve(
        engine.ONION,
        token_loader=lambda: "super-secret",
        client_factory=lambda token, home: client,
        home=tmp_path,
    )
    status = result.public_status()
    assert status["resolved_engine"] == engine.ONION
    assert status["onionwright_version"] == engine.MIN_ONIONWRIGHT_VERSION
    assert "super-secret" not in repr(status)
    assert str(tmp_path) not in repr(status)

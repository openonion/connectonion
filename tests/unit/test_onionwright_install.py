import hashlib
import json
import time
from types import SimpleNamespace

import pytest
from nacl.signing import SigningKey

from connectonion.cli.commands import browser_commands
from connectonion.cli.commands import onionwright_install as installer
from connectonion.credentials import MissingAmbientAPIKey


class _Response:
    def __init__(self, *, status_code=200, json_body=None, chunks=()):
        self.status_code = status_code
        self._json_body = json_body
        self._chunks = list(chunks)
        self.closed = False

    def json(self):
        if isinstance(self._json_body, Exception):
            raise self._json_body
        return self._json_body

    def iter_content(self, chunk_size):
        assert chunk_size == 1024 * 1024
        yield from self._chunks

    def close(self):
        self.closed = True


MANIFEST_NOW = 1_800_000_000


def _signed_document(signing_key, document, *, canonical=True):
    if canonical:
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    else:
        payload = json.dumps(document).encode("utf-8")
    return {
        "payload": payload.hex(),
        "signature": signing_key.sign(payload).signature.hex(),
    }


def _signed_manifest(
    signing_key,
    wheel,
    *,
    channel="preview",
    issued_at=None,
    canonical=True,
    artifacts=None,
    **changes,
):
    digest = hashlib.sha256(wheel).hexdigest()
    issued_at = int(time.time()) if issued_at is None else issued_at
    document = {
        "v": installer.MANIFEST_VERSION,
        "purpose": installer.MANIFEST_PURPOSE,
        "product": installer.MANIFEST_PRODUCT,
        "issued_at": issued_at,
        "expires_at": issued_at + installer.MANIFEST_LIFETIME_SECONDS,
        "artifacts": (
            {installer.ONIONWRIGHT_ARTIFACT: digest}
            if artifacts is None
            else artifacts
        ),
        "channel": channel,
        **changes,
    }
    return _signed_document(
        signing_key, document, canonical=canonical
    ), digest


def test_already_compatible_does_not_read_credentials_or_touch_network(monkeypatch):
    monkeypatch.setattr(
        installer, "_installed_version", lambda: installer.ONIONWRIGHT_VERSION
    )
    monkeypatch.setattr(
        installer,
        "require_ambient_api_key",
        lambda: (_ for _ in ()).throw(AssertionError("read credentials")),
    )
    monkeypatch.setattr(
        installer.requests,
        "request",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )

    result = installer.install_onionwright()

    assert result == installer.InstallResult(
        version=installer.ONIONWRIGHT_VERSION, already_installed=True
    )


@pytest.mark.parametrize(
    "version",
    [
        None,
        "0.0.12",
        "0.0.13.dev1",
        "0.0.13.dev2",
        "0.0.13",
        "0.0.14",
        "invalid",
    ],
)
def test_only_the_exact_preview_client_is_compatible(version):
    assert installer._is_compatible(version) is False


def test_signed_wheel_is_verified_before_exact_current_python_pip(monkeypatch):
    wheel = b"real private wheel bytes"
    signing_key = SigningKey.generate()
    signed, digest = _signed_manifest(signing_key, wheel)
    manifest_response = _Response(json_body=signed)
    grant_response = _Response(
        json_body={
            "url": "https://downloads.test/signed-wheel",
            "sha256": digest,
        }
    )
    wheel_response = _Response(chunks=[wheel[:7], b"", wheel[7:]])
    requests_seen = []
    installed_versions = iter([None, installer.ONIONWRIGHT_VERSION])
    pip_calls = []

    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )
    monkeypatch.setattr(
        installer, "_installed_version", lambda: next(installed_versions)
    )
    monkeypatch.setattr(installer, "require_ambient_api_key", lambda: "secret-token")
    monkeypatch.setattr(installer, "api_url", lambda: "https://api.test")

    def request(method, url, **kwargs):
        requests_seen.append((method, url, kwargs))
        return manifest_response if method == "get" else grant_response

    monkeypatch.setattr(installer.requests, "request", request)
    monkeypatch.setattr(
        installer.requests,
        "get",
        lambda url, **kwargs: wheel_response,
    )

    def run(command, check):
        assert check is False
        wheel_path = command[-1]
        assert installer.Path(wheel_path).read_bytes() == wheel
        pip_calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installer.subprocess, "run", run)

    result = installer.install_onionwright()

    assert result == installer.InstallResult(
        version=installer.ONIONWRIGHT_VERSION, already_installed=False
    )
    assert requests_seen == [
        (
            "get",
            "https://api.test/api/v1/license/manifest",
            {
                "timeout": installer.REQUEST_TIMEOUT,
                "allow_redirects": False,
                "headers": {"Authorization": "Bearer secret-token"},
            },
        ),
        (
            "post",
            "https://api.test/api/v1/license/download",
            {
                "timeout": installer.REQUEST_TIMEOUT,
                "allow_redirects": False,
                "headers": {"Authorization": "Bearer secret-token"},
                "json": {"artifact": installer.ONIONWRIGHT_ARTIFACT},
            },
        ),
    ]
    assert pip_calls[0][0:5] == [
        installer.sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
    ]
    assert "--disable-pip-version-check" in pip_calls[0]
    assert wheel_response.closed


def test_bad_manifest_signature_stops_before_download_or_pip(monkeypatch):
    signing_key = SigningKey.generate()
    signed, _digest = _signed_manifest(signing_key, b"wheel")
    signed["signature"] = (b"x" * 64).hex()

    monkeypatch.setattr(installer, "_installed_version", lambda: None)
    monkeypatch.setattr(installer, "require_ambient_api_key", lambda: "token")
    monkeypatch.setattr(installer, "api_url", lambda: "https://api.test")
    monkeypatch.setattr(
        installer.requests,
        "request",
        lambda *args, **kwargs: _Response(json_body=signed),
    )
    monkeypatch.setattr(
        installer.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("downloaded")),
    )
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ran pip")),
    )

    with pytest.raises(installer.OnionwrightInstallError, match="signature or schema"):
        installer.install_onionwright()


@pytest.mark.parametrize("channel", ["production", "staging", ""])
def test_nonpreview_manifest_stops_before_download_or_pip(monkeypatch, channel):
    signing_key = SigningKey.generate()
    signed, _digest = _signed_manifest(signing_key, b"wheel", channel=channel)

    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )
    monkeypatch.setattr(installer, "_installed_version", lambda: None)
    monkeypatch.setattr(installer, "require_ambient_api_key", lambda: "token")
    monkeypatch.setattr(installer, "api_url", lambda: "https://api.test")
    monkeypatch.setattr(
        installer.requests,
        "request",
        lambda *args, **kwargs: _Response(json_body=signed),
    )
    monkeypatch.setattr(
        installer.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("downloaded")),
    )
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ran pip")),
    )

    with pytest.raises(installer.OnionwrightInstallError, match="signature or schema"):
        installer.install_onionwright()


def test_preview_bootstrap_accepts_only_the_fresh_exact_v2_contract(monkeypatch):
    signing_key = SigningKey.generate()
    signed, digest = _signed_manifest(
        signing_key, b"wheel", issued_at=MANIFEST_NOW
    )
    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )

    assert installer._verified_manifest_digest(
        signed, clock=lambda: MANIFEST_NOW + 1
    ) == digest


@pytest.mark.parametrize(
    "changes",
    [
        {"v": True},
        {"v": 1},
        {"v": "2"},
        {"purpose": "browser-paid-manifest"},
        {"product": "onion-browser"},
        {"issued_at": True},
        {"issued_at": str(MANIFEST_NOW)},
        {"expires_at": float(MANIFEST_NOW + 900)},
        {"expires_at": MANIFEST_NOW + 899},
        {"expires_at": MANIFEST_NOW + 901},
        {"artifacts": {}},
        {"artifacts": []},
        {"artifacts": {installer.ONIONWRIGHT_ARTIFACT: "A" * 64}},
        {"artifacts": {installer.ONIONWRIGHT_ARTIFACT: "a" * 63}},
        {"artifacts": {"onionwright/other.whl": "a" * 64}},
    ],
)
def test_preview_bootstrap_rejects_other_signed_protocol_shapes(
    monkeypatch, changes
):
    signing_key = SigningKey.generate()
    valid, _digest = _signed_manifest(
        signing_key, b"wheel", issued_at=MANIFEST_NOW
    )
    document = json.loads(bytes.fromhex(valid["payload"]))
    document.update(changes)
    signed = _signed_document(signing_key, document)
    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )

    with pytest.raises(installer.OnionwrightInstallError, match="signature or schema"):
        installer._verified_manifest_digest(
            signed, clock=lambda: MANIFEST_NOW + 1
        )


@pytest.mark.parametrize(
    ("issued_at", "now", "accepted"),
    [
        (MANIFEST_NOW + 60, MANIFEST_NOW, True),
        (MANIFEST_NOW + 61, MANIFEST_NOW, False),
        (MANIFEST_NOW, MANIFEST_NOW + 899, True),
        (MANIFEST_NOW, MANIFEST_NOW + 900, False),
        (MANIFEST_NOW, MANIFEST_NOW + 901, False),
    ],
)
def test_preview_bootstrap_enforces_future_skew_and_expiry(
    monkeypatch, issued_at, now, accepted
):
    signing_key = SigningKey.generate()
    signed, digest = _signed_manifest(
        signing_key, b"wheel", issued_at=issued_at
    )
    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )

    if accepted:
        assert installer._verified_manifest_digest(
            signed, clock=lambda: now
        ) == digest
    else:
        with pytest.raises(
            installer.OnionwrightInstallError, match="signature or schema"
        ):
            installer._verified_manifest_digest(signed, clock=lambda: now)


def test_preview_bootstrap_requires_exact_signed_and_envelope_fields(monkeypatch):
    signing_key = SigningKey.generate()
    signed, digest = _signed_manifest(
        signing_key, b"wheel", issued_at=MANIFEST_NOW
    )
    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )
    document = {
        "v": installer.MANIFEST_VERSION,
        "purpose": installer.MANIFEST_PURPOSE,
        "product": installer.MANIFEST_PRODUCT,
        "issued_at": MANIFEST_NOW,
        "expires_at": MANIFEST_NOW + installer.MANIFEST_LIFETIME_SECONDS,
        "artifacts": {installer.ONIONWRIGHT_ARTIFACT: digest},
        "channel": installer.RELEASE_CHANNEL,
    }
    missing_channel = dict(document)
    missing_channel.pop("channel")

    cases = [
        {**signed, "generated_at": MANIFEST_NOW},
        {"payload": signed["payload"]},
        {**signed, "payload": signed["payload"].upper()},
        {**signed, "signature": signed["signature"].upper()},
        {**signed, "signature": signed["signature"][:-2]},
        _signed_document(signing_key, missing_channel),
        _signed_document(signing_key, {**document, "generated_at": MANIFEST_NOW}),
        [signed],
    ]
    for candidate in cases:
        with pytest.raises(
            installer.OnionwrightInstallError, match="signature or schema"
        ):
            installer._verified_manifest_digest(
                candidate, clock=lambda: MANIFEST_NOW + 1
            )


def test_preview_bootstrap_rejects_noncanonical_signed_json(monkeypatch):
    signing_key = SigningKey.generate()
    signed, _digest = _signed_manifest(
        signing_key, b"wheel", issued_at=MANIFEST_NOW, canonical=False
    )
    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )

    with pytest.raises(installer.OnionwrightInstallError, match="signature or schema"):
        installer._verified_manifest_digest(
            signed, clock=lambda: MANIFEST_NOW + 1
        )


@pytest.mark.parametrize(
    "artifact",
    [
        "",
        "/absolute/path",
        "artifact/",
        "artifact//file",
        "artifact/./file",
        "artifact/../file",
        "artifact\\file",
        ".hidden/artifact",
        "artifact:stream",
        "artifact-☃",
        "a" * 513,
    ],
)
def test_preview_bootstrap_validates_every_artifact_mapping(
    monkeypatch, artifact
):
    signing_key = SigningKey.generate()
    wheel = b"wheel"
    digest = hashlib.sha256(wheel).hexdigest()
    signed, _digest = _signed_manifest(
        signing_key,
        wheel,
        issued_at=MANIFEST_NOW,
        artifacts={
            installer.ONIONWRIGHT_ARTIFACT: digest,
            artifact: "a" * 64,
        },
    )
    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )

    with pytest.raises(installer.OnionwrightInstallError, match="signature or schema"):
        installer._verified_manifest_digest(
            signed, clock=lambda: MANIFEST_NOW + 1
        )


def test_preview_bootstrap_caps_the_decoded_signed_payload(monkeypatch):
    signing_key = SigningKey.generate()
    payload = b"x" * (installer.MAX_MANIFEST_PAYLOAD_BYTES + 1)
    signed = {
        "payload": payload.hex(),
        "signature": signing_key.sign(payload).signature.hex(),
    }
    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )

    with pytest.raises(installer.OnionwrightInstallError, match="signature or schema"):
        installer._verified_manifest_digest(signed, clock=lambda: MANIFEST_NOW)


@pytest.mark.parametrize("now", [True, "now", float("nan"), float("inf")])
def test_preview_bootstrap_rejects_an_invalid_verifier_clock(monkeypatch, now):
    signing_key = SigningKey.generate()
    signed, _digest = _signed_manifest(
        signing_key, b"wheel", issued_at=MANIFEST_NOW
    )
    monkeypatch.setattr(
        installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex()
    )

    with pytest.raises(installer.OnionwrightInstallError, match="signature or schema"):
        installer._verified_manifest_digest(signed, clock=lambda: now)


def test_download_checksum_mismatch_stops_before_pip(monkeypatch, tmp_path):
    response = _Response(chunks=[b"tampered"])
    monkeypatch.setattr(installer, "api_url", lambda: "https://api.test")
    monkeypatch.setattr(installer.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(installer.OnionwrightInstallError, match="checksum"):
        installer._download_wheel(
            "https://api.test/download",
            tmp_path / "onionwright.whl",
            hashlib.sha256(b"expected").hexdigest(),
        )

    assert response.closed


def test_download_redirect_is_refused_without_reading_body(monkeypatch, tmp_path):
    response = _Response(status_code=302, chunks=[b"never read"])
    monkeypatch.setattr(installer, "api_url", lambda: "https://api.test")

    def get(url, **kwargs):
        assert kwargs["allow_redirects"] is False
        return response

    monkeypatch.setattr(installer.requests, "get", get)

    with pytest.raises(installer.OnionwrightInstallError, match="HTTP 302"):
        installer._download_wheel(
            "https://api.test/download",
            tmp_path / "onionwright.whl",
            hashlib.sha256(b"never read").hexdigest(),
        )

    assert response.closed
    assert not (tmp_path / "onionwright.whl").exists()


@pytest.mark.parametrize(
    ("download_url", "preview_api_url"),
    [
        ("http://downloads.test/wheel", "https://preview.test"),
        ("http://downloads.test/wheel", "http://127.0.0.1:8000"),
        ("http://127.0.0.1:9000/wheel", "https://preview.test"),
        ("http://user:pass@127.0.0.1:9000/wheel", "http://127.0.0.1:8000"),
    ],
)
def test_insecure_download_is_rejected_before_network(
    monkeypatch, tmp_path, download_url, preview_api_url
):
    monkeypatch.setattr(
        installer.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )

    with pytest.raises(installer.OnionwrightInstallError, match="insecure|invalid"):
        installer._download_wheel(
            download_url,
            tmp_path / "onionwright.whl",
            hashlib.sha256(b"wheel").hexdigest(),
            preview_api_url=preview_api_url,
        )


def test_loopback_preview_may_download_from_loopback_http(monkeypatch, tmp_path):
    wheel = b"local preview wheel"
    response = _Response(chunks=[wheel])
    monkeypatch.setattr(installer.requests, "get", lambda *args, **kwargs: response)

    destination = tmp_path / "onionwright.whl"
    installer._download_wheel(
        "http://localhost:9000/wheel",
        destination,
        hashlib.sha256(wheel).hexdigest(),
        preview_api_url="http://127.0.0.1:8000",
    )

    assert destination.read_bytes() == wheel
    assert response.closed


def test_manifest_http_error_is_sanitized(monkeypatch):
    monkeypatch.setattr(
        installer.requests,
        "request",
        lambda *args, **kwargs: _Response(
            status_code=503, json_body={"detail": "secret"}
        ),
    )

    with pytest.raises(installer.OnionwrightInstallError) as raised:
        installer._request_json(
            "get",
            "https://api.test/path?token=do-not-print",
            headers={"Authorization": "Bearer do-not-print"},
        )

    assert "503" in str(raised.value)
    assert "do-not-print" not in str(raised.value)
    assert "secret" not in str(raised.value)


def test_cli_install_returns_before_contacting_browser_daemon(monkeypatch, capsys):
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("contacted daemon")
        ),
    )
    monkeypatch.setattr(
        installer,
        "install_onionwright",
        lambda: installer.InstallResult(
            version=installer.ONIONWRIGHT_VERSION, already_installed=False
        ),
    )

    assert browser_commands.handle_browser(["install-onion"]) == 0
    output = capsys.readouterr()
    assert f"Installed Onionwright {installer.ONIONWRIGHT_VERSION}" in output.out
    assert output.err == ""


def test_cli_missing_credentials_fails_before_daemon(monkeypatch, capsys):
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("contacted daemon")
        ),
    )
    monkeypatch.setattr(
        installer,
        "install_onionwright",
        lambda: (_ for _ in ()).throw(MissingAmbientAPIKey()),
    )

    assert browser_commands.handle_browser(["install-onion"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Run 'co init' or 'co auth'" in output.err


def test_cli_install_rejects_extra_arguments_without_daemon(monkeypatch, capsys):
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("contacted daemon")
        ),
    )

    assert browser_commands.handle_browser(["install-onion", "unexpected"]) == 2
    assert "usage: co browser install-onion" in capsys.readouterr().err


def test_a_manifest_signed_by_another_key_is_rejected_with_the_pin_untouched(monkeypatch):
    """The trust root must be the pinned key, not one the response supplies.

    Every other test here monkeypatches RELEASE_VERIFY_KEY_HEX to its own
    generated key, so none proves the real pin rejects an attacker's signature.
    This one signs a perfectly valid manifest with a DIFFERENT key and leaves
    the pin alone: replacing the module constant with a key read from the
    response body would make this pass, which is exactly the bypass it guards.
    """
    attacker_key = SigningKey.generate()
    assert bytes(attacker_key.verify_key).hex() != installer.RELEASE_VERIFY_KEY_HEX
    signed, _digest = _signed_manifest(attacker_key, b"wheel")

    monkeypatch.setattr(installer, "_installed_version", lambda: None)
    monkeypatch.setattr(installer, "require_ambient_api_key", lambda: "token")
    monkeypatch.setattr(installer, "api_url", lambda: "https://api.test")
    monkeypatch.setattr(
        installer.requests,
        "request",
        lambda *args, **kwargs: _Response(json_body=signed),
    )
    monkeypatch.setattr(
        installer.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("downloaded")),
    )
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ran pip")),
    )

    with pytest.raises(installer.OnionwrightInstallError, match="signature or schema"):
        installer.install_onionwright()

import hashlib
import json
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


def _signed_manifest(signing_key, wheel):
    digest = hashlib.sha256(wheel).hexdigest()
    payload = json.dumps(
        {
            "artifacts": {installer.ONIONWRIGHT_ARTIFACT: digest},
            "generated_at": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "payload": payload.hex(),
        "signature": signing_key.sign(payload).signature.hex(),
    }, digest


def test_already_compatible_does_not_read_credentials_or_touch_network(monkeypatch):
    monkeypatch.setattr(installer, "_installed_version", lambda: "0.0.13")
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

    assert result == installer.InstallResult(version="0.0.13", already_installed=True)


def test_signed_wheel_is_verified_before_exact_current_python_pip(monkeypatch):
    wheel = b"real private wheel bytes"
    signing_key = SigningKey.generate()
    signed, digest = _signed_manifest(signing_key, wheel)
    manifest_response = _Response(json_body=signed)
    grant_response = _Response(json_body={
        "url": "https://downloads.test/signed-wheel",
        "sha256": digest,
    })
    wheel_response = _Response(chunks=[wheel[:7], b"", wheel[7:]])
    requests_seen = []
    installed_versions = iter([None, "0.0.12"])
    pip_calls = []

    monkeypatch.setattr(installer, "RELEASE_VERIFY_KEY_HEX", bytes(signing_key.verify_key).hex())
    monkeypatch.setattr(installer, "_installed_version", lambda: next(installed_versions))
    monkeypatch.setattr(installer, "require_ambient_api_key", lambda: "secret-token")
    monkeypatch.setattr(installer, "backend_url", lambda: "https://api.test")

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

    assert result == installer.InstallResult(version="0.0.12", already_installed=False)
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
    monkeypatch.setattr(installer, "backend_url", lambda: "https://api.test")
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


def test_download_checksum_mismatch_stops_before_pip(monkeypatch, tmp_path):
    response = _Response(chunks=[b"tampered"])
    monkeypatch.setattr(installer, "backend_url", lambda: "https://api.test")
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
    monkeypatch.setattr(installer, "backend_url", lambda: "https://api.test")

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


def test_manifest_http_error_is_sanitized(monkeypatch):
    monkeypatch.setattr(
        installer.requests,
        "request",
        lambda *args, **kwargs: _Response(status_code=503, json_body={"detail": "secret"}),
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
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("contacted daemon")),
    )
    monkeypatch.setattr(
        installer,
        "install_onionwright",
        lambda: installer.InstallResult(version="0.0.12", already_installed=False),
    )

    assert browser_commands.handle_browser(["install-onion"]) == 0
    output = capsys.readouterr()
    assert "Installed Onionwright 0.0.12" in output.out
    assert output.err == ""


def test_cli_missing_credentials_fails_before_daemon(monkeypatch, capsys):
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("contacted daemon")),
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
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("contacted daemon")),
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
    monkeypatch.setattr(installer, "backend_url", lambda: "https://api.test")
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

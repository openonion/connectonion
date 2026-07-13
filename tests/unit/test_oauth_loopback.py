"""Socket-level tests for the single-use Microsoft OAuth loopback receiver."""

from __future__ import annotations

import socket
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from connectonion.cli.oauth_loopback import (
    MicrosoftOAuthLoopback,
    OAuthLoopbackTimeout,
)


AUTHORIZATION_ID = "a" * 43


def _wait_in_thread(listener: MicrosoftOAuthLoopback, timeout: float = 3):
    result = {}

    def wait() -> None:
        try:
            result["value"] = listener.wait_for_result(
                AUTHORIZATION_ID,
                timeout=timeout,
            )
        except BaseException as exc:  # make thread failures visible to pytest
            result["error"] = exc

    thread = Thread(target=wait)
    thread.start()
    return thread, result


def _get(url: str, host: str | None = None):
    request = Request(url, headers={"Host": host} if host else {})
    return urlopen(request, timeout=2)


def test_loopback_rejects_probes_then_accepts_exact_correlated_code(capsys):
    code = "one-use-code+/=?"
    with MicrosoftOAuthLoopback() as listener:
        thread, outcome = _wait_in_thread(listener)

        bad_urls = [
            listener.callback_uri.replace(
                "/oauth/microsoft/callback",
                "/wrong-path",
            )
            + "?"
            + urlencode({"authorization_id": AUTHORIZATION_ID, "code": code}),
            listener.callback_uri
            + "?"
            + urlencode({"authorization_id": "wrong-state", "code": code}),
            listener.callback_uri
            + "?authorization_id="
            + AUTHORIZATION_ID
            + "&authorization_id=duplicate&code=secret",
            listener.callback_uri
            + "?"
            + urlencode({"authorization_id": "é" * 43, "code": code}),
        ]
        for url in bad_urls:
            with pytest.raises(HTTPError) as exc_info:
                _get(url)
            assert exc_info.value.code == 400

        with pytest.raises(HTTPError) as exc_info:
            _get(
                listener.callback_uri
                + "?"
                + urlencode({"authorization_id": AUTHORIZATION_ID, "code": code}),
                host="evil.example",
            )
        assert exc_info.value.code == 400

        response = _get(
            listener.callback_uri
            + "?"
            + urlencode({"authorization_id": AUTHORIZATION_ID, "code": code})
        )
        page = response.read().decode()
        assert response.status == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        assert code not in page
        assert AUTHORIZATION_ID not in page

        thread.join(3)
        assert not thread.is_alive()
        assert "error" not in outcome
        assert outcome["value"].code == code
        assert outcome["value"].error is None
        captured = capsys.readouterr()
        assert code not in captured.out
        assert "Traceback" not in captured.err


def test_loopback_returns_sanitized_authorization_error():
    with MicrosoftOAuthLoopback() as listener:
        thread, outcome = _wait_in_thread(listener)
        response = _get(
            listener.callback_uri
            + "?"
            + urlencode(
                {
                    "authorization_id": AUTHORIZATION_ID,
                    "error": "authorization_failed",
                }
            )
        )
        assert response.status == 200
        assert "not completed" in response.read().decode()

        thread.join(3)
        assert "error" not in outcome
        assert outcome["value"].code is None
        assert outcome["value"].error == "authorization_failed"


def test_loopback_timeout_and_context_close_the_port():
    listener = MicrosoftOAuthLoopback()
    port = listener.port
    with pytest.raises(OAuthLoopbackTimeout):
        listener.wait_for_result(AUTHORIZATION_ID, timeout=0.05)
    listener.close()

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.5)
        assert probe.connect_ex(("127.0.0.1", port)) != 0
    finally:
        probe.close()


@pytest.mark.parametrize("timeout", [0, -1])
def test_loopback_rejects_nonpositive_timeout(timeout):
    with MicrosoftOAuthLoopback() as listener:
        with pytest.raises(ValueError, match="timeout must be positive"):
            listener.wait_for_result(AUTHORIZATION_ID, timeout=timeout)


@pytest.mark.parametrize(
    "authorization_id",
    ["", "a" * 31, "é" * 43, "a" * 42 + "!"],
)
def test_loopback_rejects_invalid_authorization_id(authorization_id):
    with MicrosoftOAuthLoopback() as listener:
        with pytest.raises(ValueError, match="authorization_id is invalid"):
            listener.wait_for_result(authorization_id, timeout=0.05)

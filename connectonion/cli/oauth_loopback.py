"""Small, single-use loopback receiver for browser OAuth completion."""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlsplit


MICROSOFT_CALLBACK_PATH = "/oauth/microsoft/callback"
_MIN_AUTHORIZATION_ID_LENGTH = 32
_MAX_AUTHORIZATION_ID_LENGTH = 128
_MAX_AUTHORIZATION_CODE_LENGTH = 8192
_REQUEST_TIMEOUT_SECONDS = 1.0


class OAuthLoopbackTimeout(TimeoutError):
    """Raised when the browser does not return before the local deadline."""


@dataclass(frozen=True)
class OAuthLoopbackResult:
    """A terminal result received from the browser on loopback."""

    code: Optional[str] = None
    error: Optional[str] = None


def is_valid_microsoft_authorization_id(value: object) -> bool:
    """Return whether a value has the shape of the server-generated state."""
    return (
        isinstance(value, str)
        and _MIN_AUTHORIZATION_ID_LENGTH <= len(value) <= _MAX_AUTHORIZATION_ID_LENGTH
        and value.isascii()
        and all(character.isalnum() or character in "-_" for character in value)
    )


class _LoopbackHTTPServer(HTTPServer):
    """Bound only to IPv4 loopback, with a timeout for accepted sockets."""

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(_REQUEST_TIMEOUT_SECONDS)
        return request, client_address


class MicrosoftOAuthLoopback:
    """Receive exactly one correlated Microsoft OAuth result on 127.0.0.1."""

    def __init__(self) -> None:
        self._authorization_id: Optional[str] = None
        self._result: Optional[OAuthLoopbackResult] = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ConnectOnion"
            sys_version = ""

            def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
                owner._handle_get(self)

            def log_message(self, _format: str, *args) -> None:
                # Never copy the callback query (which contains a one-use code)
                # into terminal or application logs.
                return

        self._server = _LoopbackHTTPServer(("127.0.0.1", 0), Handler)
        self._server.timeout = 0.5

    @property
    def callback_uri(self) -> str:
        """Canonical URI accepted by oo-api's strict redirect allowlist."""
        return (
            f"http://127.0.0.1:{self._server.server_port}"
            f"{MICROSOFT_CALLBACK_PATH}"
        )

    @property
    def port(self) -> int:
        return self._server.server_port

    def wait_for_result(
        self,
        authorization_id: str,
        timeout: float = 5 * 60,
    ) -> OAuthLoopbackResult:
        """Serve loopback until the matching result arrives or time expires."""
        if not is_valid_microsoft_authorization_id(authorization_id):
            raise ValueError("authorization_id is invalid")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self._authorization_id = authorization_id
        deadline = time.monotonic() + timeout
        while self._result is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OAuthLoopbackTimeout("Microsoft authorization timed out")
            self._server.timeout = min(0.5, remaining)
            self._server.handle_request()
        return self._result

    def close(self) -> None:
        self._server.server_close()

    def __enter__(self) -> "MicrosoftOAuthLoopback":
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def _handle_get(self, handler: BaseHTTPRequestHandler) -> None:
        try:
            parsed = urlsplit(handler.path)
            params = parse_qs(
                parsed.query,
                keep_blank_values=True,
                max_num_fields=8,
            )
        except ValueError:
            self._send_page(handler, 400, _INVALID_PAGE)
            return

        expected_host = f"127.0.0.1:{self._server.server_port}"
        host_headers = handler.headers.get_all("Host", [])
        allowed_keys = {"authorization_id", "code", "error"}
        authorization_ids = params.get("authorization_id", [])
        codes = params.get("code", [])
        errors = params.get("error", [])

        valid_envelope = (
            self._authorization_id is not None
            and parsed.scheme == ""
            and parsed.netloc == ""
            and parsed.path == MICROSOFT_CALLBACK_PATH
            and parsed.fragment == ""
            and len(host_headers) == 1
            and host_headers[0] == expected_host
            and set(params).issubset(allowed_keys)
            and len(authorization_ids) == 1
            and is_valid_microsoft_authorization_id(authorization_ids[0])
            and hmac.compare_digest(
                authorization_ids[0].encode("ascii"),
                (self._authorization_id or "").encode("ascii"),
            )
            and (
                (
                    len(codes) == 1
                    and 0 < len(codes[0]) <= _MAX_AUTHORIZATION_CODE_LENGTH
                    and not errors
                )
                or (
                    not codes
                    and errors == ["authorization_failed"]
                )
            )
        )
        if not valid_envelope:
            self._send_page(handler, 400, _INVALID_PAGE)
            return

        if codes:
            self._result = OAuthLoopbackResult(code=codes[0])
            self._send_page(handler, 200, _SUCCESS_PAGE)
        else:
            self._result = OAuthLoopbackResult(error="authorization_failed")
            self._send_page(handler, 200, _CANCELLED_PAGE)

    @staticmethod
    def _send_page(
        handler: BaseHTTPRequestHandler,
        status_code: int,
        body: bytes,
    ) -> None:
        handler.send_response(status_code)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(body)


_SUCCESS_PAGE = (
    b"<!doctype html><html><head><title>Microsoft connected</title></head>"
    b"<body><h1>Microsoft connected</h1>"
    b"<p>You can close this window and return to the terminal.</p></body></html>"
)
_CANCELLED_PAGE = (
    b"<!doctype html><html><head><title>Authorization cancelled</title></head>"
    b"<body><h1>Authorization was not completed</h1>"
    b"<p>You can close this window and return to the terminal.</p></body></html>"
)
_INVALID_PAGE = (
    b"<!doctype html><html><head><title>Invalid callback</title></head>"
    b"<body><h1>Invalid authorization callback</h1></body></html>"
)

"""Unit tests for connectonion/network/asgi/http.py

Tests cover:
- read_body() ASGI body reading
- send_json() JSON response sending
- send_html() HTML response sending
- send_text() plain text response sending
- handle_http() HTTP routing
- CORS headers
- Admin endpoint authentication
"""

import json
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch

from connectonion.network.asgi.http import (
    read_body,
    send_json,
    send_html,
    send_text,
    handle_http,
    CORS_HEADERS,
)


@pytest.mark.asyncio
class TestReadBody:
    """Test read_body async function."""

    async def test_reads_single_chunk(self):
        """read_body reads single-chunk body."""
        async def receive():
            return {"body": b"Hello world", "more_body": False}

        result = await read_body(receive)

        assert result == b"Hello world"

    async def test_reads_multiple_chunks(self):
        """read_body reads multi-chunk body."""
        chunks = [
            {"body": b"Hello ", "more_body": True},
            {"body": b"world", "more_body": False},
        ]
        chunk_index = [0]

        async def receive():
            chunk = chunks[chunk_index[0]]
            chunk_index[0] += 1
            return chunk

        result = await read_body(receive)

        assert result == b"Hello world"

    async def test_reads_empty_body(self):
        """read_body handles empty body."""
        async def receive():
            return {"body": b"", "more_body": False}

        result = await read_body(receive)

        assert result == b""

    async def test_handles_missing_body_key(self):
        """read_body handles missing body key in message."""
        async def receive():
            return {"more_body": False}  # No body key

        result = await read_body(receive)

        assert result == b""


@pytest.mark.asyncio
class TestSendJson:
    """Test send_json async function."""

    async def test_sends_json_response(self):
        """send_json sends properly formatted JSON."""
        sent = []

        async def send(msg):
            sent.append(msg)

        await send_json(send, {"key": "value"})

        assert len(sent) == 2
        # First message is response start
        assert sent[0]["type"] == "http.response.start"
        assert sent[0]["status"] == 200
        # Second message is body
        assert sent[1]["type"] == "http.response.body"
        assert json.loads(sent[1]["body"]) == {"key": "value"}

    async def test_sends_with_custom_status(self):
        """send_json sends custom status code."""
        sent = []

        async def send(msg):
            sent.append(msg)

        await send_json(send, {"error": "not found"}, status=404)

        assert sent[0]["status"] == 404

    async def test_includes_cors_headers(self):
        """send_json includes CORS headers."""
        sent = []

        async def send(msg):
            sent.append(msg)

        await send_json(send, {})

        headers = dict(sent[0]["headers"])
        assert b"access-control-allow-origin" in headers

    async def test_content_type_json(self):
        """send_json sets content-type to application/json."""
        sent = []

        async def send(msg):
            sent.append(msg)

        await send_json(send, {})

        headers = dict(sent[0]["headers"])
        assert headers[b"content-type"] == b"application/json"


@pytest.mark.asyncio
class TestSendHtml:
    """Test send_html async function."""

    async def test_sends_html_response(self):
        """send_html sends HTML content."""
        sent = []

        async def send(msg):
            sent.append(msg)

        await send_html(send, b"<html><body>Hello</body></html>")

        assert sent[0]["status"] == 200
        headers = dict(sent[0]["headers"])
        assert b"text/html" in headers[b"content-type"]
        assert sent[1]["body"] == b"<html><body>Hello</body></html>"

    async def test_sends_with_custom_status(self):
        """send_html sends custom status."""
        sent = []

        async def send(msg):
            sent.append(msg)

        await send_html(send, b"<h1>Error</h1>", status=500)

        assert sent[0]["status"] == 500


@pytest.mark.asyncio
class TestSendText:
    """Test send_text async function."""

    async def test_sends_plain_text(self):
        """send_text sends plain text content."""
        sent = []

        async def send(msg):
            sent.append(msg)

        await send_text(send, "Hello world")

        assert sent[0]["status"] == 200
        headers = dict(sent[0]["headers"])
        assert b"text/plain" in headers[b"content-type"]
        assert sent[1]["body"] == b"Hello world"

    async def test_includes_cors_headers(self):
        """send_text includes CORS headers."""
        sent = []

        async def send(msg):
            sent.append(msg)

        await send_text(send, "text")

        headers = dict(sent[0]["headers"])
        assert b"access-control-allow-origin" in headers


class TestCorsHeaders:
    """Test CORS headers constant."""

    def test_allows_all_origins(self):
        """CORS allows all origins."""
        headers_dict = {k: v for k, v in CORS_HEADERS}
        assert headers_dict[b"access-control-allow-origin"] == b"*"

    def test_allows_common_methods(self):
        """CORS allows GET, POST, OPTIONS."""
        headers_dict = {k: v for k, v in CORS_HEADERS}
        methods = headers_dict[b"access-control-allow-methods"]
        assert b"GET" in methods
        assert b"POST" in methods
        assert b"OPTIONS" in methods

    def test_allows_common_headers(self):
        """CORS allows authorization and content-type headers."""
        headers_dict = {k: v for k, v in CORS_HEADERS}
        allowed = headers_dict[b"access-control-allow-headers"]
        assert b"authorization" in allowed
        assert b"content-type" in allowed


@pytest.mark.asyncio
class TestHandleHttpRouting:
    """Test handle_http routing logic."""

    async def test_cors_preflight_options(self):
        """OPTIONS requests return 204 with CORS headers."""
        scope = {"method": "OPTIONS", "path": "/input", "headers": []}
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {}
        storage = Mock()

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=storage,
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 204

    async def test_health_endpoint(self):
        """GET /health returns health status."""
        scope = {"method": "GET", "path": "/health", "headers": []}
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {
            "health": lambda start_time: {"status": "healthy", "uptime": 100},
        }

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 200
        body = json.loads(sent[1]["body"])
        assert body["status"] == "healthy"

    async def test_info_endpoint(self):
        """GET /info returns agent info."""
        scope = {"method": "GET", "path": "/info", "headers": []}
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {
            "info": lambda trust: {"name": "test", "trust": trust},
        }

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="careful",
            result_ttl=3600,
            start_time=0
        )

        body = json.loads(sent[1]["body"])
        assert body["name"] == "test"
        assert body["trust"] == "careful"

    async def test_sessions_list_endpoint(self):
        """GET /sessions returns session list."""
        scope = {"method": "GET", "path": "/sessions", "headers": []}
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {
            "sessions": lambda storage: {"sessions": [{"id": "1"}, {"id": "2"}]},
        }

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        body = json.loads(sent[1]["body"])
        assert len(body["sessions"]) == 2

    async def test_session_by_id_found(self):
        """GET /sessions/{id} returns session when found."""
        scope = {"method": "GET", "path": "/sessions/abc123", "headers": []}
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {
            "session": lambda storage, id: {"session_id": id, "status": "done"},
        }

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 200
        body = json.loads(sent[1]["body"])
        assert body["session_id"] == "abc123"

    async def test_session_by_id_not_found(self):
        """GET /sessions/{id} returns 404 when not found."""
        scope = {"method": "GET", "path": "/sessions/unknown", "headers": []}
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {
            "session": lambda storage, id: None,
        }

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 404

    async def test_input_endpoint_success(self):
        """POST /input processes authenticated request."""
        scope = {"method": "POST", "path": "/input", "headers": []}
        sent = []

        async def receive():
            return {
                "body": json.dumps({
                    "payload": {"prompt": "Hello", "timestamp": 123},
                    "from": "0xtest",
                    "signature": "0xsig"
                }).encode(),
                "more_body": False
            }

        async def send(msg):
            sent.append(msg)

        handlers = {
            "auth": lambda data, trust, **kw: ("Hello", "0xtest", True, None),
            "input": lambda storage, prompt, ttl, session: {"result": "World", "session_id": "x"},
        }

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 200
        body = json.loads(sent[1]["body"])
        assert body["result"] == "World"

    async def test_input_endpoint_auth_error(self):
        """POST /input returns 401 on auth error."""
        scope = {"method": "POST", "path": "/input", "headers": []}
        sent = []

        async def receive():
            return {"body": b'{"prompt": "Hello"}', "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {
            "auth": lambda data, trust, **kw: (None, None, False, "unauthorized: invalid"),
        }

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 401

    async def test_input_endpoint_forbidden(self):
        """POST /input returns 403 on forbidden error."""
        scope = {"method": "POST", "path": "/input", "headers": []}
        sent = []

        async def receive():
            return {"body": b'{}', "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {
            "auth": lambda data, trust, **kw: (None, "0x", True, "forbidden: blacklisted"),
        }

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 403

    async def test_input_invalid_json(self):
        """POST /input returns 400 on invalid JSON."""
        scope = {"method": "POST", "path": "/input", "headers": []}
        sent = []

        async def receive():
            return {"body": b"not json{", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {}

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 400
        body = json.loads(sent[1]["body"])
        assert "Invalid JSON" in body["error"]

    async def test_unknown_route_404(self):
        """Unknown routes return 404."""
        scope = {"method": "GET", "path": "/unknown", "headers": []}
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {}

        await handle_http(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            trust="open",
            result_ttl=3600,
            start_time=0
        )

        assert sent[0]["status"] == 404


@pytest.mark.asyncio
class TestAdminEndpoints:
    """Test admin endpoint authentication."""

    async def test_admin_without_auth_rejected(self):
        """Admin endpoint without API key is rejected."""
        scope = {"method": "GET", "path": "/admin/logs", "headers": []}
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {"admin_logs": lambda: {"content": "logs"}}

        with patch.dict(os.environ, {"OPENONION_API_KEY": "secret123"}):
            await handle_http(
                scope, receive, send,
                route_handlers=handlers,
                storage=Mock(),
                trust="open",
                result_ttl=3600,
                start_time=0
            )

        assert sent[0]["status"] == 401

    async def test_admin_with_wrong_key_rejected(self):
        """Admin endpoint with wrong API key is rejected."""
        scope = {
            "method": "GET",
            "path": "/admin/logs",
            "headers": [(b"authorization", b"Bearer wrongkey")]
        }
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {"admin_logs": lambda: {"content": "logs"}}

        with patch.dict(os.environ, {"OPENONION_API_KEY": "secret123"}):
            await handle_http(
                scope, receive, send,
                route_handlers=handlers,
                storage=Mock(),
                trust="open",
                result_ttl=3600,
                start_time=0
            )

        assert sent[0]["status"] == 401

    async def test_admin_logs_with_valid_key(self):
        """Admin logs endpoint with valid key succeeds."""
        scope = {
            "method": "GET",
            "path": "/admin/logs",
            "headers": [(b"authorization", b"Bearer secret123")]
        }
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {"admin_logs": lambda: {"content": "log content here"}}

        with patch.dict(os.environ, {"OPENONION_API_KEY": "secret123"}):
            await handle_http(
                scope, receive, send,
                route_handlers=handlers,
                storage=Mock(),
                trust="open",
                result_ttl=3600,
                start_time=0
            )

        assert sent[0]["status"] == 200
        assert sent[1]["body"] == b"log content here"

    async def test_admin_sessions_with_valid_key(self):
        """Admin sessions endpoint with valid key succeeds."""
        scope = {
            "method": "GET",
            "path": "/admin/sessions",
            "headers": [(b"authorization", b"Bearer mykey")]
        }
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        handlers = {"admin_sessions": lambda: {"sessions": []}}

        with patch.dict(os.environ, {"OPENONION_API_KEY": "mykey"}):
            await handle_http(
                scope, receive, send,
                route_handlers=handlers,
                storage=Mock(),
                trust="open",
                result_ttl=3600,
                start_time=0
            )

        assert sent[0]["status"] == 200
        body = json.loads(sent[1]["body"])
        assert "sessions" in body


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

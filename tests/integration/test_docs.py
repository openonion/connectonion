"""Tests for GET /docs static page."""

import asyncio


class ASGITestClient:
    def __init__(self, app):
        self.app = app

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def get(self, path: str):
        return self._run(self._request("GET", path))

    async def _request(self, method: str, path: str):
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [],
        }

        async def receive():
            return {"type": "http.disconnect"}

        class Resp:
            status_code = 0
            headers = []
            body = b""

        resp = Resp()

        async def send(message):
            if message["type"] == "http.response.start":
                resp.status_code = message["status"]
                resp.headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                resp.body = message.get("body", b"")

        await self.app(scope, receive, send)
        return resp


def test_docs_served(tmp_path):
    from unittest.mock import MagicMock
    from connectonion.network.host import _make_app

    agent = MagicMock()
    agent.name = "docs-agent"
    agent.tools = MagicMock()
    agent.tools.list_names = MagicMock(return_value=["t1"]) 
    agent.input = MagicMock(return_value="ok")

    app = _make_app(agent, trust="open")
    client = ASGITestClient(app)

    resp = client.get("/docs")
    assert resp.status_code == 200
    # Check content-type header contains text/html
    content_types = [v.decode() for k,v in resp.headers if k == b"content-type"]
    assert any("text/html" in ct for ct in content_types)
    body = resp.body.decode("utf-8", errors="ignore")
    assert "ConnectOnion Docs" in body
    assert "Agent" in body
    assert "HTTP /input" in body
    assert "WebSocket /ws" in body
    assert "Tasks" in body


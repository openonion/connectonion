"""The URL the banner prints answers with where to go next.

Found on 1.8.8b7: the host banner prints `http://localhost:<port>` and a new
user's first move is to open it, which returned 404 {"error": "not found"}.
The URL worked; it just had nothing at `/`. Now `/` names the endpoints
that do exist, and an unknown path is still a 404.
"""

import json

import pytest

from connectonion.network.host.http_router import handle_http


async def _get(path):
    sent = []

    async def receive():
        return {"body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await handle_http({"method": "GET", "path": path, "headers": []}, receive, send,
                      route_handlers={}, storage=None, trust="open", start_time=0)
    return sent[0]["status"], json.loads(sent[1]["body"])


@pytest.mark.asyncio
async def test_the_root_points_at_docs_and_info():
    status, body = await _get("/")

    assert status == 200
    assert body["docs"] == "/docs"
    assert body["info"] == "/info"


@pytest.mark.asyncio
async def test_an_unknown_path_is_still_not_found():
    status, _ = await _get("/nothing-here")

    assert status == 404

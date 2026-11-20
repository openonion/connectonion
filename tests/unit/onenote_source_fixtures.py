"""Synthetic Graph routes shared by the independent OneNote Story tests."""
import json
from pathlib import Path
import httpx
import pytest

BASE = "https://graph.microsoft.com/v1.0"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "onenote"
DATA = json.loads((FIXTURES / "pages.json").read_text(encoding="utf-8"))
HTML = (FIXTURES / "page.html").read_text(encoding="utf-8")

@pytest.fixture
def graph(monkeypatch):
    monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "fixture-secret-token")
    monkeypatch.setenv("MICROSOFT_SCOPES", "Notes.Read User.Read")
    routes = {
        "/me": {"id": "fixture-account"},
        "/me/onenote/notebooks": {"value": DATA["notebooks"]},
        "/me/onenote/notebooks/nb-fixture/sections": {"value": DATA["sections"]},
        "/me/onenote/notebooks/nb-fixture/sectionGroups": {"value": []},
        "/me/onenote/sections/section-fixture/pages": {"value": DATA["pages"][:2]},
    }
    for page in DATA["pages"]:
        routes[f"/me/onenote/pages/{page['id']}"] = page
        routes[f"/me/onenote/pages/{page['id']}/content"] = HTML if page["id"] != "page-empty" else ""
    calls = []

    def request(method, url, **kwargs):
        assert method == "GET", "The source must never write to OneNote"
        calls.append((method, url, kwargs))
        key = url.removeprefix(BASE)
        body = routes.get(key, routes.get(key.split("?")[0], (404, {"error": "private provider message"})))
        if callable(body):
            body = body()
        if isinstance(body, httpx.Response):
            return body
        status, body = body if isinstance(body, tuple) else (200, body)
        options = {"text": body, "headers": {"Content-Type": "text/html"}} if isinstance(body, str) else {"json": body}
        return httpx.Response(status, request=httpx.Request(method, url), **options)

    monkeypatch.setattr(httpx, "request", request)
    return routes, calls

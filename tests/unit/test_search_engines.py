"""Tests for web_search: which engine answers, and what an agent is told when one cannot.

LLM-Note: Tests for connectonion.useful_tools.search_engines with every engine behind httpx.MockTransport

What it tests:
- the managed engine sends the query with the ConnectOnion token and parses its results
- out of credits: auto still answers from DuckDuckGo and says why; an explicit co names the free engine
- not logged in: auto skips managed search silently; a user's own key is spent before credits
- DuckDuckGo's redirect links are unwrapped to the real URL and ads are dropped
"""

import importlib
import json

import httpx
import pytest

engines = importlib.import_module("connectonion.useful_tools.search_engines")

DDG_HTML = """
<div class="result results_links result--ad"><a class="result__a" href="https://ads.example/">Ad</a></div>
<div class="result results_links"><a class="result__a"
   href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2F&rut=x">Python docs</a>
   <a class="result__snippet">The official documentation.</a></div>
"""


@pytest.fixture
def web(monkeypatch):
    """Route every engine's HTTP call to `web.routes[host]`, recording each request."""
    state = type("Web", (), {"routes": {}, "requests": []})()

    def handler(request):
        state.requests.append(request)
        return state.routes[request.url.host](request)

    monkeypatch.setattr(engines, "_http", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    for key in ("OPENONION_API_KEY", "SERPER_API_KEY", "BRAVE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CONNECTONION_BACKEND_URL", "https://oo.test")
    state.routes["html.duckduckgo.com"] = lambda r: httpx.Response(200, text=DDG_HTML)
    return state


def managed(status, body=None):
    return lambda request: httpx.Response(status, json=body or {})


def test_managed_search_sends_the_query_with_the_token(web, monkeypatch):
    monkeypatch.setenv("OPENONION_API_KEY", "tok")
    web.routes["oo.test"] = managed(200, {"answer": "Use json.dumps.",
                                          "results": [{"title": "A", "url": "https://a.example", "snippet": "s"}]})

    found = engines.search("python json", count=3)

    request = web.requests[0]
    assert request.url.path == "/api/v1/search" and request.headers["authorization"] == "Bearer tok"
    assert json.loads(request.content) == {"query": "python json", "count": 3}
    assert found == {"engine": "co", "answer": "Use json.dumps.",
                     "results": [{"title": "A", "url": "https://a.example", "snippet": "s"}], "notes": []}
    assert engines.format_results(found).startswith("Results from co:\nAnswer: Use json.dumps.\n\nSources:\n1. A")


def test_out_of_credits_auto_answers_from_duckduckgo_and_says_why(web, monkeypatch):
    monkeypatch.setenv("OPENONION_API_KEY", "tok")
    web.routes["oo.test"] = managed(402, {"detail": {"error": "insufficient_credits"}})

    text = engines.web_search("python docs")

    assert "Results from ddg" in text and "https://docs.python.org/3/" in text
    assert "credits are used up" in text and "--engine ddg" in text


def test_explicit_managed_engine_out_of_credits_names_the_free_engine(web, monkeypatch):
    monkeypatch.setenv("OPENONION_API_KEY", "tok")
    web.routes["oo.test"] = managed(402)

    with pytest.raises(engines.SearchError) as raised:
        engines.search("q", engine="co")

    assert raised.value.code == "payment_required" and "--engine ddg" in raised.value.hint


def test_not_logged_in_goes_straight_to_duckduckgo_without_a_note(web):
    found = engines.search("python docs")

    assert found["engine"] == "ddg" and found["notes"] == []
    assert [r["url"] for r in found["results"]] == ["https://docs.python.org/3/"], "ads are dropped, links unwrapped"


def test_a_users_own_key_is_spent_before_credits(web, monkeypatch):
    monkeypatch.setenv("OPENONION_API_KEY", "tok")
    monkeypatch.setenv("SERPER_API_KEY", "mine")
    web.routes["google.serper.dev"] = lambda r: httpx.Response(200, json={"organic": [{"title": "S", "link": "https://s.example", "snippet": ""}]})

    found = engines.search("q")

    assert found["engine"] == "serper" and web.requests[0].headers["x-api-key"] == "mine"


def test_brave_results_are_normalised(web, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    web.routes["api.search.brave.com"] = lambda r: httpx.Response(
        200, json={"web": {"results": [{"title": "B", "url": "https://b.example", "description": "d"}]}})

    assert engines.search("q", engine="brave")["results"] == [{"title": "B", "url": "https://b.example", "snippet": "d"}]


def test_an_unknown_engine_is_refused_with_the_choices(web):
    assert "auto, co, serper, brave, ddg" in engines.web_search("q", engine="google")


def test_a_network_failure_on_the_last_engine_is_a_message_not_a_crash(web):
    def down(request):
        raise httpx.ConnectError("no route")
    web.routes["html.duckduckgo.com"] = down

    assert engines.web_search("q", engine="ddg") == "Search failed (network_error): ddg: could not connect (ConnectError)."

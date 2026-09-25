"""Tests for web_fetch: a public page comes back as Markdown, and nothing private is reachable.

LLM-Note: Tests for connectonion.useful_tools.page_fetch with DNS and HTTP faked

What it tests:
- HTML becomes Markdown: headings, links made absolute, lists, code kept verbatim; nav and scripts dropped
- a host resolving to a private, loopback or link-local address is refused, on every redirect hop
- a redirect to another site is reported, not followed; a same-site one is followed
- binary content is refused; a nearly empty page points at co browser; long pages are truncated
- with a prompt, the small model gets the page and its answer comes back instead
"""

import importlib

import httpx
import pytest

page_fetch = importlib.import_module("connectonion.useful_tools.page_fetch")

ARTICLE = """<html><head><title>Guide</title><script>track()</script></head><body>
<nav>Home | About</nav><main><h1>Install</h1><p>Read the <a href="/faq">FAQ</a> first.</p>
<ul><li>fast</li><li>small</li></ul><pre>def f():
    return 1</pre>""" + "<p>" + "Plenty of real text here. " * 20 + "</p></main></body></html>"


@pytest.fixture
def web(monkeypatch):
    state = type("Web", (), {"pages": {}, "dns": {}, "requests": []})()

    def handler(request):
        state.requests.append(str(request.url))
        return state.pages[str(request.url)]

    monkeypatch.setattr(page_fetch, "_http", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(page_fetch, "_resolve", lambda host: state.dns.get(host, ["93.184.216.34"]))
    monkeypatch.setattr(page_fetch, "_cache", {})
    return state


def html(body, status=200):
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})


def test_a_page_comes_back_as_markdown(web):
    web.pages["https://docs.example.com/install"] = html(ARTICLE)

    text = page_fetch.web_fetch("docs.example.com/install")

    assert "Title: Guide" in text and "# Install" in text
    assert "[FAQ](https://docs.example.com/faq)" in text and "- fast\n- small" in text
    assert "def f():\n    return 1" in text, "code keeps its indentation"
    assert "track()" not in text and "About" not in text


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
def test_a_host_that_resolves_privately_is_refused(web, address):
    web.dns["internal.example.com"] = [address]

    text = page_fetch.web_fetch("https://internal.example.com/")

    assert "private address" in text and web.requests == []


def test_a_dotless_host_is_refused_without_a_lookup(web):
    assert "not a public host name" in page_fetch.web_fetch("http://localhost:8000/admin")


def test_a_redirect_into_a_private_address_is_refused(web):
    web.pages["https://a.example.com/"] = httpx.Response(302, headers={"location": "https://a.example.com/in"})
    web.dns["a.example.com"] = ["93.184.216.34"]
    original = page_fetch._resolve
    calls = []

    def resolve(host):
        calls.append(host)
        return ["93.184.216.34"] if len(calls) == 1 else ["10.1.1.1"]
    page_fetch._resolve = resolve
    try:
        text = page_fetch.web_fetch("https://a.example.com/")
    finally:
        page_fetch._resolve = original

    assert "private address" in text and web.requests == ["https://a.example.com/"]


def test_a_redirect_to_another_site_is_reported_not_followed(web):
    web.pages["https://short.example/x"] = httpx.Response(301, headers={"location": "https://elsewhere.example/page"})

    text = page_fetch.web_fetch("https://short.example/x")

    assert "redirects to another site: https://elsewhere.example/page" in text
    assert web.requests == ["https://short.example/x"]


def test_a_same_site_redirect_is_followed(web):
    web.pages["https://example.com/old"] = httpx.Response(301, headers={"location": "https://www.example.com/new"})
    web.pages["https://www.example.com/new"] = html(ARTICLE)

    assert "URL: https://www.example.com/new" in page_fetch.web_fetch("https://example.com/old")


def test_binary_content_is_refused(web):
    web.pages["https://example.com/a.zip"] = httpx.Response(200, content=b"PK", headers={"content-type": "application/zip"})

    assert "application/zip, not a text page" in page_fetch.web_fetch("https://example.com/a.zip")


def test_a_nearly_empty_page_points_at_the_browser(web):
    web.pages["https://app.example.com/"] = html("<html><body><div id=root></div></body></html>")

    assert "co browser" in page_fetch.web_fetch("https://app.example.com/")


def test_a_long_page_is_truncated_and_says_so(web):
    web.pages["https://example.com/long"] = html("<p>" + "word " * 5000 + "</p>")

    text = page_fetch.web_fetch("https://example.com/long", max_chars=100)

    assert "[Truncated at 100 of" in text


def test_a_prompt_is_answered_from_the_page(web, monkeypatch):
    web.pages["https://docs.example.com/install"] = html(ARTICLE)
    seen = {}
    llm_do_module = importlib.import_module("connectonion.llm_do")

    def fake(prompt, model):
        seen.update(prompt=prompt, model=model)
        return "Read the FAQ first."
    monkeypatch.setattr(llm_do_module, "llm_do", fake)

    text = page_fetch.web_fetch("https://docs.example.com/install", prompt="What comes first?")

    assert text.endswith("Read the FAQ first.")
    assert "What comes first?" in seen["prompt"] and "# Install" in seen["prompt"]
    assert seen["model"] == page_fetch.PROMPT_MODEL


def test_a_second_fetch_of_the_same_url_is_served_from_the_cache(web):
    web.pages["https://example.com/"] = html(ARTICLE)

    page_fetch.web_fetch("https://example.com/")
    page_fetch.web_fetch("https://example.com/")

    assert web.requests == ["https://example.com/"]

"""Tests for `co search` and `co fetch` through the real Typer app, with the network faked.

LLM-Note: Tests for connectonion.cli.commands.web_commands via connectonion.cli.main.app

What it tests:
- search prints results and names `co fetch <first result>` on stderr; --json stdout is pure JSON
- out of credits on --engine co: exit 1, one Next line, and it is the free engine
- fetch prints Markdown; a refused private address exits 1 and names curl; a cross-site redirect names the target
- co ai carries both tools, and the approval policy treats them as reads
"""

import importlib
import json

import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.commands import command_tips
from connectonion.cli.main import app

engines = importlib.import_module("connectonion.useful_tools.search_engines")
page_fetch = importlib.import_module("connectonion.useful_tools.page_fetch")

RESULTS = {"results": [{"title": "Python", "url": "https://docs.python.org/3/", "snippet": "docs"}]}


@pytest.fixture
def net(monkeypatch):
    routes = {}

    def handler(request):
        return routes[request.url.host](request)

    def client():
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(engines, "_http", client)
    monkeypatch.setattr(page_fetch, "_http", client)
    monkeypatch.setattr(page_fetch, "_cache", {})
    monkeypatch.setattr(page_fetch, "_resolve", lambda host: ["10.0.0.1"] if host.startswith("intranet") else ["93.184.216.34"])
    monkeypatch.setenv("CONNECTONION_BACKEND_URL", "https://oo.test")
    monkeypatch.setenv("OPENONION_API_KEY", "tok")
    monkeypatch.setenv("CO_TIPS", "on")
    command_tips.forget_next_step_named()
    return routes


def co(*args):
    return CliRunner().invoke(app, list(args))


def test_search_prints_results_and_names_the_fetch(net):
    net["oo.test"] = lambda r: httpx.Response(200, json=RESULTS)

    result = co("search", "python docs")

    assert result.exit_code == 0 and "1. Python" in result.stdout
    assert "Next: co fetch https://docs.python.org/3/" in result.stderr


def test_search_json_is_pure_json_on_stdout(net):
    net["oo.test"] = lambda r: httpx.Response(200, json=RESULTS)

    result = co("search", "python docs", "--json")

    assert json.loads(result.stdout)["engine"] == "co"


def test_out_of_credits_names_one_next_step_and_it_is_free(net):
    net["oo.test"] = lambda r: httpx.Response(402, json={"detail": {"error": "insufficient_credits"}})

    result = co("search", "python docs", "--engine", "co")

    assert result.exit_code == 1 and "credits are used up" in result.stderr
    assert result.stderr.count("Next:") == 1
    assert "Next: co search 'python docs' --engine ddg" in result.stderr


def test_fetch_prints_the_page(net):
    net["example.com"] = lambda r: httpx.Response(200, text="<main><h1>Hi</h1><p>" + "text " * 60 + "</p></main>",
                                                  headers={"content-type": "text/html"})

    result = co("fetch", "https://example.com/")

    assert result.exit_code == 0 and "# Hi" in result.stdout


def test_fetch_of_a_private_address_exits_1_and_names_curl(net):
    result = co("fetch", "https://intranet.example.com/")

    assert result.exit_code == 1 and "private address" in result.stderr
    assert "Next: curl -sL https://intranet.example.com/" in result.stderr


def test_fetch_of_a_cross_site_redirect_names_the_target(net):
    net["t.example"] = lambda r: httpx.Response(302, headers={"location": "https://real.example/a"})

    result = co("fetch", "https://t.example/x")

    assert result.exit_code == 0 and "Next: co fetch https://real.example/a" in result.stderr


def test_co_ai_approves_web_reads_without_asking():
    from connectonion.useful_plugins.tool_approval.policy import READ_TOOLS

    assert {"web_search", "web_fetch"} <= READ_TOOLS

"""`co proxy diagnose` names the endpoints it could not reach (#1387).

It said "the host is not reachable directly" and stopped. The cause — the host
announcing http://34.129.161.131:8001 behind a firewall that allowed only
22/80/443 — took a manual relay query and a curl to find.
"""

import asyncio
import importlib

import httpx

from connectonion.cli.commands import proxy_commands

# The module, not the `connect()` function the package re-exports under that name.
connect = importlib.import_module("connectonion.network.connect")

HOST = "0x" + "a" * 64


def fake_network(monkeypatch):
    def handler(request: httpx.Request):
        url = str(request.url)
        if url.endswith(f"/api/agents/{HOST}"):
            return httpx.Response(200, json={"endpoints": [
                "http://34.129.161.131:8001", "ws://34.129.161.131:8001/ws",
                "http://10.0.0.2:8001", "http://10.0.0.3:8001"]})
        if "34.129.161.131" in url:
            raise httpx.ConnectTimeout("timed out", request=request)
        if "10.0.0.2" in url:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"address": "0x" + "b" * 64})

    real = httpx.AsyncClient
    monkeypatch.setattr(connect.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_every_listed_endpoint_says_how_it_answered(monkeypatch):
    fake_network(monkeypatch)

    reach = asyncio.run(connect.probe_endpoints(HOST, "wss://relay.example"))

    results = {p["endpoint"]: p["result"] for p in reach["probes"]}
    assert results == {
        "http://34.129.161.131:8001": "connect timeout",
        "http://10.0.0.2:8001": "refused or unreachable",
        "http://10.0.0.3:8001": "answered /info, but for a different address",
    }
    assert "ws://34.129.161.131:8001/ws" in reach["listed"]   # verbatim, not only probed


def test_all_timing_out_is_said_as_a_firewall_in_words():
    text = proxy_commands._describe_reach({"listed": [], "probes": [
        {"endpoint": "http://34.129.161.131:8001", "result": "connect timeout"}]})

    assert "http://34.129.161.131:8001  → connect timeout" in text
    assert "Nothing answers at 34.129.161.131:8001 from this network" in text
    assert "answers on 443" in text


def test_diagnose_carries_the_probes_in_its_summary_and_json(monkeypatch, capsys):
    monkeypatch.setattr(proxy_commands, "_load", lambda: {HOST: {}})
    monkeypatch.setattr(proxy_commands, "_row", lambda address, share: {
        "alive": True, "state": "reconnecting",
        "detail": "the host is not reachable directly; retrying in 60s"})
    monkeypatch.setattr(proxy_commands, "_probe_reach", lambda address: {
        "listed": ["http://34.129.161.131:8001"],
        "probes": [{"endpoint": "http://34.129.161.131:8001", "result": "connect timeout"}]})

    code = proxy_commands._diagnose(HOST, as_json=False)

    out = capsys.readouterr()
    assert code != 0
    assert "34.129.161.131:8001  → connect timeout" in out.out + out.err

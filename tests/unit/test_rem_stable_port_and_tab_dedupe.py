"""Regression tests for stable preferred REM live Host port, tab deduplication, and upgrade reload UX."""

import asyncio
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.rem import live_host, reader
from connectonion.rem.config import prepare
from connectonion.rem.files import write_json
from connectonion.rem.reader_template import read_part


def test_first_launch_picks_dedicated_rem_default_port_and_steps_when_busy(monkeypatch):
    assert live_host.REM_DEFAULT_PORT == 18765

    busy = {18765, 18766}
    monkeypatch.setattr(live_host, "_free", lambda port: port not in busy)
    assert live_host._preferred_port({}) == 18767

    # Saved port still wins when free.
    assert live_host._preferred_port({"port": 18770}) == 18770
    # When saved port is busy, falls back deterministically to preferred range.
    assert live_host._preferred_port({"port": 18765}) == 18767


def test_spawn_uses_preferred_port_when_none_given(tmp_path, monkeypatch):
    monkeypatch.setattr(live_host, "_preferred_port", lambda saved: 18765)
    called = {}

    def popen(command, **kwargs):
        called["command"] = command
        return SimpleNamespace(pid=99, args=command)

    monkeypatch.setattr(live_host.subprocess, "Popen", popen)
    live_host._spawn(tmp_path)
    idx = called["command"].index("--port")
    assert called["command"][idx + 1] == "18765"


def test_known_ports_includes_dedicated_rem_port_before_8000(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: tmp_path)
    assert live_host._known_ports() == [live_host.REM_DEFAULT_PORT, live_host.DEFAULT_PORT]

    write_json(tmp_path / "rem-live-host.json", {"port": 19999})
    assert live_host._known_ports() == [19999, live_host.REM_DEFAULT_PORT, live_host.DEFAULT_PORT]


def test_rem_http_version_reports_active_reader_age(tmp_path, monkeypatch):
    from connectonion.network.host import rem_http

    root = tmp_path / "rem"
    prepare(root)
    identity = tmp_path / "co"
    identity.mkdir()
    token = live_host.reader_token(identity)
    rem_http.ACTIVE_READER_SEEN.clear()

    async def call(path):
        sent = []
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "client": ("127.0.0.1", 55555),
            "headers": [
                (b"host", b"127.0.0.1:18765"),
                (b"cookie", f"co_rem={token}".encode()),
            ],
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        await rem_http.handle_rem_http(scope, receive, send, {"rem_root": root, "identity_dir": identity})
        return sent[0]["status"], b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")

    monkeypatch.setattr("connectonion.rem.reader.latest", lambda r: {"version": "v1", "installed": "1.9.7rc32"})
    status, body = asyncio.run(call("/rem/version"))
    assert status == 200
    payload = json.loads(body.decode("utf-8"))
    assert "active_reader_age_s" in payload
    assert payload["active_reader_age_s"] is None or payload["active_reader_age_s"] >= 0

    # A second request immediately afterwards sees a fresh active reader heartbeat.
    status2, body2 = asyncio.run(call("/rem/version"))
    assert status2 == 200
    payload2 = json.loads(body2.decode("utf-8"))
    assert payload2["active_reader_age_s"] is not None
    assert payload2["active_reader_age_s"] < 5.0


def test_local_or_snapshot_focuses_existing_tab_instead_of_opening_duplicate(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    monkeypatch.setattr("connectonion.rem.live_host.ensure_local",
                        lambda addr: ("http://127.0.0.1:18765/rem?token=abc", None))
    monkeypatch.setattr(reader, "_has_saved_page", lambda r: False)
    focused = []
    opened = []
    monkeypatch.setattr(reader, "_focus_existing_tab", lambda url: focused.append(url) or True)
    monkeypatch.setattr(reader.webbrowser, "open", lambda url: opened.append(url))

    result = reader.local_or_snapshot(root, "0xowner", launch=True)
    assert focused == ["http://127.0.0.1:18765/rem?token=abc"]
    assert opened == []
    assert result["reused_tab"] is True


def test_open_morning_respects_headless_uninitialized_daily_dedupe_and_active_tab(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    # 1. Uninitialized notebook -> skips safely without launching browser.
    monkeypatch.setattr(reader, "gui_available", lambda: True)
    res_uninit = reader.open_morning(root, "0xowner", launch=True)
    assert res_uninit["outcome"] == "skipped"
    assert "not initialized" in res_uninit["reason"]

    # 2. Headless host -> skips safely even when notebook exists.
    prepare(root)
    monkeypatch.setattr(reader, "gui_available", lambda: False)
    res_headless = reader.open_morning(root, "0xowner", launch=True)
    assert res_headless["outcome"] == "skipped"
    assert "graphical" in res_headless["reason"]

    # 3. Active reader already open -> skips opening a duplicate tab and records today's dedupe.
    monkeypatch.setattr(reader, "gui_available", lambda: True)
    monkeypatch.setattr(reader, "_active_reader_open", lambda addr: True)
    res_active = reader.open_morning(root, "0xowner", launch=True, now=lambda: datetime(2026, 11, 27, 9, 0, tzinfo=timezone.utc))
    assert res_active["outcome"] == "skipped"
    assert "already open" in res_active["reason"]

    # 4. Fresh day with no active tab -> opens once, second call same day dedupes.
    opened = []
    monkeypatch.setattr(reader, "_active_reader_open", lambda addr: False)
    monkeypatch.setattr(reader, "local_or_snapshot", lambda r, a, launch=True, say=None: opened.append(r) or {
        "page": "http://127.0.0.1:18765/rem", "link": "http://127.0.0.1:18765/rem?token=t", "launched": launch,
    })
    day2 = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)
    first = reader.open_morning(root, "0xowner", launch=True, now=lambda: day2)
    assert first["outcome"] == "opened"
    assert len(opened) == 1

    second = reader.open_morning(root, "0xowner", launch=True, now=lambda: day2)
    assert second["outcome"] == "skipped"
    assert "already opened today" in second["reason"]
    assert len(opened) == 1


def test_wait_for_new_build_extends_timeout_and_offers_reload():
    js = read_part("scripts/router_evidence_palette.js")
    assert "waitForNewBuild.tries > 45" in js
    # On timeout, must keep a visible reload offer rather than silently disappearing.
    snippet = js[js.index("function waitForNewBuild"):js.index("async function reconnect")]
    assert "offerReload()" in snippet

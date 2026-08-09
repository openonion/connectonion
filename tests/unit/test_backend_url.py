"""#733: one backend selection must govern every network client."""

import pytest
from pathlib import Path

from connectonion.backend import (
    DEFAULT_BACKEND_URL,
    DEFAULT_BACKEND_WS_URL,
    backend_url,
    backend_ws_url,
)


@pytest.mark.parametrize(
    "environment, expected",
    [
        ({}, DEFAULT_BACKEND_URL),
        ({"OPENONION_DEV": "1"}, "http://localhost:8000"),
        ({"ENVIRONMENT": "development"}, "http://localhost:8000"),
        ({"OPENONION_API_URL": "https://legacy-api.test/"}, "https://legacy-api.test"),
        ({"OPENONION_BASE_URL": "https://legacy-base.test/"}, "https://legacy-base.test"),
        (
            {
                "CONNECTONION_BACKEND_URL": "http://127.0.0.1:9/",
                "OPENONION_API_URL": "https://ignored.test",
                "OPENONION_DEV": "1",
            },
            "http://127.0.0.1:9",
        ),
    ],
)
def test_backend_url_precedence(monkeypatch, environment, expected):
    for name in (
        "CONNECTONION_BACKEND_URL",
        "OPENONION_API_URL",
        "OPENONION_BASE_URL",
        "OPENONION_DEV",
        "ENVIRONMENT",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    assert backend_url() == expected


def test_websocket_url_uses_the_same_origin(monkeypatch):
    monkeypatch.setenv("CONNECTONION_BACKEND_URL", "http://127.0.0.1:9/")
    assert backend_ws_url() == "ws://127.0.0.1:9"


def test_default_websocket_url_matches_the_default_http_origin(monkeypatch):
    for name in (
        "CONNECTONION_BACKEND_URL",
        "OPENONION_API_URL",
        "OPENONION_BASE_URL",
        "OPENONION_DEV",
        "ENVIRONMENT",
    ):
        monkeypatch.delenv(name, raising=False)
    assert backend_ws_url() == DEFAULT_BACKEND_WS_URL


def test_no_packaged_network_client_hardcodes_the_production_origin():
    package = Path(__file__).parents[2] / "connectonion"
    allowed = {package / "backend.py", package / "derive.py"}
    offenders = [
        path.relative_to(package)
        for path in package.rglob("*")
        if path.suffix in {".py", ".yaml", ".yml"} or path.name == "SKILL.md"
        if path not in allowed
        and any(
            origin in path.read_text(encoding="utf-8")
            for origin in ("https://oo.openonion.ai", "wss://oo.openonion.ai")
        )
    ]
    assert offenders == []

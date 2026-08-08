"""#733: one backend selection must govern every network client."""

import pytest
from pathlib import Path

from connectonion.backend import DEFAULT_BACKEND_URL, backend_url, backend_ws_url


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


def test_no_python_network_client_hardcodes_the_production_origin():
    package = Path(__file__).parents[2] / "connectonion"
    allowed = {package / "backend.py", package / "derive.py"}
    offenders = [
        path.relative_to(package)
        for path in package.rglob("*.py")
        if path not in allowed and "https://oo.openonion.ai" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []

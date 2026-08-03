"""`co init` says the backend is unhappy instead of raising through it.

On a non-200, `authenticate()` reads the reason with:

    error_msg = response.json().get("detail", "Registration failed")

A gateway in front of the backend does not answer in JSON. When it returns a
502 HTML page, `.json()` raises `JSONDecodeError` out of `co init` and `co auth`
as a traceback, and init stops before writing the project's `.env` — leaving
half a project and a stack trace where an explanation belongs.

Not hypothetical. It happened during this release loop, at 22:00 on 2026-08-03:
the relay returned 502 for about twenty seconds (`[host] relay still unreachable
after 5 attempts` on the deployed agent), and in the same window every test that
runs a real `co init` failed the same way:

    json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
      … connectonion/cli/commands/auth_commands.py:141 in authenticate
        error_msg = response.json().get("detail", "Registration failed")

A backend blip is ordinary operation for something meant to run for years. What
the operator should see is which status came back, not the shape of the reply
the code expected.
"""

from types import SimpleNamespace

import pytest

from connectonion.cli.commands import auth_commands


class FakeResponse:
    """A response whose body is not JSON, as a gateway error page is not."""

    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def json(self):
        import json
        return json.loads(self.text)      # raises, exactly as requests does


@pytest.fixture
def project(tmp_path, monkeypatch):
    """conftest already points HOME at a tmp dir; this is the .co inside it."""
    from connectonion import address

    co = tmp_path / ".co"
    co.mkdir()
    address.save(address.generate(), co)
    return co


def _authenticate_against(response, co_dir, monkeypatch) -> bool:
    monkeypatch.setattr(auth_commands.requests, "post", lambda *a, **k: response)
    return auth_commands.authenticate(co_dir, save_to_project=False)


class TestAGatewayErrorPage:

    HTML = "<html><head><title>502 Bad Gateway</title></head><body>…</body></html>"

    def test_it_does_not_raise(self, project, monkeypatch):
        assert _authenticate_against(FakeResponse(502, self.HTML), project, monkeypatch) is False

    def test_the_status_is_reported(self, project, monkeypatch, capsys):
        _authenticate_against(FakeResponse(502, self.HTML), project, monkeypatch)

        printed = capsys.readouterr()
        assert "502" in printed.out + printed.err

    def test_an_empty_body_is_survivable_too(self, project, monkeypatch):
        assert _authenticate_against(FakeResponse(503, ""), project, monkeypatch) is False


class TestAProperJsonError:
    """The backend's own errors still read the way they did."""

    def test_the_detail_is_shown(self, project, monkeypatch, capsys):
        response = FakeResponse(400, '{"detail": "address already registered"}')

        assert _authenticate_against(response, project, monkeypatch) is False

        printed = capsys.readouterr()
        assert "address already registered" in printed.out + printed.err

    def test_json_without_a_detail_field(self, project, monkeypatch):
        response = FakeResponse(400, '{"oops": true}')

        assert _authenticate_against(response, project, monkeypatch) is False

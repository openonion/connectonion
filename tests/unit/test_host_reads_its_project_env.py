"""`python agent.py` reads the project's .env, so the invite code `co create` wrote opens the door.

Found on 1.8.8b7 by a first-run tester:

    co create my-agent && cd my-agent && python agent.py
    ...
    Invite: no one can onboard — CO_INVITE_CODE is not set. Add it to .env,
    or run `co init ./` to mint one.

The generated .env had CO_INVITE_CODE. Nothing read it: load_environment()
reads only ~/.co/keys.env, so the code `co create` minted for the owner opened
nothing, and the banner told them to add a line that was already there.

Precedence, highest first: the process environment (a shell export, systemd's
EnvironmentFile) > the project's .env > ~/.co/keys.env.
"""

import os

import pytest

from connectonion import environment
from connectonion.environment import load_project_env, publish_values

KEYS = ("CO_INVITE_CODE", "MODEL", "OPENONION_API_KEY",
        "GOOGLE_ACCESS_TOKEN", "GOOGLE_REFRESH_TOKEN", "GOOGLE_EMAIL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # delenv records each key, so whatever these tests publish is undone.
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(environment, "_loaded", {})


def test_the_project_env_fills_what_nothing_else_set(tmp_path):
    (tmp_path / ".env").write_text("CO_INVITE_CODE=ABCDE-FGHJK-LMNPQ\n")

    load_project_env(tmp_path / ".env")

    assert os.environ["CO_INVITE_CODE"] == "ABCDE-FGHJK-LMNPQ"


def test_the_project_env_beats_the_global_keys_env(tmp_path):
    publish_values({"MODEL": "from-keys-env"})  # what load_environment() does
    (tmp_path / ".env").write_text("MODEL=from-project\n")

    load_project_env(tmp_path / ".env")

    assert os.environ["MODEL"] == "from-project"


def test_an_explicit_process_value_beats_the_project_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL", "from-shell")
    (tmp_path / ".env").write_text("MODEL=from-project\n")

    load_project_env(tmp_path / ".env")

    assert os.environ["MODEL"] == "from-shell"


def test_a_provider_record_is_taken_whole_not_mixed(tmp_path):
    """Two halves of two Google accounts would be a record for neither."""
    publish_values({"GOOGLE_ACCESS_TOKEN": "global-a", "GOOGLE_EMAIL": "global@x"})
    (tmp_path / ".env").write_text("GOOGLE_ACCESS_TOKEN=project-a\n")

    load_project_env(tmp_path / ".env")

    assert os.environ["GOOGLE_ACCESS_TOKEN"] == "project-a"
    assert "GOOGLE_EMAIL" not in os.environ


def test_no_project_env_is_not_an_error(tmp_path):
    assert load_project_env(tmp_path / ".env") == []


class TestHostUsesIt:
    """The helper is only the fix if host() calls it before the banner."""

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        from connectonion import address

        co = tmp_path / ".co"
        co.mkdir()
        address.save(address.generate(), co)
        (co / "host.yaml").write_text("name: t\nentrypoint: agent.py\nport: 8124\ntrust: careful\n")
        (tmp_path / ".env").write_text("CO_INVITE_CODE=ABCDE-FGHJK-LMNPQ\n")
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_the_banner_says_the_invite_is_set(self, project, monkeypatch, capsys):
        from connectonion import Agent
        from connectonion.network.host import server

        monkeypatch.setattr(server.uvicorn, "run", lambda app, **kw: None)
        server.host(Agent("t", tools=[], model="co/gemini-2.5-flash", api_key="k"),
                    relay_url=None)

        out = " ".join(capsys.readouterr().out.split())
        assert "no one can onboard" not in out
        assert "Invite: set" in out

    def test_the_code_from_the_project_env_is_accepted(self, project, monkeypatch):
        from connectonion import Agent
        from connectonion.network.host import server
        from connectonion.network.trust.fast_rules import _resolve_codes

        monkeypatch.setattr(server.uvicorn, "run", lambda app, **kw: None)
        server.host(Agent("t", tools=[], model="co/gemini-2.5-flash", api_key="k"),
                    relay_url=None)

        assert _resolve_codes(["$CO_INVITE_CODE"]) == ["ABCDE-FGHJK-LMNPQ"]

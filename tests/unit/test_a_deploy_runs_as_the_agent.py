"""A deployed agent runs as itself, not as whoever deployed it.

`co init` copies AGENT_ADDRESS, AGENT_EMAIL, IS_EMAIL_ACTIVE and
OPENONION_API_KEY from ~/.co/keys.env into the project `.env` on purpose — a
project you are developing should run as you, locally, with no second setup
step.

`co deploy --to` then wrote that same file to /etc/connectonion/<agent>.env
verbatim. The server already has its own key in .co/keys/, so the deployed agent
was cryptographically itself and financially its author: AGENT_EMAIL overrode
the mailbox it derives from its own address, and OPENONION_API_KEY billed every
model call to the operator. Nothing failed. One agent ran for nine days that
way, and the spend cannot be split back out afterwards because usage_logs
records no column naming the machine.

These tests look at what the deploy actually sends, not at how it is spelled.
"""

import base64
import subprocess
from unittest.mock import Mock, patch

import pytest

from connectonion.cli.commands import deploy_to_server as dts


OPERATOR = "0x10e68f6dff39ab1c50cc48ea1c74e7fd6ce7269aa6e8123829b344e57d005508"
AGENT = "0xcf1619cb4cd96c6d5bcb8f8a0cac4e7e0091c511fbce329e3acb6b8d4fb0c8c6"

# What `co init` leaves in a project .env, plus the app's own secrets.
PROJECT_ENV = {
    "OPENONION_API_KEY": "eyJ-operators-token",
    "AGENT_ADDRESS": OPERATOR,
    "AGENT_EMAIL": "aaron.xie@mail.openonion.ai",
    "IS_EMAIL_ACTIVE": "true",
    "AGENT_CONFIG_PATH": "/Users/someone/.co",
    "GEMINI_API_KEY": "AIza-app-secret",
    "DATABASE_URL": "postgres://app",
}

AGENT_ACCOUNT = {
    "OPENONION_API_KEY": "eyJ-agents-token",
    "AGENT_ADDRESS": AGENT,
    "AGENT_EMAIL": "0xcf1619cb4c@mail.openonion.ai",
    "IS_EMAIL_ACTIVE": "true",
}


def _ok():
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def _env_written_over_ssh(tmp_path, agent_account):
    """Run the real _sync_env and return the file body it sent to the server."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".env").write_text(
        "".join(f"{k}={v}\n" for k, v in PROJECT_ENV.items()))

    sent = {}

    def fake_ssh(target, script, **kwargs):
        for token in script.split():
            try:
                decoded = base64.b64decode(token.strip("'"), validate=True)
            except Exception:
                continue
            if b"=" in decoded and b"\n" in decoded:
                sent["body"] = decoded.decode()
        return _ok()

    with patch.object(dts, "_ssh", side_effect=fake_ssh):
        assert dts._sync_env("prod", "myagent", project, agent_account)

    return dict(
        line.split("=", 1) for line in sent["body"].strip().splitlines() if line)


def test_the_operators_account_does_not_reach_the_server(tmp_path):
    """The regression. Every one of these four described the operator."""
    written = _env_written_over_ssh(tmp_path, AGENT_ACCOUNT)

    assert OPERATOR not in written.values(), "operator's address was shipped"
    assert "aaron.xie@mail.openonion.ai" not in written.values(), \
        "operator's mailbox was shipped — the agent would send mail as them"
    assert written["OPENONION_API_KEY"] != "eyJ-operators-token", \
        "operator's token was shipped — every model call bills them"


def test_the_agents_own_account_reaches_the_server_instead(tmp_path):
    written = _env_written_over_ssh(tmp_path, AGENT_ACCOUNT)

    assert written["AGENT_ADDRESS"] == AGENT
    assert written["AGENT_EMAIL"] == "0xcf1619cb4c@mail.openonion.ai"
    assert written["OPENONION_API_KEY"] == "eyJ-agents-token"
    assert written["IS_EMAIL_ACTIVE"] == "true"


def test_the_applications_own_secrets_still_travel(tmp_path):
    """Dropping identity must not drop the keys the agent needs to work."""
    written = _env_written_over_ssh(tmp_path, AGENT_ACCOUNT)

    assert written["GEMINI_API_KEY"] == "AIza-app-secret"
    assert written["DATABASE_URL"] == "postgres://app"
    assert written["AGENT_CONFIG_PATH"] == "/srv/myagent/.co", \
        "still corrected for the machine it is going to"


def test_without_an_account_the_operators_identity_is_still_dropped(tmp_path):
    """`--own-identity`, or an auth that failed.

    An agent with no account cannot call co/* models, which is visible and
    fixable. An agent quietly spending someone else's credits is neither.
    """
    written = _env_written_over_ssh(tmp_path, None)

    assert "OPENONION_API_KEY" not in written
    assert "AGENT_EMAIL" not in written
    assert OPERATOR not in written.values()
    assert written["GEMINI_API_KEY"] == "AIza-app-secret"


def test_a_project_with_no_env_still_gets_its_account(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    sent = {}

    def fake_ssh(target, script, **kwargs):
        for token in script.split():
            try:
                decoded = base64.b64decode(token.strip("'"), validate=True)
            except Exception:
                continue
            if b"=" in decoded and b"\n" in decoded:
                sent["body"] = decoded.decode()
        return _ok()

    with patch.object(dts, "_ssh", side_effect=fake_ssh):
        assert dts._sync_env("prod", "myagent", project, AGENT_ACCOUNT)

    assert "eyJ-agents-token" in sent["body"]


def test_failed_remote_auth_clears_old_account_metadata(tmp_path):
    """Omitting new fields is insufficient if yesterday's env file survives."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".env").write_text(
        f"OPENONION_API_KEY=stale-token\nAGENT_ADDRESS={OPERATOR}\n"
    )

    with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
        assert dts._sync_env("prod", "myagent", project, None)

    script = ssh.call_args.args[1]
    assert dts.ENV_FILE_TEMPLATE.format(agent="myagent") in script
    assert "stale-token" not in script
    assert "printf %s '' | base64 -d" in script


class TestAgentAccount:
    """Authenticating as the agent, from the key this machine derived."""

    IDENTITY = {"address": AGENT, "key_bytes": bytes(32)}

    def _response(self, status=200, payload=None):
        response = Mock()
        response.status_code = status
        response.json.return_value = payload or {}
        return response

    def test_it_signs_as_the_agent_not_the_operator(self):
        with patch("requests.post") as post:
            post.return_value = self._response(payload={
                "token": "eyJ-agents-token",
                "user": {"email": {"address": "0xcf1619cb4c@mail.openonion.ai"}},
            })
            dts._agent_account(self.IDENTITY)

        body = post.call_args.kwargs["json"]
        assert body["public_key"] == AGENT
        assert body["message"].startswith(f"ConnectOnion-Auth-{AGENT}-")

    def test_the_mailbox_comes_from_the_backend(self):
        """The backend routes the mail, so it decides the address.

        The local fallback format (`address[:10]`) has not always agreed with
        what the backend issues, and a computed-but-wrong mailbox fails by
        silently not receiving.
        """
        with patch("requests.post") as post:
            post.return_value = self._response(payload={
                "token": "t",
                "user": {"email": {"address": "0xcf1619cb4c@mail.openonion.ai"}},
            })
            account = dts._agent_account(self.IDENTITY)

        assert account["AGENT_EMAIL"] == "0xcf1619cb4c@mail.openonion.ai"

    def test_a_refused_auth_yields_no_account(self):
        """Rather than falling back to whatever was in the project .env."""
        with patch("requests.post") as post:
            post.return_value = self._response(status=401)
            assert dts._agent_account(self.IDENTITY) is None

    def test_an_unreachable_backend_yields_no_account(self):
        import requests as requests_module

        with patch("requests.post",
                   side_effect=requests_module.exceptions.ConnectionError()):
            assert dts._agent_account(self.IDENTITY) is None


def test_init_and_deploy_read_one_definition_of_identity():
    """`co init` propagates exactly the keys `co deploy --to` withholds.

    Two lists of "what counts as identity" drift, and the one that drifts is the
    one nobody is looking at. Restating them separately is how this bug would
    come back with a fifth key.
    """
    import inspect

    from connectonion.cli.commands import init as init_module
    from connectonion.cli.commands.env_inheritance import AGENT_IDENTITY_KEYS

    source = inspect.getsource(init_module.handle_init)
    assert "AGENT_IDENTITY_KEYS" in source, \
        "co init should use the shared constant, not its own copy"
    assert dts.is_operator_identity(AGENT_IDENTITY_KEYS[0])

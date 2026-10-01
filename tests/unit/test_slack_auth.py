"""`co auth slack`: one manifest, tokens pasted (never arguments), each checked by Slack before it is saved (#2051).

LLM-Note: Tests for connectonion/cli/commands/slack_auth.py

What it tests:
- the manifest turns on Socket Mode, subscribes the inbox's events and asks for every bot scope the
  inbox and the read verbs need, plus search:read as a user scope; the link carries it
- tokens on stdin are told apart by prefix, verified (auth.test, apps.connections.open) and written
  to the selected env file; the optional user token is verified the same way
- a token Slack rejects, or a required one missing, exits 1 and writes nothing
- scopes the tokens lack are listed with the reinstall step, and the working tokens are still saved
- no token is ever printed
- `co auth slack` reaches it, and `co auth --help` names it

No network: httpx.MockTransport stands in for slack.com.
"""

import io
import json
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.commands import slack_auth, slack_commands
from connectonion.inbox.slack import INBOX_SCOPES, READ_SCOPES

BOT = "xoxb-1-secret-bot"
APP = "xapp-1-A0-secret-app"
USER = "xoxp-1-secret-user"
ALL_BOT = ",".join(sorted(set(INBOX_SCOPES) | set(READ_SCOPES)))


def slack(bot_scopes=ALL_BOT, user_scopes="search:read,users:read", errors=None):
    """A fake slack.com: auth.test per token, apps.connections.open for the app token."""
    errors = errors or {}
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        token = request.headers["authorization"].removeprefix("Bearer ")
        method = request.url.path.rsplit("/", 1)[1]
        seen.append((method, token[:5]))
        if token in errors:
            return httpx.Response(200, json={"ok": False, "error": errors[token]})
        if method == "apps.connections.open":
            return httpx.Response(200, json={"ok": True, "url": "wss://wss.slack.test/link"})
        scopes = bot_scopes if token.startswith("xoxb-") else user_scopes
        who = "opsbot" if token.startswith("xoxb-") else "aaron"
        return httpx.Response(200, headers={"x-oauth-scopes": scopes},
                              json={"ok": True, "user": who, "team": "Acme", "url": "https://acme.slack.com/"})

    return httpx.MockTransport(answer), seen


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / "co"))
    (tmp_path / "co").mkdir()
    for name in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_USER_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "co" / "keys.env"


def run(monkeypatch, stdin, transport):
    monkeypatch.setattr(slack_commands, "transport", transport)
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    slack_auth.handle_slack_auth()


class TestTheManifest:
    def test_it_configures_the_inbox_and_every_read_scope(self):
        manifest = slack_auth.MANIFEST
        assert manifest["settings"]["socket_mode_enabled"] is True
        assert {"app_mention", "message.im"} <= set(manifest["settings"]["event_subscriptions"]["bot_events"])
        assert set(INBOX_SCOPES) | set(READ_SCOPES) <= set(manifest["oauth_config"]["scopes"]["bot"])
        assert "search:read" in manifest["oauth_config"]["scopes"]["user"]
        assert manifest["features"]["app_home"]["messages_tab_enabled"] is True

    def test_the_link_carries_it(self):
        query = parse_qs(urlparse(slack_auth.manifest_link()).query)
        assert query["new_app"] == ["1"]
        assert json.loads(unquote(query["manifest_json"][0])) == slack_auth.MANIFEST


class TestSetup:
    def test_tokens_on_stdin_are_verified_and_saved(self, home, monkeypatch, capsys):
        transport, seen = slack()
        run(monkeypatch, f"{APP}\n{BOT}\n{USER}\n", transport)

        saved = home.read_text()
        assert f"SLACK_BOT_TOKEN={BOT}" in saved and f"SLACK_APP_TOKEN={APP}" in saved
        assert f"SLACK_USER_TOKEN={USER}" in saved
        assert ("auth.test", "xoxb-") in seen and ("apps.connections.open", "xapp-") in seen
        assert ("auth.test", "xoxp-") in seen
        out = capsys.readouterr().out
        assert "✓ bot opsbot in Acme" in out and "/invite @opsbot" in out and "Next: co slack check" in out
        assert "Missing" not in out

    def test_the_user_token_is_optional(self, home, monkeypatch):
        transport, seen = slack()
        run(monkeypatch, f"{BOT} {APP}", transport)
        assert "SLACK_USER_TOKEN" not in home.read_text()
        assert all(prefix != "xoxp-" for _, prefix in seen)

    def test_a_rejected_token_saves_nothing(self, home, monkeypatch, capsys):
        transport, _ = slack(errors={APP: "invalid_auth"})
        with pytest.raises(SystemExit) as exit_:
            run(monkeypatch, f"{BOT}\n{APP}\n", transport)
        assert exit_.value.code == 1
        err = capsys.readouterr().err
        assert "SLACK_APP_TOKEN" in err and "invalid_auth" in err and "Nothing was saved" in err
        assert not home.exists()

    def test_a_missing_required_token_saves_nothing(self, home, monkeypatch, capsys):
        transport, seen = slack()
        with pytest.raises(SystemExit) as exit_:
            run(monkeypatch, BOT, transport)
        assert exit_.value.code == 1
        assert "xapp-" in capsys.readouterr().err and seen == [] and not home.exists()

    def test_a_token_already_set_is_kept_and_checked(self, home, monkeypatch, capsys):
        monkeypatch.setenv("SLACK_APP_TOKEN", APP)
        transport, seen = slack()
        run(monkeypatch, BOT, transport)
        assert ("apps.connections.open", "xapp-") in seen
        assert "SLACK_APP_TOKEN" not in home.read_text()  # it was not pasted, so not rewritten

    def test_missing_scopes_are_named_and_the_tokens_still_saved(self, home, monkeypatch, capsys):
        transport, _ = slack(bot_scopes="chat:write,im:history,app_mentions:read", user_scopes="users:read")
        run(monkeypatch, f"{BOT} {APP} {USER}", transport)
        out = capsys.readouterr().out
        assert "Missing Bot Token Scopes:" in out and "channels:read" in out
        assert "Missing User Token Scopes: search:read" in out and "Reinstall to Workspace" in out
        assert f"SLACK_BOT_TOKEN={BOT}" in home.read_text()

    def test_no_token_is_ever_printed(self, home, monkeypatch, capsys):
        transport, _ = slack(errors={USER: "invalid_auth"})
        with pytest.raises(SystemExit):
            run(monkeypatch, f"{BOT} {APP} {USER}", transport)
        printed = "".join(capsys.readouterr())
        assert not any(token in printed for token in (BOT, APP, USER))


class TestTheCommand:
    def test_co_auth_slack_reaches_it(self, home, monkeypatch):
        from connectonion.cli.main import app

        transport, _ = slack()
        monkeypatch.setattr(slack_commands, "transport", transport)
        result = CliRunner().invoke(app, ["auth", "slack"], input=f"{BOT}\n{APP}\n")
        assert result.exit_code == 0, result.output
        assert f"SLACK_BOT_TOKEN={BOT}" in home.read_text()

    def test_auth_help_names_slack(self):
        from connectonion.cli.main import app

        page = CliRunner().invoke(app, ["auth", "--help"], env={"COLUMNS": "200"}).output
        assert "slack" in page

"""`co slack channels | history | thread | search` against a fake Slack Web API (#2051).

LLM-Note: Tests for connectonion/cli/commands/slack_commands.py

What it tests:
- channels: the bot's channels and IMs from conversations.list, IMs named by person, --json lines
- history: '#name' resolved to an id, oldest first, -n across pages, user ids and <@U…> mentions
  resolved to display names with one users.info per person, reply counts, --json
- thread: a reply's ts reads the whole thread from its root; a bad id is a usage error
- search: needs SLACK_USER_TOKEN (exit 1 naming token, scope and co auth slack, no request);
  in:/from: modifiers, the thread root from the permalink, the user token only for search.messages
  and the bot token for names (a user token with just search:read is enough)
- the Next: line comes after the results in a pipe, and on stderr under --json
- tokens saved with `co env set --secret` are found (environment.setting)
- Slack's ok:false (missing_scope, not_in_channel, channel_not_found, invalid_auth) → one
  sentence with the next command, exit 1; one HTTP 429 waited out
- `co slack check` names the read scopes the bot token lacks, from x-oauth-scopes

No network: httpx.MockTransport stands in for slack.com.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.commands import slack_commands
from connectonion.inbox import slack as slack_module
from connectonion.inbox.slack import READ_SCOPES, Slack

BOT = "xoxb-secret-bot-token"
USER = "xoxp-secret-user-token"
OPS = "C0OPS00001"

PEOPLE = {
    "U0ALICE001": {"name": "alice", "profile": {"display_name": "Alice", "real_name": "Alice Wu"}},
    "U0BOB00001": {"name": "bob", "profile": {"display_name": "", "real_name": "Bob Li"}},
}
CHANNELS = [
    {"id": OPS, "name": "ops", "is_channel": True, "is_member": True, "num_members": 12},
    {"id": "C0RANDOM01", "name": "random", "is_channel": True, "is_member": False, "num_members": 80},
    {"id": "G0SECRET01", "name": "secret", "is_private": True, "is_member": True, "num_members": 3},
    {"id": "D0DIRECT01", "is_im": True, "user": "U0ALICE001"},
]
# conversations.history answers newest first.
HISTORY = [
    {"type": "message", "user": "U0BOB00001", "text": "on it", "ts": "1727500300.000300"},
    {"type": "message", "user": "U0ALICE001", "text": "<@U0BOB00001> deploy failed", "ts": "1727500200.000200",
     "thread_ts": "1727500200.000200", "reply_count": 2},
    {"type": "message", "bot_id": "B0BOT", "bot_profile": {"name": "CI"}, "text": "build 41 red",
     "ts": "1727500100.000100"},
]


class FakeSlack:
    """slack.com/api: answers per method, records every request."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        params = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.requests.append((method, params, request.headers.get("authorization")))
        answer = self.answers.get(method)
        if callable(answer):
            answer = answer(params)
        if answer is None:
            answer = self.default(method, params)
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer)

    def default(self, method, params):
        if method == "users.info":
            return {"ok": True, "user": {"id": params["user"], **PEOPLE[params["user"]]}}
        if method == "conversations.list":
            return {"ok": True, "channels": CHANNELS}
        if method == "conversations.history":
            return {"ok": True, "messages": HISTORY}
        raise AssertionError(f"unexpected {method}")

    def methods(self):
        return [method for method, _, _ in self.requests]


@pytest.fixture
def slack(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", BOT)
    monkeypatch.delenv("SLACK_USER_TOKEN", raising=False)
    fake = FakeSlack()
    monkeypatch.setattr(slack_commands, "transport", httpx.MockTransport(fake))
    return fake


def json_lines(out):
    return [json.loads(line) for line in out.splitlines() if line.strip()]


class TestChannels:
    def test_lists_the_bots_channels_and_dms_with_people_named(self, slack, capsys):
        slack_commands.handle_channels(json_output=False)
        *rows, tip = [line.split("\t") for line in capsys.readouterr().out.splitlines()]
        assert tip == ["Next: co slack history <channel> -n 50"]
        assert rows == [[OPS, "#ops", "public", "12 members"],
                        ["G0SECRET01", "#secret", "private", "3 members"],
                        ["D0DIRECT01", "@Alice", "im", ""]]
        listed = dict((m, p) for m, p, _ in slack.requests)["conversations.list"]
        assert listed["types"] == "public_channel,private_channel,im"

    def test_json_is_one_object_per_line(self, slack, capsys):
        slack_commands.handle_channels(json_output=True)
        rows = json_lines(capsys.readouterr().out)
        assert rows[0] == {"id": OPS, "name": "#ops", "kind": "public", "members": 12}
        assert rows[2]["kind"] == "im" and rows[2]["members"] is None


class TestHistory:
    def test_a_name_resolves_and_messages_read_oldest_first_with_names(self, slack, capsys):
        slack_commands.handle_history("#ops", 50, json_output=True)
        records = json_lines(capsys.readouterr().out)

        assert [r["text"] for r in records] == ["build 41 red", "@Bob Li deploy failed", "on it"]
        assert [r["sender_name"] for r in records] == ["CI", "Alice", "Bob Li"]
        assert records[1] == {"id": f"{OPS}:1727500200.000200", "chat": OPS, "thread": None,
                              "at": "2024-09-28T05:10:00Z", "sender": "U0ALICE001",
                              "sender_name": "Alice", "text": "@Bob Li deploy failed", "replies": 2}
        history = [p for m, p, _ in slack.requests if m == "conversations.history"]
        assert history[0]["channel"] == OPS

    def test_each_person_is_looked_up_once(self, slack, capsys):
        slack_commands.handle_history(OPS, 50, json_output=False)
        looked_up = [p["user"] for m, p, _ in slack.requests if m == "users.info"]
        assert sorted(looked_up) == ["U0ALICE001", "U0BOB00001"]
        assert "conversations.list" not in slack.methods()  # an id needs no lookup

    def test_the_plain_view_has_time_author_id_and_reply_count(self, slack, capsys):
        slack_commands.handle_history("ops", 50, json_output=False)
        out = capsys.readouterr().out
        assert f"Alice  {OPS}:1727500200.000200  (2 replies)" in out
        assert "\n  @Bob Li deploy failed\n" in out

    def test_one_reply_is_singular(self, slack, capsys):
        slack.answers["conversations.history"] = {"ok": True, "messages": [dict(HISTORY[1], reply_count=1)]}
        slack_commands.handle_history(OPS, 50, json_output=False)
        assert "(1 reply)" in capsys.readouterr().out

    def test_n_follows_the_cursor_and_stops_at_n(self, slack, capsys):
        pages = iter([{"ok": True, "messages": HISTORY[:2], "response_metadata": {"next_cursor": "p2"}},
                      {"ok": True, "messages": HISTORY[2:], "response_metadata": {"next_cursor": "p3"}}])
        slack.answers["conversations.history"] = lambda params: next(pages)
        slack_commands.handle_history(OPS, 3, json_output=True)
        assert len(json_lines(capsys.readouterr().out)) == 3
        calls = [p for m, p, _ in slack.requests if m == "conversations.history"]
        assert [c.get("cursor") for c in calls] == [None, "p2"] and calls[0]["limit"] == "3"

    def test_an_unknown_name_points_to_channels(self, slack, capsys):
        with pytest.raises(SystemExit) as exit_:
            slack_commands.handle_history("#nope", 50, json_output=False)
        assert exit_.value.code == 1
        assert "Next: co slack channels" in capsys.readouterr().err


class TestThread:
    def test_a_replys_id_reads_the_whole_thread_from_its_root(self, slack, capsys):
        root = {"user": "U0ALICE001", "text": "deploy failed", "ts": "1727500200.000200",
                "thread_ts": "1727500200.000200", "reply_count": 1}
        reply = {"user": "U0BOB00001", "text": "rolled back", "ts": "1727500250.000250",
                 "thread_ts": "1727500200.000200"}
        slack.answers["conversations.replies"] = lambda params: (
            {"ok": True, "messages": [reply]} if params["ts"] == reply["ts"]
            else {"ok": True, "messages": [root, reply]})

        slack_commands.handle_thread(f"{OPS}:1727500250.000250", json_output=True)

        records = json_lines(capsys.readouterr().out)
        assert [r["text"] for r in records] == ["deploy failed", "rolled back"]
        assert records[1]["thread"] == "1727500200.000200" and records[0]["thread"] is None
        asked = [p["ts"] for m, p, _ in slack.requests if m == "conversations.replies"]
        assert asked == ["1727500250.000250", "1727500200.000200"]

    def test_not_a_message_id_is_a_usage_error(self, slack, capsys):
        with pytest.raises(SystemExit) as exit_:
            slack_commands.handle_thread("1727500200.000200", json_output=False)
        assert exit_.value.code == 2
        assert "C0123456789:1727500000.123456" in capsys.readouterr().err
        assert slack.requests == []


class TestSearch:
    MATCH = {"channel": {"id": OPS, "name": "ops"}, "user": "U0ALICE001", "username": "alice",
             "ts": "1727500250.000250", "text": "deploy failed again",
             "permalink": f"https://acme.slack.com/archives/{OPS}/p1727500250000250"
                          "?thread_ts=1727500200.000200&cid=C0OPS00001"}

    def test_without_a_user_token_it_names_token_scope_and_command(self, slack, capsys):
        with pytest.raises(SystemExit) as exit_:
            slack_commands.handle_search("deploy", None, None, 20, json_output=False)
        err = capsys.readouterr().err
        assert exit_.value.code == 1
        assert "SLACK_USER_TOKEN" in err and "search:read" in err and "Next: co auth slack" in err
        assert slack.requests == []

    def test_a_bot_token_in_the_user_slot_is_caught(self, slack, monkeypatch, capsys):
        monkeypatch.setenv("SLACK_USER_TOKEN", BOT)
        with pytest.raises(SystemExit):
            slack_commands.handle_search("deploy", None, None, 20, json_output=False)
        err = capsys.readouterr().err
        assert "xoxp-" in err and BOT not in err

    def test_modifiers_thread_and_the_user_token(self, slack, monkeypatch, capsys):
        monkeypatch.setenv("SLACK_USER_TOKEN", USER)
        slack.answers["search.messages"] = {"ok": True, "messages": {"matches": [self.MATCH]}}

        slack_commands.handle_search("deploy failed", "#ops", "@alice", 5, json_output=True)

        method, params, auth = slack.requests[0]
        assert method == "search.messages" and auth == f"Bearer {USER}"
        assert {auth for m, _, auth in slack.requests if m == "users.info"} == {f"Bearer {BOT}"}
        assert params["query"] == "deploy failed in:#ops from:@alice"
        assert params["count"] == "5" and params["sort"] == "timestamp"
        [record] = json_lines(capsys.readouterr().out)
        assert record["id"] == f"{OPS}:1727500250.000250" and record["chat_name"] == "ops"
        assert record["thread"] == "1727500200.000200" and record["sender_name"] == "Alice"
        assert "replies" not in record

    def test_ids_use_slacks_own_reference_syntax(self):
        query = slack_commands.search_query("x", "C0OPS00001", "U0ALICE001")
        assert query == "x in:<#C0OPS00001> from:<@U0ALICE001>"


class TestRefusals:
    @pytest.mark.parametrize("answer, words", [
        ({"ok": False, "error": "missing_scope", "needed": "channels:history", "provided": "chat:write"},
         ["channels:history", "Bot Token Scopes", "Reinstall to Workspace", "Next: co slack check"]),
        ({"ok": False, "error": "not_in_channel"}, [OPS, "/invite", "Next: co slack channels"]),
        ({"ok": False, "error": "channel_not_found"}, [OPS, "Next: co slack channels"]),
        ({"ok": False, "error": "invalid_auth"}, ["SLACK_BOT_TOKEN", "invalid_auth", "Next: co auth slack"]),
    ])
    def test_each_refusal_is_one_sentence_and_a_next_command(self, slack, capsys, answer, words):
        slack.answers["conversations.history"] = answer
        with pytest.raises(SystemExit) as exit_:
            slack_commands.handle_history(OPS, 50, json_output=False)
        err = capsys.readouterr().err
        assert exit_.value.code == 1
        assert all(word in err for word in words), err
        assert BOT not in err

    def test_no_bot_token_names_co_auth_slack(self, slack, monkeypatch, capsys):
        monkeypatch.delenv("SLACK_BOT_TOKEN")
        with pytest.raises(SystemExit) as exit_:
            slack_commands.handle_channels(json_output=False)
        assert exit_.value.code == 1 and "Next: co auth slack" in capsys.readouterr().err
        assert slack.requests == []

    def test_one_rate_limit_is_waited_out(self, slack, monkeypatch, capsys):
        waits = []
        monkeypatch.setattr(slack_commands.time, "sleep", waits.append)
        answers = iter([httpx.Response(429, headers={"Retry-After": "2"}, json={"ok": False, "error": "ratelimited"}),
                        {"ok": True, "channels": CHANNELS}])
        slack.answers["conversations.list"] = lambda params: next(answers)
        slack_commands.handle_channels(json_output=True)
        assert waits == [2.0] and len(json_lines(capsys.readouterr().out)) == 3


class TestTheCommandLine:
    def test_json_stdout_stays_parseable_with_the_next_tip(self, slack):
        from connectonion.cli.main import app

        result = CliRunner().invoke(app, ["slack", "history", OPS, "--json"])
        assert result.exit_code == 0, result.output
        lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
        assert len(lines) == 3

    @pytest.mark.parametrize("args", [["channels"], ["history", OPS], ["thread", f"{OPS}:1727500200.000200"],
                                      ["history", OPS, "--json"]])
    def test_next_comes_after_the_results_when_piped(self, slack, args):
        import subprocess
        import sys

        # Through a real pipe, stdout and stderr into one file, as an agent captures it.
        code = ("import httpx, sys; from connectonion.cli.commands import slack_commands as s; "
                "from tests.unit.test_slack_read_commands import FakeSlack, HISTORY; f = FakeSlack(); "
                "f.answers['conversations.replies'] = {'ok': True, 'messages': [HISTORY[1]]}; "
                "s.transport = httpx.MockTransport(f); from connectonion.cli.main import cli; "
                f"sys.argv = ['co', 'slack', *{args!r}]; cli()")
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE, cwd=root,
                                stderr=subprocess.STDOUT, text=True, timeout=120)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert result.returncode == 0, result.stdout
        assert lines[-1].startswith("Next: ") and sum(line.startswith("Next:") for line in lines) == 1

    def test_under_json_next_goes_to_stderr(self, slack, capsys):
        slack_commands.handle_history(OPS, 50, json_output=True)
        out, err = capsys.readouterr()
        assert "Next:" not in out and f"Next: co slack thread {OPS}:1727500200.000200" in err

    def test_every_read_verb_has_a_next_step(self):
        from connectonion.cli.commands.command_tips import NEXT

        for verb in ("channels", "history", "thread", "search"):
            assert f"co slack {verb}" in NEXT  # HANDLER: the handler prints it after the results


class TestSecretTokens:
    def test_a_token_saved_with_secret_is_read(self, slack, monkeypatch, tmp_path, capsys):
        from connectonion import address, secret_store

        phrase = "legal winner thank year wave sausage worth useful legal winner thank yellow"
        (tmp_path / "keys").mkdir()
        (tmp_path / "keys" / "agent.key").write_bytes(bytes(address.recover(phrase)["signing_key"]))
        monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path))
        monkeypatch.delenv("SLACK_BOT_TOKEN")
        secret_store.put(tmp_path, "SLACK_BOT_TOKEN", BOT)

        slack_commands.handle_channels(json_output=True)

        assert slack.requests[0][2] == f"Bearer {BOT}"
        assert Slack().bot_token == BOT


class Response:
    def __init__(self, payload, headers):
        self.status_code = 200
        self.payload = payload
        self.headers = headers

    def json(self):
        return self.payload


class TestCheckNamesMissingReadScopes:
    def _check(self, monkeypatch, scopes):
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-1-secret")
        monkeypatch.setenv("SLACK_BOT_TOKEN", BOT)
        monkeypatch.setattr(slack_module.requests, "post", lambda url, **kwargs: Response(
            {"ok": True, "user_id": "U0BOT", "user": "opsbot", "url": "wss://x"},
            {"x-oauth-scopes": ",".join(scopes)}))
        bot = Slack()
        assert bot.check() == []
        return bot.advice()

    def test_the_missing_ones_and_the_reinstall_step(self, monkeypatch):
        monkeypatch.setenv("SLACK_USER_TOKEN", USER)
        [line] = self._check(monkeypatch, ["chat:write", "im:history", "app_mentions:read"])
        assert "channels:read" in line and "users:read" in line and "Reinstall to Workspace" in line
        assert "im:history" not in line

    def test_nothing_to_say_when_everything_is_there(self, monkeypatch):
        monkeypatch.setenv("SLACK_USER_TOKEN", USER)
        assert self._check(monkeypatch, list(READ_SCOPES)) == []

    def test_a_missing_search_token_is_mentioned_not_failed(self, monkeypatch):
        monkeypatch.delenv("SLACK_USER_TOKEN", raising=False)
        [line] = self._check(monkeypatch, list(READ_SCOPES))
        assert "SLACK_USER_TOKEN" in line and "co auth slack" in line

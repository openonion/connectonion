"""Microsoft Teams chats, teams and channels for agents and the terminal (#1907).

Work or school Microsoft accounts (`co auth microsoft`) can list and read 1:1,
group and meeting chats, send plain-text chat messages with explicit approval,
and list joined teams and their channels. Personal Microsoft accounts (MSA
tenant 9188040d-6c67-4c5b-b112-36a304b66dad) are refused before calling Graph.
"""

import base64
import json
import os
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest


MSA_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"
WORK_TENANT_ID = "72f988bf-86f1-41af-91ab-2d7cd011db47"
FULL_SCOPES = "Mail.ReadWrite,Chat.Read,ChatMessage.Send,Team.ReadBasic.All,Channel.ReadBasic.All"


def _jwt(claims: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{header}.{body}.signature"


WORK_TOKEN = _jwt({
    "tid": WORK_TENANT_ID,
    "oid": "00000000-0000-0000-0000-000000000001",
    "upn": "ada@contoso.example",
    "scp": "Chat.Read ChatMessage.Send Team.ReadBasic.All Channel.ReadBasic.All",
})
MSA_TOKEN = _jwt({
    "tid": MSA_TENANT_ID,
    "sub": "consumer-subject",
    "iss": f"https://login.microsoftonline.com/{MSA_TENANT_ID}/v2.0",
})
GUEST_IN_WORK_TENANT_TOKEN = _jwt({
    "tid": WORK_TENANT_ID,
    "idp": f"https://sts.windows.net/{MSA_TENANT_ID}/",
    "oid": "00000000-0000-0000-0000-000000000002",
    "upn": "guest_outlook.com#EXT#@contoso.example",
})


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("MICROSOFT_SCOPES", FULL_SCOPES)
    monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", WORK_TOKEN)
    monkeypatch.setenv("MICROSOFT_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("MICROSOFT_EMAIL", "ada@contoso.example")
    from connectonion.useful_tools.outlook import Outlook
    monkeypatch.setattr(Outlook, "_refresh_via_backend", lambda self, rt: WORK_TOKEN)


def _graph(routes):
    """httpx.request stand-in: {(METHOD, path suffix): (status, json-body)}; records calls."""
    calls = []

    def request(method, url, headers=None, **kwargs):
        calls.append((method, url, headers, kwargs))
        path = url.split("?")[0]
        for (m, suffix), (status, body) in routes.items():
            if m == method and path.endswith(suffix):
                response = MagicMock(status_code=status, headers={})
                response.text = json.dumps(body) if body is not None else ""
                response.json = MagicMock(return_value=body)
                return response
        raise AssertionError(f"unexpected {method} {url}")

    return request, calls


SAMPLE_CHATS = {
    "value": [
        {
            "id": "19:chat-unread@thread.v2",
            "topic": "Release planning",
            "chatType": "group",
            "webUrl": "https://teams.microsoft.com/l/chat/19:chat-unread@thread.v2",
            "viewpoint": {"lastMessageReadDateTime": "2026-11-24T20:00:00.0000000Z"},
            "lastMessagePreview": {
                "id": "m2",
                "createdDateTime": "2026-11-25T01:30:00.1234567Z",
                "body": {"contentType": "html", "content": "<p>RC27 is green &amp; ready</p>"},
                "from": {"user": {"id": "u2", "displayName": "Grace Hopper"}},
            },
        },
        {
            "id": "19:chat-read@thread.v2",
            "topic": None,
            "chatType": "oneOnOne",
            "viewpoint": {"lastMessageReadDateTime": "2026-11-23T12:00:00Z"},
            "lastMessagePreview": {
                "id": "m1",
                "createdDateTime": "2026-11-23T10:00:00Z",
                "body": {"contentType": "html", "content": "<div>See you tomorrow</div>"},
                "from": {"user": {"id": "u3", "displayName": "Alan Turing"}},
            },
        },
    ]
}

SAMPLE_MESSAGES = {
    "value": [
        {
            "id": "msg-newest",
            "messageType": "message",
            "createdDateTime": "2026-11-25T01:35:00Z",
            "from": {"user": {"id": "u1", "displayName": "Ada Lovelace"}},
            "body": {
                "contentType": "html",
                "content": '<p><at id="0">Grace Hopper</at> ship it!<br/>Logs&nbsp;attached</p>'
                           '<attachment id="att1"></attachment>',
            },
            "attachments": [{"id": "att1", "name": "build.log"}],
        },
        {
            "id": "msg-oldest",
            "messageType": "message",
            "createdDateTime": "2026-11-25T01:30:00Z",
            "from": {"user": {"id": "u2", "displayName": "Grace Hopper"}},
            "body": {
                "contentType": "html",
                "content": "<html><body><script>evil()</script><p>RC27 is green &amp; ready</p></body></html>",
            },
        },
    ]
}

SAMPLE_TEAMS = {
    "value": [
        {"id": "team-1", "displayName": "Engineering", "description": "Core platform"},
        {"id": "team-2", "displayName": "Operations", "description": "Incident response"},
    ]
}

SAMPLE_CHANNELS = {
    "value": [
        {"id": "19:gen@thread.tacv2", "displayName": "General", "membershipType": "standard"},
        {"id": "19:sec@thread.tacv2", "displayName": "Security", "membershipType": "private"},
    ]
}


class TestPersonalAccountRefusal:
    """Personal Microsoft accounts (MSA tenant 9188040d-6c67-4c5b-b112-36a304b66dad) stop before Graph."""

    @pytest.mark.parametrize("call", [
        lambda t: t.list_chats(),
        lambda t: t.read_chat("19:chat@thread.v2"),
        lambda t: t.send_message("19:chat@thread.v2", "hello"),
        lambda t: t.list_teams(),
        lambda t: t.list_channels("team-1"),
    ])
    def test_msa_jwt_tenant_is_refused_before_any_graph_call(self, call):
        from connectonion.useful_tools.teams import Teams

        request, calls = _graph({})
        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": MSA_TOKEN, "MICROSOFT_SCOPES": "Mail.ReadWrite"}), \
                patch("connectonion.useful_tools.outlook.httpx.request", request):
            with pytest.raises(ValueError) as refused:
                call(Teams())
        message = str(refused.value)
        assert calls == []
        assert "work or school" in message
        assert MSA_TENANT_ID in message
        assert "co auth microsoft" in message

    def test_msa_compact_ticket_is_refused_before_any_graph_call(self):
        from connectonion.useful_tools.teams import Teams

        request, calls = _graph({})
        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": "EwB4A8l6BAAUcompactticket"}), \
                patch("connectonion.useful_tools.outlook.httpx.request", request):
            with pytest.raises(ValueError, match="work or school"):
                Teams().list_chats()
        assert calls == []

    def test_guest_user_signed_into_a_work_tenant_is_allowed(self):
        from connectonion.useful_tools.teams import Teams

        request, calls = _graph({("GET", "/me/joinedTeams"): (200, SAMPLE_TEAMS)})
        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": GUEST_IN_WORK_TENANT_TOKEN}), \
                patch("connectonion.useful_tools.outlook.httpx.request", request):
            output = Teams().list_teams()
        assert "Engineering" in output
        assert len(calls) == 1


class TestTeamsCheck:

    def test_check_reports_work_tenant_and_granted_scopes(self):
        from connectonion.useful_tools.teams import Teams

        status = Teams().check()
        assert status["ok"] is True
        assert status["tenant_kind"] == "work_or_school"
        assert status["tenant_id"] == WORK_TENANT_ID
        assert status["token"]["configured"] is True
        assert status["scopes"] == {
            "Chat.Read": True,
            "ChatMessage.Send": True,
            "Team.ReadBasic.All": True,
            "Channel.ReadBasic.All": True,
        }

    def test_check_reports_personal_tenant_as_not_ok_without_calling_graph(self):
        from connectonion.useful_tools.teams import Teams

        request, calls = _graph({})
        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": MSA_TOKEN}), \
                patch("connectonion.useful_tools.outlook.httpx.request", request):
            status = Teams().check()
        assert calls == []
        assert status["ok"] is False
        assert status["tenant_kind"] == "personal"
        assert status["tenant_id"] == MSA_TENANT_ID

    def test_check_reports_missing_send_scope_accurately(self):
        from connectonion.useful_tools.teams import Teams

        token = _jwt({"tid": WORK_TENANT_ID, "scp": "Chat.Read"})
        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": token, "MICROSOFT_SCOPES": "Chat.Read"}):
            status = Teams().check()
        assert status["ok"] is True
        assert status["scopes"]["Chat.Read"] is True
        assert status["scopes"]["ChatMessage.Send"] is False
        assert status["scopes"]["Team.ReadBasic.All"] is False
        assert status["scopes"]["Channel.ReadBasic.All"] is False


class TestChatsAndMessages:

    def test_list_chats_expands_preview_orders_desc_and_marks_unread(self):
        from connectonion.useful_tools.teams import Teams

        request, calls = _graph({("GET", "/me/chats"): (200, SAMPLE_CHATS)})
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            teams = Teams()
            items = teams.chat_items(limit=15)
            rendered = teams.list_chats(limit=15)

        params = calls[0][3]["params"]
        assert params["$expand"] == "lastMessagePreview"
        assert params["$orderby"] == "lastMessagePreview/createdDateTime desc"
        assert params["$top"] == 15
        assert items[0]["id"] == "19:chat-unread@thread.v2"
        assert items[0]["unread"] is True
        assert items[0]["preview"] == "RC27 is green & ready"
        assert items[1]["id"] == "19:chat-read@thread.v2"
        assert items[1]["unread"] is False
        assert items[1]["title"] == "Alan Turing"
        assert "[UNREAD]" in rendered and "Release planning" in rendered

    def test_chat_never_opened_with_preview_is_marked_unread(self):
        from connectonion.useful_tools.teams import Teams

        unread_never_opened = {
            "value": [{
                "id": "19:new@thread.v2",
                "topic": "Incident #42",
                "chatType": "group",
                "viewpoint": {"lastMessageReadDateTime": None},
                "lastMessagePreview": {
                    "id": "m9",
                    "createdDateTime": "2026-11-25T03:00:00Z",
                    "body": {"contentType": "text", "content": "Paging on-call"},
                },
            }]
        }
        request, _ = _graph({("GET", "/me/chats"): (200, unread_never_opened)})
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            items = Teams().chat_items()
        assert items[0]["unread"] is True

    def test_list_chats_since_filters_out_older_conversations(self):
        from connectonion.useful_tools.teams import Teams

        request, _ = _graph({("GET", "/me/chats"): (200, SAMPLE_CHATS)})
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            items = Teams().chat_items(since="2026-11-24T00:00:00Z")
        assert [item["id"] for item in items] == ["19:chat-unread@thread.v2"]

    def test_read_chat_returns_clean_plain_text_in_chronological_order(self):
        from connectonion.useful_tools.teams import Teams

        request, calls = _graph({("GET", "/chats/19:chat-unread@thread.v2/messages"): (200, SAMPLE_MESSAGES)})
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            text = Teams().read_chat("19:chat-unread@thread.v2", limit=10)

        assert calls[0][3]["params"]["$top"] == 10
        assert "<p>" not in text and "<script>" not in text and "evil()" not in text
        assert "RC27 is green & ready" in text
        assert "@Grace Hopper ship it!" in text
        assert "Logs attached" in text
        assert "[attachment: build.log]" in text
        assert text.index("RC27 is green & ready") < text.index("@Grace Hopper ship it!")

    def test_plain_text_message_keeps_angle_brackets(self):
        from connectonion.useful_tools.teams import Teams

        plain = {
            "value": [{
                "id": "m1",
                "messageType": "message",
                "createdDateTime": "2026-11-25T01:00:00Z",
                "from": {"user": {"id": "u1", "displayName": "Ada"}},
                "body": {"contentType": "text", "content": "check x < 10 and y > 20"},
            }]
        }
        request, _ = _graph({("GET", "/chats/19:c1@thread.v2/messages"): (200, plain)})
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            text = Teams().read_chat("19:c1@thread.v2")
        assert "check x < 10 and y > 20" in text


class TestSendMessageAndScopes:

    def test_send_message_requires_chatmessage_send_scope(self):
        from connectonion.useful_tools.teams import Teams

        token = _jwt({"tid": WORK_TENANT_ID, "scp": "Chat.Read"})
        request, calls = _graph({})
        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": token, "MICROSOFT_SCOPES": "Chat.Read"}), \
                patch("connectonion.useful_tools.outlook.httpx.request", request):
            with pytest.raises(ValueError, match="ChatMessage.Send") as refused:
                Teams().send_message("19:chat-unread@thread.v2", "Hello")
        assert "co auth microsoft" in str(refused.value)
        assert calls == []

    def test_send_message_posts_to_chat_messages(self):
        from connectonion.useful_tools.teams import Teams

        request, calls = _graph({
            ("POST", "/chats/19:chat-unread@thread.v2/messages"): (201, {"id": "1732502000000"}),
        })
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            result = Teams().send_message("19:chat-unread@thread.v2", "All tests green")
        method, url, _, kwargs = calls[0]
        assert method == "POST"
        assert url.endswith("/chats/19:chat-unread@thread.v2/messages")
        assert kwargs["json"] == {"body": {"contentType": "text", "content": "All tests green"}}
        assert "1732502000000" in result

    def test_send_timeout_never_suggests_blind_retry(self):
        from connectonion.useful_tools.teams import Teams

        def slow_post(method, url, **kwargs):
            raise httpx.ReadTimeout("timed out")

        with patch("connectonion.useful_tools.outlook.httpx.request", slow_post):
            with pytest.raises(ValueError) as failed:
                Teams().send_message("19:chat-unread@thread.v2", "Deploy started")
        message = str(failed.value)
        assert "may already have been" in message
        assert "co teams read" in message
        assert "Try again: co teams send" not in message


class TestTeamsAndChannels:

    def test_list_teams_and_channels_note_admin_consent_boundary(self):
        from connectonion.useful_tools.teams import Teams

        request, _ = _graph({
            ("GET", "/me/joinedTeams"): (200, SAMPLE_TEAMS),
            ("GET", "/teams/team-1/channels"): (200, SAMPLE_CHANNELS),
        })
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            teams_out = Teams().list_teams()
            channels_out = Teams().list_channels("team-1")
        assert "Engineering" in teams_out and "team-1" in teams_out
        assert "General" in channels_out and "Security" in channels_out
        assert "ChannelMessage.Read.All" in channels_out


class TestExportsAndApprovalPolicy:

    def test_teams_is_exported_and_does_not_leak_outlook_mail_tools(self):
        from connectonion import Agent, Teams
        from connectonion.useful_tools import Teams as UsefulTeams
        from tests.utils.mock_helpers import MockLLM

        assert Teams is UsefulTeams
        agent = Agent("teams-agent", tools=[Teams()], llm=MockLLM(), log=False)
        names = set(agent.tools.names()) if hasattr(agent.tools, "names") else {t.name for t in agent.tools}
        assert {"list_chats", "read_chat", "send_message", "list_teams", "list_channels"} <= names
        assert not ({"archive_email", "send_draft", "delete_draft"} & names)

    def test_send_message_requires_approval_and_acts_as_owner(self, tmp_path, monkeypatch):
        from connectonion import Agent
        from connectonion.core.tool_executor import execute_single_tool
        from connectonion.useful_plugins.tool_approval.policy import evaluate_auto_approve, special_class
        from connectonion.useful_tools.teams import Teams
        from tests.utils.mock_helpers import MockLLM

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".co").mkdir()

        verdict = evaluate_auto_approve("send_message", {"chat_id": "c1", "text": "hi"}, tmp_path)
        assert verdict["decision"] == "ask"
        assert verdict["effect_class"] == "external_effect"
        assert verdict["requires_human"] is True

        cli_verdict = evaluate_auto_approve("bash", {"command": 'co teams send 1 "hi" --yes'}, tmp_path)
        assert cli_verdict["decision"] == "ask"
        assert cli_verdict["effect_class"] == "external_effect"

        assert special_class("send_message", {"chat_id": "c1", "text": "hi"}, owner_class="Teams", root=tmp_path) == "as_owner"
        assert special_class("bash", {"command": 'co teams send 1 "hi" --yes'}, root=tmp_path) == "as_owner"

        agent = Agent("t", tools=[Teams()], llm=MockLLM(), co_dir=tmp_path / ".co")
        agent.current_session = {
            "messages": [], "trace": [], "turn": 1, "iteration": 1,
            "mode": "full_access", "permissions": {},
            "requester": {"address": "feishu:ou_stranger", "level": "open"},
        }
        entry = execute_single_tool(
            tool_name="send_message",
            tool_args={"chat_id": "19:c1@thread.v2", "text": "spoof"},
            tool_id="call-1",
            tools=agent.tools,
            agent=agent,
            logger=agent.logger,
        )
        assert entry["status"] == "error"
        assert "as_owner" in entry["result"]


@pytest.fixture
def cli_listings(monkeypatch, tmp_path):
    from connectonion.cli.commands import teams_commands
    monkeypatch.setattr(teams_commands, "LISTINGS", tmp_path / "teams-listings")
    monkeypatch.setattr(teams_commands, "_account", lambda client: "ada@contoso.example")


class TestTeamsCLI:

    def test_teams_help_lists_all_subcommands(self):
        from typer.testing import CliRunner
        from connectonion.cli.main import app

        result = CliRunner().invoke(app, ["teams", "--help"], env={"COLUMNS": "200"})
        assert result.exit_code == 0, result.output
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert all(verb in plain for verb in ("check", "chats", "ls", "read", "send", "teams", "channels"))

    def test_bare_teams_and_chats_and_ls_list_numbered_chats(self, monkeypatch, cli_listings):
        from typer.testing import CliRunner
        from connectonion.cli.commands import teams_commands
        from connectonion.cli.main import app

        fake = SimpleNamespace(chat_items=lambda limit=20, since=None: [
            {"id": "19:c1@thread.v2", "title": "Release planning", "chat_type": "group",
             "unread": True, "last_message_at": "2026-11-25T01:30:00Z",
             "from": "Grace Hopper", "preview": "RC27 is green"},
        ])
        monkeypatch.setattr(teams_commands, "_teams", lambda: fake)
        runner = CliRunner()
        for argv in (["teams"], ["teams", "chats"], ["teams", "ls"], ["teams", "read"]):
            res = runner.invoke(app, argv)
            assert res.exit_code == 0, res.output
            assert "1." in res.output and "Release planning" in res.output
            assert "[UNREAD]" in res.output
            assert "19:c1@thread.v2" not in res.output
            assert "Next: co teams read 1" in res.output

        with_ids = runner.invoke(app, ["teams", "chats", "--ids"])
        assert "19:c1@thread.v2" in with_ids.output

    def test_numbered_journey_for_chats_and_teams_with_listing_pin(self, monkeypatch, cli_listings):
        from typer.testing import CliRunner
        from connectonion.cli.commands import teams_commands
        from connectonion.cli.main import app

        seen = []
        batches = iter([
            [{"id": "19:first@thread.v2", "title": "First", "chat_type": "oneOnOne", "unread": False,
              "last_message_at": "2026-11-25T01:00:00Z", "from": "Alan", "preview": "Hi"}],
            [{"id": "19:second@thread.v2", "title": "Second", "chat_type": "oneOnOne", "unread": False,
              "last_message_at": "2026-11-25T02:00:00Z", "from": "Grace", "preview": "Yo"}],
        ])
        fake = SimpleNamespace(
            chat_items=lambda limit=20, since=None: next(batches),
            read_chat=lambda chat_id, limit=20: seen.append(("read", chat_id, limit)) or "Conversation body",
            team_items=lambda: SAMPLE_TEAMS["value"],
            channel_items=lambda team_id: seen.append(("channels", team_id)) or SAMPLE_CHANNELS["value"],
        )
        monkeypatch.setattr(teams_commands, "_teams", lambda: fake)
        runner = CliRunner()

        first = runner.invoke(app, ["teams", "chats"])
        token = re.search(r"Listing: ([a-f0-9]{32})", first.output).group(1)
        assert runner.invoke(app, ["teams", "chats"]).exit_code == 0
        pinned = runner.invoke(app, ["teams", "read", "1", "--listing", token])
        assert pinned.exit_code == 0, pinned.output
        latest = runner.invoke(app, ["teams", "read", "1"])
        assert latest.exit_code == 0, latest.output

        listed_teams = runner.invoke(app, ["teams", "teams"])
        assert listed_teams.exit_code == 0, listed_teams.output
        ch = runner.invoke(app, ["teams", "channels", "2"])
        assert ch.exit_code == 0, ch.output
        assert "ChannelMessage.Read.All" in ch.output

        assert seen == [
            ("read", "19:first@thread.v2", 20),
            ("read", "19:second@thread.v2", 20),
            ("channels", "team-2"),
        ]

    def test_empty_relist_account_switch_and_expiry_invalidate_row_numbers(self, monkeypatch, cli_listings):
        from typer.testing import CliRunner
        from connectonion.cli.commands import gmail_listings, teams_commands
        from connectonion.cli.main import app

        now = [1000.0]
        account = ["ada@contoso.example"]
        monkeypatch.setattr(gmail_listings.time, "time", lambda: now[0])
        monkeypatch.setattr(teams_commands, "_account", lambda client: account[0])
        read_mock = MagicMock(return_value="secret")
        chat_rows = [[{"id": "19:c1@thread.v2", "title": "Secret", "chat_type": "oneOnOne",
                       "unread": False, "last_message_at": "", "from": "", "preview": ""}]]
        fake = SimpleNamespace(chat_items=lambda limit=20, since=None: chat_rows[0], read_chat=read_mock)
        monkeypatch.setattr(teams_commands, "_teams", lambda: fake)
        runner = CliRunner()

        assert runner.invoke(app, ["teams", "chats"]).exit_code == 0
        account[0] = "other@contoso.example"
        assert runner.invoke(app, ["teams", "read", "1"]).exit_code != 0

        account[0] = "ada@contoso.example"
        now[0] += 15 * 60
        assert runner.invoke(app, ["teams", "read", "1"]).exit_code != 0

        assert runner.invoke(app, ["teams", "chats"]).exit_code == 0
        chat_rows[0] = []
        assert runner.invoke(app, ["teams", "chats"]).exit_code == 0
        assert runner.invoke(app, ["teams", "read", "1"]).exit_code != 0
        read_mock.assert_not_called()

    def test_send_previews_by_default_and_sends_only_with_yes(self, monkeypatch, cli_listings):
        from typer.testing import CliRunner
        from connectonion.cli.commands import teams_commands
        from connectonion.cli.main import app

        sent = MagicMock(return_value={"id": "msg-99"})
        fake = SimpleNamespace(
            chat_items=lambda limit=20, since=None: [
                {"id": "19:c1@thread.v2", "title": "Release planning", "chat_type": "group",
                 "unread": False, "last_message_at": "", "from": "", "preview": ""},
            ],
            _send_message_item=sent,
            send_message=lambda chat_id, text: f"Sent message {sent(chat_id, text)['id']} to chat {chat_id}",
        )
        monkeypatch.setattr(teams_commands, "_teams", lambda: fake)
        runner = CliRunner()

        assert runner.invoke(app, ["teams", "chats"]).exit_code == 0

        preview = runner.invoke(app, ["teams", "send", "1", "Ship rc27"])
        assert preview.exit_code == 0, preview.output
        assert "Preview" in preview.output
        assert "19:c1@thread.v2" in preview.output
        assert "Ship rc27" in preview.output
        assert "--yes" in preview.output
        sent.assert_not_called()

        json_preview = runner.invoke(app, ["teams", "send", "1", "Ship rc27", "--json"])
        assert json_preview.exit_code == 0, json_preview.output
        parsed = json.loads(json_preview.stdout)
        assert parsed["preview"] is True and parsed["sent"] is False
        assert parsed["chat_id"] == "19:c1@thread.v2" and parsed["text"] == "Ship rc27"
        sent.assert_not_called()

        confirmed = runner.invoke(app, ["teams", "send", "1", "Ship rc27", "--yes"])
        assert confirmed.exit_code == 0, confirmed.output
        sent.assert_called_once_with("19:c1@thread.v2", "Ship rc27")
        assert "msg-99" in confirmed.output

    def test_json_modes_emit_clean_stdout_json(self, monkeypatch, cli_listings):
        from typer.testing import CliRunner
        from connectonion.cli.commands import teams_commands
        from connectonion.cli.main import app

        fake = SimpleNamespace(
            check=lambda: {"ok": True, "tenant_kind": "work_or_school", "tenant_id": WORK_TENANT_ID,
                           "token": {"configured": True, "status": "valid"},
                           "scopes": {"Chat.Read": True, "ChatMessage.Send": True,
                                      "Team.ReadBasic.All": True, "Channel.ReadBasic.All": True}},
            chat_items=lambda limit=20, since=None: [{"id": "19:c1@thread.v2", "title": "Release", "unread": True}],
            message_items=lambda chat_id, limit=20: [{"id": "m1", "from": "Ada", "text": "Hello"}],
            team_items=lambda: SAMPLE_TEAMS["value"],
            channel_items=lambda team_id: SAMPLE_CHANNELS["value"],
        )
        monkeypatch.setattr(teams_commands, "_teams", lambda: fake)
        runner = CliRunner()

        for argv in (
            ["teams", "check", "--json"],
            ["teams", "chats", "--json"],
            ["teams", "read", "19:c1@thread.v2", "--json"],
            ["teams", "teams", "--json"],
            ["teams", "channels", "team-1", "--json"],
        ):
            res = runner.invoke(app, argv)
            assert res.exit_code == 0, res.output
            data = json.loads(res.stdout)
            assert data

    def test_cli_send_timeout_warns_message_may_be_sent(self, monkeypatch, cli_listings):
        from typer.testing import CliRunner
        from connectonion.cli.commands import teams_commands
        from connectonion.cli.main import app

        def timeout_send(chat_id, text):
            raise httpx.ReadTimeout("slow")

        monkeypatch.setattr(teams_commands, "_teams", lambda: SimpleNamespace(
            _send_message_item=timeout_send, send_message=timeout_send))
        res = CliRunner().invoke(app, ["teams", "send", "19:c1@thread.v2", "Hello", "--yes"])
        assert res.exit_code == 1
        combined = res.stdout + res.stderr
        assert "may already have been" in combined
        assert "co teams read" in combined
        assert "Traceback" not in combined

    def test_cli_check_exits_nonzero_on_personal_account(self, monkeypatch):
        from typer.testing import CliRunner
        from connectonion.cli.main import app

        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": MSA_TOKEN}):
            res = CliRunner().invoke(app, ["teams", "check"])
            assert res.exit_code == 1
            combined = res.stdout + res.stderr
            assert MSA_TENANT_ID in combined
            assert "co auth microsoft" in combined

            json_res = CliRunner().invoke(app, ["teams", "check", "--json"])
            assert json_res.exit_code == 1
            payload = json.loads(json_res.stdout)
            assert payload["ok"] is False
            assert payload["tenant_kind"] == "personal"

    def test_cli_send_reads_stdin_when_dash_given(self, monkeypatch, cli_listings):
        from typer.testing import CliRunner
        from connectonion.cli.commands import teams_commands
        from connectonion.cli.main import app

        sent = MagicMock(return_value={"id": "msg-stdin"})
        monkeypatch.setattr(teams_commands, "_teams", lambda: SimpleNamespace(_send_message_item=sent))
        runner = CliRunner()

        preview = runner.invoke(app, ["teams", "send", "19:c1@thread.v2", "-"], input="Line 1\nLine 2\n")
        assert preview.exit_code == 0, preview.output
        sent.assert_not_called()

        confirmed = runner.invoke(app, ["teams", "send", "19:c1@thread.v2", "-", "--yes"], input="Line 1\nLine 2\n")
        assert confirmed.exit_code == 0, confirmed.output
        sent.assert_called_once_with("19:c1@thread.v2", "Line 1\nLine 2\n")


def test_path_traversal_ids_and_gateway_timeout_on_send():
    from connectonion.useful_tools.teams import Teams

    teams = Teams()
    for bad in ("", "   ", "../me", "chat/../../me", "chat?x=1", "chat#frag"):
        with pytest.raises(ValueError):
            teams.read_chat(bad)

    request, _ = _graph({("POST", "/chats/19:c1@thread.v2/messages"): (504, {"error": {"code": "UnknownError"}})})
    with patch("connectonion.useful_tools.outlook.httpx.request", request):
        with pytest.raises(ValueError) as failed:
            teams.send_message("19:c1@thread.v2", "Hello")
    assert "may already have been" in str(failed.value)
    assert "co teams read" in str(failed.value)


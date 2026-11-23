"""Unit tests for Discord as the owner's own account (experimental).

LLM-Note: Tests for connectonion.inbox.discord_user, connectonion.inbox.discord_remote_auth and `co discord link`

What it tests:
- account() picks the linked account, DISCORD_USER_TOKEN, or the bot exactly as before
- Against a real local WebSocket server playing the Gateway: Identify as the web client (no intents, no "Bot "),
  DMs and group DMs reach the inbox in the bot's shape, own messages and non-allowlisted guild messages do not,
  RECONNECT resumes, close 4004 stops the listener for good and records why
- send(): typing, then a pause, then the message, to the right channel, as the web client;
  unknown channels refused; per-channel and global rate caps; a disabled, limited or captcha'd account stops everything
- Remote auth against a fake remote-auth gateway: RSA-OAEP nonce proof, the fingerprint's QR URL, the user preview,
  the ticket exchange, a captcha and a cancel
- `co discord link --token`: needs --yes without a terminal, writes a 0600 session, names the account

No network and no Discord account: the Gateway and remote-auth servers listen on 127.0.0.1, REST is httpx.MockTransport.
"""

import asyncio
import base64
import hashlib
import json
import os
import stat

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from typer.testing import CliRunner
from websockets.asyncio.server import serve

from connectonion.inbox import ListenerStopped, provider
from connectonion.inbox import discord_remote_auth as remote
from connectonion.inbox import discord_user as user_module
from connectonion.inbox.discord import Discord
from connectonion.inbox.discord_user import DiscordUser, account, save_session
from connectonion.inbox.store import Inbox

ME = "100000000000000001"
FRIEND = "100000000000000002"
DM = "200000000000000001"
GROUP_DM = "200000000000000002"
GUILD_CHANNEL = "300000000000000001"
ALLOWED_CHANNEL = "300000000000000002"
TOKEN = "user-secret-token"


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.delenv("DISCORD_USER_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_USER_CHANNELS", raising=False)
    return Inbox("discord")


def linked(box, transport=None, channels=(DM, GROUP_DM)):
    save_session(box, TOKEN, {"id": ME, "username": "owner"}, "qr")
    (box.root / user_module.CHANNELS_FILE).write_text(json.dumps({"private": list(channels)}))
    value = DiscordUser(box=box, transport=transport)
    value.sleep = lambda seconds: value.slept.append(seconds)
    value.slept = []
    return value


def message(channel, author=FRIEND, guild=None, text="are you free tomorrow?", mid="400000000000000001"):
    event = {"id": mid, "channel_id": channel, "author": {"id": author, "username": "ellis", "global_name": "Ellis"},
             "content": text, "mentions": [], "timestamp": "2026-11-22T01:00:00.000000+00:00"}
    if guild:
        event["guild_id"] = guild
        event["mentions"] = [{"id": ME}]
    return {"op": 0, "t": "MESSAGE_CREATE", "d": event}


class TestWhichAccount:
    def test_a_bot_token_and_no_session_is_the_bot_exactly_as_before(self, box, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "bot-token")
        chosen = provider("discord")
        assert type(chosen) is Discord
        assert chosen._headers()["Authorization"] == "Bot bot-token"

    def test_a_linked_session_acts_as_the_owner(self, box, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "bot-token")
        save_session(box, TOKEN, {"id": ME, "username": "owner"}, "qr")
        chosen = account()
        assert isinstance(chosen, DiscordUser)
        assert chosen._headers()["Authorization"] == TOKEN
        assert "your own Discord account @owner" in chosen.acting_as()

    def test_discord_user_token_in_keys_env_is_the_fallback(self, box, monkeypatch):
        monkeypatch.setenv("DISCORD_USER_TOKEN", "env-token")
        chosen = account()
        assert isinstance(chosen, DiscordUser) and chosen.token == "env-token"
        assert "DISCORD_USER_TOKEN" in chosen.acting_as()

    def test_the_session_file_is_private(self, box):
        path = save_session(box, TOKEN, {"id": ME, "username": "owner"}, "qr")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


async def _gateway(script):
    """A local Gateway: each connection runs the next scripted coroutine."""
    seen = {"requests": [], "frames": []}
    connections = list(script)

    async def handler(socket):
        seen["requests"].append(dict(socket.request.headers))
        await connections.pop(0)(socket, seen)

    server = await serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, f"ws://127.0.0.1:{port}/", seen


async def _receive(socket, seen):
    frame = json.loads(await socket.recv())
    seen["frames"].append(frame)
    return frame


def _ready(url):
    return {"op": 0, "t": "READY", "s": 1, "d": {
        "session_id": "s1", "resume_gateway_url": url, "user": {"id": ME, "username": "owner"},
        "private_channels": [{"id": DM, "type": 1}, {"id": GROUP_DM, "type": 3}]}}


class TestListening:
    def test_dms_reach_the_inbox_guilds_and_own_messages_do_not_and_4004_stops_for_good(self, box, monkeypatch):
        monkeypatch.setenv("DISCORD_USER_CHANNELS", ALLOWED_CHANNEL)
        user = linked(box, channels=())

        async def first(socket, seen):
            await socket.send(json.dumps({"op": 10, "d": {"heartbeat_interval": 60000}}))
            await _receive(socket, seen)
            await socket.send(json.dumps({**_ready(seen["url"])}))
            for index, event in enumerate([
                message(DM, mid="401"),
                message(GROUP_DM, mid="402", text="dinner at 7?"),
                message(DM, author=ME, mid="403", text="my own words"),
                message(GUILD_CHANNEL, guild="500", mid="404"),
                message(ALLOWED_CHANNEL, guild="500", mid="405", text="deploy?"),
            ], start=2):
                await socket.send(json.dumps({**event, "s": index}))
            await socket.send(json.dumps({"op": 7, "d": None}))
            await socket.wait_closed()

        async def second(socket, seen):
            await socket.send(json.dumps({"op": 10, "d": {"heartbeat_interval": 60000}}))
            await _receive(socket, seen)
            await socket.close(4004, "Authentication failed.")

        async def scenario():
            server, url, seen = await _gateway([first, second])
            seen["url"] = url
            monkeypatch.setattr(user_module, "GATEWAY", url)
            try:
                with pytest.raises(ListenerStopped, match="4004"):
                    await user._run(box)
            finally:
                server.close()
            return seen

        seen = asyncio.run(scenario())

        identify, resume = seen["frames"]
        assert identify["op"] == 2
        body = identify["d"]
        assert body["token"] == TOKEN and "intents" not in body
        assert body["capabilities"] == user_module.CLIENT["capabilities"]
        assert body["presence"]["status"] == "invisible"
        assert body["properties"]["browser"] == "Chrome"
        assert body["properties"]["client_build_number"] == user_module.CLIENT["client_build_number"]
        assert body["properties"]["has_client_mods"] is False
        assert resume == {"op": 6, "d": {"token": TOKEN, "session_id": "s1", "seq": 6}}
        headers = {k.lower(): v for k, v in seen["requests"][0].items()}
        assert headers["origin"] == "https://discord.com"
        assert "Chrome/" in headers["user-agent"]

        queued = [json.loads(path.read_text()) for path in sorted(box.new.iterdir())]
        assert [m["id"] for m in queued] == ["401", "402", "405"]
        bot_shape = set(Discord().to_message(message(DM)["d"]).to_dict())
        assert set(queued[0]) == bot_shape
        assert queued[0]["chat"] == DM and queued[0]["mentioned"] is True
        assert queued[1]["chat"] == GROUP_DM

        assert set(json.loads((box.root / user_module.CHANNELS_FILE).read_text())["private"]) == {DM, GROUP_DM}
        (problem,) = DiscordUser(box=box).missing()
        assert "will not log in again by itself" in problem and "co discord link" in problem
        assert TOKEN not in box.logfile.read_text()

    def test_a_rotated_token_in_ready_is_kept(self, box):
        user = linked(box)
        user._dispatch({"op": 0, "t": "READY", "d": {**_ready("wss://x")["d"], "auth_token": "rotated"}},
                       box, raw=False)
        saved = json.loads((box.root / user_module.SESSION_FILE).read_text())
        assert saved["token"] == "rotated" and user.http.headers["Authorization"] == "rotated"


class FakeRest:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        status, payload = self.responses.pop(0) if self.responses else (200, {"id": "sent-id"})
        return httpx.Response(status, json=payload) if payload is not None else httpx.Response(status)


class TestReplying:
    def test_a_reply_types_waits_then_sends_to_that_channel_as_the_web_client(self, box):
        rest = FakeRest((204, None), (200, {"id": "sent-id"}))
        user = linked(box, transport=httpx.MockTransport(rest))

        assert user.send(DM, "yes, after lunch", reply_to="401") == "sent-id"

        typing, posted = rest.requests
        assert (typing.method, typing.url.path) == ("POST", f"/api/v9/channels/{DM}/typing")
        assert posted.url.path == f"/api/v9/channels/{DM}/messages"
        body = json.loads(posted.content)
        assert body["content"] == "yes, after lunch"
        assert body["message_reference"]["message_id"] == "401"
        assert body["allowed_mentions"] == {"parse": [], "replied_user": False}
        assert body["nonce"].isdigit() and body["tts"] is False
        assert posted.headers["authorization"] == TOKEN
        properties = json.loads(base64.b64decode(posted.headers["x-super-properties"]))
        assert properties["browser"] == "Chrome"
        (pause,) = user.slept
        assert 1.5 <= pause <= 9.0

    def test_a_longer_message_waits_longer(self, box):
        user = linked(box, transport=httpx.MockTransport(FakeRest()))
        user.send(DM, "ok")
        user.send(GROUP_DM, "x" * 200)
        assert user.slept[1] > user.slept[0]

    def test_an_unknown_channel_is_refused_without_the_network(self, box):
        rest = FakeRest()
        user = linked(box, transport=httpx.MockTransport(rest))
        with pytest.raises(RuntimeError, match="never opens a new DM, sends a friend request, joins a server"):
            user.send(GUILD_CHANNEL, "hello")
        assert rest.requests == []

    def test_an_allowlisted_guild_channel_may_be_answered(self, box, monkeypatch):
        monkeypatch.setenv("DISCORD_USER_CHANNELS", f"{ALLOWED_CHANNEL}, 999")
        user = linked(box, transport=httpx.MockTransport(FakeRest()))
        assert user.send(ALLOWED_CHANNEL, "on it") == "sent-id"

    def test_the_per_channel_cap_refuses_the_fourth_send_in_a_minute(self, box):
        rest = FakeRest()
        user = linked(box, transport=httpx.MockTransport(rest))
        for _ in range(3):
            box.record_sent(chat=DM, text="x", provider_id="1")
        box.record_sent(chat=DM, text="failed", error="boom")
        with pytest.raises(RuntimeError, match="rate cap"):
            user.send(DM, "fourth")
        assert rest.requests == []
        assert user.send(GROUP_DM, "another channel is fine") == "sent-id"

    def test_the_global_cap_counts_every_channel_and_forgets_after_a_minute(self, box):
        user = linked(box, transport=httpx.MockTransport(FakeRest()))
        old = {"at": "2026-01-01T00:00:00Z", "chat": DM, "ok": True}
        with box.sent.open("a") as handle:
            handle.write(json.dumps(old) + "\n")
        for index in range(10):
            box.record_sent(chat=f"chat{index}", text="x", provider_id=str(index))
        with pytest.raises(RuntimeError, match="10 in all"):
            user.send(DM, "eleventh")

    @pytest.mark.parametrize("status,payload", [
        (401, {"message": "401: Unauthorized", "code": 0}),
        (403, {"message": "You need to verify your account in order to perform this action.", "code": 40002}),
        (400, {"captcha_key": ["captcha-required"], "captcha_sitekey": "x"}),
    ])
    def test_a_disabled_limited_or_challenged_account_stops_the_listener(self, box, monkeypatch, status, payload):
        killed = []
        user = linked(box, transport=httpx.MockTransport(FakeRest((204, None), (status, payload))))
        monkeypatch.setattr(box, "listener_pid", lambda: 4242)
        monkeypatch.setattr(user_module.os, "kill", lambda pid, sig: killed.append(pid))

        with pytest.raises(RuntimeError, match="will not log in again by itself"):
            user.send(DM, "hello")

        assert killed == [4242]
        assert DiscordUser(box=box).missing()
        assert (box.root / user_module.STOPPED_FILE).exists()


# ---- remote auth ---------------------------------------------------------------

def _encrypt(public_b64, data: bytes) -> str:
    public = serialization.load_der_public_key(base64.b64decode(public_b64))
    return base64.b64encode(public.encrypt(data, remote._OAEP)).decode()


async def _remote_auth_server(ending):
    seen = {}

    async def handler(socket):
        await socket.send(json.dumps({"op": "hello", "heartbeat_interval": 41250, "timeout_ms": 120000}))
        init = json.loads(await socket.recv())
        seen["public_key"] = init["encoded_public_key"]
        nonce = b"nonce-from-discord"
        await socket.send(json.dumps({"op": "nonce_proof", "encrypted_nonce": _encrypt(init["encoded_public_key"], nonce)}))
        seen["proof"] = json.loads(await socket.recv())
        seen["expected"] = base64.urlsafe_b64encode(hashlib.sha256(nonce).digest()).decode().rstrip("=")
        await socket.send(json.dumps({"op": "pending_remote_init", "fingerprint": "fp-abc"}))
        await socket.send(json.dumps({"op": "pending_ticket", "encrypted_user_payload":
                                      _encrypt(init["encoded_public_key"], f"{ME}:0:avatarhash:owner".encode())}))
        await socket.send(json.dumps(ending))
        await socket.wait_closed()

    server = await serve(handler, "127.0.0.1", 0)
    return server, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/", seen


def _run_remote_auth(ending, key):
    shown = {"qr": [], "user": []}

    async def scenario():
        server, url, seen = await _remote_auth_server(ending)
        try:
            return await remote.ticket(shown["qr"].append, shown["user"].append, key=key, url=url), seen
        finally:
            server.close()

    login, seen = asyncio.run(scenario())
    return login, seen, shown


class TestRemoteAuth:
    def test_the_handshake_proves_the_nonce_shows_the_qr_and_returns_the_ticket(self):
        key = remote.new_key()
        login, seen, shown = _run_remote_auth({"op": "pending_login", "ticket": "ticket-1"}, key)

        assert login == "ticket-1"
        assert seen["proof"] == {"op": "nonce_proof", "proof": seen["expected"]}
        assert seen["public_key"] == remote.encoded_public_key(key)
        assert shown["qr"] == ["https://discord.com/ra/fp-abc"]
        assert shown["user"][0]["username"] == "owner" and shown["user"][0]["id"] == ME

    def test_a_cancel_on_the_phone_links_nothing(self):
        with pytest.raises(RuntimeError, match="cancelled on the phone"):
            _run_remote_auth({"op": "cancel"}, remote.new_key())

    def test_the_ticket_is_exchanged_for_the_decrypted_token(self):
        key = remote.new_key()
        posted = []

        def rest(request):
            posted.append(request)
            return httpx.Response(200, json={"encrypted_token": _encrypt(remote.encoded_public_key(key), b"the-token")})

        http = httpx.Client(transport=httpx.MockTransport(rest))
        assert remote.exchange(http, key, "ticket-1") == "the-token"
        assert posted[0].url.path == "/api/v9/users/@me/remote-auth/login"
        assert json.loads(posted[0].content) == {"ticket": "ticket-1"}

    def test_a_captcha_says_so_and_points_to_the_paste_fallback(self):
        http = httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(400, json={"captcha_key": ["captcha-required"]})))
        with pytest.raises(remote.Captcha, match="captcha.*co discord link --token"):
            remote.exchange(http, remote.new_key(), "ticket-1")


# ---- co discord link -------------------------------------------------------------

class TestLinkCommand:
    def _app(self, monkeypatch, status=200):
        from connectonion.cli.commands import discord_commands
        from connectonion.cli.main import app

        monkeypatch.setattr(discord_commands, "_http", lambda: httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"id": ME, "username": "owner"}))))
        return app

    def test_without_yes_and_no_terminal_nothing_is_linked(self, box, monkeypatch):
        result = CliRunner().invoke(self._app(monkeypatch), ["discord", "link", "--token"], input=TOKEN)
        assert result.exit_code == 2
        assert "against" in result.output or "terms" in result.output
        assert not (box.root / user_module.SESSION_FILE).exists()

    def test_a_pasted_token_is_verified_and_kept_privately(self, box, monkeypatch):
        result = CliRunner().invoke(self._app(monkeypatch), ["discord", "link", "--token", "--yes"],
                                    input=TOKEN + "\n")
        assert result.exit_code == 0, result.output
        assert "linked @owner" in result.output and "throwaway account" in result.output
        assert TOKEN not in result.output
        path = box.root / user_module.SESSION_FILE
        assert json.loads(path.read_text())["token"] == TOKEN
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_a_token_discord_refuses_is_not_kept(self, box, monkeypatch):
        result = CliRunner().invoke(self._app(monkeypatch, status=401), ["discord", "link", "--token", "--yes"],
                                    input="bad\n")
        assert result.exit_code == 1
        assert not (box.root / user_module.SESSION_FILE).exists()

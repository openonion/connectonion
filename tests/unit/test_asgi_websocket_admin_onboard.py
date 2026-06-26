"""Unit tests for websocket onboarding and admin flows.

Coverage:
- ONBOARD_REQUIRED emission when forbidden + onboard config
- ONBOARD_SUBMIT invite/payment handling
- ADMIN_* message handling (auth, admin checks, success/error cases)
"""
"""
LLM-Note: Tests for asgi websocket admin onboard

What it tests:
- Asgi Websocket Admin Onboard functionality

Components under test:
- Module: asgi_websocket_admin_onboard
"""


import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from connectonion.network.asgi import handle_websocket
from connectonion.network.trust.ws_admin import (
    get_onboard_requirements,
    handle_onboard_submit,
    handle_admin_message,
)
from connectonion.network.host.session import ActiveSessionRegistry


def _extract_ws_messages(sent_messages):
    return [
        json.loads(m["text"])
        for m in sent_messages
        if m.get("type") == "websocket.send" and "text" in m
    ]


class TestOnboardRequirements:
    def test_no_onboard_returns_none(self):
        trust_agent = SimpleNamespace(config={})
        assert get_onboard_requirements(trust_agent) is None

    def test_invite_and_payment(self):
        trust_agent = SimpleNamespace(
            config={"onboard": {"invite_code": ["CODE"], "payment": 10}},
            get_self_address=lambda: "0xagent123"
        )
        result = get_onboard_requirements(trust_agent)
        assert result == {"methods": ["invite_code", "payment"], "payment_amount": 10, "payment_address": "0xagent123"}


@pytest.mark.asyncio
class TestHandleWebSocketOnboardRequired:
    async def test_sends_onboard_required_for_forbidden(self):
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        recv_count = [0]

        async def receive():
            recv_count[0] += 1
            if recv_count[0] == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({
                        "type": "CONNECT",
                        "payload": {"timestamp": 1234567890},
                        "from": "0xuser",
                        "signature": "0xsig",
                    }),
                }
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = SimpleNamespace(
            config={"onboard": {"invite_code": ["BETA"], "payment": 10}},
            get_self_address=lambda: "0xagent123"
        )
        handlers = {
            "auth": lambda data, trust, **kw: (None, "0xuser", True, "forbidden: strangers"),
            "ws_input": Mock(),
            "trust_agent": trust_agent,
        }

        await handle_websocket(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            registry=ActiveSessionRegistry(),
            trust="careful",
        )

        events = _extract_ws_messages(sent_messages)
        onboard = [e for e in events if e.get("type") == "ONBOARD_REQUIRED"]
        assert len(onboard) == 1
        assert onboard[0]["methods"] == ["invite_code", "payment"]
        assert onboard[0]["payment_amount"] == 10
        assert onboard[0]["payment_address"] == "0xagent123"

    async def test_forbidden_without_onboard_sends_error(self):
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        recv_count = [0]

        async def receive():
            recv_count[0] += 1
            if recv_count[0] == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({
                        "type": "CONNECT",
                        "payload": {"timestamp": 1234567890},
                        "from": "0xuser",
                        "signature": "0xsig",
                    }),
                }
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = SimpleNamespace(config={})
        handlers = {
            "auth": lambda data, trust, **kw: (None, "0xuser", True, "forbidden: strangers"),
            "ws_input": Mock(),
            "trust_agent": trust_agent,
        }

        await handle_websocket(
            scope, receive, send,
            route_handlers=handlers,
            storage=Mock(),
            registry=ActiveSessionRegistry(),
            trust="careful",
        )

        events = _extract_ws_messages(sent_messages)
        error = [e for e in events if e.get("type") == "ERROR"]
        assert len(error) == 1
        assert "forbidden" in error[0]["message"]


@pytest.mark.asyncio
class TestHandleOnboardSubmit:
    async def test_invalid_signature_rejected(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_blocked.return_value = False

        handlers = {
            "auth": lambda data, trust: (None, "0xuser", False, "unauthorized: invalid signature"),
            "trust_agent": trust_agent,
        }

        await handle_onboard_submit({"type": "ONBOARD_SUBMIT"}, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert "unauthorized" in sent_messages[0]["message"]

    async def test_blocked_user_rejected(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_blocked.return_value = True

        handlers = {
            "auth": lambda data, trust: (None, "0xuser", True, None),
            "trust_agent": trust_agent,
        }

        await handle_onboard_submit({"type": "ONBOARD_SUBMIT"}, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert sent_messages[0]["message"] == "forbidden: blocked"

    async def test_invite_success(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_blocked.return_value = False
        trust_agent.verify_invite.return_value = True
        trust_agent.get_level.return_value = "contact"

        handlers = {
            "auth": lambda data, trust: (None, "0xuser", True, None),
            "trust_agent": trust_agent,
        }

        data = {
            "type": "ONBOARD_SUBMIT",
            "payload": {"invite_code": "BETA2024"},
        }
        await handle_onboard_submit(data, send, handlers)

        assert sent_messages[0]["type"] == "ONBOARD_SUCCESS"
        assert sent_messages[0]["level"] == "contact"

    async def test_invite_invalid(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_blocked.return_value = False
        trust_agent.verify_invite.return_value = False

        handlers = {
            "auth": lambda data, trust: (None, "0xuser", True, None),
            "trust_agent": trust_agent,
        }

        data = {
            "type": "ONBOARD_SUBMIT",
            "payload": {"invite_code": "WRONG"},
        }
        await handle_onboard_submit(data, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert "Invalid invite code" in sent_messages[0]["message"]

    async def test_payment_success(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_blocked.return_value = False
        trust_agent.verify_payment.return_value = True
        trust_agent.get_level.return_value = "contact"

        handlers = {
            "auth": lambda data, trust: (None, "0xuser", True, None),
            "trust_agent": trust_agent,
        }

        data = {
            "type": "ONBOARD_SUBMIT",
            "payload": {"payment": 10},
        }
        await handle_onboard_submit(data, send, handlers)

        assert sent_messages[0]["type"] == "ONBOARD_SUCCESS"
        assert sent_messages[0]["level"] == "contact"

    async def test_payment_insufficient(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_blocked.return_value = False
        trust_agent.verify_payment.return_value = False

        handlers = {
            "auth": lambda data, trust: (None, "0xuser", True, None),
            "trust_agent": trust_agent,
        }

        data = {
            "type": "ONBOARD_SUBMIT",
            "payload": {"payment": 5},
        }
        await handle_onboard_submit(data, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert "Insufficient payment" in sent_messages[0]["message"]

    async def test_missing_credentials(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_blocked.return_value = False

        handlers = {
            "auth": lambda data, trust: (None, "0xuser", True, None),
            "trust_agent": trust_agent,
        }

        data = {"type": "ONBOARD_SUBMIT", "payload": {}}
        await handle_onboard_submit(data, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert "invite_code or payment required" in sent_messages[0]["message"]


@pytest.mark.asyncio
class TestHandleAdminMessage:
    async def test_auth_error_rejected(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_admin.return_value = True

        handlers = {
            "auth": lambda data, trust: (None, "0xadmin", False, "unauthorized: invalid"),
            "trust_agent": trust_agent,
            "admin_trust_promote": Mock(),
        }

        await handle_admin_message({"type": "ADMIN_PROMOTE"}, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert "unauthorized" in sent_messages[0]["message"]

    async def test_requires_admin(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_admin.return_value = False

        handlers = {
            "auth": lambda data, trust: (None, "0xuser", True, None),
            "trust_agent": trust_agent,
            "admin_trust_promote": Mock(),
        }

        await handle_admin_message({"type": "ADMIN_PROMOTE"}, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert sent_messages[0]["message"] == "forbidden: admin only"

    async def test_missing_client_id_error(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_admin.return_value = True

        handlers = {
            "auth": lambda data, trust: (None, "0xadmin", True, None),
            "trust_agent": trust_agent,
            "admin_trust_promote": Mock(),
        }

        await handle_admin_message({"type": "ADMIN_PROMOTE", "payload": {}}, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert sent_messages[0]["message"] == "client_id required"

    async def test_promote_success(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_admin.return_value = True

        handlers = {
            "auth": lambda data, trust: (None, "0xadmin", True, None),
            "trust_agent": trust_agent,
            "admin_trust_promote": Mock(return_value={"success": True, "level": "contact"}),
        }

        data = {"type": "ADMIN_PROMOTE", "payload": {"client_id": "0xclient"}}
        await handle_admin_message(data, send, handlers)

        assert sent_messages[0]["type"] == "ADMIN_RESULT"
        assert sent_messages[0]["action"] == "promote"
        assert sent_messages[0]["success"] is True
        assert sent_messages[0]["level"] == "contact"

    async def test_add_admin_requires_super_admin(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_admin.return_value = True
        trust_agent.is_super_admin.return_value = False

        handlers = {
            "auth": lambda data, trust: (None, "0xadmin", True, None),
            "trust_agent": trust_agent,
            "admin_admins_add": Mock(),
        }

        data = {"type": "ADMIN_ADD", "payload": {"admin_id": "0xnew"}}
        await handle_admin_message(data, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert sent_messages[0]["message"] == "forbidden: super admin only"

    async def test_add_admin_success(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_admin.return_value = True
        trust_agent.is_super_admin.return_value = True

        handlers = {
            "auth": lambda data, trust: (None, "0xadmin", True, None),
            "trust_agent": trust_agent,
            "admin_admins_add": Mock(return_value={"success": True, "message": "added"}),
        }

        data = {"type": "ADMIN_ADD", "payload": {"admin_id": "0xnew"}}
        await handle_admin_message(data, send, handlers)

        assert sent_messages[0]["type"] == "ADMIN_RESULT"
        assert sent_messages[0]["action"] == "add_admin"
        assert sent_messages[0]["success"] is True

    async def test_unknown_admin_action(self):
        sent_messages = []

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = Mock()
        trust_agent.is_admin.return_value = True

        handlers = {
            "auth": lambda data, trust: (None, "0xadmin", True, None),
            "trust_agent": trust_agent,
        }

        data = {"type": "ADMIN_UNKNOWN", "payload": {}}
        await handle_admin_message(data, send, handlers)

        assert sent_messages[0]["type"] == "ERROR"
        assert "Unknown admin action" in sent_messages[0]["message"]



@pytest.mark.asyncio
class TestOnboardCompletesConnect:
    async def test_input_after_onboard_runs_without_reconnect(self):
        """The trust gate interrupts CONNECT before conn is populated. A successful
        ONBOARD_SUBMIT must finish establishing the connection (CONNECTED sent,
        conn authenticated) so the client's queued INPUT runs — the original bug
        rejected it with 'authenticate first (send CONNECT)'."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        frames = [
            {"type": "CONNECT", "session_id": "sess-1",
             "payload": {"timestamp": 1234567890}, "from": "0xuser", "signature": "0xsig"},
            {"type": "ONBOARD_SUBMIT", "payload": {"invite_code": "BETA", "timestamp": 1234567891},
             "from": "0xuser", "signature": "0xsig2"},
            {"type": "INPUT", "prompt": "hello", "input_id": "i1"},
        ]
        recv_count = [0]

        async def receive():
            recv_count[0] += 1
            if recv_count[0] <= len(frames):
                return {"type": "websocket.receive", "text": json.dumps(frames[recv_count[0] - 1])}
            # The agent runs on a thread; let it consume the INPUT before closing.
            import asyncio
            for _ in range(200):
                if ws_input.call_count:
                    break
                await asyncio.sleep(0.005)
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = SimpleNamespace(
            config={"onboard": {"invite_code": ["BETA"]}},
            get_self_address=lambda: "0xagent123",
            is_blocked=lambda identity: False,
            verify_invite=lambda identity, code: code == "BETA",
            get_level=lambda identity: "contact",
        )

        def auth(data, trust, **kw):
            # CONNECT from a stranger is forbidden; the ONBOARD_SUBMIT signature
            # check (trust="open") passes.
            if trust == "open":
                return None, "0xuser", True, None
            return None, "0xuser", True, "forbidden: strangers"

        ws_input = Mock(return_value={"result": "done", "duration_ms": 1, "session": {}})
        storage = Mock()
        storage.get.return_value = None

        await handle_websocket(
            scope, receive, send,
            route_handlers={"auth": auth, "ws_input": ws_input, "trust_agent": trust_agent},
            storage=storage,
            registry=ActiveSessionRegistry(),
            trust="careful",
        )

        events = _extract_ws_messages(sent_messages)
        types = [e["type"] for e in events]

        assert "ONBOARD_SUCCESS" in types
        connected = [e for e in events if e["type"] == "CONNECTED"]
        assert connected and connected[0]["session_id"] == "sess-1"
        assert types.index("ONBOARD_SUCCESS") < types.index("CONNECTED")
        assert not any("authenticate first" in str(e.get("message", "")) for e in events)
        ws_input.assert_called_once()

    async def test_onboard_does_not_bypass_blacklist(self):
        """A blacklisted client must not pass the trust gate by onboarding: even with a
        valid invite, after ONBOARD_SUCCESS the host re-applies the blacklist, so CONNECTED
        is never sent and the queued INPUT never runs."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        frames = [
            {"type": "CONNECT", "session_id": "sess-bl",
             "payload": {"timestamp": 1234567890}, "from": "0xbad", "signature": "0xsig"},
            {"type": "ONBOARD_SUBMIT", "payload": {"invite_code": "BETA", "timestamp": 1234567891},
             "from": "0xbad", "signature": "0xsig2"},
            {"type": "INPUT", "prompt": "hello", "input_id": "i1"},
        ]
        recv_count = [0]

        async def receive():
            recv_count[0] += 1
            if recv_count[0] <= len(frames):
                return {"type": "websocket.receive", "text": json.dumps(frames[recv_count[0] - 1])}
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = SimpleNamespace(
            config={"onboard": {"invite_code": ["BETA"]}},
            get_self_address=lambda: "0xagent123",
            is_blocked=lambda identity: False,    # not trust-blocked — only host-blacklisted
            verify_invite=lambda identity, code: code == "BETA",
            get_level=lambda identity: "contact",
        )

        def auth(data, trust, **kw):
            # ONBOARD_SUBMIT signature (trust="open") passes; the CONNECT is forbidden
            # because the identity is on the host blacklist.
            if trust == "open":
                return None, "0xbad", True, None
            return None, "0xbad", True, "forbidden: blacklisted"

        ws_input = Mock(return_value={"result": "done", "duration_ms": 1, "session": {}})
        storage = Mock()
        storage.get.return_value = None

        await handle_websocket(
            scope, receive, send,
            route_handlers={"auth": auth, "ws_input": ws_input, "trust_agent": trust_agent},
            storage=storage,
            registry=ActiveSessionRegistry(),
            trust="careful",
            blacklist={"0xbad"},
        )

        events = _extract_ws_messages(sent_messages)
        types = [e["type"] for e in events]

        assert "ONBOARD_SUCCESS" in types                              # the invite itself was valid
        assert "CONNECTED" not in types                               # but the blacklist still blocks
        assert any(e["type"] == "ERROR" and "blacklisted" in str(e.get("message", ""))
                   for e in events)
        ws_input.assert_not_called()                                  # the queued INPUT never runs

    async def test_onboard_completes_even_with_whitelist_configured(self):
        """whitelist is an allow-bypass, not a restrict-to gate: a stranger who onboards to
        a contact must still get CONNECTED even when the host has a whitelist set (they were
        never on it — whitelisted identities don't need to onboard in the first place)."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        frames = [
            {"type": "CONNECT", "session_id": "sess-wl",
             "payload": {"timestamp": 1234567890}, "from": "0xuser", "signature": "0xsig"},
            {"type": "ONBOARD_SUBMIT", "payload": {"invite_code": "BETA", "timestamp": 1234567891},
             "from": "0xuser", "signature": "0xsig2"},
        ]
        recv_count = [0]

        async def receive():
            recv_count[0] += 1
            if recv_count[0] <= len(frames):
                return {"type": "websocket.receive", "text": json.dumps(frames[recv_count[0] - 1])}
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        trust_agent = SimpleNamespace(
            config={"onboard": {"invite_code": ["BETA"]}},
            get_self_address=lambda: "0xagent123",
            is_blocked=lambda identity: False,
            verify_invite=lambda identity, code: code == "BETA",
            get_level=lambda identity: "contact",
        )

        def auth(data, trust, **kw):
            if trust == "open":
                return None, "0xuser", True, None
            return None, "0xuser", True, "forbidden: strangers"

        ws_input = Mock(return_value={"result": "done", "duration_ms": 1, "session": {}})
        storage = Mock()
        storage.get.return_value = None

        await handle_websocket(
            scope, receive, send,
            route_handlers={"auth": auth, "ws_input": ws_input, "trust_agent": trust_agent},
            storage=storage,
            registry=ActiveSessionRegistry(),
            trust="careful",
            whitelist={"0xsomeone-else"},   # the onboarding identity is NOT on the whitelist
        )

        events = _extract_ws_messages(sent_messages)
        types = [e["type"] for e in events]

        assert "ONBOARD_SUCCESS" in types
        assert "CONNECTED" in types                                   # whitelist must not block an onboarded contact
        assert not any("not whitelisted" in str(e.get("message", "")) for e in events)

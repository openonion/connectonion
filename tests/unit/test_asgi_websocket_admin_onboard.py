"""Unit tests for websocket onboarding and admin flows.

Coverage:
- ONBOARD_REQUIRED emission when forbidden + onboard config
- ONBOARD_SUBMIT invite/payment handling
- ADMIN_* message handling (auth, admin checks, success/error cases)
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from connectonion.network.asgi import handle_websocket
from connectonion.network.asgi.websocket import (
    _get_onboard_requirements,
    _handle_onboard_submit,
    _handle_admin_message,
)


def _extract_ws_messages(sent_messages):
    return [
        json.loads(m["text"])
        for m in sent_messages
        if m.get("type") == "websocket.send" and "text" in m
    ]


class TestOnboardRequirements:
    def test_no_onboard_returns_none(self):
        trust_agent = SimpleNamespace(config={})
        assert _get_onboard_requirements(trust_agent) is None

    def test_invite_and_payment(self):
        trust_agent = SimpleNamespace(
            config={"onboard": {"invite_code": ["CODE"], "payment": 10}},
            get_self_address=lambda: "0xagent123"
        )
        result = _get_onboard_requirements(trust_agent)
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
                        "type": "INPUT",
                        "payload": {"prompt": "hello", "timestamp": 1234567890},
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
                        "type": "INPUT",
                        "payload": {"prompt": "hello", "timestamp": 1234567890},
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

        await _handle_onboard_submit({"type": "ONBOARD_SUBMIT"}, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert "unauthorized" in events[0]["message"]

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

        await _handle_onboard_submit({"type": "ONBOARD_SUBMIT"}, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert events[0]["message"] == "forbidden: blocked"

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
        await _handle_onboard_submit(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ONBOARD_SUCCESS"
        assert events[0]["level"] == "contact"

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
        await _handle_onboard_submit(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert "Invalid invite code" in events[0]["message"]

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
        await _handle_onboard_submit(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ONBOARD_SUCCESS"
        assert events[0]["level"] == "contact"

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
        await _handle_onboard_submit(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert "Insufficient payment" in events[0]["message"]

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
        await _handle_onboard_submit(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert "invite_code or payment required" in events[0]["message"]


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

        await _handle_admin_message({"type": "ADMIN_PROMOTE"}, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert "unauthorized" in events[0]["message"]

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

        await _handle_admin_message({"type": "ADMIN_PROMOTE"}, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert events[0]["message"] == "forbidden: admin only"

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

        await _handle_admin_message({"type": "ADMIN_PROMOTE", "payload": {}}, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert events[0]["message"] == "client_id required"

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
        await _handle_admin_message(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ADMIN_RESULT"
        assert events[0]["action"] == "promote"
        assert events[0]["success"] is True
        assert events[0]["level"] == "contact"

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
        await _handle_admin_message(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert events[0]["message"] == "forbidden: super admin only"

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
        await _handle_admin_message(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ADMIN_RESULT"
        assert events[0]["action"] == "add_admin"
        assert events[0]["success"] is True

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
        await _handle_admin_message(data, send, handlers)

        events = _extract_ws_messages(sent_messages)
        assert events[0]["type"] == "ERROR"
        assert "Unknown admin action" in events[0]["message"]


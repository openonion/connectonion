"""Direct EXEC is authenticated and constrained by the host whitelist.

#653 measured the original missing-caller bug end to end: EXEC did not receive
the signed caller address, so even a stranger could drive a whitelisted tool.
The host now passes the address and resolves its server-authoritative trust
level before calling the tool runner.

    1. connect                  -> ONBOARD_REQUIRED ['invite_code']
    2. submit the invite code   -> CONNECTED           (a stranger is now a contact)
    3. the contact ran  whoami  -> changxing

Step 3 is now expected product behavior after an operator-issued invite, but
only for tools the operator already allowed in the server-side whitelist.
Unlike the old bug, strangers and blocked identities remain outside this path.

    def handle_ws_input(storage, prompt, connection, session=None, images=None,
                        files=None, requester_address=None):
        ...
        requester = {'address': requester_address, 'level': level}

    def handle_ws_exec(tool_name, args):
        return exec_handler(create_agent, exec_permissions, tool_name, args)

INPUT resolves the caller's level and carries it down. EXEC is handed neither
the address nor the level, so *any* authenticated connection may run *any*
whitelisted tool. The session loop's comment says "Auth is the same gate as
INPUT", and the authentication is — the authorisation is not.

`conn["agent_address"]` has held the authenticated caller's address all along.
Nothing asked it.

## Product boundary

EXEC accepts contact, legacy whitelist, or admin. It is the terminal-style fast
path: no LLM, no session, and no approval dialog. The server-side permission
whitelist remains authoritative, including its protected-control-file guard.
Admin remains distinct on control-plane routes rather than ordinary execution.

The remaining half of #653 is the *scope* of what is whitelisted --
`Bash(co *)` is auto-approved, and `co` is not a read-only tool -- which is
#652 and a decision about defaults rather than a missing check.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from connectonion.network.host.ws_router.exec import run_exec


ADMIN = "0x" + "1" * 64
WHITELISTED = "0x" + "2" * 64
CONTACT = "0x" + "3" * 64
STRANGER = "0x" + "4" * 64


@pytest.fixture
def ran():
    """What actually reached the tool runner."""
    return []


@pytest.fixture
def handlers(ran):
    """route_handlers whose ws_exec records the call it was asked to make."""
    def ws_exec(tool_name, args, requester_address=None):
        ran.append((tool_name, requester_address))
        return {"status": "success", "result": "changxing"}

    return {"ws_exec": ws_exec}


def _exec_as(address, handlers):
    """One EXEC frame from this caller, returning the reply frames."""
    sent = []

    async def send_msg(msg):
        sent.append(msg)

    asyncio.run(run_exec({"exec_id": "e1", "tool": "bash", "args": {"command": "whoami"}},
                         send_msg, handlers, requester_address=address))
    return sent


class TestTheCallerReachesTheGate:

    def test_exec_is_told_who_asked(self, handlers, ran):
        _exec_as(ADMIN, handlers)

        assert ran == [("bash", ADMIN)], (
            "the tool ran without the gate ever learning who asked"
        )

    def test_it_forwards_exactly_what_the_connection_had(self, handlers, ran):
        """Including nothing, so the gate can refuse it.

        run_exec does not decide anything -- deciding in two places is how the
        advertised and enforced halves of the payment gate drifted apart
        (#690). It carries the address; TestWhoMayDriveToolsDirectly below
        checks what the real handler does with None.
        """
        _exec_as(None, handlers)

        assert ran == [("bash", None)]

    def test_the_result_reaches_the_client(self, handlers):
        sent = _exec_as(ADMIN, handlers)

        assert sent[0]["type"] == "EXEC_RESULT"
        assert sent[0]["status"] == "success"


class TestWhoMayDriveToolsDirectly:
    """Against the real handler, not the fake above."""

    def _handler(self, levels, admins):
        from connectonion.network.host import server

        trust = MagicMock()
        trust.is_admin.side_effect = lambda a: a in admins
        trust.get_level.side_effect = lambda a: levels.get(a, "stranger")
        return trust

    @pytest.fixture
    def ws_exec(self):
        """The real handle_ws_exec, with a trust agent that knows four callers."""
        from connectonion.network.host import server

        trust = self._handler(
            {WHITELISTED: "whitelist", CONTACT: "contact", STRANGER: "stranger"},
            {ADMIN},
        )
        calls = []

        def exec_handler(create_agent, permissions, tool_name, args):
            calls.append(tool_name)
            return {"status": "success", "result": "ok"}

        with patch.object(server, "exec_handler", exec_handler):
            yield server._make_ws_exec(lambda: None, {}, trust), calls

    def test_the_operator_may(self, ws_exec):
        handler, calls = ws_exec
        result = handler("bash", {"command": "whoami"}, requester_address=ADMIN)

        assert result["status"] == "success"
        assert calls == ["bash"]

    def test_a_whitelisted_caller_may(self, ws_exec):
        handler, calls = ws_exec
        result = handler("bash", {"command": "whoami"}, requester_address=WHITELISTED)

        assert result["status"] == "success"

    def test_a_contact_may_run_a_pre_authorised_tool(self, ws_exec):
        """An operator-issued invite is the normal B2B user grant."""
        handler, calls = ws_exec
        result = handler("bash", {"command": "whoami"}, requester_address=CONTACT)

        assert result["status"] == "success"
        assert calls == ["bash"]

    def test_a_stranger_may_not(self, ws_exec):
        handler, calls = ws_exec
        result = handler("bash", {"command": "whoami"}, requester_address=STRANGER)

        assert result["status"] == "error"
        assert calls == []

    def test_the_refusal_says_what_is_needed(self, ws_exec):
        handler, _ = ws_exec
        result = handler("bash", {"command": "whoami"}, requester_address=STRANGER)

        assert "contact or admin" in result["error"].lower(), result["error"]

    def test_no_address_is_refused(self, ws_exec):
        handler, calls = ws_exec
        result = handler("bash", {"command": "whoami"}, requester_address=None)

        assert result["status"] == "error"
        assert calls == []


class TestInputIsUnaffected:
    """A contact can still talk to the agent — the model and the approval flow
    are in the way there, which is the whole difference."""

    def test_input_still_carries_a_contacts_level(self):
        import inspect

        from connectonion.network.host import server

        source = inspect.getsource(server._create_route_handlers)

        assert "requester = {'address': requester_address, 'level': level}" in source, (
            "the INPUT path stopped resolving the caller's level"
        )

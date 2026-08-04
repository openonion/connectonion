"""`co call` can answer the onboarding it is asked for.

Part 2 of #614. `call()` refuses and points at something a CLI user cannot do:

    if etype == "ONBOARD_REQUIRED":
        return ExecResult(text="", status="error",
                          error="agent requires onboarding — run input() once to onboard, then call() works")

`input()` is the Python API. `co call --help` lists `--out`, `--timeout` and
`--relay`, and no way to submit an invite code at all — so a CLI user who meets
a stranger's agent is told to go and write a script.

`input()` already does the whole exchange, on the same socket and the same
frames: on ONBOARD_REQUIRED it collects credentials, sends ONBOARD_SUBMIT, and
carries on. The server finishes the interrupted CONNECT itself — ws_router/session.py
pops the stashed `pending_connect` on a successful submit and calls
`establish_connection`, which sends CONNECTED — so the waiting loop in `call()`
needs nothing new to receive it.

Two entry points that disagree about the same protocol, which is the shape #630
had. The one that can already do it is the one that is right.

Not made unconditional: with no terminal to ask, prompting would hang a script
on stdin. Then it still fails, but says the thing the caller can act on.
"""

import asyncio
import json

import pytest

from connectonion.network.connect import RemoteAgent


AGENT = "0x" + "b" * 64


class FakeWebSocket:
    """Answers frames the way the host does, and records what it was sent."""

    def __init__(self, script):
        self.script = list(script)
        self.sent = []
        self._outbox = []

    async def send(self, raw):
        message = json.loads(raw)
        self.sent.append(message)
        for trigger, replies in self.script:
            if message.get("type") == trigger:
                for reply in replies:
                    reply = dict(reply)
                    # The host echoes the exec_id, and the client skips any
                    # EXEC_RESULT that does not carry the one it sent. A fake
                    # that omits it looks like a silent agent, not a passing test.
                    if reply.get("type") == "EXEC_RESULT" and "exec_id" in message:
                        reply["exec_id"] = message["exec_id"]
                    self._outbox.append(reply)

    async def recv(self):
        if not self._outbox:
            raise AssertionError(
                f"the client waited for a frame nobody sent; it had sent: "
                f"{[m.get('type') for m in self.sent]}")
        return json.dumps(self._outbox.pop(0))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _agent_that(monkeypatch, script, tty=True, invite="LETMEIN"):
    """A RemoteAgent whose socket follows `script`, with the terminal faked."""
    socket = FakeWebSocket(script)

    import websockets

    # connect.py does `import websockets` inside the method, so the attribute on
    # the real module is what it will reach for.
    monkeypatch.setattr(websockets, "connect", lambda *a, **k: socket)
    monkeypatch.setattr("sys.stdin", type("Stdin", (), {"isatty": lambda self: tty})())
    monkeypatch.setattr("builtins.input", lambda *a: invite)

    agent = RemoteAgent(AGENT, keys=None, relay_url="wss://relay.test")
    return agent, socket


ONBOARD_THEN_IN = [
    ("CONNECT", [{"type": "ONBOARD_REQUIRED", "methods": ["invite_code"]}]),
    ("ONBOARD_SUBMIT", [{"type": "CONNECTED", "session_id": "s1"}]),
    ("EXEC", [{"type": "EXEC_RESULT", "status": "success", "result": "MARKER"}]),
]


class TestAnAgentThatAsksForAnInviteCode:

    def test_the_command_runs(self, monkeypatch):
        agent, _ = _agent_that(monkeypatch, ONBOARD_THEN_IN)

        assert agent.call("bash", command="pwd").ok

    def test_the_result_comes_back(self, monkeypatch):
        agent, _ = _agent_that(monkeypatch, ONBOARD_THEN_IN)

        assert "MARKER" in agent.call("bash", command="pwd").text

    def test_the_code_is_submitted(self, monkeypatch):
        agent, socket = _agent_that(monkeypatch, ONBOARD_THEN_IN, invite="LETMEIN")

        agent.call("bash", command="pwd")

        submits = [m for m in socket.sent if m.get("type") == "ONBOARD_SUBMIT"]
        assert submits, [m.get("type") for m in socket.sent]
        assert "LETMEIN" in json.dumps(submits[0])

    def test_the_exec_is_sent_only_after_connected(self, monkeypatch):
        """Order is the protocol: an EXEC before CONNECTED is refused by the host."""
        agent, socket = _agent_that(monkeypatch, ONBOARD_THEN_IN)

        agent.call("bash", command="pwd")

        types = [m.get("type") for m in socket.sent]
        assert types.index("ONBOARD_SUBMIT") < types.index("EXEC"), types


class TestWithNoTerminalToAsk:
    """A script has no stdin to answer with; hanging on input() is worse than failing."""

    def test_it_fails_instead_of_prompting(self, monkeypatch):
        def explode(*a):
            raise AssertionError("prompted for an invite code with no terminal")

        agent, _ = _agent_that(monkeypatch, ONBOARD_THEN_IN, tty=False)
        monkeypatch.setattr("builtins.input", explode)

        assert not agent.call("bash", command="pwd").ok

    def test_the_error_does_not_send_the_reader_to_the_python_api(self, monkeypatch):
        """The old text said "run input() once", which is not a thing a CLI user has."""
        agent, _ = _agent_that(monkeypatch, ONBOARD_THEN_IN, tty=False)

        error = agent.call("bash", command="pwd").error

        assert "input()" not in error, error

    def test_the_error_says_what_is_needed(self, monkeypatch):
        agent, _ = _agent_that(monkeypatch, ONBOARD_THEN_IN, tty=False)

        assert "invite" in agent.call("bash", command="pwd").error.lower()


class TestWhatMustNotChange:

    def test_an_agent_that_needs_nothing_is_unaffected(self, monkeypatch):
        agent, socket = _agent_that(monkeypatch, [
            ("CONNECT", [{"type": "CONNECTED", "session_id": "s1"}]),
            ("EXEC", [{"type": "EXEC_RESULT", "status": "success", "result": "PLAIN"}]),
        ])

        result = agent.call("bash", command="pwd")

        assert result.ok and "PLAIN" in result.text
        assert not [m for m in socket.sent if m.get("type") == "ONBOARD_SUBMIT"]

    def test_a_refusal_is_still_a_refusal(self, monkeypatch):
        agent, _ = _agent_that(monkeypatch, [
            ("CONNECT", [{"type": "ERROR", "message": "forbidden: blacklisted"}]),
        ])

        result = agent.call("bash", command="pwd")

        assert not result.ok
        assert "blacklisted" in result.error


class TestACodeThatIsWrong:
    """The path a typo takes. `handle_onboard_submit` answers a bad code with
    `{"type": "ERROR", "message": "Invalid invite code"}`, which the loop already
    knows how to end on — so submitting must not turn a refusal into a hang or a
    prompt that keeps asking."""

    WRONG = [
        ("CONNECT", [{"type": "ONBOARD_REQUIRED", "methods": ["invite_code"]}]),
        ("ONBOARD_SUBMIT", [{"type": "ERROR", "message": "Invalid invite code"}]),
    ]

    def test_it_reports_the_reason(self, monkeypatch):
        agent, _ = _agent_that(monkeypatch, self.WRONG, invite="NOPE")

        result = agent.call("bash", command="pwd")

        assert not result.ok
        assert "Invalid invite code" in result.error

    def test_it_does_not_ask_again(self, monkeypatch):
        asked = []
        agent, _ = _agent_that(monkeypatch, self.WRONG)
        monkeypatch.setattr("builtins.input", lambda *a: asked.append(1) or "NOPE")

        agent.call("bash", command="pwd")

        assert len(asked) == 1, f"prompted {len(asked)} times"

    def test_no_command_is_run(self, monkeypatch):
        agent, socket = _agent_that(monkeypatch, self.WRONG)

        agent.call("bash", command="pwd")

        assert not [m for m in socket.sent if m.get("type") == "EXEC"]

"""The heartbeat never sends a frame the relay is certain to refuse.

The fallback re-stamped the original ANNOUNCE and sent it again. Two faults
stacked: the relay verifies the signature over every field, so a changed
timestamp invalidates it — and the value written was `asyncio.get_event_loop().
time()`, a monotonic clock, which is decades away from the epoch seconds the
freshness check compares against. openonion/connectonion#429
"""

import inspect
from pathlib import Path

import pytest

from connectonion.network import relay


class TestTheFallbackDoesNotSendSomethingUnsignable:
    def test_no_frame_is_sent_without_a_signing_key(self):
        """Re-signing needs the private key, and the branch exists precisely
        because it is absent. Sending anyway is a guaranteed rejection."""
        source = inspect.getsource(relay)
        fallback = source[source.index("heartbeat_interval (60s) elapsed"):]
        fallback = fallback[:fallback.index("except websockets")]

        else_branch = fallback[fallback.index("else:"):]
        assert "send_announce" not in else_branch, \
            "still sends a frame it cannot sign"

    def test_the_timestamp_is_never_overwritten_in_place(self):
        """Mutating a signed message is what invalidated it."""
        source = inspect.getsource(relay)

        assert 'announce_message["timestamp"] =' not in source

    def test_the_monotonic_clock_is_not_used_as_a_timestamp(self):
        """get_event_loop().time() counts from an arbitrary origin — here it was
        off from epoch by more than fifty years, against a 300-second window."""
        source = inspect.getsource(relay)

        assert "get_event_loop().time()" not in source

    def test_the_operator_is_told_the_registration_will_lapse(self):
        """Silence would leave an agent that reads as online and is not."""
        source = inspect.getsource(relay)

        assert "registration will lapse" in source


class TestTheHealthyPathIsUnchanged:
    def test_a_signing_key_still_produces_a_fresh_signed_frame(self):
        """The branch that works builds a new message rather than editing one,
        which is the only way it can carry a valid signature."""
        source = inspect.getsource(relay)
        fallback = source[source.index("heartbeat_interval (60s) elapsed"):]

        assert "create_announce_message(" in fallback
        assert fallback.index("create_announce_message(") < fallback.index("else:")


class TestTheClockTheRelayActuallyChecks:
    def test_a_monotonic_value_would_fail_the_freshness_window(self):
        """Not an assumption about the relay — the arithmetic, run."""
        import asyncio
        import time

        async def gap():
            return int(time.time()) - int(asyncio.get_event_loop().time())

        assert abs(asyncio.run(gap())) > 300

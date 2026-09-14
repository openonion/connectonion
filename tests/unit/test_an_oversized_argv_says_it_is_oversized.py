"""#1524: a too-large argv entry was refused as "contains an invalid value".

The message named the wrong problem and no limit. A caller following the
documented `"$(cat args.json)"` pattern with a 73 KiB payload went looking for
a bad character in a string whose only characters were the letter `a`.
"""

import pytest

from connectonion.network.oip import browser_daemon_pb2 as wire
from connectonion.network.oip.framing import (
    ARGV_ENTRY_BYTES,
    ARGV_TOTAL_BYTES,
    ProtocolError,
    encode_frame,
)


def _command(*argv: str):
    return wire.Envelope(
        protocol_version=2,
        request_id="req-1",
        command=wire.BrowserCommand(argv=list(argv)),
    )


def test_an_oversized_entry_names_the_limit_and_the_size():
    oversized = "a" * (ARGV_ENTRY_BYTES + 1)

    with pytest.raises(ProtocolError) as excinfo:
        encode_frame(_command("run_page_script", oversized))

    message = str(excinfo.value)
    # The two numbers a caller needs to act: what they sent, and what is
    # allowed. Neither appeared anywhere before -- not in the message, not
    # in `co browser help`, not in the docs.
    assert str(ARGV_ENTRY_BYTES + 1) in message
    assert str(ARGV_ENTRY_BYTES) in message
    assert "invalid value" not in message


def test_an_oversized_entry_says_which_entry():
    oversized = "a" * (ARGV_ENTRY_BYTES + 1)

    with pytest.raises(ProtocolError) as excinfo:
        encode_frame(_command("run_page_script", "echo.js", oversized))

    # A command carries up to 128 entries; "one of them is too big" is not
    # an answer when the payload is assembled from several.
    assert "entry 2" in str(excinfo.value)


def test_a_nul_byte_is_still_reported_as_a_nul_byte():
    with pytest.raises(ProtocolError) as excinfo:
        encode_frame(_command("run_page_script", "before\x00after"))

    message = str(excinfo.value)
    assert "NUL" in message
    # Not a size complaint: this value is well under the limit, and saying
    # otherwise would be the same conflation in the other direction.
    assert str(ARGV_ENTRY_BYTES) not in message


def test_a_total_over_the_limit_names_the_total_limit():
    # Each entry is legal on its own; together they are not.
    half = "a" * (ARGV_ENTRY_BYTES - 1)

    with pytest.raises(ProtocolError) as excinfo:
        encode_frame(_command(half, half, half))

    message = str(excinfo.value)
    assert str(ARGV_TOTAL_BYTES) in message
    assert "3 entries" in message


def test_an_entry_at_the_limit_is_accepted():
    # The accept control. The refusal has to be about crossing the line, not
    # about approaching it -- an off-by-one here costs a caller the last
    # kilobyte of a payload for no stated reason.
    at_limit = "a" * ARGV_ENTRY_BYTES

    encoded = encode_frame(_command(at_limit))

    assert len(encoded) > ARGV_ENTRY_BYTES


def test_an_ordinary_command_is_untouched():
    encoded = encode_frame(_command("go_to", "https://example.com"))

    assert encoded.startswith(b"OIP2")

"""Comments must not describe the retired identity derivation as current (#1015).

The agent identity moved from a bare `SigningKey(seed[:32])` to SLIP-0010 in
#404, and the account-migrate path is gone. A comment that still says the
identity is `seed[:32]` "(unchanged)", or tells a reader to run
`co account migrate`, sends the next person reasoning about addresses to a
derivation and a command that no longer exist.
"""

from pathlib import Path

import connectonion

SOURCE = Path(connectonion.__file__).parent


def _lines():
    for path in SOURCE.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            yield f"{path.relative_to(SOURCE)}:{number}", line


def test_no_comment_calls_seed_slice_the_current_agent_identity():
    stale = [where for where, line in _lines()
             if "seed[:32]" in line and ("unchanged" in line or "original derivation" in line)]
    assert stale == []


def test_no_comment_points_at_the_retired_account_migrate_command():
    stale = [where for where, line in _lines() if "co account migrate" in line]
    assert stale == []

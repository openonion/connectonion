"""#2359: oo-api names an agent's mailbox 0x + the first 10 hex characters
of its address (email_service.get_agent_email_address, public_key[:12]).
The client derived 0x + 8 hex in six places, a mailbox nobody reads."""

import re
from pathlib import Path

from connectonion import address

PACKAGE = Path(address.__file__).resolve().parent


def test_a_new_identity_gets_the_mailbox_oo_api_reads():
    identity = address.generate()

    assert identity["email"] == f"{identity['address'][:12]}@mail.openonion.ai"
    assert len(identity["email"].split("@")[0]) == 12


def test_a_recovered_identity_gets_the_same_mailbox():
    identity = address.generate()

    recovered = address.recover(identity["seed_phrase"])

    assert recovered["email"] == identity["email"]


def test_only_agent_email_builds_a_mailbox():
    """The fallbacks in auth, reset, deploy and send_email each wrote their
    own f-string; one rule in address.agent_email replaces them."""
    built_by_hand = re.compile(r"\[:\d+\]\}@mail\.openonion\.ai")
    offenders = [str(path.relative_to(PACKAGE)) for path in PACKAGE.rglob("*.py")
                 if built_by_hand.search(path.read_text(encoding="utf-8"))]

    assert offenders == ["address.py"]

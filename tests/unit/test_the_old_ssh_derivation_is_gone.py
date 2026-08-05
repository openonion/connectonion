"""#427 step 4: the HKDF SSH key and the single global key are retired.

#423 moved identity onto the SLIP-0010 tree and left the SSH key behind on a
second construction:

    SSH_DERIVATION_INFO = b"connectonion:ssh:v1"
    ssh_seed = _hkdf_sha512(seed, SSH_DERIVATION_INFO)

One key for every server, cached at ~/.co/ssh/id_ed25519, installed into
authorized_keys at provisioning and offered on every ssh call. #427 committed to
removing it by 1.6 and set out what done means:

  - grep -r "connectonion:ssh:v1" returns nothing outside a changelog
  - _hkdf_sha512 is gone from address.py
  - ~/.co/ssh/ holds a key per server, not one global key
  - co keys --ssh requires a host, or prints the set

This is the breaking step, and #427 says why it could not ship earlier: the old
public line is in authorized_keys on every machine provisioned before the
per-server key existed, and "there is no undo: the way back in *is* the key".

The precondition was checked against the real fleet before this was written —
each live server opened with its per-server key alone, offered on its own:

    nw-runner  (claude-runner)    NEW_KEY_WORKS
    nw-prod    (naturewill-test)  NEW_KEY_WORKS
    naturewill-prod               NEW_KEY_WORKS
    test       (co-test-deploy)   host unreachable — the box is gone

So no reachable machine is left holding only the old line.
"""

import inspect
import re
from pathlib import Path

import pytest

from connectonion import address


REPO = Path(__file__).resolve().parents[2]


class TestTheConstructionIsGone:

    def test_no_hkdf_helper(self):
        assert not hasattr(address, "_hkdf_sha512"), "the second construction is still here"

    def test_no_derivation_label(self):
        assert not hasattr(address, "SSH_DERIVATION_INFO")

    def test_the_label_is_not_in_the_shipped_package(self):
        """#427's first condition: nothing outside a changelog names it.

        Scoped to `connectonion/` — the artifact that ships. This file names the
        label in its own docstring to say what was removed, which is the same
        exemption #427 gave a changelog.
        """
        offenders = [
            str(path.relative_to(REPO))
            for path in (REPO / "connectonion").rglob("*.py")
            if "connectonion:ssh:v1" in path.read_text(encoding="utf-8", errors="replace")
        ]

        assert offenders == [], f"the retired label survives in: {offenders}"


class TestEveryKeyBelongsToAServer:

    def test_a_host_is_required(self):
        """The hostless call was the single global key."""
        phrase = address.generate()["seed_phrase"]

        with pytest.raises(TypeError):
            address.derive_ssh_key(phrase)

    def test_a_per_host_key_still_derives(self):
        phrase = address.generate()["seed_phrase"]

        keys = address.derive_ssh_key(phrase, host="example-server")

        assert keys["public_line"].startswith("ssh-ed25519 ")
        assert "PRIVATE KEY" in keys["private_key"]

    def test_two_servers_get_two_keys(self):
        """The point of the migration: a snapshot of one box does not open the others."""
        phrase = address.generate()["seed_phrase"]

        one = address.derive_ssh_key(phrase, host="server-one")["public_line"]
        two = address.derive_ssh_key(phrase, host="server-two")["public_line"]

        assert one != two

    def test_the_same_server_derives_the_same_key(self):
        phrase = address.generate()["seed_phrase"]

        first = address.derive_ssh_key(phrase, host="stable")["public_line"]
        second = address.derive_ssh_key(phrase, host="stable")["public_line"]

        assert first == second


class TestNothingStillAsksForTheGlobalKey:
    """Callers that passed no host were asking for the retired construction."""

    @pytest.mark.parametrize("module", [
        "connectonion.cli.commands.server_commands",
        "connectonion.cli.commands.keys_commands",
    ])
    def test_no_hostless_derive_call(self, module):
        import importlib

        source = inspect.getsource(importlib.import_module(module))
        hostless = re.findall(r"derive_ssh_key\(\s*[^),]+\s*\)", source)

        assert hostless == [], f"{module} still derives without a host: {hostless}"

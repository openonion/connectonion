"""Unit tests for the SSH key derived from the recovery phrase (address.py).

The fixed vectors below are the point of this file. The agent address is the
primary key for balances, trust relationships and the agent's email — if a
future refactor moves the derivation, every existing agent loses its identity.
A test with a hardcoded expectation is what stops that from happening quietly.
"""

import base64

import pytest

from connectonion import address


# A BIP39 test-vector phrase. Any valid phrase would do; a fixed one lets the
# expected outputs be hardcoded.
PHRASE = "legal winner thank year wave sausage worth useful legal winner thank yellow"

EXPECTED_ADDRESS = "0xc6f2ac5598970c79633714d3eb5c34d7bfc3e92da58c7354b37996d9a4af3ab2"
EXPECTED_SSH_LINE = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBs9N4V0K4pXPZNr5XPKmSJusfyalyjdi4xN36gqLt8U"
    " connectonion"
)


class TestAgentAddressIsUnchanged:
    """The agent identity must not move. This is the whole risk of the change."""

    def test_known_phrase_produces_the_same_address(self):
        assert address.recover(PHRASE)["address"] == EXPECTED_ADDRESS

    def test_agent_key_still_uses_the_bare_first_half_of_the_seed(self):
        """Explicitly pin the derivation, not just its output.

        The SSH key uses HKDF; the agent key deliberately does not. If someone
        "tidies up" by routing both through HKDF, this fails immediately instead
        of silently reissuing every address.
        """
        from mnemonic import Mnemonic
        from nacl.signing import SigningKey

        seed = Mnemonic("english").to_seed(PHRASE)
        expected = "0x" + bytes(SigningKey(seed[:32]).verify_key).hex()

        assert address.recover(PHRASE)["address"] == expected


class TestDeriveSSHKey:
    def test_known_phrase_produces_the_same_ssh_key(self):
        assert address.derive_ssh_key(PHRASE)["public_line"] == EXPECTED_SSH_LINE

    def test_derivation_is_deterministic(self):
        assert address.derive_ssh_key(PHRASE) == address.derive_ssh_key(PHRASE)

    def test_different_phrases_produce_different_keys(self):
        other = "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong"
        assert address.derive_ssh_key(other)["public_line"] != EXPECTED_SSH_LINE

    def test_invalid_phrase_is_rejected(self):
        with pytest.raises(ValueError, match="Invalid recovery phrase"):
            address.derive_ssh_key("not actually a bip39 phrase at all")

    def test_ssh_key_is_not_the_agent_key(self):
        """Two keys, not one used twice.

        A signing oracle in the agent protocol must not be usable against SSH
        login, so neither key may be the other — and the SSH key must not be the
        unused second half of the seed either, which would be a slice rather
        than a derivation.
        """
        from mnemonic import Mnemonic

        seed = Mnemonic("english").to_seed(PHRASE)
        ssh_seed = address._hkdf_sha512(seed, address.SSH_DERIVATION_INFO)

        assert ssh_seed != seed[:32]
        assert ssh_seed != seed[32:]


class TestOpenSSHEncoding:
    """The output has to be usable verbatim by real ssh tooling."""

    def test_public_line_has_the_three_authorized_keys_fields(self):
        parts = address.derive_ssh_key(PHRASE)["public_line"].split()
        assert len(parts) == 3
        assert parts[0] == "ssh-ed25519"
        assert parts[2] == "connectonion"

    def test_public_blob_declares_its_own_type_and_carries_32_bytes(self):
        """Decode the base64 the way sshd does: length-prefixed strings."""
        blob = base64.b64decode(address.derive_ssh_key(PHRASE)["public_line"].split()[1])

        type_len = int.from_bytes(blob[0:4], "big")
        key_type = blob[4:4 + type_len]
        key_len = int.from_bytes(blob[4 + type_len:8 + type_len], "big")

        assert key_type == b"ssh-ed25519"
        assert key_len == 32
        assert len(blob) == 8 + type_len + key_len

    def test_private_key_is_an_unencrypted_openssh_block(self):
        private = address.derive_ssh_key(PHRASE)["private_key"]

        assert private.startswith("-----BEGIN OPENSSH PRIVATE KEY-----\n")
        assert private.rstrip().endswith("-----END OPENSSH PRIVATE KEY-----")

        body = base64.b64decode("".join(private.splitlines()[1:-1]))
        assert body.startswith(b"openssh-key-v1\x00")
        # cipher "none" and kdf "none" — the recovery phrase is the secret being
        # protected, and the file can always be re-derived from it
        assert b"none" in body[:40]

    def test_private_blob_length_is_a_multiple_of_the_block_size(self):
        """OpenSSH pads the private section to the cipher block size (8 for none).

        Getting this wrong produces a file that looks right and that ssh-keygen
        refuses to load.
        """
        private = address.derive_ssh_key(PHRASE)["private_key"]
        body = base64.b64decode("".join(private.splitlines()[1:-1]))

        offset = len(b"openssh-key-v1\x00")
        for _ in range(3):  # cipher, kdf, kdf options
            length = int.from_bytes(body[offset:offset + 4], "big")
            offset += 4 + length
        offset += 4  # number of keys
        pub_len = int.from_bytes(body[offset:offset + 4], "big")
        offset += 4 + pub_len
        priv_len = int.from_bytes(body[offset:offset + 4], "big")

        assert priv_len % 8 == 0

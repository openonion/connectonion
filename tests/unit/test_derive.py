"""SLIP-0010 / SLIP-0013 derivation.

The vectors below are the published ones from the SLIP-0010 spec, not values
copied out of this implementation — a test that records what the code does would
pass just as happily if the code were wrong, and "wrong" here means every key in
the tree is wrong.

They were additionally cross-checked against Trezor's `slip10` package: 20
derivations across both seeds and every path used here, byte-identical. That
package is not a test dependency (installing a crypto library to test a
40-line one would be its own risk), so the vectors are pinned here instead.
"""

import pytest

from connectonion.derive import (
    ACCOUNT_URI,
    HARDENED,
    derive_path,
    identity_uri,
    master_key,
    slip13_path,
    ssh_uri,
)

# SLIP-0010, Test vector 1 for ed25519. Seed 000102030405060708090a0b0c0d0e0f.
VECTOR_1_SEED = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
VECTOR_1 = {
    "m": "2b4be7f19ee27bbf30c667b642d5f4aa69fd169872f8fc3059c08ebae2eb19e7",
    "m/0'": "68e0fe46dfb67e368c75379acec591dad19df3cde26e63b93a8e704f1dade7a3",
    "m/0'/1'": "b1d0bad404bf35da785a64ca1ac54b2617211d2777696fbffaf208f746ae84f2",
    "m/0'/1'/2'": "92a5b23c0b8a99e37d07df3fb9966917f5d06e02ddbd909c7e184371463e9fc9",
    "m/0'/1'/2'/2'": "30d1dc7e5fc04c31219ab25a27ae00b50f6fd66622f6e9c913253d6511d1e662",
    "m/0'/1'/2'/2'/1000000000'": "8f94d394a8e8fd6b1bc2f3f49f5c47e385281d5c17e65324b0f62483e37e8793",
}

# SLIP-0010, Test vector 2 for ed25519.
VECTOR_2_SEED = bytes.fromhex(
    "fffcf9f6f3f0edeae7e4e1dedbd8d5d2cfccc9c6c3c0bdbab7b4b1aeaba8a5a2"
    "9f9c999693908d8a8784817e7b7875726f6c696663605d5a5754514e4b484542"
)
VECTOR_2 = {
    "m": "171cb88b1b3c1db25add599712e36245d75bc65a1a5c9e18d76f9f2b1eab4012",
    "m/0'": "1559eb2bbec5790b0c65d8693e4d0875b1747f4970ae8b650486ed7470845635",
}


@pytest.mark.parametrize("path,expected", VECTOR_1.items())
def test_slip10_vector_1(path, expected):
    assert derive_path(VECTOR_1_SEED, path).hex() == expected


@pytest.mark.parametrize("path,expected", VECTOR_2.items())
def test_slip10_vector_2(path, expected):
    assert derive_path(VECTOR_2_SEED, path).hex() == expected


def test_master_chain_code_matches_the_spec():
    """The chain code is half the master output and never leaves this module, so
    a wrong one shows up only as wrong children — pin it directly."""
    _, chain_code = master_key(VECTOR_1_SEED)
    assert chain_code.hex() == "90046a93de5380a72b5e45010748567d5ea02bbf6522f979e05c0d8d8ca9fffb"


# --- Hardened-only: the property we are buying ---


def test_an_unhardened_path_level_is_refused():
    """Ed25519 has no public derivation. Accepting m/13/7 and quietly treating it
    as m/13'/7' would hand back a different key than the caller asked for."""
    with pytest.raises(ValueError, match="not hardened"):
        derive_path(VECTOR_1_SEED, "m/13'/7")


def test_a_path_must_start_at_the_master():
    with pytest.raises(ValueError, match="must start with 'm'"):
        derive_path(VECTOR_1_SEED, "13'/7'")


def test_a_non_numeric_level_is_refused():
    with pytest.raises(ValueError, match="not a number"):
        derive_path(VECTOR_1_SEED, "m/abc'")


def test_h_and_apostrophe_mean_the_same_thing():
    assert derive_path(VECTOR_1_SEED, "m/0h") == derive_path(VECTOR_1_SEED, "m/0'")


# --- SLIP-0013 identity paths ---

# Computed independently in the design note for #404, before this implementation
# existed. Matching them is the check that the name→path rule is the standard one
# and not something only this code agrees with.
def test_slip13_paths_match_the_published_examples():
    assert slip13_path(identity_uri("customer-bot")) == \
        "m/13'/1444947841'/1033670849'/1098573961'/1372853139'"
    assert slip13_path(identity_uri("linkedin")) == \
        "m/13'/473400136'/1637201591'/27483200'/1850547836'"
    assert slip13_path(ssh_uri("co", "server")) == \
        "m/13'/2092296577'/727006075'/1801353878'/1387973565'"


def test_a_name_is_canonicalised_before_it_becomes_a_path():
    """An address is a name people retype. ' LinkedIn ' and 'linkedin' must not be
    two different agents."""
    assert identity_uri("  LinkedIn  ") == "agent://linkedin"
    assert slip13_path(identity_uri("LinkedIn")) == slip13_path(identity_uri("linkedin"))


def test_an_empty_name_is_refused():
    with pytest.raises(ValueError, match="empty"):
        identity_uri("   ")


def test_rotation_changes_the_key_and_nothing_else_does():
    uri = identity_uri("customer-bot")
    assert slip13_path(uri, 0) != slip13_path(uri, 1)
    assert slip13_path(uri, 0) == slip13_path(uri, 0)


def test_every_slip13_level_is_hardened_and_in_range():
    """slip13_path writes the masked value; _parse_path adds the hardened bit.
    If those two disagreed, paths would round-trip to a different key."""
    from connectonion.derive import _parse_path

    for level in _parse_path(slip13_path(identity_uri("customer-bot"))):
        assert level >= HARDENED
        assert level < 2 ** 32


def test_different_purposes_from_one_seed_are_different_keys():
    """The whole point of the tree: an SSH login key that leaks must not be the
    agent's protocol key, and neither must be the account key."""
    keys = {
        derive_path(VECTOR_1_SEED, slip13_path(identity_uri("bot"))),
        derive_path(VECTOR_1_SEED, slip13_path(ssh_uri("co", "server"))),
        derive_path(VECTOR_1_SEED, slip13_path(ACCOUNT_URI)),
    }
    assert len(keys) == 3


def test_derived_keys_are_usable_ed25519_seeds():
    from nacl.signing import SigningKey

    key = derive_path(VECTOR_1_SEED, slip13_path(identity_uri("bot")))
    signed = SigningKey(key).sign(b"hello")
    assert SigningKey(key).verify_key.verify(signed) == b"hello"


def test_a_seed_of_the_wrong_size_is_refused():
    with pytest.raises(ValueError, match="16-64 bytes"):
        master_key(b"too short")

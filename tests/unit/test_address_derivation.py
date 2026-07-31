"""Identity is derived through SLIP-0010, not from a slice of the seed.

The address vector below is pinned deliberately. It is the whole contract of a
recovery phrase: if a refactor moves it, every agent that ever wrote those twelve
words down has silently lost its identity, and nothing else in the suite would
notice.
"""

from pathlib import Path

import pytest
from nacl.signing import SigningKey

from connectonion import address
from connectonion.derive import ACCOUNT_URI, derive_path, slip13_path

# A BIP-39 test phrase — never use it for anything real.
PHRASE = "legal winner thank year wave sausage worth useful legal winner thank yellow"
EXPECTED = "0xf8405257284c15e67fd759703d0c04afdf2f216153b9781946f096cae1990a95"



def test_a_phrase_derives_the_slip10_account_address():
    assert address.recover(PHRASE)["address"] == EXPECTED


def test_recover_matches_the_documented_path():
    """Pinning the address is not enough on its own — it would also pass if
    recover() hard-coded a constant. Derive it the long way and compare."""
    from mnemonic import Mnemonic

    seed = Mnemonic("english").to_seed(PHRASE)
    key = SigningKey(derive_path(seed, slip13_path(ACCOUNT_URI)))

    assert address.recover(PHRASE)["address"] == "0x" + bytes(key.verify_key).hex()


def test_generate_and_recover_agree():
    """They are two code paths to one key. If they drift, an agent generated
    today cannot be recovered tomorrow."""
    generated = address.generate()
    recovered = address.recover(generated["seed_phrase"])

    assert recovered["address"] == generated["address"]
    assert bytes(recovered["signing_key"]) == bytes(generated["signing_key"])


def test_the_seed_slice_is_retired():
    """The exact thing #400 is about: seed[:32] must no longer be the identity."""
    from mnemonic import Mnemonic

    seed = Mnemonic("english").to_seed(PHRASE)
    old_style = "0x" + bytes(SigningKey(seed[:32]).verify_key).hex()

    assert address.recover(PHRASE)["address"] != old_style


def test_email_follows_the_new_address():
    assert address.recover(PHRASE)["email"] == f"{EXPECTED[:10]}@mail.openonion.ai"


# --- The break, and saying it out loud ---


def _write_keys(co_dir: Path, signing_key: SigningKey, phrase: str) -> None:
    keys = co_dir / "keys"
    keys.mkdir(parents=True)
    (keys / "agent.key").write_bytes(bytes(signing_key))
    (keys / "recovery.txt").write_text(phrase, encoding="utf-8")


def test_a_pre_switch_key_still_loads_and_is_flagged(tmp_path):
    """The key on disk is the identity the agent has been using; it keeps working.
    What must not happen is loading it silently, because the phrase saved beside
    it now recovers a different agent."""
    from mnemonic import Mnemonic

    seed = Mnemonic("english").to_seed(PHRASE)
    _write_keys(tmp_path, SigningKey(seed[:32]), PHRASE)

    loaded = address.load(tmp_path)

    assert loaded is not None
    assert loaded["legacy_derivation"] is True


def test_a_current_key_is_not_flagged(tmp_path):
    generated = address.generate()
    _write_keys(tmp_path, generated["signing_key"], generated["seed_phrase"])

    assert address.load(tmp_path)["legacy_derivation"] is False


def test_a_key_with_no_saved_phrase_is_not_flagged(tmp_path):
    """Nothing to compare against is not evidence of a legacy key — claiming it
    would warn every agent whose recovery.txt the operator moved somewhere safe."""
    keys = tmp_path / "keys"
    keys.mkdir(parents=True)
    (keys / "agent.key").write_bytes(bytes(address.generate()["signing_key"]))

    assert address.load(tmp_path)["legacy_derivation"] is False


def test_derives_from_rejects_an_invalid_phrase():
    assert address.derives_from("not even a mnemonic", address.generate()["signing_key"]) is False


def test_derives_from_is_true_for_a_matching_pair():
    generated = address.generate()
    assert address.derives_from(generated["seed_phrase"], generated["signing_key"]) is True

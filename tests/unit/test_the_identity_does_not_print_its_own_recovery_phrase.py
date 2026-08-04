"""Printing the loaded identity prints the 12-word recovery phrase.

`address.load()` returns a plain dict, and it puts the recovery phrase in it:

    recovery_file = keys_dir / "recovery.txt"
    ...
    seed_phrase = recovery_file.read_text(...).strip()

A plain dict prints everything it holds. This one gets held in ordinary places:

    keys = address.load(co_dir)          documented, in connect()'s own docstring
    agent = connect(addr, keys=keys)     stored as RemoteAgent._keys
    print(keys)                          -> the phrase, in full

I did this to myself while reviewing #673 — one `print()` of the loaded dict
during a five-line probe put the machine identity's recovery phrase into a
session transcript. It is not an exotic mistake: `print(keys)`, a logger call, a
crash reporter that renders locals, or `repr(agent.__dict__)` on a client all do
the same thing, and after #673 every client holds this dict by default rather
than only the ones that opted in.

The phrase is not removed, because it is genuinely needed after load: `co server`
derives the deploy SSH key from it (`server_commands.py`) and `co keys` shows it
on request. Taking it out of `load()` would break those. What changes is that
reading it becomes something you ask for — `keys["seed_phrase"]` — rather than
something that falls out of printing the object.

The signing key is hidden for the same reason. It is the private half; a repr
that renders it is the same leak by another route.
"""

import json

import pytest

from connectonion import address


@pytest.fixture
def identity(tmp_path):
    co = tmp_path / ".co"
    co.mkdir()
    data = address.generate()
    address.save(data, co)
    return address.load(co), data["seed_phrase"]


class TestItDoesNotPrintTheSecret:

    def test_repr_hides_the_recovery_phrase(self, identity):
        keys, phrase = identity

        assert phrase not in repr(keys)

    def test_str_hides_it(self, identity):
        keys, phrase = identity

        assert phrase not in str(keys)

    def test_an_f_string_hides_it(self, identity):
        keys, phrase = identity

        assert phrase not in f"{keys}"

    def test_the_signing_key_is_hidden_too(self, identity):
        """The private half — a repr that renders it is the same leak."""
        keys, _ = identity

        assert "signing_key" in keys
        assert "SigningKey object" not in repr(keys)

    def test_a_client_holding_it_does_not_print_it(self, identity, monkeypatch, tmp_path):
        """#673 gave every client one of these by default."""
        from connectonion.network import connect

        keys, phrase = identity
        agent = connect("0x" + "a" * 64, keys=keys)

        assert phrase not in repr(agent.__dict__)

    def test_the_word_hidden_says_what_happened(self, identity):
        """Silence would read as 'this identity has no recovery phrase'."""
        keys, _ = identity

        assert "hidden" in repr(keys).lower()


class TestItIsStillAnOrdinaryDict:
    """Everything that reads it must keep working — `co server` derives the
    deploy SSH key from the phrase, `co keys` shows it on request."""

    def test_the_phrase_is_readable_when_asked_for(self, identity):
        keys, phrase = identity

        assert keys["seed_phrase"] == phrase

    def test_get_works(self, identity):
        keys, phrase = identity

        assert keys.get("seed_phrase") == phrase

    def test_the_address_is_unchanged(self, identity, tmp_path):
        keys, _ = identity

        assert keys["address"].startswith("0x")
        assert len(keys["address"]) == 66

    def test_it_is_a_dict(self, identity):
        keys, _ = identity

        assert isinstance(keys, dict)

    def test_keys_and_items_are_complete(self, identity):
        keys, phrase = identity

        assert "seed_phrase" in set(keys.keys())
        assert phrase in [v for _, v in keys.items()]

    def test_it_can_still_sign(self, identity):
        keys, _ = identity
        signature = address.sign(keys, b"a message")

        assert address.verify(keys["address"], b"a message", signature)

    def test_json_of_the_public_part_still_works(self, identity):
        keys, _ = identity
        public = {k: keys[k] for k in ("address", "short_address")}

        assert json.loads(json.dumps(public))["address"] == keys["address"]


class TestGenerateToo:
    """Same dict, same hazard — `co init` shows the phrase deliberately, by
    reading the field, not by printing the object."""

    def test_repr_hides_the_phrase(self):
        data = address.generate()

        assert data["seed_phrase"] not in repr(data)

    def test_the_field_still_reads(self):
        data = address.generate()

        assert len(data["seed_phrase"].split()) == 12


class TestAnIdentityWithNoPhrase:
    """A key saved without recovery.txt — nothing to hide, nothing to claim."""

    def test_it_still_prints(self, tmp_path):
        co = tmp_path / ".co"
        co.mkdir()
        address.save(address.generate(), co)
        (co / "keys" / "recovery.txt").unlink()

        keys = address.load(co)

        assert keys.get("seed_phrase") is None
        assert repr(keys)

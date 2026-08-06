"""`co keys` shows the first two words of the recovery phrase.

The panel ends with "Secrets are masked." and the recovery row reads:

    Recovery    symptom frin...************

That is `_mask(seed, 12)` — twelve characters of a BIP39 mnemonic, which is
about two words.

Not an exploit: ten unknown words carry ~110 bits, so nothing is brute-forced
from this. It is a promise the panel does not keep, about the one credential
that moves an identity and its balance, in output people paste into issues and
screen-shares because they were told it was masked.

The API key is a different case and keeps its prefix. `eyJhbGci` is the constant
base64 of a JWT header — no secret in it — and the prefix is how you tell which
key you are looking at when two are configured. A mnemonic prefix identifies
nothing you would need, so showing it buys nothing to weigh against.

`--reveal` is unchanged. Wanting to see the phrase is a real thing to want; the
default claiming to hide it while showing part is the problem.
"""

import pytest

from connectonion.cli.commands.keys_commands import _mask


PHRASE = "symptom fringe absorb kitten velvet oyster " \
         "napkin gadget mirror pledge canyon ribbon"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"


class TestNoWordOfThePhraseSurvives:

    def test_the_first_word_is_hidden(self):
        assert "symptom" not in _mask(PHRASE, secret=True)

    def test_the_second_word_is_hidden(self):
        assert "fringe" not in _mask(PHRASE, secret=True)

    @pytest.mark.parametrize("word", PHRASE.split())
    def test_no_word_at_all_appears(self, word):
        assert word not in _mask(PHRASE, secret=True)

    def test_something_is_still_shown(self):
        """A blank cell reads as "no recovery phrase set", which is worse."""
        assert _mask(PHRASE, secret=True).strip()

    def test_it_does_not_leak_the_length(self):
        short = "abandon ability able about"

        assert _mask(PHRASE, secret=True) == _mask(short, secret=True)


class TestTheApiKeyKeepsItsPrefix:
    """Different case, deliberately: the prefix carries no secret and is how you
    tell two configured keys apart."""

    def test_the_header_is_still_visible(self):
        assert "eyJhbGci" in _mask(JWT)

    def test_the_rest_is_not(self):
        assert "payload" not in _mask(JWT)
        assert "signature" not in _mask(JWT)

    def test_two_different_keys_look_different(self):
        other = "eyJraWQiOiJhYmMifQ.other.sig"

        assert _mask(JWT) != _mask(other)


class TestTheEdgesAreUnchanged:

    def test_empty_is_empty(self):
        assert _mask("") == ""
        assert _mask("", secret=True) == ""

    def test_a_short_value_is_not_expanded(self):
        assert _mask("abc") == "abc"


class TestRevealStillReveals:
    """The row is built by the command, so assert where the choice is made."""

    def test_the_command_shows_the_phrase_with_reveal(self):
        import inspect

        from connectonion.cli.commands import keys_commands

        source = inspect.getsource(keys_commands)

        assert "seed if reveal" in source, (
            "co keys --reveal must still print the phrase in full"
        )

"""The prompt that runs is the prompt that was signed.

`_build_input_message` signs the prompt:

    payload = {"prompt": prompt, "timestamp": input_msg["timestamp"]}
    signature = addr.sign(self._keys, canonical.encode())
    input_msg["payload"] = payload

`start_agent` read the unsigned top-level field instead:

    if not conn["authenticated"]: ...
    prompt = data.get("prompt")

Measured against a live agent, with the signature covering one prompt and the
top-level field saying another:

    POST /input              signed: SIGNED-PROMPT   top-level: UNSIGNED-PROMPT
                             the agent ran: SIGNED-PROMPT

    INPUT over WebSocket     signed: SIGNED-PROMPT   top-level: UNSIGNED-PROMPT
                             the agent ran: UNSIGNED-PROMPT

So the HTTP path is bound to what was signed and the WebSocket path was not —
the same protocol, the same client, two different guarantees. The client signs
either way, which is what made the WebSocket path look authenticated when the
signature decided nothing.

This is the half of #649 that is a gap rather than a decision: the HTTP path
already establishes the intended reading, and nothing on the wire changes.

What stays a decision, and is not done here: whether a signature should be
*required*. A client built without keys sends none, and the connection it is on
was authenticated by its CONNECT. Honouring a signature that is present is the
part with no trade in it.
"""

import json

import pytest

from connectonion import address


def _signed_input(keys, signed_prompt, top_level_prompt=None, to=None):
    """An INPUT frame whose signature covers `signed_prompt`."""
    import time

    payload = {"prompt": signed_prompt, "timestamp": int(time.time())}
    if to:
        payload["to"] = to
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "type": "INPUT",
        "input_id": "i1",
        "prompt": signed_prompt if top_level_prompt is None else top_level_prompt,
        "payload": payload,
        "from": keys["address"],
        "signature": address.sign(keys, canonical.encode()).hex(),
    }


@pytest.fixture
def keys():
    return address.generate()


def _prompt_taken_from(data):
    """What start_agent would run, without spawning anything.

    The real verifier, not a stand-in: it is the same callable the HTTP path and
    the admin messages use, so a fake here would be testing my idea of the check
    rather than the check.
    """
    from connectonion.network.host.auth import extract_and_authenticate
    from connectonion.network.host.ws_router.agent_io import verified_prompt

    handlers = {"auth": lambda d, trust: extract_and_authenticate(d, trust)}
    prompt, error = verified_prompt(data, handlers)
    if error:
        raise AssertionError(f"refused: {error}")
    return prompt


class TestTheSignedPromptWins:

    def test_a_substituted_top_level_prompt_is_not_used(self, keys):
        frame = _signed_input(keys, "the signed one", top_level_prompt="the substituted one")

        assert _prompt_taken_from(frame) == "the signed one"

    def test_an_ordinary_frame_is_unaffected(self, keys):
        """The client sends the same text in both places."""
        frame = _signed_input(keys, "do the thing")

        assert _prompt_taken_from(frame) == "do the thing"

    def test_the_to_field_does_not_disturb_it(self, keys):
        """Relayed frames carry `to` in the signed payload; direct ones do not."""
        frame = _signed_input(keys, "the signed one", top_level_prompt="other",
                              to="0x" + "a" * 64)

        assert _prompt_taken_from(frame) == "the signed one"


class TestWithoutASignature:
    """A client built with no keys signs nothing, and its connection was
    authenticated by its CONNECT. Requiring a signature here is the decision
    filed in #649; honouring one that is present is not."""

    def test_the_top_level_prompt_is_used(self):
        assert _prompt_taken_from({"type": "INPUT", "prompt": "unsigned but connected"}) == \
            "unsigned but connected"

    def test_a_payload_with_no_signature_is_not_trusted_over_it(self):
        """Half a signature is not a signature."""
        frame = {"type": "INPUT", "prompt": "top level",
                 "payload": {"prompt": "claimed but unsigned"}}

        assert _prompt_taken_from(frame) == "top level"

    def test_a_missing_prompt_is_still_missing(self):
        assert _prompt_taken_from({"type": "INPUT"}) is None


class TestTheTwoPathsAgree:
    """The HTTP path is the one that was already right; this is about matching it."""

    def test_http_reads_the_signed_prompt(self, keys):
        from connectonion.network.host.auth import extract_and_authenticate

        frame = _signed_input(keys, "the signed one", top_level_prompt="the substituted one")
        prompt, _, valid, _ = extract_and_authenticate(frame, "open")

        assert valid and prompt == "the signed one"

    def test_and_now_so_does_the_websocket_path(self, keys):
        frame = _signed_input(keys, "the signed one", top_level_prompt="the substituted one")

        from connectonion.network.host.auth import extract_and_authenticate

        http_prompt, _, _, _ = extract_and_authenticate(frame, "open")
        assert _prompt_taken_from(frame) == http_prompt


class TestASignatureThatDoesNotHold:
    """Reading the signed field is not enough on its own — an unverified payload
    can say anything, so a frame that carries a signature must pass it."""

    def test_a_forged_signature_is_refused(self, keys):
        frame = _signed_input(keys, "the signed one", top_level_prompt="the substituted one")
        frame["signature"] = "00" * 64

        with pytest.raises(AssertionError, match="refused"):
            _prompt_taken_from(frame)

    def test_a_payload_edited_after_signing_is_refused(self, keys):
        frame = _signed_input(keys, "the signed one")
        frame["payload"]["prompt"] = "swapped in afterwards"

        with pytest.raises(AssertionError, match="refused"):
            _prompt_taken_from(frame)

    def test_a_signature_from_someone_else_is_refused(self, keys):
        other = address.generate()
        frame = _signed_input(keys, "the signed one")
        frame["from"] = other["address"]

        with pytest.raises(AssertionError, match="refused"):
            _prompt_taken_from(frame)

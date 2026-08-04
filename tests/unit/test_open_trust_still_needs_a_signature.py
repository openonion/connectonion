"""`open` trust allows everyone in. It does not let anyone in unsigned.

The shipped policy says the second thing:

    connectonion/network/trust/policies/open.md

        # Open Trust (Development)
        # Allow everyone - no verification needed
        default: allow

Verification is exactly what is still needed. `extract_and_authenticate` refuses
an unsigned request before any trust level is consulted:

    # Protocol requirement: ALL requests must be signed
    if "payload" not in data or "signature" not in data:
        return None, None, False, "unauthorized: signed request required"

Measured against a real agent started with `trust: open` in host.yaml:

    GET  /info    ->  {"trust": "open"}
    POST /input   ->  401 {"error": "unauthorized: signed request required"}

The levels decide *authorisation* — which signed identity may act. `open` means
any identity, `careful` means admin/whitelisted/contact, `strict` means the
whitelist. None of them decides *authentication*, which is the signature and is
not optional.

`careful.md` and `strict.md` describe themselves in exactly those terms — "Who
has access", "Only whitelisted users". `open.md` was the one that conflated the
two, and it is the level a developer picks precisely when they want to curl the
thing. What they get instead looks like a bug in the framework.

The behavioural assertions here matter more than the wording one: they pin a
security property. An `open` that skipped signatures would let an unauthenticated
caller run an agent's tools, and it would look like it was doing what its own
documentation said.
"""

import pytest

from connectonion.network.host.auth import extract_and_authenticate
from connectonion.network.trust.factory import PROMPTS_DIR


UNSIGNED = {"prompt": "run something"}


def _authenticate(data, trust="open"):
    return extract_and_authenticate(data, trust)


class TestOpenStillRequiresASignature:

    def test_an_unsigned_request_is_refused(self):
        _, _, valid, error = _authenticate(UNSIGNED)

        assert not valid
        assert "signed" in error

    def test_a_payload_without_a_signature_is_refused(self):
        _, _, valid, error = _authenticate({"payload": {"prompt": "hi"}})

        assert not valid
        assert "signed" in error

    def test_a_signature_without_a_payload_is_refused(self):
        _, _, valid, _ = _authenticate({"signature": "0xdeadbeef"})

        assert not valid

    @pytest.mark.parametrize("level", ["open", "careful", "strict"])
    def test_no_level_makes_the_signature_optional(self, level):
        """Authentication is not what the levels decide."""
        _, _, valid, error = _authenticate(UNSIGNED, trust=level)

        assert not valid, f"{level} accepted an unsigned request"
        assert "signed" in error


class TestThePolicySaysWhatItDoes:
    """The wording is what sent a reader to curl an agent that will refuse them."""

    def test_open_does_not_claim_verification_is_unnecessary(self):
        text = (PROMPTS_DIR / "open.md").read_text(encoding="utf-8")

        assert "no verification needed" not in text.lower(), (
            "open.md still says verification is not needed; a request without a "
            "signature is refused before the trust level is read"
        )

    def test_open_still_allows_by_default(self):
        """The functional half must not change while the wording does."""
        import yaml

        from connectonion.network.trust import parse_policy

        config, _ = parse_policy((PROMPTS_DIR / "open.md").read_text(encoding="utf-8"))

        assert config.get("default") == "allow"

    @pytest.mark.parametrize("name", ["open", "careful", "strict"])
    def test_every_level_still_parses(self, name):
        from connectonion.network.trust import parse_policy

        config, _ = parse_policy((PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"))

        assert config, f"{name}.md stopped parsing"

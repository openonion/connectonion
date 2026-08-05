"""Tests for fast_rules.py - YAML parsing and rule execution."""
"""
LLM-Note: Tests for fast rules

What it tests:
- Fast Rules functionality

Components under test:
- Module: fast_rules
"""


import pytest
import yaml
from pathlib import Path

from connectonion.network.trust.fast_rules import parse_policy, evaluate_request
from connectonion.network.trust import tools


@pytest.fixture
def temp_co_dir(tmp_path, monkeypatch):
    """A directory that *is* this agent — the lists live inside it.

    These fixtures used to redirect a module-level CO_DIR, which is the shape
    of the bug they were working around: one global path meant one whitelist
    for every agent on the machine. Now the agent's cwd decides, so the way to
    isolate a test is to give it its own agent directory.
    """
    co_dir = tmp_path / ".co"
    co_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    return co_dir


class TestParsePolicy:
    """Test YAML frontmatter parsing."""

    def test_parse_simple_yaml(self):
        """Parse simple YAML frontmatter."""
        policy = """---
default: allow
---

# Body
"""
        config, body = parse_policy(policy)
        assert config["default"] == "allow"
        assert "Body" in body

    def test_parse_complex_yaml(self):
        """Parse complex YAML with nested config."""
        policy = """---
allow:
  - whitelisted
  - contact
onboard:
  invite_code: [CODE1, CODE2]
  payment: 10
default: ask
---

# Trust Agent
"""
        config, body = parse_policy(policy)
        assert config["allow"] == ["whitelisted", "contact"]
        assert config["onboard"]["invite_code"] == ["CODE1", "CODE2"]
        assert config["onboard"]["payment"] == 10
        assert config["default"] == "ask"

    def test_parse_no_yaml(self):
        """Handle markdown without YAML frontmatter."""
        policy = "# Just markdown\n\nNo YAML here."
        config, body = parse_policy(policy)
        assert config == {}
        assert "Just markdown" in body

    def test_parse_empty_yaml(self):
        """Handle empty YAML frontmatter."""
        policy = """---
---

# Body
"""
        config, body = parse_policy(policy)
        assert config == {}
        assert "Body" in body


class TestEvaluateRequestOpenMode:
    """Test evaluate_request with default: allow config."""

    def test_default_allow_allows_everyone(self, temp_co_dir):
        """default: allow allows any request."""
        config = {"default": "allow"}
        result = evaluate_request(config, "any-client", {})
        assert result == "allow"


class TestEvaluateRequestBlocklist:
    """Test blocklist checking."""

    def test_blocked_client_denied(self, temp_co_dir):
        """Blocked client is denied."""
        (temp_co_dir / "blocklist.txt").write_text("bad-client\n")

        config = {"deny": ["blocked"]}
        result = evaluate_request(config, "bad-client", {})
        assert result == "deny"

    def test_unblocked_client_not_denied(self, temp_co_dir):
        """Non-blocked client is not denied by blocklist."""
        (temp_co_dir / "blocklist.txt").write_text("other-client\n")

        config = {"deny": ["blocked"], "default": "allow"}
        result = evaluate_request(config, "good-client", {})
        assert result == "allow"


class TestEvaluateRequestWhitelist:
    """Test whitelist checking."""

    def test_whitelisted_client_allowed(self, temp_co_dir):
        """Whitelisted client is allowed."""
        (temp_co_dir / "whitelist.txt").write_text("trusted-client\n")

        config = {"allow": ["whitelisted"]}
        result = evaluate_request(config, "trusted-client", {})
        assert result == "allow"

    def test_whitelist_wildcard(self, temp_co_dir):
        """Whitelist wildcard pattern works."""
        (temp_co_dir / "whitelist.txt").write_text("payment-*\n")

        config = {"allow": ["whitelisted"]}
        result = evaluate_request(config, "payment-gateway-1", {})
        assert result == "allow"


class TestEvaluateRequestStrictMode:
    """Test strict mode (whitelist only)."""

    def test_strict_allows_whitelisted(self, temp_co_dir):
        """Strict mode allows whitelisted clients."""
        (temp_co_dir / "whitelist.txt").write_text("trusted\n")

        config = {"allow": ["whitelisted"], "default": "deny"}
        result = evaluate_request(config, "trusted", {})
        assert result == "allow"

    def test_strict_denies_others(self, temp_co_dir):
        """Strict mode denies non-whitelisted clients."""
        config = {"allow": ["whitelisted"], "default": "deny"}
        result = evaluate_request(config, "unknown-client", {})
        assert result == "deny"


class TestEvaluateRequestContact:
    """Test contact access."""

    def test_contact_allowed(self, temp_co_dir):
        """Contact is allowed when in allow list."""
        (temp_co_dir / "contacts.txt").write_text("existing-contact\n")

        config = {"allow": ["whitelisted", "contact"]}
        result = evaluate_request(config, "existing-contact", {})
        assert result == "allow"

    def test_contact_not_allowed_if_not_in_list(self, temp_co_dir):
        """Contact not allowed if 'contact' not in allow list."""
        (temp_co_dir / "contacts.txt").write_text("existing-contact\n")

        config = {"allow": ["whitelisted"], "default": "deny"}
        result = evaluate_request(config, "existing-contact", {})
        assert result == "deny"


class TestEvaluateRequestOnboard:
    """Test onboarding (stranger → contact)."""

    def test_valid_invite_code_onboards(self, temp_co_dir):
        """Valid invite code promotes to contact and allows."""
        config = {
            "allow": ["contact"],
            "onboard": {"invite_code": ["BETA2024", "FRIEND123"]}
        }
        request = {"invite_code": "BETA2024"}
        result = evaluate_request(config, "new-client", request)
        assert result == "allow"
        assert tools.is_contact("new-client")

    def test_invalid_invite_code_rejected(self, temp_co_dir):
        """Invalid invite code doesn't onboard."""
        config = {
            "onboard": {"invite_code": ["BETA2024"]},
            "default": "deny"
        }
        request = {"invite_code": "WRONG"}
        result = evaluate_request(config, "client", request)
        assert result == "deny"
        assert not tools.is_contact("client")

    def test_a_claimed_payment_does_not_onboard(self, temp_co_dir):
        """`request["payment"]` is a number the client wrote in its own frame.

        These two used to assert the opposite -- that {"payment": 15} against
        `payment: 10` returned "allow" and made the client a contact. Nothing on
        this path verifies a transfer; verify_payment and its oo-api call are on
        ONBOARD_SUBMIT. Demonstrated against a real host, from a
        freshly-generated identity with no balance and no history:

            claimed payment: 999, transferred: nothing
            -> {"type": "CONNECTED", "session_id": ..., "status": "new"}
               contacts.txt: 1 entry

        The signature on that frame proves who said it, not that anything was
        paid. Payment is decided on ONBOARD_SUBMIT now, where it is checked.
        """
        config = {"onboard": {"payment": 10}, "default": "deny"}
        request = {"payment": 15}
        result = evaluate_request(config, "paying-client", request)
        assert result == "deny"
        assert not tools.is_contact("paying-client")

    def test_not_even_the_exact_amount(self, temp_co_dir):
        config = {"onboard": {"payment": 10}, "default": "deny"}
        request = {"payment": 10}
        result = evaluate_request(config, "client", request)
        assert result == "deny"
        assert not tools.is_contact("client")

    def test_insufficient_payment_rejected(self, temp_co_dir):
        """Insufficient payment doesn't onboard."""
        config = {"onboard": {"payment": 10}, "default": "deny"}
        request = {"payment": 5}
        result = evaluate_request(config, "client", request)
        assert result == "deny"


class TestEvaluateRequestDefault:
    """Test default action for strangers."""

    def test_default_allow(self, temp_co_dir):
        """default: allow allows strangers."""
        config = {"default": "allow"}
        result = evaluate_request(config, "stranger", {})
        assert result == "allow"

    def test_default_deny(self, temp_co_dir):
        """default: deny denies strangers."""
        config = {"default": "deny"}
        result = evaluate_request(config, "stranger", {})
        assert result == "deny"

    def test_default_ask(self, temp_co_dir):
        """default: ask returns None for LLM evaluation."""
        config = {"default": "ask"}
        result = evaluate_request(config, "stranger", {})
        assert result is None

    def test_default_is_deny(self, temp_co_dir):
        """Default fallback is deny."""
        config = {}
        result = evaluate_request(config, "stranger", {})
        assert result == "deny"


class TestEvaluateRequestPriority:
    """Test rule evaluation priority."""

    def test_deny_before_allow(self, temp_co_dir):
        """Deny is checked before allow."""
        (temp_co_dir / "blocklist.txt").write_text("client\n")
        (temp_co_dir / "whitelist.txt").write_text("client\n")

        config = {"deny": ["blocked"], "allow": ["whitelisted"]}
        result = evaluate_request(config, "client", {})
        assert result == "deny"

    def test_allow_before_onboard(self, temp_co_dir):
        """Allowed client doesn't need to onboard."""
        (temp_co_dir / "whitelist.txt").write_text("trusted\n")

        config = {
            "allow": ["whitelisted"],
            "onboard": {"invite_code": ["CODE"]}
        }
        result = evaluate_request(config, "trusted", {})
        assert result == "allow"


class TestAnAdminIsNotAStranger:
    """`co deploy --to` writes the operator's key into .co/admins.txt and prints
    "admin: 0x… (your key)". The trust gate then never consulted that list, so a
    freshly deployed agent answered its own owner with "agent requires
    onboarding" — for a machine they had just paid for and installed their key
    on. Found by running `co call` against a server created minutes earlier.
    """

    def test_an_admin_is_allowed(self, monkeypatch):
        config = {"allow": ["admin", "whitelisted", "contact"], "deny": ["blocked"]}
        monkeypatch.setattr("connectonion.network.trust.fast_rules.is_admin",
                            lambda cid: cid == "0xadmin")
        monkeypatch.setattr("connectonion.network.trust.fast_rules.is_blocked",
                            lambda cid: False)

        assert evaluate_request(config, "0xadmin", {}) == "allow"

    def test_a_stranger_is_still_not(self, monkeypatch):
        config = {"allow": ["admin"], "deny": ["blocked"], "default": "deny"}
        monkeypatch.setattr("connectonion.network.trust.fast_rules.is_admin",
                            lambda cid: cid == "0xadmin")
        monkeypatch.setattr("connectonion.network.trust.fast_rules.is_blocked",
                            lambda cid: False)

        assert evaluate_request(config, "0xstranger", {}) == "deny"

    def test_a_blocked_admin_is_still_blocked(self, monkeypatch):
        """Deny is evaluated first, and being the operator does not undo it."""
        config = {"allow": ["admin"], "deny": ["blocked"]}
        monkeypatch.setattr("connectonion.network.trust.fast_rules.is_admin",
                            lambda cid: True)
        monkeypatch.setattr("connectonion.network.trust.fast_rules.is_blocked",
                            lambda cid: True)

        assert evaluate_request(config, "0xadmin", {}) == "deny"

    def test_the_shipped_policies_let_the_operator_in(self):
        """A policy that omits `admin` puts the operator back outside."""
        from connectonion.network.trust.fast_rules import parse_policy

        for level in ("careful", "strict"):
            path = (Path(__file__).parent.parent.parent / "connectonion" / "network" /
                    "trust" / "policies" / f"{level}.md")
            config, _ = parse_policy(path.read_text())
            assert "admin" in config.get("allow", []), level


class TestAYamlErrorNamesThePolicyFile:
    """A typo in a policy still stops the host — that is the right outcome for a
    config file it cannot understand. What was missing is *which* file: PyYAML
    names the stream it was given, and a bare string is named "<unicode
    string>", so an operator with several policies and the built-in ones had a
    line number and no way to know where to look. openonion/connectonion#381
    """

    def test_the_error_names_the_file_when_the_caller_knows_it(self):
        bad = "---\nallow: [whitelisted, contact\n---\n# Body\n"

        with pytest.raises(yaml.YAMLError) as exc:
            parse_policy(bad, source=".co/trust/custom.md")

        assert ".co/trust/custom.md" in str(exc.value)

    def test_it_is_still_the_parsers_own_error(self):
        """Not caught and re-raised: the parser says what is wrong, and it says
        it better than a message we would write, including the offending line."""
        bad = "---\nallow: [whitelisted, contact\n---\n# Body\n"

        with pytest.raises(yaml.YAMLError) as exc:
            parse_policy(bad, source="p.md")

        assert "expected ',' or ']'" in str(exc.value)

    def test_inline_policy_text_still_parses(self):
        """Not every caller has a file — inline policies are passed as text."""
        config, body = parse_policy("---\nallow: [admin]\n---\n# Body")

        assert config == {"allow": ["admin"]}

    def test_loading_a_policy_file_names_that_file(self, tmp_path):
        from connectonion.network.trust.trust_agent import TrustAgent

        policy = tmp_path / "custom.md"
        policy.write_text("---\nallow: [whitelisted, contact\n---\n# Body\n")

        with pytest.raises(yaml.YAMLError) as exc:
            TrustAgent(str(policy))

        assert "custom.md" in str(exc.value)

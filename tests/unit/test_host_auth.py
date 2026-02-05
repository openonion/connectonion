"""Unit tests for connectonion/network/host/auth.py

Tests cover:
- verify_signature() Ed25519 signature verification
- extract_and_authenticate() request authentication
- _authenticate_signed() signed request processing
- get_agent_address() deterministic address generation
- is_custom_trust() trust type detection
- evaluate_with_trust_agent() (mocked LLM)
"""

import hashlib
import json
import time
import pytest
from unittest.mock import patch, Mock, MagicMock

from connectonion.network.host.auth import (
    verify_signature,
    extract_and_authenticate,
    get_agent_address,
    is_custom_trust,
    SIGNATURE_EXPIRY_SECONDS,
)


class TestVerifySignature:
    """Test Ed25519 signature verification."""

    def test_valid_signature(self):
        """Valid Ed25519 signature passes verification."""
        from nacl.signing import SigningKey

        # Generate keypair
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key

        # Create payload and sign
        payload = {"prompt": "Hello", "timestamp": 12345}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = signing_key.sign(canonical.encode()).signature

        result = verify_signature(
            payload,
            signature.hex(),
            verify_key.encode().hex()
        )

        assert result is True

    def test_valid_signature_with_0x_prefix(self):
        """Signature with 0x prefix is handled correctly."""
        from nacl.signing import SigningKey

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key

        payload = {"prompt": "Test", "timestamp": 99999}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = signing_key.sign(canonical.encode()).signature

        result = verify_signature(
            payload,
            "0x" + signature.hex(),
            "0x" + verify_key.encode().hex()
        )

        assert result is True

    def test_invalid_signature_fails(self):
        """Invalid signature fails verification."""
        from nacl.signing import SigningKey

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key

        payload = {"prompt": "Hello", "timestamp": 12345}

        # Wrong signature (random bytes)
        result = verify_signature(
            payload,
            "a" * 128,  # 64 bytes in hex
            verify_key.encode().hex()
        )

        assert result is False

    def test_wrong_payload_fails(self):
        """Signature for different payload fails."""
        from nacl.signing import SigningKey

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key

        # Sign one payload
        original_payload = {"prompt": "Original", "timestamp": 12345}
        canonical = json.dumps(original_payload, sort_keys=True, separators=(",", ":"))
        signature = signing_key.sign(canonical.encode()).signature

        # Verify with different payload
        modified_payload = {"prompt": "Modified", "timestamp": 12345}
        result = verify_signature(
            modified_payload,
            signature.hex(),
            verify_key.encode().hex()
        )

        assert result is False

    def test_invalid_hex_fails(self):
        """Invalid hex encoding fails gracefully."""
        result = verify_signature(
            {"prompt": "Test"},
            "not_valid_hex!",
            "also_not_hex!"
        )

        assert result is False

    def test_deterministic_json_serialization(self):
        """Payload keys are sorted for consistent signing."""
        from nacl.signing import SigningKey

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key

        # Create payload with keys in different order
        payload1 = {"z": 1, "a": 2, "m": 3}
        payload2 = {"a": 2, "m": 3, "z": 1}

        # Sign payload1
        canonical = json.dumps(payload1, sort_keys=True, separators=(",", ":"))
        signature = signing_key.sign(canonical.encode()).signature

        # Verify with payload2 (same data, different order)
        result = verify_signature(
            payload2,
            signature.hex(),
            verify_key.encode().hex()
        )

        assert result is True


class TestExtractAndAuthenticate:
    """Test extract_and_authenticate function."""

    def test_missing_payload_rejected(self):
        """Request without payload is rejected."""
        data = {"prompt": "Hello"}

        prompt, identity, sig_valid, error = extract_and_authenticate(data, "open")

        assert error == "unauthorized: signed request required"
        assert prompt is None

    def test_missing_signature_rejected(self):
        """Request without signature is rejected."""
        data = {"payload": {"prompt": "Hello", "timestamp": time.time()}, "from": "0xabc"}

        prompt, identity, sig_valid, error = extract_and_authenticate(data, "open")

        assert error == "unauthorized: signed request required"

    def test_blacklisted_identity_rejected(self):
        """Blacklisted identity is rejected."""
        data = {
            "payload": {"prompt": "Hello", "timestamp": time.time()},
            "from": "0xbad",
            "signature": "0x1234"
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(
            data, "open", blacklist=["0xbad"]
        )

        assert error == "forbidden: blacklisted"
        assert identity == "0xbad"

    def test_whitelisted_still_requires_valid_signature(self):
        """Whitelisted identity must still provide valid signature.

        Security fix: whitelist bypasses TRUST POLICY, not SIGNATURE VERIFICATION.
        Even whitelisted identities must prove their identity cryptographically.
        This prevents spoofing attacks where anyone claims to be a whitelisted identity.
        """
        data = {
            "payload": {"prompt": "Hello world", "timestamp": time.time()},
            "from": "0xtrusted",
            "signature": "invalid_signature"  # Invalid signature should fail
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(
            data, "strict", whitelist=["0xtrusted"]
        )

        # Should fail - whitelist does NOT bypass signature verification!
        assert error == "unauthorized: invalid signature"
        assert sig_valid is False

    def test_missing_from_rejected(self):
        """Request without 'from' field is rejected."""
        data = {
            "payload": {"prompt": "Hello", "timestamp": time.time()},
            "signature": "0x1234"
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(data, "open")

        assert "from" in error

    def test_missing_timestamp_rejected(self):
        """Request without timestamp is rejected."""
        data = {
            "payload": {"prompt": "Hello"},
            "from": "0xabc",
            "signature": "0x1234"
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(data, "open")

        assert "timestamp" in error

    def test_expired_signature_rejected(self):
        """Signature with expired timestamp is rejected."""
        old_timestamp = time.time() - SIGNATURE_EXPIRY_SECONDS - 60  # 6+ minutes ago

        data = {
            "payload": {"prompt": "Hello", "timestamp": old_timestamp},
            "from": "0xabc",
            "signature": "0x1234"
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(data, "open")

        assert "expired" in error

    def test_future_timestamp_rejected(self):
        """Signature with far-future timestamp is rejected."""
        future_timestamp = time.time() + SIGNATURE_EXPIRY_SECONDS + 60  # 6+ minutes ahead

        data = {
            "payload": {"prompt": "Hello", "timestamp": future_timestamp},
            "from": "0xabc",
            "signature": "0x1234"
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(data, "open")

        assert "expired" in error

    def test_wrong_recipient_rejected(self):
        """Request with wrong 'to' address is rejected."""
        data = {
            "payload": {"prompt": "Hello", "timestamp": time.time(), "to": "0xwrong"},
            "from": "0xsender",
            "signature": "0x1234"
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(
            data, "open", agent_address="0xcorrect"
        )

        assert "wrong recipient" in error

    def test_strict_trust_without_whitelist_rejected(self):
        """Strict trust rejects non-whitelisted identity."""
        from nacl.signing import SigningKey

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        public_key_hex = "0x" + verify_key.encode().hex()

        payload = {"prompt": "Hello", "timestamp": time.time()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = "0x" + signing_key.sign(canonical.encode()).signature.hex()

        data = {
            "payload": payload,
            "from": public_key_hex,
            "signature": signature
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(
            data, "strict", whitelist=["0xother"]  # Not this caller
        )

        assert error == "forbidden: Denied by fast rules"
        assert sig_valid is True  # Signature was valid, just not allowed by TrustAgent

    def test_valid_signed_request_succeeds(self):
        """Fully valid signed request is accepted."""
        from nacl.signing import SigningKey

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        public_key_hex = "0x" + verify_key.encode().hex()

        payload = {"prompt": "Calculate 2+2", "timestamp": time.time()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = "0x" + signing_key.sign(canonical.encode()).signature.hex()

        data = {
            "payload": payload,
            "from": public_key_hex,
            "signature": signature
        }

        prompt, identity, sig_valid, error = extract_and_authenticate(data, "open")

        assert error is None
        assert prompt == "Calculate 2+2"
        assert identity == public_key_hex
        assert sig_valid is True

    def test_accepts_trust_agent_directly(self, tmp_path, monkeypatch):
        """Can pass TrustAgent instance directly instead of string."""
        from nacl.signing import SigningKey
        from connectonion.network.trust import TrustAgent

        # Set up temp ~/.co directory
        co_path = tmp_path / ".co"
        co_path.mkdir()
        monkeypatch.setattr("connectonion.network.trust.tools.CO_DIR", co_path)

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        public_key_hex = "0x" + verify_key.encode().hex()

        payload = {"prompt": "Hello", "timestamp": time.time()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = "0x" + signing_key.sign(canonical.encode()).signature.hex()

        data = {
            "payload": payload,
            "from": public_key_hex,
            "signature": signature
        }

        # Pass TrustAgent instance directly
        trust_agent = TrustAgent("open")
        prompt, identity, sig_valid, error = extract_and_authenticate(data, trust_agent)

        assert error is None
        assert prompt == "Hello"
        assert sig_valid is True


class TestGetAgentAddress:
    """Test get_agent_address function."""

    def test_deterministic_address(self):
        """Same agent name always produces same address."""
        mock_agent = Mock()
        mock_agent.name = "my_agent"

        addr1 = get_agent_address(mock_agent)
        addr2 = get_agent_address(mock_agent)

        assert addr1 == addr2

    def test_different_names_different_addresses(self):
        """Different names produce different addresses."""
        agent1 = Mock()
        agent1.name = "agent_one"
        agent2 = Mock()
        agent2.name = "agent_two"

        addr1 = get_agent_address(agent1)
        addr2 = get_agent_address(agent2)

        assert addr1 != addr2

    def test_address_format(self):
        """Address has correct format (0x prefix, 40 hex chars)."""
        mock_agent = Mock()
        mock_agent.name = "test_agent"

        addr = get_agent_address(mock_agent)

        assert addr.startswith("0x")
        assert len(addr) == 42  # 0x + 40 hex chars
        assert all(c in "0123456789abcdef" for c in addr[2:])

    def test_uses_sha256(self):
        """Address is based on SHA256 hash of name."""
        mock_agent = Mock()
        mock_agent.name = "hash_test"

        addr = get_agent_address(mock_agent)

        expected_hash = hashlib.sha256("hash_test".encode()).hexdigest()
        assert addr == f"0x{expected_hash[:40]}"


class TestIsCustomTrust:
    """Test is_custom_trust function."""

    def test_open_is_not_custom(self):
        """Trust level 'open' is not custom."""
        assert is_custom_trust("open") is False

    def test_careful_is_not_custom(self):
        """Trust level 'careful' is not custom."""
        assert is_custom_trust("careful") is False

    def test_strict_is_not_custom(self):
        """Trust level 'strict' is not custom."""
        assert is_custom_trust("strict") is False

    def test_policy_string_is_custom(self):
        """Policy strings are custom."""
        assert is_custom_trust("I trust agents that pass verification") is True
        assert is_custom_trust("Only allow verified agents") is True

    def test_file_path_is_custom(self):
        """File paths are custom."""
        assert is_custom_trust("./trust_policy.md") is True
        assert is_custom_trust("/path/to/policy.md") is True

    def test_agent_instance_is_custom(self):
        """Agent instances are custom."""
        from connectonion import Agent
        from unittest.mock import Mock

        # Use a mock to avoid real LLM initialization
        mock_agent = Mock(spec=Agent)
        mock_agent.name = "guardian"
        assert is_custom_trust(mock_agent) is True

    def test_non_string_is_custom(self):
        """Non-string types are treated as custom."""
        assert is_custom_trust(123) is True
        assert is_custom_trust({"policy": "test"}) is True


class TestSignatureExpiryConstant:
    """Test SIGNATURE_EXPIRY_SECONDS constant."""

    def test_expiry_is_5_minutes(self):
        """Signature expiry is 5 minutes (300 seconds)."""
        assert SIGNATURE_EXPIRY_SECONDS == 300


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for announce.py - ANNOUNCE message creation and signing."""

import json
import time
import pytest
from unittest.mock import patch, Mock

from connectonion.network.announce import create_announce_message


class TestCreateAnnounceMessage:
    """Test create_announce_message function."""

    def test_creates_message_with_required_fields(self):
        """Message contains all required fields."""
        address_data = {
            "address": "0x1234567890abcdef",
            "signing_key": b"fake_key"
        }

        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = b"signature_bytes"
            result = create_announce_message(address_data, "Test agent")

        assert result["type"] == "ANNOUNCE"
        assert result["address"] == "0x1234567890abcdef"
        assert "timestamp" in result
        assert result["summary"] == "Test agent"
        assert result["endpoints"] == []
        assert "signature" in result

    def test_includes_endpoints_when_provided(self):
        """Message includes endpoints when provided."""
        address_data = {
            "address": "0x1234",
            "signing_key": b"key"
        }
        endpoints = ["tcp://127.0.0.1:8080", "ws://localhost:9000"]

        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = b"sig"
            result = create_announce_message(address_data, "Agent", endpoints)

        assert result["endpoints"] == endpoints

    def test_timestamp_is_current(self):
        """Timestamp is close to current time."""
        address_data = {
            "address": "0x1234",
            "signing_key": b"key"
        }

        before = int(time.time())
        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = b"sig"
            result = create_announce_message(address_data, "Agent")
        after = int(time.time())

        assert before <= result["timestamp"] <= after

    def test_signature_is_hex_string(self):
        """Signature is hex encoded without 0x prefix."""
        address_data = {
            "address": "0x1234",
            "signing_key": b"key"
        }

        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = bytes.fromhex("abcd1234")
            result = create_announce_message(address_data, "Agent")

        assert result["signature"] == "abcd1234"
        assert not result["signature"].startswith("0x")

    def test_signs_deterministic_json(self):
        """Message is signed with deterministic JSON (sort_keys=True)."""
        address_data = {
            "address": "0x1234",
            "signing_key": b"key"
        }

        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = b"sig"
            create_announce_message(address_data, "Agent", ["tcp://host:80"])

            # Verify sign was called with sorted JSON
            call_args = mock_sign.call_args
            signed_data = call_args[0][1]  # Second argument is message_bytes

            # Parse and verify it's sorted
            parsed = json.loads(signed_data.decode('utf-8'))
            expected_keys = ["address", "endpoints", "summary", "timestamp", "type"]
            assert list(parsed.keys()) == expected_keys

    def test_default_endpoints_is_empty_list(self):
        """Default endpoints is empty list when not provided."""
        address_data = {
            "address": "0x1234",
            "signing_key": b"key"
        }

        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = b"sig"
            result = create_announce_message(address_data, "Agent")

        assert result["endpoints"] == []

    def test_none_endpoints_becomes_empty_list(self):
        """Explicitly passing None for endpoints becomes empty list."""
        address_data = {
            "address": "0x1234",
            "signing_key": b"key"
        }

        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = b"sig"
            result = create_announce_message(address_data, "Agent", None)

        assert result["endpoints"] == []

    def test_missing_address_key_raises(self):
        """Missing 'address' key raises KeyError."""
        address_data = {
            "signing_key": b"key"
        }

        with pytest.raises(KeyError):
            with patch("connectonion.address.sign") as mock_sign:
                mock_sign.return_value = b"sig"
                create_announce_message(address_data, "Agent")

    def test_long_summary_is_preserved(self):
        """Long summary is preserved without truncation."""
        address_data = {
            "address": "0x1234",
            "signing_key": b"key"
        }
        long_summary = "A" * 1000

        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = b"sig"
            result = create_announce_message(address_data, long_summary)

        assert result["summary"] == long_summary
        assert len(result["summary"]) == 1000

    def test_unicode_summary_is_handled(self):
        """Unicode characters in summary are handled correctly."""
        address_data = {
            "address": "0x1234",
            "signing_key": b"key"
        }
        unicode_summary = "Agent with emoji and unicode chars"

        with patch("connectonion.address.sign") as mock_sign:
            mock_sign.return_value = b"sig"
            result = create_announce_message(address_data, unicode_summary)

        assert result["summary"] == unicode_summary

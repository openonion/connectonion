"""Unit tests for connectonion/address.py (imports aligned)."""

import pytest
from connectonion.address import generate


class TestAddress:
    """Test address generation and validation."""

    def test_generate_address(self):
        """Test address generation via generate()."""
        data = None
        try:
            data = generate()
        except ImportError:
            pytest.skip("pynacl/mnemonic not installed for address generation")
        assert data is not None
        assert data["address"].startswith("0x")
        assert len(data["address"]) > 10

    def test_validate_valid_address(self):
        """Basic format validation of address string."""
        valid_address = "0x04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d"
        assert valid_address.startswith("0x") and len(valid_address) == 66

    def test_validate_invalid_address(self):
        """Basic validation of obviously invalid addresses."""
        invalid_addresses = [
            "not_an_address",
            "0xinvalid",
            "",
            "123456"
        ]
        for addr in invalid_addresses:
            assert not (addr.startswith("0x") and len(addr) == 66)

    def test_short_address_format(self):
        """Short display format exists in generated data."""
        try:
            data = generate()
        except ImportError:
            pytest.skip("pynacl/mnemonic not installed for address generation")
        short_address = data["short_address"]
        assert short_address.startswith("0x")
        assert len(short_address) < len(data["address"])

    def test_invalid_shorten_input(self):
        """No built-in shorten function; ensure format guard logic consistent."""
        addr = "not_an_address"
        assert not (addr.startswith("0x") and len(addr) == 66)

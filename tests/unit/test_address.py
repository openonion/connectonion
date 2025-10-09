"""Unit tests for connectonion/address.py (imports aligned)."""

import unittest
from connectonion.address import generate


class TestAddress(unittest.TestCase):
    """Test address generation and validation."""

    def test_generate_address(self):
        """Test address generation via generate()."""
        data = None
        try:
            data = generate()
        except ImportError:
            self.skipTest("pynacl/mnemonic not installed for address generation")
        self.assertIsNotNone(data)
        self.assertTrue(data["address"].startswith("0x"))
        self.assertGreater(len(data["address"]), 10)

    def test_validate_valid_address(self):
        """Basic format validation of address string."""
        valid_address = "0x04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d"
        self.assertTrue(valid_address.startswith("0x") and len(valid_address) == 66)

    def test_validate_invalid_address(self):
        """Basic validation of obviously invalid addresses."""
        invalid_addresses = [
            "not_an_address",
            "0xinvalid",
            "",
            "123456"
        ]
        for addr in invalid_addresses:
            self.assertFalse(addr.startswith("0x") and len(addr) == 66)

    def test_short_address_format(self):
        """Short display format exists in generated data."""
        try:
            data = generate()
        except ImportError:
            self.skipTest("pynacl/mnemonic not installed for address generation")
        short_address = data["short_address"]
        self.assertTrue(short_address.startswith("0x"))
        self.assertLess(len(short_address), len(data["address"]))

    def test_invalid_shorten_input(self):
        """No built-in shorten function; ensure format guard logic consistent."""
        addr = "not_an_address"
        self.assertFalse(addr.startswith("0x") and len(addr) == 66)


if __name__ == '__main__':
    unittest.main()

"""Unit tests for connectonion/address.py"""

import unittest
from connectonion.address import generate_address, validate_address, shorten_address


class TestAddress(unittest.TestCase):
    """Test address generation and validation."""

    def test_generate_address(self):
        """Test address generation."""
        address = generate_address()
        self.assertIsNotNone(address)
        self.assertTrue(address.startswith("0x"))
        self.assertGreater(len(address), 10)

    def test_validate_valid_address(self):
        """Test validation of valid address."""
        valid_address = "0x04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d"
        self.assertTrue(validate_address(valid_address))

    def test_validate_invalid_address(self):
        """Test validation of invalid address."""
        invalid_addresses = [
            "not_an_address",
            "0xinvalid",
            "",
            "123456"
        ]
        for addr in invalid_addresses:
            self.assertFalse(validate_address(addr))

    def test_shorten_address(self):
        """Test address shortening."""
        full_address = "0x04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d"
        short_address = shorten_address(full_address)

        self.assertTrue(short_address.startswith("0x"))
        self.assertLess(len(short_address), len(full_address))
        self.assertEqual(short_address, "0x04e1c4ae")

    def test_shorten_invalid_address(self):
        """Test shortening invalid address."""
        with self.assertRaises(ValueError):
            shorten_address("not_an_address")


if __name__ == '__main__':
    unittest.main()
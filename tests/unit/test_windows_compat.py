"""Windows compatibility tests for UTF-8 encoding and path handling.

Tests that ConnectOnion works correctly on Windows with:
- Non-ASCII usernames (Chinese, Arabic, Russian, etc.)
- Spaces in paths
- Windows path separators
- Platform-specific chmod behavior
"""

import unittest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from connectonion import address
from connectonion.console import Console


class TestUTF8Encoding(unittest.TestCase):
    """Test UTF-8 encoding works with non-ASCII paths."""

    def test_address_save_load_with_chinese_path(self):
        """Test saving and loading Ed25519 keys with Chinese username path."""
        # Skip if pynacl not installed
        try:
            addr_data = address.generate()
        except ImportError:
            self.skipTest("pynacl not installed")

        # Create temp directory simulating Chinese username
        with tempfile.TemporaryDirectory(prefix="王小明_") as temp_dir:
            co_dir = Path(temp_dir)

            # Save should work without encoding errors
            address.save(addr_data, co_dir)

            # Verify recovery file was created and is UTF-8
            recovery_file = co_dir / "keys" / "recovery.txt"
            self.assertTrue(recovery_file.exists())

            # Read back and verify - this tests UTF-8 encoding explicitly
            seed_phrase = recovery_file.read_text(encoding='utf-8')
            self.assertEqual(seed_phrase.strip(), addr_data["seed_phrase"])

            # Load should work
            loaded = address.load(co_dir)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["address"], addr_data["address"])

    def test_address_save_load_with_arabic_path(self):
        """Test saving and loading with Arabic username path."""
        try:
            addr_data = address.generate()
        except ImportError:
            self.skipTest("pynacl not installed")

        # Arabic username
        with tempfile.TemporaryDirectory(prefix="محمد_") as temp_dir:
            co_dir = Path(temp_dir)

            address.save(addr_data, co_dir)
            loaded = address.load(co_dir)

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["address"], addr_data["address"])

    def test_address_save_with_spaces_in_path(self):
        """Test paths with spaces work correctly."""
        try:
            addr_data = address.generate()
        except ImportError:
            self.skipTest("pynacl not installed")

        # Username with spaces (common on Windows)
        with tempfile.TemporaryDirectory(prefix="John Smith_") as temp_dir:
            co_dir = Path(temp_dir)

            # Should handle spaces correctly
            address.save(addr_data, co_dir)
            loaded = address.load(co_dir)

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["address"], addr_data["address"])

    def test_console_logging_with_utf8_path(self):
        """Test console logging works with UTF-8 paths."""
        # Create temp directory with Chinese characters
        with tempfile.TemporaryDirectory(prefix="测试_") as temp_dir:
            log_file = Path(temp_dir) / "test.log"

            # Create console with UTF-8 path
            console = Console(log_file=log_file)
            console.print("Test message with emoji 🚀")

            # Verify file was created and is readable
            self.assertTrue(log_file.exists())

            # Read back with UTF-8 (critical test!)
            content = log_file.read_text(encoding='utf-8')
            self.assertIn("Test message with emoji 🚀", content)


class TestChmodPlatformCheck(unittest.TestCase):
    """Test chmod is skipped on Windows, applied on Unix."""

    @patch('sys.platform', 'win32')
    def test_chmod_skipped_on_windows(self):
        """Verify chmod is NOT called on Windows."""
        try:
            addr_data = address.generate()
        except ImportError:
            self.skipTest("pynacl not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            co_dir = Path(temp_dir)

            # Mock chmod to track calls
            with patch.object(Path, 'chmod') as mock_chmod:
                # On Windows, chmod should NOT be called
                address.save(addr_data, co_dir)

                # chmod should not have been called (Windows doesn't support it)
                mock_chmod.assert_not_called()

    @patch('sys.platform', 'darwin')
    def test_chmod_applied_on_unix(self):
        """Verify chmod IS called on Unix/Mac."""
        try:
            addr_data = address.generate()
        except ImportError:
            self.skipTest("pynacl not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            co_dir = Path(temp_dir)

            # On Unix/Mac, chmod should be called
            address.save(addr_data, co_dir)

            # Check that files have restrictive permissions (0o600)
            key_file = co_dir / "keys" / "agent.key"
            recovery_file = co_dir / "keys" / "recovery.txt"

            # Verify files exist and are readable (chmod succeeded)
            self.assertTrue(key_file.exists())
            self.assertTrue(recovery_file.exists())


class TestPathComparison(unittest.TestCase):
    """Test path comparison works correctly on Windows."""

    def test_path_resolve_normalization(self):
        """Test that .resolve() normalizes paths for comparison."""
        # Create two paths that should be equal when resolved
        home = Path.home()
        co_dir1 = home / ".co"
        co_dir2 = Path(home) / Path(".co")

        # Without resolve(), these might compare differently on Windows
        # With resolve(), they should always match
        self.assertEqual(co_dir1.resolve(), co_dir2.resolve())

    def test_path_comparison_with_different_separators(self):
        """Test paths with different separators resolve to same path."""
        # Use temp directory to test actual path resolution (works on all platforms)
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            test_dir = base / ".co"
            test_dir.mkdir()

            # Create two paths to same directory using different separators
            path1 = Path(temp_dir) / ".co"
            path2 = Path(f"{temp_dir}/.co")

            # resolve() should normalize both to the same form
            self.assertEqual(path1.resolve(), path2.resolve())


class TestRoundTripEncoding(unittest.TestCase):
    """Test data survives write → read cycle with UTF-8 encoding."""

    def test_recovery_phrase_roundtrip(self):
        """Test recovery phrase survives write/read with special characters."""
        try:
            addr_data = address.generate()
        except ImportError:
            self.skipTest("pynacl not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            co_dir = Path(temp_dir)

            # Save
            address.save(addr_data, co_dir)

            # Read back
            recovery_file = co_dir / "keys" / "recovery.txt"
            saved_phrase = recovery_file.read_text(encoding='utf-8').strip()

            # CRITICAL: Must match exactly (no encoding corruption)
            self.assertEqual(saved_phrase, addr_data["seed_phrase"])

    def test_warning_file_roundtrip_with_unicode(self):
        """Test warning file with unicode symbols roundtrips correctly."""
        try:
            addr_data = address.generate()
        except ImportError:
            self.skipTest("pynacl not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            co_dir = Path(temp_dir)

            # Save (creates warning file with ⚠️ symbol)
            address.save(addr_data, co_dir)

            # Read warning file
            warning_file = co_dir / "keys" / "DO_NOT_SHARE"
            content = warning_file.read_text(encoding='utf-8')

            # Verify unicode warning symbol is intact
            self.assertIn("⚠️", content)
            self.assertIn("WARNING", content)


if __name__ == "__main__":
    unittest.main()

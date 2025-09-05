"""Tests for CLI browser feature (-b flag)."""

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from connectonion.cli.browser_utils import (
    parse_screenshot_command,
    normalize_url,
    get_viewport_size,
    execute_browser_command,
    BrowserAutomation
)


class TestScreenshotCommandParser(unittest.TestCase):
    """Test parsing of screenshot commands."""
    
    def test_basic_screenshot_command(self):
        """Test parsing basic screenshot command."""
        result = parse_screenshot_command("screenshot localhost:3000")
        self.assertEqual(result['url'], 'localhost:3000')
        self.assertIsNone(result['output'])
        self.assertIsNone(result['size'])
    
    def test_screenshot_with_save_path(self):
        """Test parsing screenshot with save to path."""
        result = parse_screenshot_command("screenshot localhost:3000 save to /tmp/test.png")
        self.assertEqual(result['url'], 'localhost:3000')
        self.assertEqual(result['output'], '/tmp/test.png')
        self.assertIsNone(result['size'])
    
    def test_screenshot_with_size(self):
        """Test parsing screenshot with size."""
        result = parse_screenshot_command("screenshot example.com size iphone")
        self.assertEqual(result['url'], 'example.com')
        self.assertIsNone(result['output'])
        self.assertEqual(result['size'], 'iphone')
    
    def test_screenshot_with_custom_size(self):
        """Test parsing screenshot with custom dimensions."""
        result = parse_screenshot_command("screenshot localhost:3000 size 390x844")
        self.assertEqual(result['url'], 'localhost:3000')
        self.assertEqual(result['size'], '390x844')
    
    def test_full_command(self):
        """Test parsing complete screenshot command."""
        cmd = "screenshot localhost:3000/xray save to /tmp/debug.png size iphone"
        result = parse_screenshot_command(cmd)
        self.assertEqual(result['url'], 'localhost:3000/xray')
        self.assertEqual(result['output'], '/tmp/debug.png')
        self.assertEqual(result['size'], 'iphone')
    
    def test_invalid_command_no_url(self):
        """Test parsing invalid command without URL."""
        result = parse_screenshot_command("screenshot")
        self.assertIsNone(result['url'])
    
    def test_invalid_command_no_screenshot_keyword(self):
        """Test parsing command without screenshot keyword."""
        result = parse_screenshot_command("capture localhost:3000")
        self.assertIsNone(result)
    
    def test_different_path_formats(self):
        """Test various path formats."""
        cases = [
            ("screenshot localhost save to debug.png", "debug.png"),
            ("screenshot localhost save to ./screenshots/test.png", "./screenshots/test.png"),
            ("screenshot localhost save to ~/Desktop/screenshot.png", "~/Desktop/screenshot.png"),
        ]
        for cmd, expected_path in cases:
            result = parse_screenshot_command(cmd)
            self.assertEqual(result['output'], expected_path)


class TestURLNormalization(unittest.TestCase):
    """Test URL normalization."""
    
    def test_localhost_normalization(self):
        """Test localhost URL handling."""
        self.assertEqual(normalize_url("localhost"), "http://localhost")
        self.assertEqual(normalize_url("localhost:3000"), "http://localhost:3000")
        self.assertEqual(normalize_url("localhost:8080"), "http://localhost:8080")
    
    def test_domain_normalization(self):
        """Test domain URL handling."""
        self.assertEqual(normalize_url("example.com"), "https://example.com")
        self.assertEqual(normalize_url("docs.connectonion.com"), "https://docs.connectonion.com")
    
    def test_full_url_unchanged(self):
        """Test that full URLs remain unchanged."""
        self.assertEqual(normalize_url("http://localhost:3000"), "http://localhost:3000")
        self.assertEqual(normalize_url("https://example.com"), "https://example.com")
        self.assertEqual(normalize_url("http://example.com:8080"), "http://example.com:8080")
    
    def test_ip_address_handling(self):
        """Test IP address URL handling."""
        self.assertEqual(normalize_url("127.0.0.1"), "http://127.0.0.1")
        self.assertEqual(normalize_url("127.0.0.1:3000"), "http://127.0.0.1:3000")
        self.assertEqual(normalize_url("192.168.1.1:8080"), "http://192.168.1.1:8080")


class TestViewportSizes(unittest.TestCase):
    """Test viewport size handling."""
    
    def test_device_presets(self):
        """Test device preset dimensions."""
        self.assertEqual(get_viewport_size("iphone"), (390, 844))
        self.assertEqual(get_viewport_size("android"), (360, 800))
        self.assertEqual(get_viewport_size("ipad"), (768, 1024))
        self.assertEqual(get_viewport_size("desktop"), (1920, 1080))
    
    def test_custom_dimensions(self):
        """Test parsing custom dimensions."""
        self.assertEqual(get_viewport_size("1280x720"), (1280, 720))
        self.assertEqual(get_viewport_size("390x844"), (390, 844))
        self.assertEqual(get_viewport_size("1920x1080"), (1920, 1080))
    
    def test_invalid_size_returns_default(self):
        """Test invalid size returns desktop default."""
        self.assertEqual(get_viewport_size("invalid"), (1920, 1080))
        self.assertEqual(get_viewport_size(""), (1920, 1080))
        self.assertEqual(get_viewport_size(None), (1920, 1080))
    
    def test_malformed_dimensions(self):
        """Test malformed dimension strings."""
        self.assertEqual(get_viewport_size("1280×720"), (1920, 1080))  # Wrong x character
        self.assertEqual(get_viewport_size("1280"), (1920, 1080))  # Missing height
        self.assertEqual(get_viewport_size("widthxheight"), (1920, 1080))  # Non-numeric


class TestBrowserAutomation(unittest.TestCase):
    """Test BrowserAutomation functionality."""
    
    @patch('connectonion.cli.browser_utils.sync_playwright')
    def test_basic_screenshot(self, mock_playwright):
        """Test taking a basic screenshot."""
        # Setup mocks
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_pw_instance = MagicMock()
        
        mock_playwright.return_value.start.return_value = mock_pw_instance
        mock_pw_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        # Create browser automation and test
        browser = BrowserAutomation()
        result = browser.take_screenshot(
            url="http://localhost:3000",
            path="test.png",
            width=1920,
            height=1080
        )
        
        # Verify
        self.assertIn('Screenshot saved', result)
        mock_page.goto.assert_called_once_with("http://localhost:3000", wait_until='networkidle')
        mock_page.set_viewport_size.assert_called_once_with({"width": 1920, "height": 1080})
        mock_page.screenshot.assert_called_once()
    
    @patch('connectonion.cli.browser_utils.sync_playwright')
    def test_screenshot_with_iphone_preset(self, mock_playwright):
        """Test taking screenshot with iPhone preset."""
        # Setup mocks
        mock_page = MagicMock()
        mock_browser = MagicMock()
        mock_pw_instance = MagicMock()
        
        mock_playwright.return_value.start.return_value = mock_pw_instance
        mock_pw_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        # Execute with BrowserAutomation
        browser = BrowserAutomation()
        result = browser.take_screenshot(
            url="http://localhost:3000",
            path="screenshot.png",
            width=390,
            height=844
        )
        
        # Verify iPhone dimensions were set
        mock_page.set_viewport_size.assert_called_once_with({"width": 390, "height": 844})
    
    @patch('connectonion.cli.browser_utils.sync_playwright')
    def test_screenshot_failure_handling(self, mock_playwright):
        """Test handling of screenshot failures."""
        # Setup mock to raise exception
        mock_playwright.return_value.start.side_effect = Exception("Browser failed to start")
        
        # Execute with BrowserAutomation
        browser = BrowserAutomation()
        result = browser.take_screenshot(
            url="http://localhost:3000",
            path="test.png"
        )
        
        # Verify error message
        self.assertIn("Error taking screenshot", result)
        self.assertIn("Browser failed to start", result)
    
    def test_playwright_not_available(self):
        """Test error when Playwright is not installed."""
        # Test with BrowserTool when Playwright not available
        with patch('connectonion.cli.browser_utils.PLAYWRIGHT_AVAILABLE', False):
            tool = BrowserTool()
            result = tool.take_screenshot_tool(
                url="http://localhost:3000",
                path="test.png"
            )
            
            # Verify proper error message
            self.assertIn('Browser tools not installed', result)
            self.assertIn('pip install playwright', result)


class TestBrowserCommandExecution(unittest.TestCase):
    """Test complete browser command execution."""
    
    @patch('connectonion.cli.browser_utils.create_browser_agent')
    def test_execute_simple_command_no_agent(self, mock_create_agent):
        """Test executing simple screenshot command without agent."""
        # Simulate no API key available
        mock_create_agent.return_value = None
        
        with patch.object(BrowserAutomation, 'take_screenshot') as mock_method:
            mock_method.return_value = 'Screenshot saved: screenshot.png'
            
            result = execute_browser_command("screenshot localhost:3000")
            
            self.assertTrue(result['success'])
            mock_method.assert_called_once_with(
                url='localhost:3000',
                path=None,
                width=1920,
                height=1080
            )
    
    @patch('connectonion.cli.browser_utils.create_browser_agent')
    def test_execute_command_with_all_options(self, mock_create_agent):
        """Test executing command with all options."""
        # Simulate no agent (direct execution)
        mock_create_agent.return_value = None
        
        with patch.object(BrowserAutomation, 'take_screenshot') as mock_method:
            mock_method.return_value = 'Screenshot saved: /tmp/test.png'
            
            cmd = "screenshot localhost:3000/api save to /tmp/test.png size iphone"
            result = execute_browser_command(cmd)
            
            self.assertTrue(result['success'])
            # Verify the tool was called with correct parameters
            mock_method.assert_called_once_with(
                url='localhost:3000/api',
                path='/tmp/test.png',
                width=390,
                height=844
            )
    
    def test_execute_invalid_command(self):
        """Test executing invalid command."""
        result = execute_browser_command("invalid command")
        self.assertFalse(result['success'])
        self.assertIn('error', result)
    
    def test_execute_empty_command(self):
        """Test executing empty command."""
        result = execute_browser_command("")
        self.assertFalse(result['success'])
        
    @patch('connectonion.cli.browser_utils.create_browser_agent')
    def test_default_output_path(self, mock_create_agent):
        """Test that default output path is None when not specified."""
        # Simulate no agent
        mock_create_agent.return_value = None
        
        with patch.object(BrowserAutomation, 'take_screenshot') as mock_method:
            mock_method.return_value = 'Screenshot saved: screenshot_20240115_143022.png'
            
            result = execute_browser_command("screenshot localhost:3000")
            
            # Verify the tool was called with None for output_path
            call_args = mock_tool.call_args[1]
            self.assertIsNone(call_args.get('path'))


class TestErrorHandling(unittest.TestCase):
    """Test error handling and user feedback."""
    
    @patch('connectonion.cli.browser_utils.create_browser_agent')
    def test_missing_playwright_error(self, mock_create_agent):
        """Test error when Playwright is not installed."""
        # No agent available
        mock_create_agent.return_value = None
        
        with patch('connectonion.cli.browser_utils.PLAYWRIGHT_AVAILABLE', False):
            result = execute_browser_command("screenshot localhost:3000")
            self.assertFalse(result['success'])
            self.assertIn('playwright', result['error'].lower())
            self.assertIn('pip install playwright', result['error'])
    
    @patch('connectonion.cli.browser_utils.create_browser_agent')
    def test_network_error(self, mock_create_agent):
        """Test handling of network errors."""
        mock_create_agent.return_value = None
        
        with patch.object(BrowserAutomation, 'take_screenshot') as mock_method:
            mock_method.return_value = 'Cannot reach http://localhost:3000. Is your server running?'
            
            result = execute_browser_command("screenshot localhost:3000")
            self.assertFalse(result['success'])
            self.assertIn('Cannot reach', result['error'])
    
    @patch('connectonion.cli.browser_utils.create_browser_agent')
    def test_permission_error(self, mock_create_agent):
        """Test handling of permission errors."""
        mock_create_agent.return_value = None
        
        with patch.object(BrowserAutomation, 'take_screenshot') as mock_method:
            mock_method.return_value = 'Cannot save to /root/test.png (permission denied)'
            
            result = execute_browser_command("screenshot localhost:3000 save to /root/test.png")
            self.assertFalse(result['success'])
            self.assertIn('permission denied', result['error'])


if __name__ == '__main__':
    unittest.main()
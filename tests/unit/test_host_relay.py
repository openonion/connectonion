#!/usr/bin/env python3
"""
Unit tests for host() relay functionality.

Tests cover:
- Key loading (existing keys)
- Key generation (first-time setup)
- ANNOUNCE message creation
- Relay connection (default and custom URLs)
- Relay disabled when relay_url=None
- Console output for monitoring

Note: This tests the host() relay setup logic. The actual relay.serve_loop()
is tested separately in test_relay.py.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from connectonion import Agent
from connectonion.core.llm import LLMResponse
from connectonion.core.usage import TokenUsage

# Get the actual module, not the function (which shadows it in __init__.py)
import connectonion.network.host  # This imports the module before __init__ shadows it
host_module = sys.modules['connectonion.network.host']


@pytest.fixture
def mock_llm():
    """Provide a mock LLM for testing."""
    llm = Mock()
    llm.model = "test-model"  # Required for Agent banner
    llm.complete.return_value = LLMResponse(
        content="Test response",
        tool_calls=[],
        raw_response=None,
        usage=TokenUsage(),
    )
    return llm


@pytest.fixture
def mock_agent(mock_llm):
    """Provide a mock agent for testing."""
    return Agent("test_agent", llm=mock_llm, quiet=True)


class TestHostRelayKeyManagement:
    """Test key loading and generation in host() with relay_url."""

    def test_host_loads_existing_keys(self, tmp_path, mock_agent):
        """Test that host() loads existing keys if present."""
        mock_addr_data = {
            'address': '0xtest123',
            'short_address': 'co/test',
            'signing_key': Mock()
        }

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr_data) as mock_load:
                with patch('connectonion.address.generate') as mock_generate:
                    with patch.object(host_module, '_start_relay_background') as mock_relay:
                        with patch('uvicorn.run'):
                            with patch.object(host_module, 'Console'):
                                host_module.host(mock_agent, relay_url="ws://test")

                                mock_load.assert_called_once()
                                mock_generate.assert_not_called()

    def test_host_generates_new_keys_if_missing(self, tmp_path, mock_agent):
        """Test that host() generates keys if none exist."""
        mock_generated_addr = {
            'address': '0xnewkeys',
            'short_address': 'co/new',
            'signing_key': Mock()
        }

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=None) as mock_load:
                with patch('connectonion.address.generate', return_value=mock_generated_addr) as mock_generate:
                    with patch('connectonion.address.save') as mock_save:
                        with patch.object(host_module, '_start_relay_background'):
                            with patch('uvicorn.run'):
                                with patch.object(host_module, 'Console'):
                                    host_module.host(mock_agent, relay_url="ws://test")

                                    mock_generate.assert_called_once()
                                    mock_save.assert_called_once()


class TestHostRelayConnection:
    """Test relay connection handling in host()."""

    def test_host_starts_relay_with_default_url(self, tmp_path, mock_agent):
        """Test that host() uses default relay URL."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_start_relay_background') as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Console'):
                            host_module.host(mock_agent)  # Uses default relay_url

                            mock_relay.assert_called_once()
                            call_args = mock_relay.call_args
                            assert call_args[0][1] == "wss://oo.openonion.ai/ws/announce"

    def test_host_starts_relay_with_custom_url(self, tmp_path, mock_agent):
        """Test that host() uses custom relay URL."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}
        custom_url = "ws://localhost:8000/ws/announce"

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_start_relay_background') as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Console'):
                            host_module.host(mock_agent, relay_url=custom_url)

                            mock_relay.assert_called_once()
                            call_args = mock_relay.call_args
                            assert call_args[0][1] == custom_url

    def test_host_does_not_start_relay_when_disabled(self, tmp_path, mock_agent):
        """Test that host() doesn't start relay when relay_url=None."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_start_relay_background') as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Console'):
                            host_module.host(mock_agent, relay_url=None)

                            mock_relay.assert_not_called()


class TestStartRelayBackground:
    """Test _start_relay_background function."""

    def test_creates_announce_message_with_system_prompt(self, mock_agent):
        """Test that relay uses system_prompt as summary."""
        mock_agent.system_prompt = "I am a helpful translation agent"
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch('connectonion.announce.create_announce_message') as mock_announce:
            with patch('connectonion.relay.connect'):
                with patch('threading.Thread') as mock_thread:
                    mock_thread.return_value = Mock()
                    host_module._start_relay_background(mock_agent, "ws://test", mock_addr)

                    mock_announce.assert_called_once()
                    call_args = mock_announce.call_args[0]
                    assert call_args[1] == mock_agent.system_prompt

    def test_truncates_long_system_prompt(self, mock_agent):
        """Test that very long system_prompts are truncated to 1000 chars."""
        mock_agent.system_prompt = "A" * 2000
        mock_addr = {'address': '0xtest', 'signing_key': Mock()}

        with patch('connectonion.announce.create_announce_message') as mock_announce:
            with patch('connectonion.relay.connect'):
                with patch('threading.Thread') as mock_thread:
                    mock_thread.return_value = Mock()
                    host_module._start_relay_background(mock_agent, "ws://test", mock_addr)

                    summary = mock_announce.call_args[0][1]
                    assert len(summary) == 1000

    def test_uses_agent_name_if_no_system_prompt(self, mock_agent):
        """Test that agent name is used if no system_prompt."""
        mock_agent.system_prompt = None
        mock_addr = {'address': '0xtest', 'signing_key': Mock()}

        with patch('connectonion.announce.create_announce_message') as mock_announce:
            with patch('connectonion.relay.connect'):
                with patch('threading.Thread') as mock_thread:
                    mock_thread.return_value = Mock()
                    host_module._start_relay_background(mock_agent, "ws://test", mock_addr)

                    summary = mock_announce.call_args[0][1]
                    assert summary == "test_agent agent"

    def test_starts_daemon_thread(self, mock_agent):
        """Test that relay runs in daemon thread."""
        mock_addr = {'address': '0xtest', 'signing_key': Mock()}

        with patch('connectonion.announce.create_announce_message'):
            with patch('connectonion.relay.connect'):
                with patch('threading.Thread') as mock_thread:
                    mock_thread_instance = Mock()
                    mock_thread.return_value = mock_thread_instance

                    host_module._start_relay_background(mock_agent, "ws://test", mock_addr)

                    mock_thread.assert_called_once()
                    assert mock_thread.call_args[1]['daemon'] is True
                    mock_thread_instance.start.assert_called_once()


class TestHostConsoleOutput:
    """Test console output during host()."""

    def test_host_displays_address(self, tmp_path, mock_agent):
        """Test that host() displays agent address."""
        mock_addr = {
            'address': '0x1234567890abcdef',
            'short_address': 'co/test',
            'signing_key': Mock()
        }

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_start_relay_background'):
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Panel') as mock_panel:
                            with patch.object(host_module, 'Console'):
                                host_module.host(mock_agent, relay_url="ws://test")

                                # Check Panel was called with address in content
                                mock_panel.assert_called_once()
                                panel_content = mock_panel.call_args[0][0]
                                assert '0x1234567890abcdef' in panel_content

    def test_host_displays_relay_status_enabled(self, tmp_path, mock_agent):
        """Test that host() shows relay enabled status."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_start_relay_background'):
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Panel') as mock_panel:
                            with patch.object(host_module, 'Console'):
                                host_module.host(mock_agent, relay_url="ws://custom")

                                panel_content = mock_panel.call_args[0][0]
                                assert 'ws://custom' in panel_content

    def test_host_displays_relay_status_disabled(self, tmp_path, mock_agent):
        """Test that host() shows relay disabled status."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_start_relay_background'):
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Panel') as mock_panel:
                            with patch.object(host_module, 'Console'):
                                host_module.host(mock_agent, relay_url=None)

                                panel_content = mock_panel.call_args[0][0]
                                assert 'disabled' in panel_content


class TestCreateHandlers:
    """Test _create_handlers function."""

    def test_creates_ws_input_handler(self, mock_agent):
        """Test that _create_handlers creates ws_input handler."""
        handlers = host_module._create_handlers(mock_agent, result_ttl=3600)

        assert "ws_input" in handlers
        assert callable(handlers["ws_input"])

    def test_creates_ws_input_with_connection_handler(self, mock_agent):
        """Test that _create_handlers creates ws_input_with_connection handler."""
        handlers = host_module._create_handlers(mock_agent, result_ttl=3600)

        assert "ws_input_with_connection" in handlers
        assert callable(handlers["ws_input_with_connection"])

    def test_ws_input_deep_copies_agent(self, mock_agent):
        """Test that ws_input creates a deep copy of agent."""
        handlers = host_module._create_handlers(mock_agent, result_ttl=3600)

        # Track if agent.input was called
        mock_agent.input = Mock(return_value="result")

        with patch('copy.deepcopy') as mock_copy:
            mock_copied_agent = Mock()
            mock_copied_agent.input = Mock(return_value="copied result")
            mock_copy.return_value = mock_copied_agent

            result = handlers["ws_input"]("test prompt")

            mock_copy.assert_called_once_with(mock_agent)
            mock_copied_agent.input.assert_called_once_with("test prompt")

    def test_ws_input_with_connection_injects_connection(self, mock_agent):
        """Test that ws_input_with_connection injects connection into agent."""
        handlers = host_module._create_handlers(mock_agent, result_ttl=3600)

        mock_connection = Mock()

        with patch('copy.deepcopy') as mock_copy:
            mock_copied_agent = Mock()
            mock_copied_agent.input = Mock(return_value="result with connection")
            mock_copy.return_value = mock_copied_agent

            result = handlers["ws_input_with_connection"]("test prompt", mock_connection)

            # Verify connection was injected
            assert mock_copied_agent.connection == mock_connection
            mock_copied_agent.input.assert_called_once_with("test prompt")

    def test_ws_input_with_connection_returns_result(self, mock_agent):
        """Test that ws_input_with_connection returns agent result."""
        handlers = host_module._create_handlers(mock_agent, result_ttl=3600)

        mock_connection = Mock()

        with patch('copy.deepcopy') as mock_copy:
            mock_copied_agent = Mock()
            mock_copied_agent.input = Mock(return_value="expected result")
            mock_copy.return_value = mock_copied_agent

            result = handlers["ws_input_with_connection"]("prompt", mock_connection)

            assert result == "expected result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

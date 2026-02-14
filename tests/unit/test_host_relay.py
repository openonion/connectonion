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

import copy
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from connectonion import Agent
from connectonion.core.llm import LLMResponse
from connectonion.core.usage import TokenUsage

# Import server module directly for internal functions
from connectonion.network.host import server as host_module


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
def create_mock_agent(mock_llm):
    """Provide a factory that creates mock agents for testing."""
    def factory():
        return Agent("test_agent", llm=mock_llm, quiet=True)
    return factory


@pytest.mark.skip(reason="Relay implementation changed to lifespan-based; tests need rewrite")
class TestHostRelayKeyManagement:
    """Test key loading and generation in host() with relay_url."""

    def test_host_loads_existing_keys(self, tmp_path, create_mock_agent):
        """Test that host() loads existing keys if present."""
        mock_addr_data = {
            'address': '0xtest123',
            'short_address': 'co/test',
            'signing_key': Mock()
        }

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr_data) as mock_load:
                with patch('connectonion.address.generate') as mock_generate:
                    with patch.object(host_module, '_create_relay_lifespan', return_value=None):
                        with patch('uvicorn.run'):
                            with patch.object(host_module, 'Console'):
                                host_module.host(create_mock_agent, relay_url="ws://test")

                                mock_load.assert_called_once()
                                mock_generate.assert_not_called()

    def test_host_generates_new_keys_if_missing(self, tmp_path, create_mock_agent):
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
                        with patch.object(host_module, '_create_relay_lifespan', return_value=None):
                            with patch('uvicorn.run'):
                                with patch.object(host_module, 'Console'):
                                    host_module.host(create_mock_agent, relay_url="ws://test")

                                    mock_generate.assert_called_once()
                                    mock_save.assert_called_once()


@pytest.mark.skip(reason="Relay implementation changed to lifespan-based; tests need rewrite")
class TestHostRelayConnection:
    """Test relay connection handling in host()."""

    def test_host_starts_relay_with_default_url(self, tmp_path, create_mock_agent):
        """Test that host() uses default relay URL (from config)."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan') as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Console'):
                            host_module.host(create_mock_agent)  # Uses default relay_url

                            # Relay lifespan is created when relay is enabled
                            mock_relay.assert_called_once()
                            call_args = mock_relay.call_args
                            # relay_url is the second positional arg
                            assert call_args[0][1] == "wss://oo.openonion.ai"

    def test_host_starts_relay_with_custom_url(self, tmp_path, create_mock_agent):
        """Test that host() uses custom relay URL."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}
        custom_url = "ws://localhost:8000"

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan') as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Console'):
                            host_module.host(create_mock_agent, relay_url=custom_url)

                            mock_relay.assert_called_once()
                            call_args = mock_relay.call_args
                            assert call_args[0][1] == custom_url

    def test_host_does_not_start_relay_when_disabled(self, tmp_path, create_mock_agent):
        """Test that host() doesn't start relay when relay_url=None."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan') as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Console'):
                            host_module.host(create_mock_agent, relay_url=None)

                            mock_relay.assert_not_called()


@pytest.mark.skip(reason="_start_relay_background was replaced with _create_relay_lifespan")
class TestStartRelayBackground:
    """Test _start_relay_background function (skipped - function removed)."""

    def test_creates_announce_message_with_system_prompt(self, create_mock_agent):
        """Test that relay uses provided agent_summary."""
        agent_summary = "I am a helpful translation agent"
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch('connectonion.announce.create_announce_message') as mock_announce:
            with patch('connectonion.relay.connect'):
                with patch('threading.Thread') as mock_thread:
                    mock_thread.return_value = Mock()
                    host_module._start_relay_background(create_mock_agent, "ws://test", mock_addr, agent_summary)

                    mock_announce.assert_called_once()
                    call_args = mock_announce.call_args[0]
                    assert call_args[1] == agent_summary

    def test_truncates_long_system_prompt(self, create_mock_agent):
        """Test that very long summaries are passed as-is (truncation happens in host())."""
        # Note: truncation now happens in host() before calling _start_relay_background
        agent_summary = "A" * 1000  # Already truncated by host()
        mock_addr = {'address': '0xtest', 'signing_key': Mock()}

        with patch('connectonion.announce.create_announce_message') as mock_announce:
            with patch('connectonion.relay.connect'):
                with patch('threading.Thread') as mock_thread:
                    mock_thread.return_value = Mock()
                    host_module._start_relay_background(create_mock_agent, "ws://test", mock_addr, agent_summary)

                    summary = mock_announce.call_args[0][1]
                    assert len(summary) == 1000

    def test_uses_agent_name_if_no_system_prompt(self, create_mock_agent):
        """Test that agent name fallback is used when passed."""
        # Note: the fallback logic now happens in host(), not _start_relay_background
        agent_summary = "test_agent agent"
        mock_addr = {'address': '0xtest', 'signing_key': Mock()}

        with patch('connectonion.announce.create_announce_message') as mock_announce:
            with patch('connectonion.relay.connect'):
                with patch('threading.Thread') as mock_thread:
                    mock_thread.return_value = Mock()
                    host_module._start_relay_background(create_mock_agent, "ws://test", mock_addr, agent_summary)

                    summary = mock_announce.call_args[0][1]
                    assert summary == "test_agent agent"

    def test_starts_daemon_thread(self, create_mock_agent):
        """Test that relay runs in daemon thread."""
        mock_addr = {'address': '0xtest', 'signing_key': Mock()}

        with patch('connectonion.announce.create_announce_message'):
            with patch('connectonion.relay.connect'):
                with patch('threading.Thread') as mock_thread:
                    mock_thread_instance = Mock()
                    mock_thread.return_value = mock_thread_instance

                    host_module._start_relay_background(create_mock_agent, "ws://test", mock_addr, "test summary")

                    mock_thread.assert_called_once()
                    assert mock_thread.call_args[1]['daemon'] is True
                    mock_thread_instance.start.assert_called_once()


@pytest.mark.skip(reason="Console output logic changed; tests need rewrite")
class TestHostConsoleOutput:
    """Test console output during host()."""

    def test_host_displays_address(self, tmp_path, create_mock_agent):
        """Test that host() displays agent address."""
        mock_addr = {
            'address': '0x1234567890abcdef',
            'short_address': 'co/test',
            'signing_key': Mock()
        }

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan', return_value=None):
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Panel') as mock_panel:
                            with patch.object(host_module, 'Console'):
                                host_module.host(create_mock_agent, relay_url="ws://test")

                                # Check Panel was called with address in content
                                mock_panel.assert_called_once()
                                panel_content = mock_panel.call_args[0][0]
                                assert '0x1234567890abcdef' in panel_content

    def test_host_displays_relay_status_enabled(self, tmp_path, create_mock_agent):
        """Test that host() shows relay enabled status."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan', return_value=None):
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Panel') as mock_panel:
                            with patch.object(host_module, 'Console'):
                                host_module.host(create_mock_agent, relay_url="ws://custom")

                                panel_content = mock_panel.call_args[0][0]
                                assert 'ws://custom' in panel_content

    def test_host_displays_relay_status_disabled(self, tmp_path, create_mock_agent):
        """Test that host() shows relay disabled status."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan', return_value=None):
                    with patch('uvicorn.run'):
                        with patch.object(host_module, 'Panel') as mock_panel:
                            with patch.object(host_module, 'Console'):
                                host_module.host(create_mock_agent, relay_url=None)

                                panel_content = mock_panel.call_args[0][0]
                                assert 'disabled' in panel_content


class TestCreateRouteHandlers:
    """Test _create_route_handlers function."""

    @pytest.fixture
    def mock_trust_agent(self):
        """Create a mock TrustAgent for testing."""
        from connectonion.network.trust import TrustAgent
        return TrustAgent("open")

    def test_creates_ws_input_handler(self, create_mock_agent, mock_trust_agent):
        """Test that _create_route_handlers creates ws_input handler."""
        agent_metadata = {"name": "test_agent", "tools": [], "address": "0xtest"}
        handlers = host_module._create_route_handlers(create_mock_agent, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent)

        assert "ws_input" in handlers
        assert callable(handlers["ws_input"])

    def test_creates_all_required_handlers(self, create_mock_agent, mock_trust_agent):
        """Test that _create_route_handlers creates all required handlers."""
        agent_metadata = {"name": "test_agent", "tools": [], "address": "0xtest"}
        handlers = host_module._create_route_handlers(create_mock_agent, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent)

        required = ["input", "session", "sessions", "health", "info", "auth", "ws_input", "admin_logs", "admin_sessions", "trust_agent"]
        for key in required:
            assert key in handlers, f"Missing handler: {key}"

    def test_ws_input_calls_factory(self, create_mock_agent, tmp_path, mock_trust_agent):
        """Test that ws_input calls the factory to create fresh agent."""
        from connectonion.network.host.session import SessionStorage
        agent_metadata = {"name": "test_agent", "tools": [], "address": "0xtest"}
        handlers = host_module._create_route_handlers(create_mock_agent, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent)
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        mock_connection = Mock()

        result = handlers["ws_input"](storage, "test prompt", mock_connection)

        # Factory was called and result returned
        assert result["status"] == "done"
        assert "session_id" in result

    def test_ws_input_injects_connection(self, tmp_path, mock_trust_agent):
        """Test that ws_input injects connection into agent."""
        from connectonion.network.host.session import SessionStorage

        # Create a factory that returns a trackable mock
        created_agents = []
        def tracking_factory():
            agent = Mock()
            agent.input = Mock(return_value="result")
            agent.current_session = {}
            created_agents.append(agent)
            return agent

        agent_metadata = {"name": "test_agent", "tools": [], "address": "0xtest"}
        handlers = host_module._create_route_handlers(tracking_factory, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent)
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        mock_connection = Mock()

        handlers["ws_input"](storage, "test prompt", mock_connection)

        # Verify connection was injected into the created agent
        assert len(created_agents) == 1
        assert created_agents[0].io == mock_connection

    def test_ws_input_returns_result_dict(self, tmp_path, mock_trust_agent):
        """Test that ws_input returns result dict with session info."""
        from connectonion.network.host.session import SessionStorage

        def mock_factory():
            agent = Mock()
            agent.input = Mock(return_value="expected result")
            agent.current_session = {"messages": []}
            return agent

        agent_metadata = {"name": "test_agent", "tools": [], "address": "0xtest"}
        handlers = host_module._create_route_handlers(mock_factory, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent)
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        mock_connection = Mock()

        result = handlers["ws_input"](storage, "prompt", mock_connection)

        assert result["result"] == "expected result"
        assert result["status"] == "done"
        assert "session_id" in result
        assert "duration_ms" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

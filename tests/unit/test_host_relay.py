"""
LLM-Note: Tests for host relay

What it tests:
- Host Relay functionality (ANNOUNCE/heartbeat protocol, including the
  display profile published with the first ANNOUNCE of each connection)

Components under test:
- Module: host_relay
"""
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
                    # _create_relay_lifespan returns (on_startup, on_shutdown) tuple
                    with patch.object(host_module, '_create_relay_lifespan', return_value=(AsyncMock(), AsyncMock())):
                        with patch('uvicorn.run'):
                            with patch.object(host_module, '_print_host_banner'):
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
                        # _create_relay_lifespan returns (on_startup, on_shutdown) tuple
                        with patch.object(host_module, '_create_relay_lifespan', return_value=(AsyncMock(), AsyncMock())):
                            with patch('uvicorn.run'):
                                with patch.object(host_module, '_print_host_banner'):
                                    host_module.host(create_mock_agent, relay_url="ws://test")

                                    mock_generate.assert_called_once()
                                    mock_save.assert_called_once()


class TestHostRelayConnection:
    """Test relay connection handling in host()."""

    def test_profile_publishes_project_scoped_skills_only(self):
        """Published profile carries display fields only. Both project-tree skill
        categories are advertised (project = .co/skills, claude-project = .claude/skills);
        the operator's personal toolboxes (user = ~/.co/skills, claude-user = ~/.claude/skills)
        and builtin skills stay private. location is the discovery category, not a path."""
        profile = host_module._build_agent_profile({
            "name": "test_agent",
            "tools": ["search"],
            "model": "co/gemini-2.5-flash",
            "summary": "private prompt summary",
            "skills": [
                {"name": "deploy-smoke", "description": "Smoke test", "location": "project"},
                {"name": "repo-helper", "description": "Repo skill", "location": "claude-project"},
                {"name": "linkedin-login", "description": "Operator skill", "location": "user"},
                {"name": "personal-notes", "description": "Personal skill", "location": "claude-user"},
                {"name": "commit", "description": "Built-in skill", "location": "builtin"},
            ],
        })

        assert profile == {
            "alias": "test_agent",
            "tools": ["search"],
            "model": "co/gemini-2.5-flash",
            "skills": [
                {"name": "deploy-smoke", "description": "Smoke test"},
                {"name": "repo-helper", "description": "Repo skill"},
            ],
        }

    def test_profile_publishes_balance_when_present(self):
        """Managed-key agents publish their balance so chat clients can show it
        (clients can't fetch it themselves — it's gated by the agent's key)."""
        profile = host_module._build_agent_profile({
            "name": "test_agent",
            "model": "co/gemini-2.5-flash",
            "balance_usd": 4.22,
            "skills": [],
        })

        assert profile["balance_usd"] == 4.22

    def test_profile_omits_balance_when_absent(self):
        """Agents on their own provider keys have no OpenOnion balance — the
        field is simply left out rather than sent as null/zero."""
        profile = host_module._build_agent_profile({
            "name": "byo_key_agent",
            "model": "gpt-4o",
            "skills": [],
        })

        assert "balance_usd" not in profile

    def test_host_passes_profile_to_relay_lifespan(self, tmp_path, create_mock_agent):
        """Hosted agents publish their profile with the relay ANNOUNCE."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan', return_value=(AsyncMock(), AsyncMock())) as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, '_print_host_banner'):
                            host_module.host(create_mock_agent, port=8080)

        profile = mock_relay.call_args.kwargs["profile"]
        assert profile["alias"]
        assert "summary" not in profile

    def test_host_starts_relay_with_default_url(self, tmp_path, create_mock_agent):
        """Test that host() uses default relay URL (from config)."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan', return_value=(AsyncMock(), AsyncMock())) as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, '_print_host_banner'):
                            host_module.host(create_mock_agent)  # Uses default relay_url

                            # Relay lifespan is created when relay is enabled
                            mock_relay.assert_called_once()
                            call_args = mock_relay.call_args
                            assert call_args[0][0] == "wss://oo.openonion.ai"

    def test_host_starts_relay_with_custom_url(self, tmp_path, create_mock_agent):
        """Test that host() uses custom relay URL."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}
        custom_url = "ws://localhost:8000"

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan', return_value=(AsyncMock(), AsyncMock())) as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, '_print_host_banner'):
                            host_module.host(create_mock_agent, relay_url=custom_url)

                            mock_relay.assert_called_once()
                            call_args = mock_relay.call_args
                            assert call_args[0][0] == custom_url

    def test_host_does_not_start_relay_when_disabled(self, tmp_path, create_mock_agent):
        """Test that host() doesn't start relay when relay_url=None."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan') as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, '_print_host_banner'):
                            host_module.host(create_mock_agent, relay_url=None)

                            mock_relay.assert_not_called()


class TestHostConsoleOutput:
    """Test console output during host()."""

    def test_host_displays_address(self, tmp_path, create_mock_agent):
        """Test that host() calls _print_host_banner with correct address."""
        mock_addr = {
            'address': '0x1234567890abcdef',
            'short_address': 'co/test',
            'signing_key': Mock()
        }

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan', return_value=(AsyncMock(), AsyncMock())):
                    with patch('uvicorn.run'):
                        with patch.object(host_module, '_print_host_banner') as mock_banner:
                            host_module.host(create_mock_agent, relay_url="ws://test")

                            # Check _print_host_banner was called with address in kwargs
                            mock_banner.assert_called_once()
                            call_kwargs = mock_banner.call_args[1]
                            assert call_kwargs['address'] == '0x1234567890abcdef'

    def test_host_displays_relay_status_enabled(self, tmp_path, create_mock_agent):
        """Test that host() passes relay_url to banner when enabled."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan', return_value=(AsyncMock(), AsyncMock())):
                    with patch('uvicorn.run'):
                        with patch.object(host_module, '_print_host_banner') as mock_banner:
                            host_module.host(create_mock_agent, relay_url="ws://custom")

                            call_kwargs = mock_banner.call_args[1]
                            assert call_kwargs['relay_url'] == "ws://custom"

    def test_host_displays_relay_status_disabled(self, tmp_path, create_mock_agent):
        """Test that host() passes relay_url=None to banner when disabled."""
        mock_addr = {'address': '0xtest', 'short_address': 'co/test', 'signing_key': Mock()}

        with patch.object(Path, 'cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch.object(host_module, '_create_relay_lifespan') as mock_relay:
                    with patch('uvicorn.run'):
                        with patch.object(host_module, '_print_host_banner') as mock_banner:
                            host_module.host(create_mock_agent, relay_url=None)

                            call_kwargs = mock_banner.call_args[1]
                            assert call_kwargs['relay_url'] is None


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
        handlers = host_module._create_route_handlers(create_mock_agent, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent, config={})

        assert "ws_input" in handlers
        assert callable(handlers["ws_input"])

    def test_creates_all_required_handlers(self, create_mock_agent, mock_trust_agent):
        """Test that _create_route_handlers creates all required handlers."""
        agent_metadata = {"name": "test_agent", "tools": [], "address": "0xtest"}
        handlers = host_module._create_route_handlers(create_mock_agent, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent, config={})

        required = ["input", "session", "sessions", "health", "info", "auth", "ws_input", "admin_logs", "admin_sessions", "trust_agent"]
        for key in required:
            assert key in handlers, f"Missing handler: {key}"

    def test_ws_input_calls_factory(self, create_mock_agent, tmp_path, mock_trust_agent):
        """Test that ws_input calls the factory to create fresh agent."""
        from connectonion.network.host.session import SessionStorage
        agent_metadata = {"name": "test_agent", "tools": [], "address": "0xtest"}
        handlers = host_module._create_route_handlers(create_mock_agent, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent, config={})
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        mock_connection = Mock()

        result = handlers["ws_input"](storage, "test prompt", mock_connection,
                                      session={"session_id": "test-123"})

        assert result["status"] == "done"
        assert result["session_id"] == "test-123"

    def test_ws_input_injects_connection(self, tmp_path, mock_trust_agent):
        """Test that ws_input injects connection into agent."""
        from connectonion.network.host.session import SessionStorage

        created_agents = []
        def tracking_factory():
            agent = Mock()
            agent.input = Mock(return_value="result")
            agent.current_session = {}
            created_agents.append(agent)
            return agent

        agent_metadata = {"name": "test_agent", "tools": [], "address": "0xtest"}
        handlers = host_module._create_route_handlers(tracking_factory, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent, config={})
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        mock_connection = Mock()

        handlers["ws_input"](storage, "test prompt", mock_connection,
                             session={"session_id": "test-123"})

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
        handlers = host_module._create_route_handlers(mock_factory, agent_metadata, result_ttl=3600, trust_agent=mock_trust_agent, config={})
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        mock_connection = Mock()

        result = handlers["ws_input"](storage, "prompt", mock_connection,
                                      session={"session_id": "test-123"})

        assert result["result"] == "expected result"
        assert result["status"] == "done"
        assert result["session_id"] == "test-123"
        assert "duration_ms" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""
Unit tests for Agent.serve() method - distributed agent serving.

Tests cover:
- Key loading (existing keys)
- Key generation (first-time setup)
- ANNOUNCE message creation
- Relay connection (default and custom URLs)
- Task handler creation and execution
- Serve loop integration
- Console output for monitoring

Critical paths from coverage analysis:
- Key loading/generation (lines 409-416)
- ANNOUNCE message creation (lines 419-425)
- Task handler definition (lines 432-434)
- Async run setup (lines 437-442)

Note: This tests the serve() setup logic. The actual relay.serve_loop()
is tested separately in test_relay.py.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from connectonion import Agent
from connectonion.llm import LLMResponse


@pytest.fixture
def mock_llm():
    """Provide a mock LLM for testing."""
    llm = Mock()
    llm.complete.return_value = LLMResponse(
        content="Test response",
        tool_calls=[],
        raw_response=None
    )
    return llm


class TestAgentServeKeyManagement:
    """Test key loading and generation in serve()."""

    @pytest.mark.asyncio
    async def test_serve_loads_existing_keys(self, tmp_path, mock_llm):
        """Test that serve() loads existing keys if present."""
        agent = Agent("test_agent", llm=mock_llm)

        # Mock existing keys
        mock_addr_data = {
            'address': '0xtest123',
            'short_address': 'co/test',
            'public_key': 'pubkey',
            'private_key': 'privkey'
        }

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr_data) as mock_load:
                with patch('connectonion.address.generate') as mock_generate:
                    with patch('connectonion.announce.create_announce_message', return_value={'type': 'ANNOUNCE'}):
                        with patch('asyncio.run'):  # Don't actually run
                            with patch('connectonion.relay.connect', new_callable=AsyncMock):
                                with patch('builtins.print'):  # Suppress output
                                    # This will try to serve, we just want to check key loading
                                    try:
                                        agent.serve()
                                    except:
                                        pass

                                    # Verify load was called
                                    mock_load.assert_called_once()
                                    # Verify generate was NOT called (keys exist)
                                    mock_generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_serve_generates_new_keys_if_missing(self, tmp_path, mock_llm):
        """Test that serve() generates keys if none exist."""
        agent = Agent("test_agent", llm=mock_llm)

        # Mock no existing keys (load returns None)
        mock_generated_addr = {
            'address': '0xnewkeys',
            'short_address': 'co/new',
            'public_key': 'newpub',
            'private_key': 'newpriv'
        }

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=None) as mock_load:
                with patch('connectonion.address.generate', return_value=mock_generated_addr) as mock_generate:
                    with patch('connectonion.address.save') as mock_save:
                        with patch('connectonion.announce.create_announce_message', return_value={'type': 'ANNOUNCE'}):
                            with patch('asyncio.run'):
                                with patch('connectonion.relay.connect', new_callable=AsyncMock):
                                    with patch('builtins.print'):
                                        try:
                                            agent.serve()
                                        except:
                                            pass

                                        # Verify generate was called
                                        mock_generate.assert_called_once()
                                        # Verify save was called with generated keys
                                        mock_save.assert_called_once_with(
                                            mock_generated_addr,
                                            tmp_path / '.co'
                                        )

    @pytest.mark.asyncio
    async def test_serve_saves_keys_to_co_directory(self, tmp_path, mock_llm):
        """Test that generated keys are saved to .co directory."""
        agent = Agent("test_agent", llm=mock_llm)

        mock_addr = {'address': '0xtest', 'short_address': 'co/test'}

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=None):
                with patch('connectonion.address.generate', return_value=mock_addr):
                    with patch('connectonion.address.save') as mock_save:
                        with patch('connectonion.announce.create_announce_message', return_value={'type': 'ANNOUNCE'}):
                            with patch('asyncio.run'):
                                with patch('connectonion.relay.connect', new_callable=AsyncMock):
                                    with patch('builtins.print'):
                                        try:
                                            agent.serve()
                                        except:
                                            pass

                                        # Verify save was called with .co directory
                                        assert mock_save.called
                                        save_path = mock_save.call_args[0][1]
                                        assert save_path == tmp_path / '.co'


class TestAgentServeAnnounceMessage:
    """Test ANNOUNCE message creation in serve()."""

    @pytest.mark.asyncio
    async def test_serve_creates_announce_with_system_prompt(self, tmp_path, mock_llm):
        """Test that ANNOUNCE uses system_prompt as summary."""
        system_prompt = "I am a helpful translation agent"
        agent = Agent("translator", system_prompt=system_prompt, llm=mock_llm)

        mock_addr = {'address': '0xtest', 'short_address': 'co/test'}

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch('connectonion.announce.create_announce_message') as mock_announce:
                    mock_announce.return_value = {'type': 'ANNOUNCE'}
                    with patch('asyncio.run'):
                        with patch('connectonion.relay.connect', new_callable=AsyncMock):
                            with patch('builtins.print'):
                                try:
                                    agent.serve()
                                except:
                                    pass

                                # Verify ANNOUNCE was created with system_prompt
                                assert mock_announce.called
                                call_args = mock_announce.call_args[0]
                                summary = call_args[1]
                                assert summary == system_prompt

    @pytest.mark.asyncio
    async def test_serve_truncates_long_system_prompt(self, tmp_path, mock_llm):
        """Test that very long system_prompts are truncated to 1000 chars."""
        long_prompt = "A" * 2000  # 2000 characters
        agent = Agent("test", system_prompt=long_prompt, llm=mock_llm)

        mock_addr = {'address': '0xtest', 'short_address': 'co/test'}

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch('connectonion.announce.create_announce_message') as mock_announce:
                    mock_announce.return_value = {'type': 'ANNOUNCE'}
                    with patch('asyncio.run'):
                        with patch('connectonion.relay.connect', new_callable=AsyncMock):
                            with patch('builtins.print'):
                                try:
                                    agent.serve()
                                except:
                                    pass

                                # Verify summary is truncated to 1000 chars
                                summary = mock_announce.call_args[0][1]
                                assert len(summary) == 1000
                                assert summary == long_prompt[:1000]

    @pytest.mark.asyncio
    async def test_serve_uses_agent_name_if_no_system_prompt(self, tmp_path, mock_llm):
        """Test that agent name is used if no system_prompt provided."""
        agent = Agent("calculator", llm=mock_llm)  # No system_prompt

        mock_addr = {'address': '0xtest', 'short_address': 'co/test'}

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch('connectonion.announce.create_announce_message') as mock_announce:
                    mock_announce.return_value = {'type': 'ANNOUNCE'}
                    with patch('asyncio.run'):
                        with patch('connectonion.relay.connect', new_callable=AsyncMock):
                            with patch('builtins.print'):
                                try:
                                    agent.serve()
                                except:
                                    pass

                                # Verify summary uses default system prompt when no custom prompt provided
                                summary = mock_announce.call_args[0][1]
                                # Agent() with no system_prompt uses default: "You are a helpful assistant..."
                                assert summary == "You are a helpful assistant that can use tools to complete tasks."


class TestAgentServeRelayConnection:
    """Test relay connection handling in serve()."""

    @pytest.mark.asyncio
    async def test_serve_connects_to_default_relay(self, tmp_path, mock_llm):
        """Test that serve() uses default relay URL when calling asyncio.run()."""
        agent = Agent("test", llm=mock_llm)

        mock_addr = {'address': '0xtest', 'short_address': 'co/test'}

        # Track what coroutine was passed to asyncio.run
        captured_coro = None

        def capture_run(coro):
            nonlocal captured_coro
            captured_coro = coro
            # Don't actually execute - just capture
            return None

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch('connectonion.announce.create_announce_message', return_value={'type': 'ANNOUNCE'}):
                    with patch('asyncio.run', side_effect=capture_run):
                        with patch('builtins.print'):
                            try:
                                agent.serve()  # Uses default relay URL
                            except:
                                pass

                            # Verify asyncio.run was called (coroutine captured)
                            assert captured_coro is not None

                            # Now test the coroutine manually to verify it connects to default URL
                            mock_ws = AsyncMock()
                            with patch('connectonion.relay.connect', new_callable=AsyncMock, return_value=mock_ws) as mock_connect:
                                with patch('connectonion.relay.serve_loop', new_callable=AsyncMock):
                                    # Execute the captured coroutine (we're already in an async test)
                                    await captured_coro

                                    # Verify default relay URL was used
                                    mock_connect.assert_called_once_with("wss://oo.openonion.ai/ws/announce")

    @pytest.mark.asyncio
    async def test_serve_connects_to_custom_relay(self, tmp_path, mock_llm):
        """Test that serve() uses custom relay URL when provided."""
        agent = Agent("test", llm=mock_llm)

        mock_addr = {'address': '0xtest', 'short_address': 'co/test'}
        custom_url = "ws://localhost:8000/ws/announce"

        # Track what coroutine was passed to asyncio.run
        captured_coro = None

        def capture_run(coro):
            nonlocal captured_coro
            captured_coro = coro
            # Don't actually execute - just capture
            return None

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch('connectonion.announce.create_announce_message', return_value={'type': 'ANNOUNCE'}):
                    with patch('asyncio.run', side_effect=capture_run):
                        with patch('builtins.print'):
                            try:
                                agent.serve(relay_url=custom_url)  # Uses custom URL
                            except:
                                pass

                            # Verify asyncio.run was called (coroutine captured)
                            assert captured_coro is not None

                            # Now test the coroutine manually to verify it connects to custom URL
                            mock_ws = AsyncMock()
                            with patch('connectonion.relay.connect', new_callable=AsyncMock, return_value=mock_ws) as mock_connect:
                                with patch('connectonion.relay.serve_loop', new_callable=AsyncMock):
                                    # Execute the captured coroutine (we're already in an async test)
                                    await captured_coro

                                    # Verify custom relay URL was used
                                    mock_connect.assert_called_once_with(custom_url)


class TestAgentServeTaskHandler:
    """Test task handler creation and execution."""

    @pytest.mark.asyncio
    async def test_serve_creates_task_handler(self, tmp_path, mock_llm):
        """Test that serve() creates task handler calling agent.input()."""
        agent = Agent("test", llm=mock_llm)
        agent.input = Mock(return_value="test response")

        mock_addr = {'address': '0xtest', 'short_address': 'co/test'}

        # Track what coroutine was passed to asyncio.run
        captured_coro = None

        def capture_run(coro):
            nonlocal captured_coro
            captured_coro = coro
            # Don't actually execute - just capture
            return None

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch('connectonion.announce.create_announce_message', return_value={'type': 'ANNOUNCE'}):
                    with patch('asyncio.run', side_effect=capture_run):
                        with patch('builtins.print'):
                            try:
                                agent.serve()
                            except:
                                pass

                            # Verify asyncio.run was called (coroutine captured)
                            assert captured_coro is not None

                            # Now test the coroutine to capture task_handler
                            captured_handler = None
                            mock_ws = AsyncMock()

                            async def capture_serve_loop(ws, announce_msg, handler, **kwargs):
                                nonlocal captured_handler
                                captured_handler = handler
                                # Don't actually loop

                            with patch('connectonion.relay.connect', new_callable=AsyncMock, return_value=mock_ws):
                                with patch('connectonion.relay.serve_loop', side_effect=capture_serve_loop):
                                    # Execute the captured coroutine (we're already in an async test)
                                    await captured_coro

                                    # Verify handler was captured
                                    assert captured_handler is not None

                                    # Test the handler (already in async context)
                                    result = await captured_handler("test prompt")
                                    agent.input.assert_called_once_with("test prompt")
                                    assert result == "test response"


class TestAgentServeConsoleOutput:
    """Test console output during serve()."""

    @pytest.mark.asyncio
    async def test_serve_prints_agent_info(self, tmp_path, mock_llm):
        """Test that serve() prints agent information."""
        agent = Agent("test_agent", llm=mock_llm)

        mock_addr = {
            'address': '0x1234567890abcdef',
            'short_address': 'co/test'
        }

        with patch('connectonion.agent.Path.cwd', return_value=tmp_path):
            with patch('connectonion.address.load', return_value=mock_addr):
                with patch('connectonion.announce.create_announce_message', return_value={'type': 'ANNOUNCE'}):
                    with patch('asyncio.run'):
                        with patch('connectonion.relay.connect', new_callable=AsyncMock):
                            # Capture console output
                            with patch.object(agent.console, 'print') as mock_print:
                                try:
                                    agent.serve()
                                except:
                                    pass

                                # Verify agent info was printed
                                print_calls = [str(call) for call in mock_print.call_args_list]

                                # Should print agent name
                                assert any("test_agent" in str(call) for call in print_calls)

                                # Should print address
                                assert any("0x1234567890abcdef" in str(call) for call in print_calls)

                                # Should print debug URL
                                assert any("https://oo.openonion.ai/agent/" in str(call) for call in print_calls)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for ULW (Ultra Light Work) plugin."""
"""
LLM-Note: Tests for useful plugins ulw

What it tests:
- ULW plugin auto-activates without mode setup
- Stops when agent says "genuinely complete"
- Stops when max_rounds reached
- UltraWork factory creates plugin with custom max_rounds

Components under test:
- Module: useful_plugins.ulw
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import importlib

ulw_mod = importlib.import_module("connectonion.useful_plugins.ulw")


def make_agent(result='some work done', rounds=0):
    agent = SimpleNamespace(
        current_session={'result': result, '_ulw_rounds': rounds},
        input=MagicMock(),
    )
    return agent


def test_ulw_starts_improvement_round():
    handler = ulw_mod._make_ulw_handler(max_rounds=5)
    agent = make_agent(result='I built the REST API.')

    handler(agent)

    agent.input.assert_called_once_with(ulw_mod.ULW_CONTINUE_PROMPT)
    assert agent.current_session['_ulw_rounds'] == 1


def test_ulw_stops_when_genuinely_complete():
    handler = ulw_mod._make_ulw_handler(max_rounds=5)
    agent = make_agent(result='The solution is genuinely complete, nothing left to improve.')

    handler(agent)

    agent.input.assert_not_called()


def test_ulw_stops_when_genuinely_complete_case_insensitive():
    handler = ulw_mod._make_ulw_handler(max_rounds=5)
    agent = make_agent(result='This is GENUINELY COMPLETE.')

    handler(agent)

    agent.input.assert_not_called()


def test_ulw_stops_at_max_rounds():
    handler = ulw_mod._make_ulw_handler(max_rounds=3)
    agent = make_agent(result='More work to do.', rounds=3)

    handler(agent)

    agent.input.assert_not_called()


def test_ulw_increments_rounds_each_call():
    handler = ulw_mod._make_ulw_handler(max_rounds=5)
    agent = make_agent(result='Needs improvement.', rounds=2)

    handler(agent)

    assert agent.current_session['_ulw_rounds'] == 3
    agent.input.assert_called_once()


def test_ulw_default_max_rounds_is_5():
    assert ulw_mod.ULW_DEFAULT_MAX_ROUNDS == 5


def test_ulw_plugin_is_list():
    assert isinstance(ulw_mod.ulw, list)
    assert len(ulw_mod.ulw) == 1


def test_ulw_handler_has_on_complete_event_type():
    handler = ulw_mod._make_ulw_handler(max_rounds=5)
    assert handler._event_type == 'on_complete'


def test_ultra_work_factory_returns_list():
    plugin = ulw_mod.UltraWork(max_rounds=3)
    assert isinstance(plugin, list)
    assert len(plugin) == 1


def test_ultra_work_factory_respects_max_rounds():
    plugin = ulw_mod.UltraWork(max_rounds=2)
    handler = plugin[0]

    agent = make_agent(result='Needs more work.', rounds=2)
    handler(agent)

    agent.input.assert_not_called()


def test_ultra_work_factory_continues_before_max_rounds():
    plugin = ulw_mod.UltraWork(max_rounds=2)
    handler = plugin[0]

    agent = make_agent(result='Needs more work.', rounds=1)
    handler(agent)

    agent.input.assert_called_once()


def test_ulw_handles_missing_rounds_key():
    handler = ulw_mod._make_ulw_handler(max_rounds=5)
    # No _ulw_rounds key in session
    agent = SimpleNamespace(
        current_session={'result': 'some result'},
        input=MagicMock(),
    )

    handler(agent)

    agent.input.assert_called_once()
    assert agent.current_session['_ulw_rounds'] == 1


def test_ulw_handles_empty_result():
    handler = ulw_mod._make_ulw_handler(max_rounds=5)
    agent = make_agent(result='')

    handler(agent)

    agent.input.assert_called_once()


def test_ulw_handles_none_result():
    handler = ulw_mod._make_ulw_handler(max_rounds=5)
    agent = SimpleNamespace(
        current_session={'result': None},
        input=MagicMock(),
    )

    handler(agent)

    agent.input.assert_called_once()

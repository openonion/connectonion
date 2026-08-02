"""Acknowledging the request is not doing the request.

Same shape as the eval plugin, same deployed agent: an @after_user_input
handler that calls a hardcoded provider, before the first tool, and takes the
turn down when that provider says no. What this one produces is a sentence
telling the user they were understood.
"""

import importlib
from unittest.mock import MagicMock, patch

# The package exports a plugin list under this name, which shadows the module.
system_reminder = importlib.import_module(
    "connectonion.cli.co_ai.plugins.system_reminder")


def make_agent(model="gemini-2.5-pro"):
    agent = MagicMock()
    agent.model = model
    agent.current_session = {"user_prompt": "整理合同", "messages": []}
    agent.io = None
    agent.logger.console = None
    return agent


def test_a_refused_call_does_not_stop_the_turn():
    agent = make_agent()

    with patch.object(system_reminder, "llm_do",
                      side_effect=RuntimeError("Insufficient ConnectOnion Credits")):
        system_reminder.detect_intent(agent)      # must not raise


def test_it_follows_the_model_the_agent_was_built_with():
    agent = make_agent(model="gemini-2.5-pro")

    with patch.object(system_reminder, "llm_do") as called:
        called.return_value = MagicMock(ack="ok", is_build=False)
        system_reminder.detect_intent(agent)

    assert called.call_args.kwargs["model"] == "gemini-2.5-pro"

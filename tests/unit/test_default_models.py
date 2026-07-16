"""Default managed models should stay aligned with the supported model list."""

import inspect

from connectonion import Agent, llm_do


def test_agent_uses_latest_managed_default():
    default = inspect.signature(Agent.__init__).parameters["model"].default

    assert default == "co/gemini-3.5-flash"


def test_llm_do_uses_latest_managed_default():
    default = inspect.signature(llm_do).parameters["model"].default

    assert default == "co/gemini-3.5-flash"

"""An unannotated tool parameter must not be guessed silently.

`param_type = type_hints.get(param_name, str)` typed anything unannotated as a
string. For `def add(a, b)` the model then correctly sent "2" and "3" per the
schema, and `a + b` evaluated to "23" — a wrong answer with no exception
anywhere, which is the kind of bug that survives for months.
"""

import warnings

import pytest

from connectonion.core.tool_factory import (
    UnannotatedParameterWarning,
    create_tool_from_function,
)


class TestItSaysSomething:
    def test_an_unannotated_parameter_warns(self):
        def add(a, b) -> int:
            """Add two numbers."""
            return a + b

        with pytest.warns(UnannotatedParameterWarning):
            create_tool_from_function(add)

    def test_the_warning_names_the_function_and_the_parameters(self):
        """A warning that does not say where to look costs as much time as no
        warning."""
        def add(a, b) -> int:
            """Add two numbers."""
            return a + b

        with pytest.warns(UnannotatedParameterWarning) as caught:
            create_tool_from_function(add)

        message = str(caught[0].message)
        assert "add" in message
        assert "a" in message and "b" in message

    def test_it_still_registers_rather_than_refusing(self):
        """Guessing is wrong; refusing would break every agent whose tools work
        today. The tool loads, and the developer is told."""
        def add(a, b) -> int:
            """Add two numbers."""
            return a + b

        with pytest.warns(UnannotatedParameterWarning):
            tool = create_tool_from_function(add)

        assert tool(a=2, b=3) == 5

    def test_the_guess_is_still_string_so_behaviour_is_unchanged(self):
        """This PR adds visibility, not a new schema. Changing the guess as well
        would move the failure rather than surface it."""
        def add(a, b) -> int:
            """Add two numbers."""
            return a + b

        with pytest.warns(UnannotatedParameterWarning):
            tool = create_tool_from_function(add)

        assert tool.get_parameters_schema()["properties"]["a"] == {"type": "string"}


class TestItStaysQuietWhenItShould:
    def test_a_fully_annotated_function_warns_about_nothing(self):
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        with warnings.catch_warnings():
            warnings.simplefilter("error", UnannotatedParameterWarning)
            create_tool_from_function(add)

    def test_agent_and_self_are_not_reported(self):
        """Both are injected rather than sent by the model, so neither is
        something the developer forgot to annotate."""
        class Tools:
            def act(self, agent, thing: str) -> str:
                """Do a thing."""
                return thing

        with warnings.catch_warnings():
            warnings.simplefilter("error", UnannotatedParameterWarning)
            create_tool_from_function(Tools().act)

    def test_a_function_with_no_parameters_warns_about_nothing(self):
        def ping() -> str:
            """Ping."""
            return "pong"

        with warnings.catch_warnings():
            warnings.simplefilter("error", UnannotatedParameterWarning)
            create_tool_from_function(ping)

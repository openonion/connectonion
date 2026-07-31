"""Passing the class instead of an instance must fail where the mistake is.

`MyTools.do_thing` and `MyTools().do_thing` are both callable, so the wrong one
is easy to pass. Schema generation accepted it — `self` was stripped, the schema
looked right — and every call then failed with a TypeError about `self`, raised
inside the agent loop, far from the line that registered the tool.
"""

import pytest

from connectonion.core.tool_factory import create_tool_from_function


class Calculator:
    def __init__(self, offset: int = 0):
        self.offset = offset

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b + self.offset


class TestUnboundMethods:
    def test_passing_the_class_method_is_refused_at_registration(self):
        with pytest.raises(TypeError):
            create_tool_from_function(Calculator.add)

    def test_the_message_says_what_to_do_instead(self):
        """A TypeError about `self` at call time describes the symptom. The
        registration site is where the fix is, so the message belongs here and
        has to name the correction."""
        with pytest.raises(TypeError) as caught:
            create_tool_from_function(Calculator.add)

        message = str(caught.value)
        assert "Calculator.add" in message
        assert "instance" in message.lower()

    def test_a_bound_method_still_works(self):
        tool = create_tool_from_function(Calculator(offset=10).add)

        assert tool(a=1, b=2) == 13
        assert "self" not in tool.get_parameters_schema()["properties"]

    def test_a_plain_function_still_works(self):
        def multiply(a: int, b: int) -> int:
            """Multiply two numbers."""
            return a * b

        assert create_tool_from_function(multiply)(a=3, b=4) == 12

    def test_a_function_whose_first_arg_is_named_self_is_not_a_method(self):
        """Nothing about the name `self` makes something a method. A plain
        function using it is unusual but legal, and refusing it would break a
        tool that works."""
        def odd(self: int, other: int) -> int:
            """Add, with a confusingly named first parameter."""
            return self + other

        tool = create_tool_from_function(odd)

        assert tool(self=1, other=2) == 3

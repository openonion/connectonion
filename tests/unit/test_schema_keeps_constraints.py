"""The schema is the only thing telling the model what a tool accepts.

Where it drops a constraint the function actually enforces, the model has no
way to know — it sends a plausible value, the tool rejects it at runtime, and
the round trip is spent discovering something the schema could have said.
"""

from enum import Enum
from typing import List, Literal, Optional, Union

from connectonion.core.tool_factory import get_json_schema_type


class Mode(str, Enum):
    FAST = "fast"
    SLOW = "slow"


class Priority(Enum):
    LOW = 1
    HIGH = 2


class TestLiteral:
    def test_the_allowed_values_reach_the_schema(self):
        """`Literal["fast","slow"]` used to fall through to a bare string, so
        the model could send "turbo" and only find out at runtime."""
        schema = get_json_schema_type(Literal["fast", "slow"])

        assert schema["type"] == "string"
        assert schema["enum"] == ["fast", "slow"]

    def test_an_integer_literal_is_typed_as_an_integer(self):
        """Saying "string" for Literal[1, 2] would make every valid value
        invalid on arrival."""
        schema = get_json_schema_type(Literal[1, 2])

        assert schema["type"] == "integer"
        assert schema["enum"] == [1, 2]

    def test_optional_literal_keeps_its_values(self):
        schema = get_json_schema_type(Optional[Literal["fast", "slow"]])

        assert schema["enum"] == ["fast", "slow"]


class TestEnum:
    def test_a_string_enum_publishes_its_values_not_its_member_names(self):
        """The model must send "fast", which is the value — not "FAST"."""
        schema = get_json_schema_type(Mode)

        assert schema["type"] == "string"
        assert schema["enum"] == ["fast", "slow"]

    def test_an_int_enum_is_typed_as_an_integer(self):
        schema = get_json_schema_type(Priority)

        assert schema["type"] == "integer"
        assert schema["enum"] == [1, 2]


class TestUnion:
    def test_a_two_type_union_offers_both(self):
        """Union[str, int] used to collapse to string, so int was never a legal
        value as far as the model could tell."""
        schema = get_json_schema_type(Union[str, int])

        assert "anyOf" in schema
        assert {"type": "string"} in schema["anyOf"]
        assert {"type": "integer"} in schema["anyOf"]

    def test_optional_is_still_the_inner_type_not_an_anyOf(self):
        """Optional[X] is Union[X, None] and already worked; a nullable
        parameter should stay a plain X rather than become a two-branch union."""
        assert get_json_schema_type(Optional[str]) == {"type": "string"}

    def test_optional_union_of_several_types_still_offers_them_all(self):
        schema = get_json_schema_type(Optional[Union[str, int]])

        assert "anyOf" in schema


class TestUntouched:
    """The shapes that already worked must keep working."""

    def test_plain_types(self):
        assert get_json_schema_type(str) == {"type": "string"}
        assert get_json_schema_type(int) == {"type": "integer"}
        assert get_json_schema_type(bool) == {"type": "boolean"}

    def test_list_of_strings(self):
        assert get_json_schema_type(List[str]) == {"type": "array", "items": {"type": "string"}}

    def test_an_unknown_type_still_falls_back_to_string(self):
        class Whatever: pass
        assert get_json_schema_type(Whatever) == {"type": "string"}

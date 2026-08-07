"""`llm_do` is one of two public entry points and had no test file of its own.

Found while fixing the `tested by [...]` references in the previous commit: its
header named `tests/test_llm_do_comprehensive.py` and `tests/test_real_llm_do.py`,
neither of which has ever existed, so the gap read as "covered elsewhere". What
does exist touches it only incidentally — test_reflect_handler and
test_intent_detection_is_not_load_bearing use it to test something else.

So this is that gap filled, at the level llm_do actually decides things: what
reaches the provider, and what the caller gets back.

The stand-in records the messages and kwargs it was handed rather than asserting
against a MagicMock that agrees with whatever is asked of it. Two things this
release has been repeatedly bitten by — a fake that diverges from the real
object, and a green test that measured nothing — both come from the other choice.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel

# The package exports a function named `llm_do`, which shadows the module of the
# same name: both `from connectonion import llm_do` and
# `import connectonion.llm_do as m` hand back the function, because `as` reads
# the attribute off the package. import_module returns the module itself.
import importlib

from connectonion.llm_do import llm_do

llm_do_module = importlib.import_module("connectonion.llm_do")


class Answer(BaseModel):
    value: int


class _RecordingLLM:
    """Records what llm_do handed the provider. Mirrors the real LLM contract:
    complete(messages, tools=None, **kwargs) -> object with .content;
    structured_complete(messages, schema, **kwargs) -> schema instance."""

    def __init__(self, **init_kwargs):
        self.init_kwargs = init_kwargs
        self.calls = []

    def complete(self, messages, tools=None, **kwargs):
        self.calls.append(("complete", messages, tools, kwargs))

        class _Response:
            content = "the answer"

        return _Response()

    def structured_complete(self, messages, output_schema, **kwargs):
        self.calls.append(("structured", messages, output_schema, kwargs))
        return output_schema(value=4)


@pytest.fixture
def llm(monkeypatch):
    """Replace the factory, and expose the instance llm_do built."""
    made = {}

    def factory(model=None, api_key=None):
        made["llm"] = _RecordingLLM(model=model, api_key=api_key)
        return made["llm"]

    monkeypatch.setattr(llm_do_module, "create_llm", factory)
    return made


class TestTheInputReachesTheProvider:

    def test_the_user_message_is_the_input(self, llm):
        llm_do("what is 2+2")

        _, messages, _, _ = llm["llm"].calls[0]
        assert messages[-1] == {"role": "user", "content": "what is 2+2"}

    def test_a_system_message_comes_first(self, llm):
        llm_do("hi")

        _, messages, _, _ = llm["llm"].calls[0]
        assert messages[0]["role"] == "system"

    def test_the_default_system_prompt_is_used(self, llm):
        llm_do("hi")

        _, messages, _, _ = llm["llm"].calls[0]
        assert messages[0]["content"] == "You are a helpful assistant."

    def test_a_string_system_prompt_is_passed_through(self, llm):
        llm_do("hi", system_prompt="You only speak in haiku.")

        _, messages, _, _ = llm["llm"].calls[0]
        assert messages[0]["content"] == "You only speak in haiku."


class TestASystemPromptCanBeAFile:
    """Documented as `Optional[Union[str, Path]]`, and a real feature — an agent
    keeps its prompt in a file next to the code."""

    def test_the_file_contents_become_the_prompt(self, llm, tmp_path):
        prompt = tmp_path / "senior_developer.txt"
        prompt.write_text("You review code carefully.", encoding="utf-8")

        llm_do("hi", system_prompt=prompt)

        _, messages, _, _ = llm["llm"].calls[0]
        assert messages[0]["content"] == "You review code carefully."

    def test_a_missing_file_is_an_error_not_a_prompt(self, llm, tmp_path):
        """Passing the path as literal prompt text would be worse than failing."""
        with pytest.raises(Exception) as excinfo:
            llm_do("hi", system_prompt=tmp_path / "nope.txt")

        assert "nope.txt" in str(excinfo.value)


class TestEmptyInputIsRefused:

    @pytest.mark.parametrize("bad", ["", "   ", "\n\t"])
    def test_it_raises(self, llm, bad):
        with pytest.raises(ValueError, match="empty"):
            llm_do(bad)

    def test_nothing_reached_the_provider(self, llm):
        with pytest.raises(ValueError):
            llm_do("")

        assert llm == {} or not llm["llm"].calls


class TestStructuredOutputTakesTheOtherPath:

    def test_it_returns_the_model_instance(self, llm):
        result = llm_do("what is 2+2", output=Answer)

        assert isinstance(result, Answer) and result.value == 4

    def test_the_schema_is_handed_over(self, llm):
        llm_do("hi", output=Answer)

        kind, _, schema, _ = llm["llm"].calls[0]
        assert kind == "structured" and schema is Answer

    def test_without_output_it_returns_text(self, llm):
        assert llm_do("hi") == "the answer"

    def test_the_plain_path_asks_for_no_tools(self, llm):
        """llm_do is one-shot: a tool call would have nothing to return to."""
        llm_do("hi")

        _, _, tools, _ = llm["llm"].calls[0]
        assert tools is None


class TestKwargsAndModelReachTheRightPlace:

    def test_temperature_goes_to_the_call_not_the_constructor(self, llm):
        llm_do("hi", temperature=0.9)

        _, _, _, kwargs = llm["llm"].calls[0]
        assert kwargs["temperature"] == 0.9
        assert "temperature" not in llm["llm"].init_kwargs

    def test_the_model_goes_to_the_constructor(self, llm):
        llm_do("hi", model="co/gemini-2.5-flash")

        assert llm["llm"].init_kwargs["model"] == "co/gemini-2.5-flash"

    def test_the_api_key_goes_to_the_constructor(self, llm):
        llm_do("hi", api_key="sk-test")

        assert llm["llm"].init_kwargs["api_key"] == "sk-test"

    def test_kwargs_reach_the_structured_path_too(self, llm):
        llm_do("hi", output=Answer, temperature=0.1)

        _, _, _, kwargs = llm["llm"].calls[0]
        assert kwargs["temperature"] == 0.1


class TestTheDefaultModelIsThePricedOne:
    """A default that is not in the price table shows its cost with a `~`."""

    def test_the_default_is_documented_and_priced(self):
        import inspect

        from connectonion.core.usage import is_estimated_price

        default = inspect.signature(llm_do).parameters["model"].default

        assert default.startswith("co/")
        assert not is_estimated_price(default)

"""The shipped quickstart must not teach unsafe or imaginary tools."""

from pathlib import Path


QUICKSTART = Path(__file__).parents[2] / "docs" / "quickstart.md"


def test_the_quickstart_does_not_execute_model_supplied_expressions():
    text = QUICKSTART.read_text()

    assert "eval(expression)" not in text


def test_the_quickstart_does_not_present_simulated_search_as_a_tool():
    text = QUICKSTART.read_text()

    assert "[simulated results]" not in text

"""Unit tests for connectonion/tui/ components

Tests cover:
- fuzzy.py: fuzzy_match, highlight_match
- divider.py: Divider class
- footer.py: Footer class
- keys.py: getch, read_key (mocked since they require terminal)
"""
"""
LLM-Note: Tests for tui components

What it tests:
- Tui Components functionality

Components under test:
- Module: tui_components
"""


from unittest.mock import Mock


class TestFuzzyMatch:
    """Tests for fuzzy_match function."""

    def test_fuzzy_match_empty_query(self):
        """Test empty query matches everything."""
        from connectonion.tui.fuzzy import fuzzy_match

        matched, score, positions = fuzzy_match("", "hello world")

        assert matched is True
        assert score == 0
        assert positions == []

    def test_fuzzy_match_exact_match(self):
        """Test exact match returns True."""
        from connectonion.tui.fuzzy import fuzzy_match

        matched, score, positions = fuzzy_match("hello", "hello world")

        assert matched is True
        assert score > 0
        assert len(positions) == 5  # All chars in "hello"

    def test_fuzzy_match_no_match(self):
        """Test no match returns False."""
        from connectonion.tui.fuzzy import fuzzy_match

        matched, score, positions = fuzzy_match("xyz", "hello")

        assert matched is False
        assert score == 0

    def test_fuzzy_match_partial_match(self):
        """Test partial fuzzy match."""
        from connectonion.tui.fuzzy import fuzzy_match

        matched, score, positions = fuzzy_match("hw", "hello world")

        assert matched is True
        assert len(positions) == 2  # 'h' and 'w'

    def test_fuzzy_match_case_insensitive(self):
        """Test fuzzy match is case insensitive."""
        from connectonion.tui.fuzzy import fuzzy_match

        matched, score, positions = fuzzy_match("HW", "hello world")

        assert matched is True

    def test_fuzzy_match_consecutive_bonus(self):
        """Test consecutive matches get higher score."""
        from connectonion.tui.fuzzy import fuzzy_match

        # "hel" consecutive should score higher than "h_e_l" non-consecutive
        matched1, score1, _ = fuzzy_match("hel", "hello")
        matched2, score2, _ = fuzzy_match("hel", "h_e_l_lo")

        assert matched1 is True
        assert matched2 is True
        assert score1 > score2

    def test_fuzzy_match_word_boundary_bonus(self):
        """Test word boundary matches get bonus."""
        from connectonion.tui.fuzzy import fuzzy_match

        # Starting with word boundary should have bonus
        matched, score, positions = fuzzy_match("t", "test")

        assert matched is True
        # First char should have word boundary bonus
        assert 0 in positions


class TestHighlightMatch:
    """Tests for highlight_match function."""

    def test_highlight_match_returns_text(self):
        """Test highlight_match returns Rich Text."""
        from connectonion.tui.fuzzy import highlight_match
        from rich.text import Text

        result = highlight_match("hello", [0, 1])

        assert isinstance(result, Text)

    def test_highlight_match_empty_positions(self):
        """Test highlight_match with no positions."""
        from connectonion.tui.fuzzy import highlight_match

        result = highlight_match("hello", [])

        assert str(result) == "hello"

    def test_highlight_match_all_positions(self):
        """Test highlight_match with all positions."""
        from connectonion.tui.fuzzy import highlight_match

        result = highlight_match("hi", [0, 1])

        # Both chars should be in result
        assert "h" in str(result)
        assert "i" in str(result)


class TestDivider:
    """Tests for Divider class."""

    def test_divider_default(self):
        """Test Divider with default settings."""
        from connectonion.tui.divider import Divider

        divider = Divider()

        assert divider.width == 40
        assert divider.char == "─"
        assert divider.style == "dim"

    def test_divider_custom_width(self):
        """Test Divider with custom width."""
        from connectonion.tui.divider import Divider

        divider = Divider(width=20)

        assert divider.width == 20

    def test_divider_custom_char(self):
        """Test Divider with custom character."""
        from connectonion.tui.divider import Divider

        divider = Divider(char="=")

        assert divider.char == "="

    def test_divider_render(self):
        """Test Divider render produces correct length."""
        from connectonion.tui.divider import Divider
        from rich.text import Text

        divider = Divider(width=10, char="-")
        result = divider.render()

        assert isinstance(result, Text)
        assert str(result) == "-" * 10

    def test_divider_render_with_style(self):
        """Test Divider render includes style."""
        from connectonion.tui.divider import Divider

        divider = Divider(style="bold")
        result = divider.render()

        # Just verify it returns without error
        assert result is not None


class TestFooter:
    """Tests for Footer class."""

    def test_footer_single_tip(self):
        """Test Footer with single tip."""
        from connectonion.tui.footer import Footer

        footer = Footer(["? help"])

        assert footer.tips == ["? help"]

    def test_footer_multiple_tips(self):
        """Test Footer with multiple tips."""
        from connectonion.tui.footer import Footer

        tips = ["? help", "/ commands", "@ contacts"]
        footer = Footer(tips)

        assert footer.tips == tips

    def test_footer_render_returns_text(self):
        """Test Footer render returns Rich Text."""
        from connectonion.tui.footer import Footer
        from rich.text import Text

        footer = Footer(["? help"])
        result = footer.render()

        assert isinstance(result, Text)

    def test_footer_render_single(self):
        """Test Footer render with single tip."""
        from connectonion.tui.footer import Footer

        footer = Footer(["? help"])
        result = footer.render()

        assert "? help" in str(result)

    def test_footer_render_multiple(self):
        """Test Footer render with multiple tips has separator."""
        from connectonion.tui.footer import Footer

        footer = Footer(["tip1", "tip2"])
        result = footer.render()

        # Both tips should be in output
        assert "tip1" in str(result)
        assert "tip2" in str(result)

    def test_footer_empty_tips(self):
        """Test Footer with empty tips list."""
        from connectonion.tui.footer import Footer

        footer = Footer([])
        result = footer.render()

        assert str(result) == ""


class TestTriggerAutoComplete:
    """Tests for TriggerAutoComplete class."""

    def test_find_trigger_position(self):
        """Test _find_trigger_position finds trigger char."""
        from connectonion.tui.chat import TriggerAutoComplete

        ac = TriggerAutoComplete.__new__(TriggerAutoComplete)
        ac.trigger = "/"

        assert ac._find_trigger_position("/help") == 0
        assert ac._find_trigger_position("hello /world") == 6
        assert ac._find_trigger_position("no trigger") == -1

    def test_get_search_string_with_trigger(self):
        """Test get_search_string returns text after trigger."""
        from connectonion.tui.chat import TriggerAutoComplete

        ac = TriggerAutoComplete.__new__(TriggerAutoComplete)
        ac.trigger = "/"

        # Create mock target_state
        target_state = Mock()
        target_state.text = "/help"

        result = ac.get_search_string(target_state)
        assert result == "help"

    def test_get_search_string_no_trigger(self):
        """Test get_search_string returns empty when no trigger."""
        from connectonion.tui.chat import TriggerAutoComplete

        ac = TriggerAutoComplete.__new__(TriggerAutoComplete)
        ac.trigger = "/"

        target_state = Mock()
        target_state.text = "hello"

        result = ac.get_search_string(target_state)
        assert result == ""

    def test_get_candidates_with_trigger(self):
        """Test get_candidates returns items when trigger present."""
        from connectonion.tui.chat import TriggerAutoComplete
        from textual_autocomplete import DropdownItem

        ac = TriggerAutoComplete.__new__(TriggerAutoComplete)
        ac.trigger = "/"
        ac._candidates = [DropdownItem(main="/help"), DropdownItem(main="/quit")]

        target_state = Mock()
        target_state.text = "/h"

        result = ac.get_candidates(target_state)
        assert len(result) == 2

    def test_get_candidates_no_trigger(self):
        """Test get_candidates returns empty when no trigger."""
        from connectonion.tui.chat import TriggerAutoComplete
        from textual_autocomplete import DropdownItem

        ac = TriggerAutoComplete.__new__(TriggerAutoComplete)
        ac.trigger = "/"
        ac._candidates = [DropdownItem(main="/help")]

        target_state = Mock()
        target_state.text = "hello"

        result = ac.get_candidates(target_state)
        assert len(result) == 0

    def test_apply_completion_uses_id(self):
        """Test apply_completion uses id when available."""
        from connectonion.tui.chat import TriggerAutoComplete
        from textual_autocomplete import DropdownItem

        ac = TriggerAutoComplete.__new__(TriggerAutoComplete)
        ac.trigger = "/"
        ac._candidates = [DropdownItem(main="/help - Show help", id="/help")]

        target_state = Mock()
        target_state.text = "/hel"

        # Library passes value (from item.main) and target_state
        result = ac.apply_completion("/help - Show help", target_state)
        assert result == "/help"

    def test_apply_completion_uses_value_if_no_id(self):
        """Test apply_completion uses value when no id."""
        from connectonion.tui.chat import TriggerAutoComplete
        from textual_autocomplete import DropdownItem

        ac = TriggerAutoComplete.__new__(TriggerAutoComplete)
        ac.trigger = "/"
        ac._candidates = [DropdownItem(main="/help")]

        target_state = Mock()
        target_state.text = "/hel"

        result = ac.apply_completion("/help", target_state)
        assert result == "/help"

    def test_apply_completion_preserves_prefix(self):
        """Test apply_completion preserves text before trigger."""
        from connectonion.tui.chat import TriggerAutoComplete
        from textual_autocomplete import DropdownItem

        ac = TriggerAutoComplete.__new__(TriggerAutoComplete)
        ac.trigger = "@"
        ac._candidates = [DropdownItem(main="John Doe - john@example.com", id="@john@example.com")]

        target_state = Mock()
        target_state.text = "Hello @joh"

        result = ac.apply_completion("John Doe - john@example.com", target_state)
        assert result == "Hello @john@example.com"

class TestChatWidgets:
    """Tests for Chat widget classes."""

    def test_thinking_indicator_frames(self):
        """Test ThinkingIndicator has animation frames."""
        from connectonion.tui.chat import ThinkingIndicator

        assert hasattr(ThinkingIndicator, 'frames')
        assert len(ThinkingIndicator.frames) > 0

    def test_thinking_indicator_has_elapsed_and_function_call(self):
        """Test ThinkingIndicator has elapsed and function_call properties."""
        from connectonion.tui.chat import ThinkingIndicator

        # Verify the class has the expected reactive properties
        assert hasattr(ThinkingIndicator, 'elapsed')
        assert hasattr(ThinkingIndicator, 'show_elapsed')
        assert hasattr(ThinkingIndicator, 'function_call')
        assert hasattr(ThinkingIndicator, 'reset_elapsed')

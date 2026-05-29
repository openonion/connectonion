"""Unit tests for connectonion/useful_tools/browser_tools/scroll.py

Focus: orchestration logic of the strategy fallback chain + screenshot diff helper.
The Playwright-driving `_ai_scroll` / `_element_scroll` / `_page_scroll` are out of scope
for unit tests — covered only at e2e where a real browser is available.
"""

from unittest.mock import Mock, patch

import pytest

from connectonion.useful_tools.browser_tools.scroll import (
    _screenshots_different,
    scroll,
)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Sleep calls inside scroll() add up — skip them in unit tests."""
    monkeypatch.setattr("time.sleep", lambda *_: None)


# ---------- top-level scroll() orchestration ----------

def test_returns_browser_not_open_when_page_is_none():
    result = scroll(None, take_screenshot=Mock())
    assert result == "Browser not open"


def test_first_strategy_succeeding_returns_its_name():
    page = Mock()
    take_ss = Mock()
    with patch('connectonion.useful_tools.browser_tools.scroll._ai_scroll'), \
         patch(
             'connectonion.useful_tools.browser_tools.scroll._screenshots_different',
             return_value=True,
         ):
        result = scroll(page, take_ss)
    assert result == "Scrolled using AI strategy"


def test_falls_through_when_first_strategy_does_not_change_content():
    """If AI scroll's screenshot diff comes back False, try Element next.
    Element succeeds → return its name."""
    page = Mock()
    take_ss = Mock()
    diff_results = iter([False, True])  # AI fails diff, Element succeeds
    with patch('connectonion.useful_tools.browser_tools.scroll._ai_scroll'), \
         patch('connectonion.useful_tools.browser_tools.scroll._element_scroll'), \
         patch(
             'connectonion.useful_tools.browser_tools.scroll._screenshots_different',
             side_effect=lambda *a, **k: next(diff_results),
         ):
        result = scroll(page, take_ss)
    assert result == "Scrolled using Element scroll"


def test_falls_all_the_way_to_page_scroll():
    page = Mock()
    take_ss = Mock()
    diff_results = iter([False, False, True])
    with patch('connectonion.useful_tools.browser_tools.scroll._ai_scroll'), \
         patch('connectonion.useful_tools.browser_tools.scroll._element_scroll'), \
         patch('connectonion.useful_tools.browser_tools.scroll._page_scroll'), \
         patch(
             'connectonion.useful_tools.browser_tools.scroll._screenshots_different',
             side_effect=lambda *a, **k: next(diff_results),
         ):
        result = scroll(page, take_ss)
    assert result == "Scrolled using Page scroll"


def test_all_strategies_failing_returns_failure_message():
    page = Mock()
    take_ss = Mock()
    with patch(
        'connectonion.useful_tools.browser_tools.scroll._ai_scroll',
        side_effect=RuntimeError("ai broke"),
    ), patch(
        'connectonion.useful_tools.browser_tools.scroll._element_scroll',
        side_effect=RuntimeError("el broke"),
    ), patch(
        'connectonion.useful_tools.browser_tools.scroll._page_scroll',
        side_effect=RuntimeError("page broke"),
    ):
        result = scroll(page, take_ss)
    assert result == "All scroll strategies failed"


def test_exception_in_one_strategy_does_not_short_circuit_chain():
    """If AI scroll raises, we should still try Element next."""
    page = Mock()
    take_ss = Mock()
    with patch(
        'connectonion.useful_tools.browser_tools.scroll._ai_scroll',
        side_effect=RuntimeError("ai broke"),
    ), patch(
        'connectonion.useful_tools.browser_tools.scroll._element_scroll',
    ) as mock_el, patch(
        'connectonion.useful_tools.browser_tools.scroll._screenshots_different',
        return_value=True,
    ):
        result = scroll(page, take_ss)
    mock_el.assert_called_once()
    assert result == "Scrolled using Element scroll"


def test_screenshots_taken_before_and_after_each_attempt():
    """take_screenshot should be called once before + once after each attempted strategy."""
    page = Mock()
    take_ss = Mock()
    with patch('connectonion.useful_tools.browser_tools.scroll._ai_scroll'), \
         patch(
             'connectonion.useful_tools.browser_tools.scroll._screenshots_different',
             return_value=True,
         ):
        scroll(page, take_ss)
    # 1 before + 1 after for the successful first strategy
    assert take_ss.call_count == 2


# ---------- _screenshots_different ----------

def _make_image(path, color):
    pytest.importorskip("PIL")
    from PIL import Image
    img = Image.new('RGB', (20, 20), color)
    img.save(path)


def test_identical_screenshots_return_false(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "screenshots").mkdir()
    _make_image(tmp_path / "screenshots" / "a.png", (255, 0, 0))
    _make_image(tmp_path / "screenshots" / "b.png", (255, 0, 0))
    assert _screenshots_different("a.png", "b.png") is False


def test_visually_different_screenshots_return_true(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "screenshots").mkdir()
    _make_image(tmp_path / "screenshots" / "a.png", (0, 0, 0))
    _make_image(tmp_path / "screenshots" / "b.png", (255, 255, 255))
    assert _screenshots_different("a.png", "b.png") is True


def test_missing_file_defensively_returns_true(tmp_path, monkeypatch):
    """If we can't open the files (e.g. screenshot wasn't created), default to 'different'
    so the strategy fallback chain doesn't incorrectly conclude success."""
    monkeypatch.chdir(tmp_path)
    assert _screenshots_different("nope1.png", "nope2.png") is True

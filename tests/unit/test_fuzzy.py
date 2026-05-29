"""Unit tests for connectonion/tui/fuzzy.py"""

from connectonion.tui.fuzzy import fuzzy_match, highlight_match


# ---------- fuzzy_match: empty / no-match cases ----------

def test_empty_query_matches_everything_with_zero_score():
    assert fuzzy_match("", "anything") == (True, 0, [])


def test_no_chars_in_text_returns_unmatched():
    matched, score, positions = fuzzy_match("xyz", "abc")
    assert matched is False
    assert score == 0
    assert positions == []


def test_partial_match_returns_unmatched_with_zero_score():
    """`fz` in `foo`: f found, z never found → unmatched, score zeroed."""
    matched, score, positions = fuzzy_match("fz", "foo")
    assert matched is False
    assert score == 0
    assert positions == [0]  # positions still capture partial progress


# ---------- fuzzy_match: matched cases & positions ----------

def test_exact_substring_returns_consecutive_positions():
    matched, _, positions = fuzzy_match("abc", "abcdef")
    assert matched is True
    assert positions == [0, 1, 2]


def test_subsequence_matches_with_gaps():
    matched, _, positions = fuzzy_match("fb", "foo bar")
    assert matched is True
    assert positions == [0, 4]  # f at 0, b at 4


def test_case_insensitive():
    matched, _, positions = fuzzy_match("FOO", "hello foo")
    assert matched is True
    assert positions == [6, 7, 8]


def test_query_longer_than_text_unmatched():
    matched, _, _ = fuzzy_match("abcdef", "ab")
    assert matched is False


# ---------- fuzzy_match: scoring behavior ----------

def test_consecutive_match_scores_higher_than_scattered():
    """`abc` consecutive in `abcxyz` beats `abc` scattered in `axbxcx`."""
    _, consecutive_score, _ = fuzzy_match("abc", "abcxyz")
    _, scattered_score, _ = fuzzy_match("abc", "axbxcx")
    assert consecutive_score > scattered_score


def test_word_boundary_after_slash_gets_bonus():
    """Match at i=1 in `/foo` gets word-boundary bonus because text[0] == '/'."""
    _, with_boundary, _ = fuzzy_match("foo", "/foo")
    _, no_boundary, _ = fuzzy_match("foo", "xfoo")
    assert with_boundary > no_boundary


def test_word_boundary_separators_all_trigger_bonus():
    """Each of / _ - . space should mark a word boundary."""
    base_score = fuzzy_match("foo", "xfoo")[1]
    for sep in ['/', '_', '-', '.', ' ']:
        text = f"x{sep}foo"
        score = fuzzy_match("foo", text)[1]
        assert score > base_score, f"separator {sep!r} did not produce bonus"


def test_score_zero_when_query_not_fully_matched_even_with_partial_progress():
    """Even if some chars found, unmatched query → score=0 (not just lower)."""
    _, score, positions = fuzzy_match("fox", "foo")
    assert score == 0
    assert len(positions) > 0  # f and o were found


# ---------- highlight_match ----------

def test_highlight_marks_listed_positions_with_style():
    text_obj = highlight_match("foobar", [0, 3])
    # Render via plain text and inspect spans
    assert str(text_obj) == "foobar"
    styled_indices = [i for i, ch in enumerate("foobar") if i in {0, 3}]
    # Inspect span coverage: every styled position should have bold magenta
    span_chars = [(span.start, span.end, str(span.style)) for span in text_obj.spans]
    matched_styles = [s for (start, end, s) in span_chars if start in styled_indices]
    assert all("magenta" in s for s in matched_styles)
    assert all("bold" in s for s in matched_styles)


def test_highlight_empty_positions_yields_unstyled_text():
    text_obj = highlight_match("hello", [])
    assert str(text_obj) == "hello"
    # No char should carry the highlight style
    for span in text_obj.spans:
        assert "magenta" not in str(span.style)


def test_highlight_preserves_full_text_length():
    text_obj = highlight_match("abcdef", [1, 3, 5])
    assert str(text_obj) == "abcdef"

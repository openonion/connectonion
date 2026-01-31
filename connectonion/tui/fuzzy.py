"""
Purpose: Fuzzy string matching for autocomplete with scoring and highlight positions
LLM-Note:
  Dependencies: imports from [rich.text.Text] | imported by [tui/dropdown.py, tui/providers.py, tui/input.py] | tested by [tests/tui/test_fuzzy.py]
  Data flow: fuzzy_match(query, text) → finds characters from query in text → calculates score based on sequential matches → returns (matched, score, positions) | highlight_match(text, positions) → creates Rich Text with highlighted characters
  State/Effects: no state (pure functions)
  Integration: exposes fuzzy_match(query, text) → (bool, int, list[int]), highlight_match(text, positions, highlight_style) → Text | used by autocomplete providers for filtering and highlighting
  Performance: O(n*m) matching (acceptable for short strings) | early exit if no match
  Errors: none (handles empty query)
Fuzzy matching utilities.
"""

from rich.text import Text


def fuzzy_match(query: str, text: str) -> tuple[bool, int, list[int]]:
    """Fuzzy match query against text.

    Args:
        query: Search query
        text: Text to match against

    Returns:
        (matched, score, positions) - Higher score = better match
    """
    if not query:
        return True, 0, []

    query = query.lower()
    text_lower = text.lower()

    positions = []
    query_idx = 0
    last_match = -1
    score = 0

    for i, char in enumerate(text_lower):
        if query_idx < len(query) and char == query[query_idx]:
            positions.append(i)
            # Consecutive match bonus
            if last_match == i - 1:
                score += 10
            # Word boundary bonus
            if i == 0 or text[i-1] in '/_-. ':
                score += 5
            score += 1
            last_match = i
            query_idx += 1

    matched = query_idx == len(query)
    return matched, score if matched else 0, positions


def highlight_match(text: str, positions: list[int]) -> Text:
    """Highlight matched characters in Rich Text.

    Uses green for matched chars (ConnectOnion theme).
    """
    result = Text()
    pos_set = set(positions)
    for i, char in enumerate(text):
        if i in pos_set:
            result.append(char, style="bold magenta")  # Violet for matched chars
        else:
            result.append(char)
    return result

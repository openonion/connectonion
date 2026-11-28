"""Jira ADF → readable text unit tests — F13FCAKE-11."""

from connectonion.useful_tools.jira_adf import adf_to_text


# Small builders so each test reads like the ADF it describes.
def _t(text, *marks):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = list(marks)
    return node


def _p(*content):
    return {"type": "paragraph", "content": list(content)}


def _li(*content):
    return {"type": "listItem", "content": list(content)}


def _doc(*content):
    return {"type": "doc", "version": 1, "content": list(content)}


def test_plain_string_and_non_document_input():
    """11-2: a plain string is trimmed; None, lists and numbers give "" instead of raising."""
    assert adf_to_text("  already plain text  ") == "already plain text"
    assert adf_to_text(None) == ""
    assert adf_to_text([_p(_t("x"))]) == ""
    assert adf_to_text(42) == ""
    assert adf_to_text(_doc()) == ""


def test_paragraphs_marks_and_hard_breaks():
    """11-3: paragraphs are separated by a blank line; code keeps backticks; a link keeps its target."""
    adf = _doc(
        _p(_t("Use "), _t("JSON Lines", {"type": "strong"}), _t(" and "), _t("rg", {"type": "code"})),
        _p(_t("docs", {"type": "link", "attrs": {"href": "https://example.com"}}),
           _t(" "), _t("https://example.com", {"type": "link", "attrs": {"href": "https://example.com"}}),
           {"type": "hardBreak"}, _t("next line")),
    )
    assert adf_to_text(adf) == (
        "Use JSON Lines and `rg`\n\n"
        "docs (https://example.com) https://example.com\nnext line"
    )


def test_headings_keep_their_level():
    """11-4: heading level 1–6 becomes that many '#'; a missing or invalid level falls back to one."""
    adf = _doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [_t("Decision")]},
        {"type": "heading", "attrs": {"level": 9}, "content": [_t("Odd level")]},
        {"type": "heading", "content": [_t("No level")]},
    )
    assert adf_to_text(adf) == "## Decision\n\n# Odd level\n\n# No level"


def test_bullet_ordered_and_nested_lists():
    """11-5: bullets use '-', numbered lists honour 'order', nested lists indent two spaces per level."""
    adf = _doc(
        {"type": "bulletList", "content": [
            _li(_p(_t("one")), {"type": "orderedList", "content": [_li(_p(_t("nested")))]}),
            _li(_p(_t("two")), _p(_t("second paragraph"))),
        ]},
        {"type": "orderedList", "attrs": {"order": 3}, "content": [_li(_p(_t("third"))), _li(_p(_t("fourth")))]},
    )
    assert adf_to_text(adf) == (
        "- one\n"
        "  1. nested\n"
        "- two\n"
        "  second paragraph\n\n"
        "3. third\n"
        "4. fourth"
    )


def test_code_blocks_quotes_rules_and_tables():
    """11-6: code is fenced with its language, quotes get '> ', a rule is '---', table rows join cells with ' | '."""
    adf = _doc(
        {"type": "codeBlock", "attrs": {"language": "python"}, "content": [_t("print('hi')")]},
        {"type": "codeBlock", "content": [_t("no language")]},
        {"type": "blockquote", "content": [_p(_t("quoted")), _p(_t("more"))]},
        {"type": "rule"},
        {"type": "table", "content": [
            {"type": "tableRow", "content": [
                {"type": "tableHeader", "content": [_p(_t("Field"))]},
                {"type": "tableHeader", "content": [_p(_t("Required"))]}]},
            {"type": "tableRow", "content": [
                {"type": "tableCell", "content": [_p(_t("summary"))]},
                {"type": "tableCell", "content": [_p(_t("yes")), _p(_t("always"))]}]},
            {"type": "tableRow", "content": [{"type": "tableCell", "content": []}]},
        ]},
    )
    assert adf_to_text(adf) == (
        "```python\nprint('hi')\n```\n\n"
        "```\nno language\n```\n\n"
        "> quoted\n>\n> more\n\n"
        "---\n\n"
        "Field | Required\n"
        "summary | yes always"
    )


def test_people_cards_status_dates_and_emoji():
    """11-7: mentions, emoji, links cards, status lozenges and dates become readable inline text."""
    adf = _doc(_p(
        {"type": "mention", "attrs": {"id": "x", "text": "@Ben Okafor"}}, _t(" "),
        {"type": "emoji", "attrs": {"shortName": ":rocket:", "text": "🚀"}}, _t(" "),
        {"type": "emoji", "attrs": {"shortName": ":tada:"}}, _t(" "),
        {"type": "status", "attrs": {"text": "IN PROGRESS"}}, _t(" "),
        {"type": "date", "attrs": {"timestamp": "1759276800000"}}, _t(" "),
        {"type": "inlineCard", "attrs": {"url": "https://test.atlassian.net/browse/DEMO-1"}},
    ), {"type": "blockCard", "attrs": {"url": "https://example.com/spec"}})
    assert adf_to_text(adf) == (
        "@Ben Okafor 🚀 :tada: [IN PROGRESS] 2025-10-01 https://test.atlassian.net/browse/DEMO-1\n\n"
        "https://example.com/spec"
    )


def test_tasks_decisions_panels_and_expands():
    """11-8: task boxes show their state, decisions are labelled, panel and expand keep their content."""
    adf = _doc(
        {"type": "taskList", "content": [
            {"type": "taskItem", "attrs": {"state": "DONE"}, "content": [_t("share wireframes")]},
            {"type": "taskItem", "attrs": {"state": "TODO"}, "content": [_t("estimate")]}]},
        {"type": "decisionList", "content": [{"type": "decisionItem", "content": [_t("Use JSON Lines")]}]},
        {"type": "panel", "attrs": {"panelType": "info"}, "content": [_p(_t("panel note"))]},
        {"type": "expand", "attrs": {"title": "Details"}, "content": [_p(_t("hidden text"))]},
        {"type": "nestedExpand", "content": [_p(_t("untitled"))]},
    )
    assert adf_to_text(adf) == (
        "[x] share wireframes\n[ ] estimate\n\n"
        "Decision: Use JSON Lines\n\n"
        "panel note\n\n"
        "Details\nhidden text\n\n"
        "untitled"
    )


def test_media_is_a_placeholder_never_downloaded():
    """11-9: images and files become '[attachment: name]' (or '[attachment]'); no bytes are fetched."""
    adf = _doc(
        {"type": "mediaSingle", "content": [{"type": "media", "attrs": {"id": "m1", "type": "file", "alt": "diagram.png"}}]},
        {"type": "mediaGroup", "content": [{"type": "media", "attrs": {"id": "m2", "type": "file"}}]},
        _p(_t("see "), {"type": "mediaInline", "attrs": {"id": "m3", "alt": "notes.pdf"}}),
    )
    assert adf_to_text(adf) == "[attachment: diagram.png]\n\n[attachment]\n\nsee [attachment: notes.pdf]"


def test_unknown_and_malformed_nodes_keep_their_text():
    """11-10: unknown node types keep their text; broken content, attrs or marks are ignored, never raised."""
    adf = _doc(
        {"type": "futureInline", "content": [_t("inline from the future")]},
        {"type": "futureBlock", "content": [_p(_t("first")), _p(_t("second"))]},
        {"type": "paragraph", "content": "not a list"},
        {"type": "heading", "attrs": "not a dict", "content": [_t("heading")]},
        _p({"type": "text", "text": "marks broken", "marks": "bold"}, _t("x", "not a mark")),
        {"type": "date", "attrs": {"timestamp": "yesterday"}},
        {"type": "mention", "attrs": {}},
        "not a node",
    )
    assert adf_to_text(adf) == (
        "inline from the future\n\n"
        "first\nsecond\n\n"
        "# heading\n\n"
        "marks brokenx"
    )


def test_output_is_tidy():
    """11-11: trailing spaces are dropped and runs of blank lines collapse to one."""
    adf = _doc(_p(_t("line with trailing spaces   ")), _p(_t("   ")), {"type": "hardBreak"}, _p(_t("end")))
    assert adf_to_text(adf) == "line with trailing spaces\n\nend"


def test_dates_outside_the_calendar_are_dropped_not_raised():
    """11-12b: huge, negative-looking or year-10000 timestamps give "" instead of OverflowError/OSError."""
    for timestamp in ("9" * 30, "253402300800000", "-1000", "1e12"):
        adf = _doc(_p(_t("due "), {"type": "date", "attrs": {"timestamp": timestamp}}))
        assert adf_to_text(adf) == "due"
    first_ms = {"type": "date", "attrs": {"timestamp": "0"}}
    last_ms = {"type": "date", "attrs": {"timestamp": "253402214400000"}}
    assert adf_to_text(_doc(_p(first_ms), _p(last_ms))) == "1970-01-01\n\n9999-12-31"

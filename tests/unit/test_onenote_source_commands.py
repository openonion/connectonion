"""OneNote JSON must survive Windows legacy-codepage native command pipes."""

import json
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import onenote_source_commands


@pytest.fixture
def unicode_source(monkeypatch):
    source = Mock()
    source.notebooks.return_value = [{"id": "nb-test", "displayName": "中文笔记本🧅"}]
    source.sections.return_value = [
        {"id": "section-b", "displayName": "Page-B"},
        {"id": "section-test", "displayName": "无标题分区"},
    ]
    source.pages.return_value = {
        "pages": [{"id": "page-test", "title": "中文页面🧅"}],
        "scope": {"notebook": "nb-test", "section": "section-test"},
        "truncated": False, "limit": 100,
    }
    monkeypatch.setattr(onenote_source_commands, "_source", lambda: source)
    return source


@pytest.mark.parametrize("operation", ["notebooks", "sections", "pages", "scope-error"])
def test_json_preserves_unicode_through_legacy_windows_pipe(unicode_source, operation):
    """AC: multilingual success/error JSON stays parseable without shell reconfiguration."""
    commands = {
        "notebooks": ["notebooks"],
        "sections": ["sections", "nb-test"],
        "pages": ["pages", "nb-test", "section-test"],
        "scope-error": ["pages", "nb-test", "中文不存在分区"],
    }
    if operation == "scope-error":
        unicode_source.pages.side_effect = ValueError("Unknown section. Use co onenote source sections.")
    result = CliRunner().invoke(app, ["onenote", "source", *commands[operation], "--json"])
    assert result.exit_code == (1 if operation == "scope-error" else 0), result.output
    original = json.loads(result.stdout)

    # Reproduce UTF-8 native stdout being decoded by a CP936/GBK consumer,
    # as in the tester's PowerShell pipe. Check actual content, not serializer flags.
    legacy_pipe = result.stdout.encode("utf-8").decode("gbk", errors="replace")
    decoded = json.loads(legacy_pipe)
    assert decoded == original, "The pipe must preserve Unicode names, titles and error scope"
    if operation == "scope-error":
        assert decoded["scope"]["section"] == "中文不存在分区"
    elif operation == "sections":
        assert decoded["sections"][1]["displayName"] == "无标题分区"
    elif operation == "pages":
        assert decoded["pages"][0]["title"] == "中文页面🧅"
    else:
        assert decoded["notebooks"][0]["displayName"] == "中文笔记本🧅"

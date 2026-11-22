"""Today shows, in one line, what last night could not read and the step that fixes it (#3353). Invented notebook."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

GAP = {"source": "wechat", "line": "微信：消息库 12 · 有密钥 2 · 缺 10 → co wechat key capture",
       "line_en": "WeChat: message databases 12 · keyed 2 · 10 missing a key → co wechat key capture",
       "fix": "co wechat key capture", "unread": 10, "missing_keys": 10}


def _open(tmp_path, gaps, language="zh-CN", shot=None):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    root = tmp_path / "rem"
    build(root, datetime(2026, 11, 20, tzinfo=timezone.utc))
    (root / ".state").mkdir(exist_ok=True)
    (root / ".state" / "coverage.json").write_text(json.dumps({"at": "2026-11-20T01:00:00+00:00", "gaps": gaps}))
    page_file = tmp_path / "reader.html"
    page_file.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale=language)
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(page_file.as_uri())
        page.wait_for_timeout(1200)
        lines = page.locator(".coverage-gap")
        found = (lines.count(), lines.first.inner_text() if lines.count() else "")
        if shot:
            page.screenshot(path=shot)
        browser.close()
    return found


def test_a_gap_is_one_line_with_its_fix(tmp_path):
    count, text = _open(tmp_path, [GAP])
    assert count == 1 and "缺 10" in text and "co wechat key capture" in text


def test_several_gaps_still_make_one_line(tmp_path):
    count, text = _open(tmp_path, [GAP, {**GAP, "source": "outlook"}])
    assert count == 1 and "1" in text


def test_no_gap_no_line(tmp_path):
    assert _open(tmp_path, [])[0] == 0

"""One night, one count (#3396).

On rc19 one Today screen gave three totals for the same night: the 昨夜 heading said «读了 17 封邮件，写了 38 页»
(the latest 21 runs' reads called mails, and the pass's investigations called pages written), the caption under the
curve said «读了 163 项 · 改写了 8 页», and the side line counted waiting items. The Codex line read «Codex 正在做 1 件事
· Codex 有 1 件事没做完就停了», one task both running and stopped. Here the night is real run files in an invented
notebook (tests/fixtures/rem_reader_notebook.py), read by the same render() path the Host uses."""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _night(now: datetime) -> list[dict]:
    """One dense stretch of 10 runs: two reads of 30 and 9 items, then eight rewrites, three of which change a page."""
    start = now - timedelta(hours=2)
    iso = lambda t: t.isoformat(timespec="seconds")
    runs = [{"phase": "sync", "started_at": iso(start), "finished_at": iso(start + timedelta(minutes=2)),
             "outcome": "completed", "items": 30, "changed": []},
            {"phase": "sync", "started_at": iso(start + timedelta(minutes=3)), "finished_at": iso(start + timedelta(minutes=5)),
             "outcome": "completed", "items": 9, "changed": []}]
    for i in range(8):
        at = start + timedelta(minutes=6 + i * 3)
        runs.append({"phase": "daily-update", "started_at": iso(at), "finished_at": iso(at + timedelta(minutes=2)),
                     "outcome": "completed", "items": 1,
                     "changed": ["people/mara-ostrowski.md"] if i in (1, 4, 6) else []})
    return runs


@pytest.fixture(scope="module")
def page_file(tmp_path_factory):
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    root = tmp_path_factory.mktemp("truth") / "rem"
    now = datetime.now(timezone.utc)
    build(root, now - timedelta(days=3))  # the fixture's own runs sit days before tonight's pass
    runs = root / ".state" / "runs"
    for i, run in enumerate(_night(now)):
        run["id"] = f"run_{0xdef000 + i:032x}"
        (runs / f"{run['id']}.json").write_text(json.dumps(run))
    path = root.parent / "reader.html"
    path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    return path


def _open(page_file, width=1440, height=900):
    from patchright.sync_api import sync_playwright
    api = sync_playwright().start()
    browser = api.chromium.launch(channel="chrome", headless=True)
    page = browser.new_context(viewport={"width": width, "height": height}, locale="en-US").new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(page_file.as_uri())
    page.locator("#main .night-card").wait_for()
    return api, browser, page


def _numbers(text: str) -> dict:
    found = {}
    for key, pattern in (("read", r"read (\d+) items?"), ("rewrote", r"rewrote (\d+) pages?"), ("translated", r"translated (\d+) pages?")):
        match = re.search(pattern, text)
        found[key] = int(match.group(1)) if match else 0
    return found


def test_the_heading_and_the_curve_caption_count_the_same_night(page_file):
    api, browser, page = _open(page_file)
    try:
        heading = page.locator("#main .night-card .night-sum").inner_text()
        captions = page.locator("#main .night-card .stretch-what").all_inner_texts()
        assert "mail" not in heading, heading  # reads come from every source, not mail alone
        assert captions, "the night's stretch has a caption"
        total = {key: sum(_numbers(caption)[key] for caption in captions) for key in ("read", "rewrote", "translated")}
        assert _numbers(heading) == total, (heading, captions)
        assert _numbers(heading)["read"] == 39 + 5, heading  # 30 + 9 read, plus the five rewrites that changed nothing
        assert _numbers(heading)["rewrote"] == 3, heading
    finally:
        browser.close()
        api.stop()


def test_working_and_stopped_are_never_said_of_one_task(page_file):
    api, browser, page = _open(page_file)
    try:
        line = page.evaluate("""() => workSummary([
          {task: {agent: 'codex', result: 'running', started_at: new Date().toISOString()}},
          {task: {agent: 'codex', result: 'failed'}}])""", isolated_context=False)
        assert "working on 1 thing" in line and "another 1 stopped before finishing" in line, line
        assert "Codex stopped before finishing" not in line, line
        alone = page.evaluate("() => workSummary([{task: {agent: 'codex', result: 'failed'}}])", isolated_context=False)
        assert alone == "Codex stopped before finishing 1 thing", alone
    finally:
        browser.close()
        api.stop()

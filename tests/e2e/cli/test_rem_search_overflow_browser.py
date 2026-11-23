"""No search or tag view is wider than the viewport (#3404).

A tag chip opens `#q=tag:<tag>`. On the owner's notebook that page scrolled sideways (1908 px at 1440, 1708 px at 390):
result snippets carry the page's own marked and cited passages, and their curtain, privacy tag and citation spans
were laid out past the row instead of being clipped by it. The notebook is the invented one in
tests/fixtures/rem_reader_notebook.py, with one tagged page whose lines are long, marked and cited the way the
writer emits them."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-search-overflow-shots"))
LONG = "Harbourmastersignoffchecklistforthepilotwithoutanyspaces" * 3
PAGE = ("# Pilot ledger\n\n- Tags: pilot [1]\n\n"
        f"The pilot budget sits in {LONG} and Quill said “the budget for the pilot has to cover every seat, the "
        "support hours and the migration before the board meets” [1][2] [sensitive]; it was agreed on 2026-09-03.\n\n"
        f"A private note about the pilot that runs long: {LONG} [2] [personal].\n\n"
        "The pilot review with Fernhill is next week, see https://example.invalid/" + "a" * 160 + " [1].\n\n"
        "## Sources\n- [1] codex:fixture:1 — 2026-09-03\n- [2] codex:fixture:2 — 2026-09-04\n")


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem import tags
    from connectonion.rem.files import Notebook, state_path, write_json
    build(root, now)
    book = Notebook(root)
    book.write("knowledge/pilot-ledger.md", PAGE)
    # The tag page REM wrote for the tag (#3140): its prose heads the tag view, through the page's own markdown, so
    # its curtains, privacy tags and citations render there (the real page that scrolled sideways had all three).
    book.write("knowledge/pilot.md", PAGE.replace("# Pilot ledger", "# Fernhill pilot").replace("- Tags: pilot [1]\n\n", "")
               .replace("## Sources", "## Pages\n- [Pilot ledger](pilot-ledger.md)\n\n## Sources"))
    # A tagged person whose first open thread is a long, marked, cited line: the row's 等你处理 line is a flex row,
    # and the passage rides in it through inline(), with its curtain, privacy tag and citation spans.
    book.write("people/quill-ashdown.md", "# Quill Ashdown\n\n- Tags: pilot [1]\n\nWorks on the pilot with Fernhill [1].\n\n"
               "## Open threads\n"
               "- **Pilot budget** — Quill wrote “please send the final pilot budget figure with the "
               "breakdown by seat, the renewal discount, the support hours and the migration estimate before the "
               "board meets on Thursday so that we can sign the addendum in the same call” [1][2] [sensitive]; "
               "the user owes the answer since 2026-09-20.\n\n"
               "## Sources\n- [1] codex:fixture:1 — 2026-09-03\n- [2] codex:fixture:2 — 2026-09-04\n")
    for path in ("people/mara-ostrowski.md", "projects/harbour.md"):
        book.write(path, tags.with_tags(book.read(path), [{"tag": "pilot", "citation": ""}]))
    write_json(state_path(root, "tags.json"), {"tags": {"pilot": {"label": "Fernhill pilot", "kind": "project", "aliases": [],
                                                                  "page": "knowledge/pilot.md"}}})
    return root


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    html = rem_reader.render(_notebook(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc)), local=True)
    errors = []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            return route.fulfill(status=200, body="{}", content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE)
        page.locator("#main .count-line .count").wait_for()

        def open_view(hash_, width, level="cover"):
            page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
            page.evaluate("""([hash, level]) => { setInterfaceLanguage('zh');
                setPrivacy(level, { save: false, redraw: false });
                location.hash = hash; render(); }""", [hash_, level], isolated_context=False)
            page.locator("#main .hits li").first.wait_for()
            return page

        yield open_view
        browser.close()
    assert not errors, errors


WIDEST = """() => [...document.querySelectorAll('#main *')].filter(n => n.getBoundingClientRect().right > innerWidth + 1)
  .slice(0, 5).map(n => n.tagName.toLowerCase() + '.' + [...n.classList].join('.'))"""


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("hash_", ["#q=tag:pilot", "#q=pilot"])
def test_search_and_tag_views_never_scroll_sideways(reader, width, hash_):
    page = reader(hash_, width)
    scroll = page.evaluate("document.scrollingElement.scrollWidth")
    assert scroll <= width, f"{hash_} at {width}: page is {scroll}px wide; past the edge: {page.evaluate(WIDEST)}"
    if os.environ.get("REM_PR_SHOTS"):
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"after-{hash_.split('=')[1].replace(':', '-')}-{width}.png"), full_page=False)


@pytest.mark.parametrize("level", ["cover", "all", "public"])
def test_no_privacy_level_widens_the_tag_view(reader, level):
    page = reader("#q=tag:pilot", 390, level)
    assert page.evaluate("document.scrollingElement.scrollWidth") <= 390, page.evaluate(WIDEST)


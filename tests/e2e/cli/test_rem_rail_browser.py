"""The rail fills its height (#3091), in a real browser (opt in).

The owner: "Why isn't the left rail filled? You put a lot of things into More", and agent sessions are raw
data, so they go last. The rail is ONE ordered list; it shows as many places as its height holds and only the
overflow sits under More, which is gone when everything fits. The phone keeps its five tabs and its More sheet
lists every place in the same order with the same groups.

The notebook is the invented one in tests/fixtures/rem_reader_notebook.py, with a page added to every category
that only shows once it holds one.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

FROZEN = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
# #3152: the calendar is part of Today and has no place of its own.
ORDER = ["#", "#view=open", "#c=people", "#c=orgs", "#c=projects",
         "#c=knowledge", "#c=decisions", "#c=principles", "#c=skills",
         "#c=sessions", "#c=opportunities", "#c=works", "#view=changes"]
GROUP_STARTS = ["#c=people", "#c=knowledge", "#c=sessions"]
# name, matches, days since the last one, what it does
SKILLS = [("lark-im", 23, 2, "Send and read Lark messages."), ("lark-doc", 3, 30, "Read and edit Lark documents."),
          ("lark-base", 0, 0, "Work with Lark Base tables."), ("co-browser", 40, 5, "Drive one persistent browser."),
          ("co-mail", 5, 3, "Read and send mail."), ("co-env", 1, 100, "See and set keys in the env file.")]


def _notebook(tmp_path, full=True):
    from rem_reader_notebook import _skill, build
    from connectonion.rem.files import Notebook
    root = build(tmp_path / "rem", FROZEN)
    if not full:
        return root
    notebook, day = Notebook(root), lambda n: (FROZEN - timedelta(days=n)).date().isoformat()
    for name, count, last, what in SKILLS:
        notebook.write(f"skills/catalog/{name}.md", _skill(name, count, day(last), what, day(20)))
    for category in ("principles", "works", "opportunities", "sessions"):
        if not any((root / category).glob("*.md")):
            notebook.write(f"{category}/invented.md", f"# An invented {category} page\n\nOne line, so the place holds a page.\n")
    return root


def _open(tmp_path, monkeypatch, full=True):
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        return {**snapshot(root, local, today=today), "as_of": FROZEN.isoformat()}

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path = tmp_path / "reader.html"
    path.write_text(rem_reader.render(_notebook(tmp_path, full), local=True), encoding="utf-8")
    return path.as_uri()


@pytest.fixture
def browser():
    from patchright.sync_api import sync_playwright
    with sync_playwright() as api:
        chrome = api.chromium.launch(channel="chrome", headless=True)
        yield chrome
        chrome.close()


def _page(browser, uri, width, height, route="", phone=False):
    page = browser.new_page(viewport={"width": width, "height": height}, locale="en-US", is_mobile=phone, has_touch=phone)
    page.goto(uri + route)
    page.locator("#nav > a").first.wait_for(state="attached")
    return page


RAIL = """() => {
  const seen = n => n.getClientRects().length > 0, box = n => n.getBoundingClientRect();
  const cells = [...document.querySelectorAll('#nav > a.nav')].filter(seen), more = document.querySelector('.nav.more');
  const rail = document.querySelector('.rail'), settings = box(document.querySelector('.settings-open'));
  const column = [...cells, ...(seen(more) ? [more] : [])];
  return {places: cells.map(a => a.getAttribute('href')), more: seen(more),
    menu: [...document.querySelectorAll('#rail-more a')].map(a => a.getAttribute('href')),
    groups: cells.filter(a => a.classList.contains('group')).map(a => a.getAttribute('href')),
    inside: column.every(n => box(n).top >= 0 && box(n).bottom <= settings.top && Math.round(box(n).height) === 52 && box(n).width === 56),
    apart: column.every((n, i) => !i || box(column[i - 1]).bottom <= box(n).top),
    scrolls: rail.scrollHeight > rail.clientHeight, sideways: document.documentElement.scrollWidth > innerWidth,
    current: [...document.querySelectorAll('.rail [aria-current="page"]:not([hidden])')].map(a => a.getAttribute('href'))};
}"""


def test_a_tall_rail_shows_every_place_in_order_and_has_no_more(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 1440, 1200)
    rail = page.evaluate(RAIL)
    assert rail["places"] == ORDER and not rail["more"] and rail["menu"] == []
    assert rail["groups"] == GROUP_STARTS  # act | who and what | what the notebook concluded | raw material
    assert rail["inside"] and rail["apart"] and not rail["scrolls"] and not rail["sideways"]
    assert rail["current"] == ["#"]  # the active place is marked and named
    words = page.locator("#nav > a.nav .w").all_inner_texts()
    assert words == ["Today", "Waiting", "People", "Orgs", "Projects", "Knowledge", "Decisions", "Principles", "Skills",
                     "Sessions", "Opps", "Works", "Changes"]
    fits = page.locator("#nav > a.nav").evaluate_all("""cells => cells.every(cell => {
      const w = cell.querySelector('.w').getBoundingClientRect(), c = cell.getBoundingClientRect(); return w.left >= c.left && w.right <= c.right; })""")
    assert fits  # no word is wider than its cell
    assert page.locator('#nav a[href="#c=sessions"]').get_attribute("aria-label") == "Sessions · Agent sessions"


def test_the_keyboard_walks_the_rail_in_the_order_you_see(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 1440, 900)
    walked = []
    for _ in range(30):
        page.keyboard.press("Tab")
        stop = page.evaluate("""() => { const a = document.activeElement; if (!a.closest('.rail')) return null;
          return a.matches('.nav.more') ? 'more' : a.matches('.settings-open') ? 'settings' : a.matches('.nav.you') ? 'you' : a.getAttribute('href'); }""")
        if stop and stop not in walked:
            walked.append(stop)
    rail = page.evaluate(RAIL)
    assert [stop for stop in walked if stop in ORDER] == rail["places"]  # hidden places are not tab stops
    assert walked[-3:] == ["more", "settings", "you"] and walked.index("more") > walked.index(rail["places"][-1])


def test_at_900_the_rail_is_filled_and_only_the_overflow_is_under_more(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 1440, 900)
    rail = page.evaluate(RAIL)
    # With the calendar inside Today (#3152) one more place fits: Opportunities joins Sessions above the fold.
    assert rail["places"] == ORDER[:11] and rail["more"]  # nothing he uses is folded
    assert rail["menu"] == ORDER[11:]
    assert rail["inside"] and rail["apart"] and not rail["scrolls"]
    page.locator(".nav.more").click()
    menu = page.locator("#rail-more").bounding_box()
    assert menu["x"] >= 64 and menu["y"] >= 0 and menu["y"] + menu["height"] <= 900
    assert [text.strip() for text in page.locator("#rail-more a").all_inner_texts()] == ["Works", "Memory changes"]
    page.locator('#rail-more a[href="#view=changes"]').click()
    page.wait_for_function("location.hash === '#view=changes'")
    rail = page.evaluate(RAIL)
    assert rail["current"] == ["#view=changes"]  # named as the current page inside More
    assert "active" in page.locator(".nav.more").get_attribute("class")  # and More is the raised cell


def test_a_short_rail_folds_from_the_end_and_refits_when_the_window_grows(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 1280, 720, "#c=skills")
    rail = page.evaluate(RAIL)
    assert rail["places"] == ORDER[:8] and rail["more"] and rail["menu"] == ORDER[8:]
    assert rail["inside"] and rail["apart"] and not rail["scrolls"] and not rail["sideways"]
    assert rail["current"] == ["#c=skills"] and "active" in page.locator(".nav.more").get_attribute("class")
    page.set_viewport_size({"width": 1280, "height": 1200})
    page.wait_for_function("document.querySelector('.nav.more').getClientRects().length === 0")
    rail = page.evaluate(RAIL)
    assert rail["places"] == ORDER and rail["menu"] == [] and rail["current"] == ["#c=skills"]
    assert "active" in page.locator('#nav a[href="#c=skills"]').get_attribute("class")
    page.set_viewport_size({"width": 1280, "height": 420})
    page.wait_for_function("document.querySelector('.nav.more').getClientRects().length > 0")
    rail = page.evaluate(RAIL)
    assert rail["places"] == ORDER[:len(rail["places"])] and 0 < len(rail["places"]) < 8
    assert rail["inside"] and not rail["scrolls"]


def test_the_phone_more_sheet_lists_every_place_in_the_rails_order(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 390, 844, phone=True)
    assert [text.split()[-1] for text in page.locator("#tabbar .tab").all_inner_texts()] == ["Today", "Waiting", "People", "Search", "More"]
    page.locator(".nav-toggle").click()
    rail = page.evaluate(RAIL)
    assert rail["places"] == ORDER and not rail["more"] and rail["groups"] == GROUP_STARTS
    names = page.locator("#nav > a.nav").evaluate_all("cells => cells.map(a => getComputedStyle(a, '::after').content.replace(/\"/g, ''))")
    assert names == ["Today", "Waiting on you", "People", "Organisations", "Projects", "Knowledge", "Decisions", "Principles",
                     "Skills", "Agent sessions", "Opportunities", "Works", "Memory changes"]
    lines = page.locator("#nav > a.nav.group").evaluate_all("""cells => cells.map(a => { const s = getComputedStyle(a, '::before');
      return parseFloat(s.borderTopWidth) > 0 && parseFloat(s.width) > 200; })""")
    assert lines == [True] * 3  # the same three hairlines, the sheet's width
    assert page.locator(".settings-open").is_visible()
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")


def test_a_category_with_no_page_yet_is_not_a_place(browser, tmp_path, monkeypatch):
    """One rule (docs/cli/rem.md): the first eight and Memory changes always show; the later categories once they hold a page."""
    page = _page(browser, _open(tmp_path, monkeypatch, full=False), 1440, 1200)
    rail = page.evaluate(RAIL)
    assert "#c=principles" not in rail["places"] + rail["menu"] and "#c=works" not in rail["places"] + rail["menu"]
    assert rail["places"] == [place for place in ORDER if place in rail["places"]] and not rail["more"]
    assert {"#c=knowledge", "#c=skills", "#c=decisions", "#view=changes"} <= set(rail["places"]) and "#c=agenda" not in rail["places"]

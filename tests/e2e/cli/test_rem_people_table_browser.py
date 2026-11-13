"""People opens straight on the table (#2991, #2841), in a real browser (opt in).

The owner: «打开"人物"那边，还有"今天有 12 人等你"什么的，上来直接就是表格不好吗？
我不需要在那里面知道，因为"人物"那里已经是沉淀好的东西了。» People is a record of
whom he knows (D-30): the page is its title and the table, nothing in between, and on
a phone the same rows as cards. The invented notebook is tests/fixtures/rem_reader_notebook.py;
mail statistics are added in the page because the fixture has no owner mailbox.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

COLUMNS = ["Name", "Organisation", "Last contact", "Messages · 90 days", "Who wrote last", "Open items", "Page depth"]

# Invented mail statistics. Two-way order: Ines, Tomas, Mara, Quinn; Noor only ever wrote to the owner.
STATS = r'''() => {
  const stats = {
    'people/mara-ostrowski.md': {last_two_way: '2026-09-20T09:00:00+00:00', last_mail: '2026-09-30T09:00:00+00:00', messages_90d: 31, last_from_you: false},
    'people/tomas-reyes.md': {last_two_way: '2026-09-25T09:00:00+00:00', last_mail: '2026-09-25T09:00:00+00:00', messages_90d: 4, last_from_you: true},
    'people/ines-halvorsen.md': {last_two_way: '2026-09-28T09:00:00+00:00', last_mail: '2026-09-28T09:00:00+00:00', messages_90d: 9, last_from_you: true},
    'people/quinn-alder.md': {last_two_way: '2026-08-01T09:00:00+00:00', last_mail: '2026-09-15T09:00:00+00:00', messages_90d: 2, last_from_you: false},
    'people/noor-bakhtiar.md': {last_two_way: '', last_mail: '2026-09-29T09:00:00+00:00', messages_90d: 1, last_from_you: false}};
  for (const [path, s] of Object.entries(stats)) {
    const r = byPath(path);
    r.index = {...(r.index || {}), relationship: {weekly_messages: Array(52).fill(0), quiet: false, ...s}};
    FACTS.delete(path);
  }
  render();
}'''


def _reader_html(tmp_path, monkeypatch, extra=0):
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        data = snapshot(root, local, today=today)
        data["as_of"] = frozen.isoformat()
        example = next(r for r in data["records"] if r["title"] == "Mara Ostrowski")
        # A real-size roster: every invented correspondent with a long page, open threads and mail statistics.
        data["records"].extend({**example, "path": f"people/example-{i}.md", "title": f"Invented Correspondent {i:03d}",
                                "index": {**(example.get("index") or {}), "relationship": {
                                    "weekly_messages": [i % 5] * 52, "messages_90d": i % 40, "last_from_you": bool(i % 2),
                                    "last_two_way": f"2026-0{1 + i % 9}-1{i % 10}T09:00:00+00:00",
                                    "last_mail": f"2026-0{1 + i % 9}-2{i % 10}T09:00:00+00:00", "quiet": False}}}
                               for i in range(extra))
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path = tmp_path / "reader.html"
    path.write_text(rem_reader.render(build(tmp_path / "rem", frozen), local=True), encoding="utf-8")
    return path.as_uri()


@pytest.fixture
def browser():
    from patchright.sync_api import sync_playwright
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        yield browser
        browser.close()


def _open(browser, uri, width, locale="en-US"):
    page = browser.new_page(viewport={"width": width, "height": 1000 if width > 500 else 844}, locale=locale,
                            is_mobile=width < 500, has_touch=width < 500)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(uri + "#c=people")
    page.locator(".people-table tbody tr").first.wait_for()
    page.evaluate(STATS, isolated_context=False)
    return page, errors


def _names(page):
    return page.locator(".people-table tbody td.c-name a").all_inner_texts()


def test_people_opens_on_the_table_with_only_the_title_above_it(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    table = page.locator(".people-table")
    assert page.locator(".people-table thead th").all_inner_texts() == COLUMNS
    # Nothing between the page's name and the table: no count, no Today link, no filters, no lede.
    main = page.locator("#main").inner_text()
    assert main.split(COLUMNS[0])[0].split() == ["People", "Columns"]
    for word in ("waiting", "Waiting", "in Today", "owe", "Show all"):
        assert word not in main, word
    head = table.locator("thead").bounding_box()
    assert head["y"] < 160 and table.locator("tbody tr").nth(4).bounding_box()["y"] < 1000
    # Default order: the last time both sides wrote; someone who only writes in comes after.
    assert _names(page) == ["Inès Halvorsen", "Tomás Reyes", "Mara Ostrowski", "Quinn Alder", "Noor Bakhtiar"]
    mara = table.locator("tbody tr").filter(has_text="Mara Ostrowski")
    assert mara.locator("td.c-org").inner_text() == "Fernhill Labs"
    assert mara.locator("td.c-m90").inner_text() == "31"
    assert mara.locator("td.c-lastby").inner_text() == "Them"
    assert int(mara.locator("td.c-open").inner_text()) >= 1
    assert mara.locator("td.c-depth").inner_text() == "Investigated"
    assert table.locator("tbody tr").filter(has_text="Tomás Reyes").locator("td.c-lastby").inner_text() == "You"
    assert table.locator("tbody tr").filter(has_text="Quinn Alder").locator("td.c-depth").inner_text() == "Mapped"
    # The table fits 1440 and a row opens its page.
    assert page.locator(".people-scroll").evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    mara.locator("td.c-m90").click()
    page.get_by_role("heading", name="Mara Ostrowski", exact=True).wait_for()
    assert not errors, errors


def test_no_waiting_words_on_people_in_chinese(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440, locale="zh-CN")
    page.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
    main = page.locator("#main").inner_text()
    assert "等你" not in main and "今天" not in main
    assert main.split("姓名")[0].split() == ["人物", "列"]
    assert not errors, errors


def test_every_column_sorts_both_ways_and_the_choice_of_columns_is_kept(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    keys = ["name", "org", "last", "m90", "lastby", "open", "depth"]
    for key in keys:
        header = page.locator(f".people-table th.c-{key}")
        header.locator("button").click()
        first = header.get_attribute("aria-sort")
        assert first in ("ascending", "descending"), key
        order = _names(page)
        header.locator("button").click()
        assert header.get_attribute("aria-sort") != first, key
        assert _names(page) == list(reversed(order)) or key in ("org", "lastby", "open", "depth"), key
    page.locator(".people-table th.c-name button").click()
    if page.locator(".people-table th.c-name").get_attribute("aria-sort") != "ascending":
        page.locator(".people-table th.c-name button").click()
    assert _names(page) == sorted(_names(page), key=str.lower)
    page.locator(".people-table th.c-m90 button").click()
    counts = [int(text) for text in page.locator(".people-table tbody td.c-m90").all_inner_texts()]
    assert counts == sorted(counts, reverse=True)
    # The column choice lives in the existing co-rem-people-columns setting and survives a reload.
    page.get_by_role("button", name="Columns").click()
    page.get_by_role("checkbox", name="Messages · 90 days").uncheck()
    page.get_by_role("checkbox", name="Email").check()
    headers = page.locator(".people-table thead th").all_inner_texts()
    assert "Messages · 90 days" not in headers and "Email" in headers
    assert "m90" not in page.evaluate("localStorage.getItem('co-rem-people-columns')")
    page.reload()
    page.locator(".people-table tbody tr").first.wait_for()
    headers = page.locator(".people-table thead th").all_inner_texts()
    assert "Messages · 90 days" not in headers and "Email" in headers
    assert not errors, errors


def test_phone_shows_the_people_as_cards(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 390)
    assert not page.locator(".people-table thead").is_visible()
    row = page.locator(".people-table tbody tr").filter(has_text="Mara Ostrowski")
    assert row.evaluate("e => getComputedStyle(e).display") == "grid"
    card = row.inner_text()
    assert "Fernhill Labs" in card and "31" in card and "Them" in card
    assert row.bounding_box()["width"] <= 390 - 2 * 16 + 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    main = page.locator("#main").inner_text()
    assert "waiting" not in main.lower() and "in Today" not in main
    # Sorting on the phone: the same columns, from one control beside the title.
    page.get_by_role("combobox", name="Sort by").select_option("name")
    assert _names(page) == sorted(_names(page), key=str.lower)
    assert not errors, errors


def test_a_real_size_roster_renders_in_under_a_second(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch, extra=150), 1440)
    timings = []
    for _ in range(3):
        timings.append(page.evaluate(r'''() => new Promise(done => {
          location.hash = ''; setTimeout(() => {
            const start = performance.now(); location.hash = 'c=people';
            const tick = () => document.querySelectorAll('.people-table tbody tr').length > 150
              ? done(performance.now() - start) : requestAnimationFrame(tick);
            tick();
          }, 200);
        })''', isolated_context=False))
    assert page.locator(".people-table tbody tr").count() == 155
    assert min(timings) < 1000, timings
    assert not errors, errors

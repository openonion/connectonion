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


def _headers(page):
    return [text.replace("↕", "").replace("↑", "").replace("↓", "").strip() for text in page.locator(".people-table thead th").all_inner_texts()]


def _names(page):
    return page.locator(".people-table tbody td.c-name a").all_inner_texts()


def test_people_opens_on_the_table_with_only_the_title_above_it(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    table = page.locator(".people-table")
    assert _headers(page) == COLUMNS
    # The default sort is the visible Last contact column, newest first, and says so with its arrow.
    assert page.locator(".people-table th.c-last").get_attribute("aria-sort") == "descending"
    assert page.locator(".people-table th.c-last").inner_text().endswith("↓")
    assert page.locator(".people-table th.c-name").inner_text().endswith("↕")
    # Nothing between the page's name and the table: no count, no Today link, no filters, no lede.
    main = page.locator("#main").inner_text()
    assert main.split(COLUMNS[0])[0].split() == ["People", "Columns"]
    for word in ("waiting on you", "Waiting", "in Today", "owe", "Show all"):
        assert word not in main, word
    head = table.locator("thead").bounding_box()
    assert head["y"] < 160 and table.locator("tbody tr").nth(4).bounding_box()["y"] < 1000
    assert _names(page) == ["Mara Ostrowski", "Noor Bakhtiar", "Inès Halvorsen", "Tomás Reyes", "Quinn Alder"]
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


MONOTONIC = r"""key => {
  const col = PEOPLE_COLUMNS.find(c => c.key === key);
  const desc = document.querySelector('.people-table th.c-' + key).getAttribute('aria-sort') === 'descending';
  const collator = new Intl.Collator('en', {numeric: true, sensitivity: 'base'});
  const keys = [...document.querySelectorAll('.people-table tbody tr')].map(tr =>
    col.sort(peopleRow(byPath(decodeURIComponent(tr.dataset.href.slice(3))))));
  const firstBlank = keys.indexOf(null);
  if (firstBlank >= 0 && keys.slice(firstBlank).some(k => k !== null)) return 'blank before a value';
  const values = keys.filter(k => k !== null);
  for (let i = 1; i < values.length; i++) {
    const order = typeof values[i] === 'string' ? collator.compare(values[i - 1], values[i]) : values[i - 1] - values[i];
    if (desc ? order < 0 : order > 0) return 'out of order at ' + i;
  }
  return 'ok';
}"""


def test_every_column_sorts_both_ways_with_blanks_last(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    page.evaluate("() => { peopleColumns = peopleColumnKeys('more'); render(); }", isolated_context=False)
    keys = page.evaluate("PEOPLE_COLUMNS.map(c => c.key)", isolated_context=False)
    assert len(keys) == 15
    for key in keys:
        header = page.locator(f".people-table th.c-{key}")
        for _ in range(2):
            header.locator("button").click()
            assert page.evaluate(MONOTONIC, key, isolated_context=False) == "ok", (key, header.get_attribute("aria-sort"))
        assert header.get_attribute("aria-sort") in ("ascending", "descending")
    page.locator(".people-table th.c-name button").click()
    if page.locator(".people-table th.c-name").get_attribute("aria-sort") != "ascending":
        page.locator(".people-table th.c-name button").click()
    assert _names(page) == sorted(_names(page), key=str.lower)
    assert not errors, errors


def test_chinese_names_sort_in_pinyin_order(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    page.evaluate("""() => {
      const titles = {'people/mara-ostrowski.md': '张伟', 'people/tomas-reyes.md': '李娜', 'people/ines-halvorsen.md': '王芳'};
      for (const [path, title] of Object.entries(titles)) byPath(path).title = title;
      setInterfaceLanguage('zh');
    }""", isolated_context=False)
    page.locator(".people-table th.c-name button").click()
    if page.locator(".people-table th.c-name").get_attribute("aria-sort") != "ascending":
        page.locator(".people-table th.c-name button").click()
    chinese = [name for name in _names(page) if not name.isascii()]
    assert chinese == ["李娜", "王芳", "张伟"]  # li, wang, zhang
    assert not errors, errors


def test_the_choice_of_columns_is_kept_and_reads_the_older_setting(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    page.get_by_role("button", name="Columns").click()
    page.get_by_role("checkbox", name="Messages · 90 days").uncheck()
    page.get_by_role("checkbox", name="Email").check()
    headers = _headers(page)
    assert "Messages · 90 days" not in headers and "Email" in headers
    assert "m90" not in page.evaluate("localStorage.getItem('co-rem-people-columns')")
    page.reload()
    page.locator(".people-table tbody tr").first.wait_for()
    headers = _headers(page)
    assert "Messages · 90 days" not in headers and "Email" in headers
    # The setting's older values: "more" was every column, "less" the default ones.
    for saved, count in (("more", 15), ("less", 7)):
        page.evaluate("saved => localStorage.setItem('co-rem-people-columns', saved)", saved)
        page.reload()
        page.locator(".people-table tbody tr").first.wait_for()
        assert len(_headers(page)) == count, saved
    assert not errors, errors


def test_the_filter_beside_the_title_narrows_and_enter_opens_the_first_match(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    find = page.locator(".people-head .people-find")
    assert abs(find.bounding_box()["y"] - page.locator(".people-head h1").bounding_box()["y"]) < 40
    find.fill("ledgerline")
    assert _names(page) == ["Inès Halvorsen"]
    find.fill("no-such-invented-person")
    assert page.locator(".empty .lead").inner_text() == "No matching pages"
    page.locator(".empty a").click()
    assert len(_names(page)) == 5
    find.fill("mara")
    find.press("Enter")
    page.get_by_role("heading", name="Mara Ostrowski", exact=True).wait_for()
    assert not errors, errors


def test_open_items_follow_today_and_the_footer_counts_who_is_left_out(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    mara = lambda: int(page.locator(".people-table tbody tr").filter(has_text="Mara Ostrowski").locator("td.c-open").inner_text())
    before = mara()
    assert before >= 1
    # An item marked done in Today leaves this count too.
    page.evaluate("""() => {
      const live = personEntries(byPath('people/mara-ostrowski.md')).find(e => !isDone(e) && !looksDone(e) && !e.t.quiet
        && (e.t.dir === 'mine' ? waitingOnYou(e) : !answered(e) && !staleEntry(e)));
      threadStates[doneKey(live)] = {state: 'done'}; render();
    }""", isolated_context=False)
    assert mara() == before - 1
    # A thread gone quiet (over 60 days, no due date) is not in Today, so it is not counted here.
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      for (const key of ['text', 'original']) if (r[key]) r[key] = r[key].replace('## Open threads\n', '## Open threads\n- You owe Mara the archived budget file, requested 2026-05-01.\n');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    assert mara() == before - 1
    foot = page.locator(".r4-people .r4-foot .held-note")
    assert foot.count() <= 1
    assert page.locator(".r4-people .r4-foot").bounding_box()["y"] > page.locator(".people-scroll").bounding_box()["y"]
    assert not errors, errors


def test_people_without_pages_say_so(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch), 1440)
    page.evaluate("() => { REM.records = REM.records.filter(r => r.category !== 'people' || r.path === REM.owner); REM.contact_candidates = []; render(); }", isolated_context=False)
    assert page.locator(".r4-people .empty .lead").inner_text() == "No contacts yet"
    assert page.locator(".people-table tbody tr").count() == 0
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
    assert page.get_by_role("combobox", name="Sort by").input_value() == "last"
    page.get_by_role("combobox", name="Sort by").select_option("name")
    assert _names(page) == sorted(_names(page), key=str.lower)
    assert not errors, errors


def test_a_thousand_people_sorted_by_open_items_render_in_under_a_second(tmp_path, monkeypatch, browser):
    page, errors = _open(browser, _reader_html(tmp_path, monkeypatch, extra=1000), 1440)
    page.evaluate("() => { PEOPLE_SORT.sort = 'open'; PEOPLE_SORT.desc = true; }", isolated_context=False)
    timings = []
    for _ in range(3):
        timings.append(page.evaluate(r"""() => new Promise(done => {
          location.hash = ''; setTimeout(() => {
            const start = performance.now(); location.hash = 'c=people';
            const tick = () => document.querySelectorAll('.people-table tbody tr').length > 1000
              ? done(performance.now() - start) : requestAnimationFrame(tick);
            tick();
          }, 200);
        })""", isolated_context=False))
    assert page.locator(".people-table tbody tr").count() == 1005
    assert page.locator(".people-table th.c-open").get_attribute("aria-sort") == "descending"
    assert min(timings) < 1000, timings
    assert not errors, errors

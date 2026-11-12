"""The redesigned reader on a realistic notebook, in a real browser (opt in).

The fixture (tests/fixtures/rem_reader_notebook.py) is invented but shaped like
real pages: cited leads, Contact fields, open threads in both directions, a
dated History, numbered Sources, an ASCII Overview, a skill's usage, a week of
run logs. Each view is checked for what a returning reader came for, and every
view must fit a phone without sideways scrolling, in both themes.
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

VIEWS = ["", "#c=people", "#c=orgs", "#c=projects", "#c=skills", "#r=people%2Fmara-ostrowski.md",
         "#r=people%2Fquinn-alder.md", "#r=projects%2Fharbour.md", "#r=orgs%2Ffernhill-labs.md",
         "#r=skills%2Fcatalog%2Fweekly-brief.md", "#q=pilot", "#q=mara", "#r=people%2Favery-lin.md", "#c=opportunities", "#reviews=1",
         "#view=activity"]


def test_private_mapped_project_explains_why_it_waits_on_desktop_and_phone(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import render

    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_project("projects/journal.md", "Journal", ["/work/journal"])
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    path.write_text(render(root))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        for width in (1440, 375):
            page = browser.new_page(viewport={"width": width, "height": 812}, locale="en-US")
            page.goto(path.as_uri() + "#r=projects%2Fjournal.md")
            statement = page.locator(".focus-statement").inner_text()
            assert "Automatic investigations skip this private project." in statement
            assert "Ask for one on this page." in statement
            assert "clamped" not in page.locator(".focus-statement").get_attribute("class")
            assert "/work/journal" not in statement
            assert "Needs your explicit request" in page.locator(".focus-kicker").inner_text()
            assert "This private project waits for your request." in page.locator(".missing").inner_text()
            # Primary reading surfaces no longer expose terminal commands.
            assert page.locator(".missing .cmd").count() == 0
            if width < 720:
                page.locator(".nav-toggle").click()
            page.locator(".settings-open").click()
            assert page.locator(".reader-settings .cmd, .reader-settings code").count() == 0  # D-60 (build 3b review): Reader settings states things in words, never a command to copy.
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.close()
        browser.close()


def test_mapped_project_hero_says_it_waits_instead_of_showing_its_folder(tmp_path, monkeypatch):
    """#2349: LayeredVisions, the busiest project, had not been written yet,
    and its hero read "WHERE THE WORK STANDS /Users/.../LayeredVisions"."""
    from patchright.sync_api import sync_playwright
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import render

    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_project("projects/browser.md", "browser", ["/work/browser"])
    page_text = notebook.read("projects/browser.md").replace(
        "- /work/browser", "- /work/browser\n- Sessions: 13\n- First seen: 2026-08-01\n- Last seen: 2026-08-02")
    notebook.write("projects/browser.md", page_text)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    path.write_text(render(root))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        for width in (1440, 375):
            page = browser.new_page(viewport={"width": width, "height": 812}, locale="en-US")
            page.goto(path.as_uri() + "#r=projects%2Fbrowser.md")
            statement = page.locator(".focus-statement").inner_text()
            assert "/work/browser" not in statement
            assert statement == "Not written yet: 13 sessions, last on Aug 2."
            assert "Where the work stands" not in page.locator(".focus-kicker").inner_text()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.close()
        browser.close()


def test_mobile_record_keeps_freshness_and_primary_navigation_in_reach(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    assert page.locator('h1').bounding_box()['y'] <= 140
    assert page.locator('#mobile-status').count() == 0
    for selector in ('#tabbar .tab-search', '.nav-toggle'):
        assert page.locator(selector).bounding_box()['height'] >= 44
    assert page.locator('#crumb a').first.is_visible()  # People, in the top bar
    assert page.get_by_role('heading', name='Full memory and sources').is_visible()
    assert page.locator('details.deep-note').get_attribute('open') is None
    page.locator('details.deep-note > summary').click()
    assert page.locator('.deep-note .note').is_visible()
    assert page.locator('.deep-note .note').bounding_box()['y'] < page.locator('.deep-note .side').bounding_box()['y']
    page.locator('.nav-toggle').click()
    page.locator('.settings-open').click()
    assert 'Updated ' in page.locator('#foot').inner_text()  # the render time (2026-11-09; was "Snapshot")
    assert 'Nightly updates are off.' in page.locator('.reader-settings').inner_text()  # D-60 (build 3b review): Reader settings states things in words, never a command to copy.
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.reload()
    page.locator('.settings-open').click()
    assert 'Nightly updates are off.' in page.locator('#foot').inner_text()  # D-60: words, no command
    assert 'Not started' not in page.locator('#foot').inner_text()
    assert '`' not in page.locator('#foot').inner_text()


def test_short_desktop_rail_keeps_every_place_and_the_settings_in_reach(reader):
    """D-132: a 72px rail of pictures with their words under them. Its content is 656 tall: a window that tall
    shows all of it, and in a lower one the rail itself scrolls, so every place, 更多, settings and you stay in reach."""
    page, uri = reader
    page.set_viewport_size({'width': 960, 'height': 700})
    page.goto(uri)
    boxes = "nodes => nodes.map(n => { const b = n.getBoundingClientRect(); return [b.top, b.bottom, b.width]; })"
    tall = page.locator('.rail .nav').evaluate_all(boxes)
    assert len(tall) == 10 and all(top >= 0 and bottom <= 700 and width == 56 for top, bottom, width in tall)
    assert all(a[1] <= b[0] for a, b in zip(tall, tall[1:])), tall
    assert page.locator('.rail').evaluate('rail => [rail.scrollHeight, rail.clientHeight, rail.getBoundingClientRect().width]') == [700, 700, 72]
    page.set_viewport_size({'width': 960, 'height': 540})
    assert page.locator('.rail').evaluate('rail => [rail.scrollHeight, rail.clientHeight, rail.getBoundingClientRect().width]') == [656, 540, 72]
    short = page.locator('.rail .nav').evaluate_all(boxes)
    assert [round(bottom - top) for top, bottom, _ in short] == [round(bottom - top) for top, bottom, _ in tall]  # none squeezed
    assert all(a[1] <= b[0] for a, b in zip(short, short[1:])), short
    reached = page.locator('.rail .nav').evaluate_all("""nodes => nodes.map(n => { n.scrollIntoView({block: 'nearest'});
      const b = n.getBoundingClientRect(); return b.top >= 0 && b.bottom <= innerHeight; })""")
    assert reached == [True] * 10
    assert page.evaluate('scrollY') == 0  # the rail scrolled, not the page
    # Each place is named under its picture without a hover; the full name is the link's accessible name.
    people = page.locator('#nav a[href="#c=people"]')
    assert people.get_attribute('aria-label') == 'People' and people.locator('.w').inner_text() == 'People'
    assert page.locator('.rail .tip').count() == 0
    words = page.locator('.rail .nav .w').evaluate_all("""words => words.map(w => { const s = getComputedStyle(w), b = w.getBoundingClientRect(),
      cell = w.parentElement.getBoundingClientRect(), picture = w.parentElement.querySelector('.ic').getBoundingClientRect();
      return {word: w.textContent, shown: s.opacity === '1' && s.visibility === 'visible', size: s.fontSize, height: b.height,
        inside: b.left >= cell.left && b.right <= cell.right && b.bottom <= cell.bottom, under: b.top >= picture.bottom}; })""")
    assert [w['word'] for w in words] == ['Today', 'Waiting', 'People', 'Orgs', 'Projects', 'Skills', 'All', 'More', 'Settings']
    assert all(w['shown'] and w['size'] == '11px' and w['height'] == 14 and w['inside'] and w['under'] for w in words), words
    page.locator('.nav.more').click()
    assert page.locator('#rail-more a[href="#view=changes"]').is_visible()
    menu = page.locator('#rail-more').bounding_box()
    assert menu['x'] >= 64 and menu['y'] >= 0 and menu['y'] + menu['height'] <= 540  # beside the rail, none of it cut off
    page.mouse.click(600, 300)
    assert not page.locator('#rail-more').is_visible()
    page.locator('.settings-open').click()
    assert page.locator('#settings').evaluate('d => d.open') and 'Updated ' in page.locator('#foot').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_mobile_browse_privacy_control_remains_a_full_touch_target(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.locator('.nav-toggle').click()
    page.locator('.settings-open').click()
    page.locator('#privacy-toggle').scroll_into_view_if_needed()
    privacy = page.get_by_role('switch', name='Hide labelled passages')
    box = privacy.bounding_box()
    assert box['height'] >= 44 and box['width'] >= 44
    assert box['y'] >= 0 and box['y'] + box['height'] <= 812
    privacy.focus()
    privacy.press('Enter')
    shown = page.get_by_role('switch', name='Show labelled passages')
    assert shown.get_attribute('aria-checked') == 'true' and shown.get_attribute('aria-pressed') is None  # a switch is checked, not pressed
    assert shown.evaluate('(node) => node === document.activeElement')
    shown.press('Space')
    assert privacy.get_attribute('aria-checked') == 'false'
    assert privacy.evaluate('(node) => node === document.activeElement')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    # Freeze the invented notebook so an age near a timezone day boundary is stable.
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        data = snapshot(root, local, today=today)
        data["as_of"] = frozen.isoformat()
        from connectonion.rem.today import queue
        data['today_queue'] = queue(root, records=data['records'], contexts=data['source_context'], states=data['threads'], as_of=frozen.date())
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path.write_text(rem_reader.render(build(tmp_path / "rem", frozen), local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        # English date literals in this fixture must not depend on Chrome's OS locale.
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="en-US")
        from connectonion.rem.today import queue
        page.expose_function('projectToday', lambda payload: queue(Path(payload['root']), records=payload['records'],
                             contexts=payload['source_context'], states=payload.get('threads', {}),
                             as_of=datetime.fromisoformat(payload['as_of']).date()))
        page.add_init_script("""window.refreshTodayQueue = async () => {
          REM.today_queue = await projectToday({root: REM.root, as_of: REM.as_of, threads: REM.threads,
            records: REM.records.map(r => ({...r, text: r.shown ? r.original ?? r.text : r.text})), source_context: REM.source_context});
          threadEntries.cached = null;
        };""")
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        page.locator(".night-card .count").wait_for()
        yield page, path.as_uri()
        browser.close()
        assert not errors, errors
        assert not requests, requests


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_org_display_name_keeps_domain_secondary_and_in_table(reader, width, theme):
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 844})
    page.emulate_media(color_scheme=theme)
    page.goto(uri + '#r=orgs%2Ffernhill-labs.md')
    page.evaluate(r"""() => {
      const r = byPath('orgs/fernhill-labs.md');
      r.title = 'ConnectOnion'; r.domain = 'connectonion.com';
      r.text = r.text.replace(/^# .*/, '# connectonion.com')
        .replace(/^## Domains\n[\s\S]*?(?=^## |(?![\s\S]))/m, '');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    # The name heads the record; the domain follows it in the facts line, smaller.
    assert _name(page.locator('.ov-say .ov-name')) == 'ConnectOnion'
    domain = page.locator('.ov-say .ov-domain')
    assert domain.inner_text() == 'connectonion.com'
    assert domain.is_visible()
    assert domain.bounding_box()['y'] >= page.locator('.ov-say .ov-name').bounding_box()['y']
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.goto(uri + '#c=orgs')
    row = page.locator('.ov-row').filter(has_text='ConnectOnion')
    assert row.locator('.ov-domain').inner_text() == 'connectonion.com'
    assert row.locator('.ov-domain').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1400, 390])
def test_night_hypnogram_clusters_dense_runs(reader, width):
    page, _ = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.evaluate("""() => {
      const start = new Date(REM.as_of).getTime() - 4 * HOUR;
      REM.logs = Array.from({length: 22}, (_, n) => {
        const at = start + (n < 20 ? n * 90e3 : HOUR + (n - 20) * 90e3);
        return {started_at: new Date(at).toISOString(), finished_at: new Date(at + 60e3).toISOString(),
          items: 3, changed: ['people/mara-ostrowski.md'], outcome: n === 4 || n === 12 ? 'failed' : 'completed'};
      }).reverse();
      render();
    }""", isolated_context=False)
    page.locator('.night-details summary').click()
    band = page.locator('.night-details .night')
    hypno = band.locator('.hypno')
    assert hypno.locator('.dot.changed').count() == 2
    assert hypno.locator('.dot.woke').count() == 1
    assert hypno.locator('.dot.dawn').count() == 1
    assert re.fullmatch(r'\d{2}:\d{2}–\d{2}:\d{2} · 20 runs · 20 pages changed',
                        hypno.locator('.dot.changed').first.get_attribute('title'))
    assert '2 runs stopped early' in hypno.locator('.dot.woke').get_attribute('title')
    assert '22 runs in 2 stretches' in hypno.get_attribute('aria-label')
    assert hypno.locator('.trace').get_attribute('d').count(' L') == 9  # Four edges per dip, then the baseline.
    dots = [dot.bounding_box() for dot in hypno.locator('.dot').all()]
    for n, a in enumerate(dots):
        for b in dots[n + 1:]:
            assert (a['x'] + a['width'] <= b['x'] or b['x'] + b['width'] <= a['x'] or
                    a['y'] + a['height'] <= b['y'] or b['y'] + b['height'] <= a['y'])
    labels = [label.bounding_box() for label in hypno.locator('.day').all()]
    assert all(a['x'] + a['width'] <= b['x'] for a, b in zip(labels, labels[1:]))
    stages = band.locator('.stages')
    assert 'Read 66 items' in stages.inner_text()
    assert '22 runs' in stages.inner_text()
    assert '2 stopped early' in stages.inner_text()
    assert stages.locator('.stat').count() == 4
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_home_opens_on_what_to_remember_and_what_is_owed(reader):
    page, _ = reader
    # Sprint 14: the display number is the sidebar's (items waiting on you); the people are a subset, in words.
    total = page.locator('#nav .n.waiting').inner_text()
    whos = page.locator('.today-brief .today-who').all_inner_texts()
    assert whos == ['Inès Halvorsen', 'Mara Ostrowski', 'Fernhill Labs', 'Harbour']
    assert int(total) > 0 and page.locator('.night-card .count').text_content() == total
    assert page.locator('.night-card .count-words').text_content() == 'things waiting on you'
    assert page.locator('.night-card .count-of').text_content() == f'Start with these {len(whos)} people'
    assert page.locator('.qcard').first.locator('.qage').inner_text() == '12 days · due Oct 3'
    assert 'Data-sharing addendum' in page.locator('.qcard[data-path="people/mara-ostrowski.md"] .words').first.inner_text()
    changes = page.locator('.overnight .overnight-change')
    assert changes.count() == 1
    assert 'Head of Partnerships' in changes.inner_text()
    assert changes.get_by_role('link', name='source', exact=True).get_attribute('href').endswith('h=src-2')
    page.locator('.week-details summary').click()
    assert set(page.locator('.week a').all_inner_texts()) >= {'Mara Ostrowski', 'Harbour', 'Fernhill Labs'}
    assert page.locator(".recall").count() == 0  # sprint 14: no "what should you remember" card without a reason
    assert page.locator(".night-details").count() == 1
    page.locator(".night-details summary").click()
    night = page.locator(".night-details .night")
    assert "46 items" in night.inner_text() and "4 pages" in night.inner_text()
    assert night.locator(".hypno .dot.changed").count() == 1
    assert night.locator('.hypno .dot.dawn').count() == 1
    assert set(night.locator(".changes a").all_inner_texts()) == {"Mara Ostrowski", "Harbour", "Fernhill Labs", "Avery Lin"}  # runs, and stamps of the night
    # The full ledger keeps both directions, yours first.
    page.locator('.others .waiting-more').click()
    bands = page.locator(".task-band")
    bands.first.wait_for()
    headings = bands.locator("h2 > span:first-child").all_inner_texts()
    order = ["Waiting on you", "Waiting on others", "Other open context"]
    assert headings[:2] == order[:2]
    assert headings == sorted(headings, key=order.index)
    for band in bands.all():
        assert band.locator("ul.threads > li").count() > 0


def test_people_open_as_a_sheet_that_sorts_filters_and_opens_a_row(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
    page.get_by_role("button", name="More columns", exact=True).click()
    sheet = page.locator("table.sheet")
    # a409b633: the owner has a separate You page, outside People.
    assert sheet.locator("tbody tr[data-href]").count() == 5
    assert not any("Avery Lin" in text for text in sheet.locator("tbody .name").all_inner_texts())
    assert "mara@fernhill.example" in sheet.inner_text()
    page.get_by_role("button", name="Yours to answer").click()
    assert sheet.locator("tbody .name a").all_inner_texts() == ["Mara Ostrowski", "Inès Halvorsen"]
    page.get_by_role("button", name="All").click()
    sheet.locator("th", has_text="Mails").locator("button").click()
    assert sheet.locator("tbody .name a").first.inner_text() == "Mara Ostrowski"
    assert sheet.locator("th", has_text="Mails").get_attribute("aria-sort") == "descending"
    page.locator(".sheet-find").fill("ledgerline")
    assert sheet.locator("tbody .name a").all_inner_texts() == ["Inès Halvorsen"]
    sheet.locator("tbody tr").first.locator("td.c-last").click()
    page.get_by_role("heading", name="Inès Halvorsen", exact=True).wait_for()


def test_older_single_mail_contacts_are_findable_without_empty_memory_pages(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    page.locator(".contact-directory summary").click()
    directory = page.locator(".contact-directory")
    assert "3 other contacts" in directory.locator("summary").inner_text()
    assert "all available history" in directory.inner_text()
    directory.get_by_role("searchbox", name="Search other contacts").fill("Leah Bell")
    assert directory.locator("tbody tr").count() == 1
    assert "leah@old-friends.example" in directory.locator("tbody").inner_text()
    assert directory.locator("tbody td").last.inner_text()
    assert directory.locator('a[href="mailto:leah@old-friends.example"]').is_visible()
    assert directory.locator(".directory-action").count() == 0
    page.set_viewport_size({"width": 390, "height": 844})
    assert directory.locator("tbody tr").first.evaluate(
        "row => getComputedStyle(row).display === 'grid'")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_the_people_sheet_fits_1440_and_says_when_it_is_cut(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
    scroller = page.locator(".sheet-scroll")
    # The default columns fit at 1440, including what is open.
    assert scroller.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    assert page.locator("th.c-open").evaluate("e => e.getBoundingClientRect().right <= innerWidth")
    assert "clip-right" not in page.locator(".sheet-box").get_attribute("class")
    page.get_by_role("button", name="More columns", exact=True).click()
    # Narrower, the expanded sheet scrolls inside itself; the name stays put.
    page.set_viewport_size({"width": 900, "height": 900})
    page.wait_for_function("document.querySelector('.sheet-box').classList.contains('clip-right')")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    scroller.evaluate("e => { e.scrollLeft = e.scrollWidth; }")
    page.wait_for_function("!document.querySelector('.sheet-box').classList.contains('clip-right')")
    assert page.locator("td.name").first.evaluate("e => e.getBoundingClientRect().left") >= scroller.evaluate("e => e.getBoundingClientRect().left") - 1


def test_people_desktop_contact_previews_and_adjacent_text_do_not_overlap(reader):
    page, uri = reader
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.goto(uri + '#c=people')
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
    page.get_by_role('button', name='More columns', exact=True).click()
    page.evaluate(r'''() => {
      const r = byPath('people/mara-ostrowski.md');
      r.index = {...r.index,
        emails: ['marcus_jian.vale.partnerships@a-much-longer-department-domain.example', 'second@example.test', 'third@example.test'],
        phone: '+61 0491570157 (mobile partnerships desk after hours); +61 0491570158 (work)'};
      // Exercise index-backed previews without explicit notebook contact values.
      r.text = (r.original || r.text).replace(/^- (?:Email|Phone):.*\n/gm, '');
      r.original = r.text;
      FACTS.delete(r.path); render();
    }''', isolated_context=False)
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")
    row = page.locator('.sheet tbody tr').filter(has_text='Mara Ostrowski')
    for kind, first, count, title in [
        ('email', 'marcus_jian.vale.partnerships@a-much-longer-department-domain.example', '+2',
         'marcus_jian.vale.partnerships@a-much-longer-department-domain.example; second@example.test; third@example.test'),
        ('phone', '+61 0491570157 (mobile partnerships desk after hours)', '+1',
         '+61 0491570157 (mobile partnerships desk after hours); +61 0491570158 (work)'),
    ]:
        cell = row.locator('.c-' + kind)
        assert cell.locator('.' + kind + '-first').inner_text() == first
        assert cell.locator('.' + kind + '-more').inner_text() == count
        assert cell.locator('.people-' + kind + 's').get_attribute('title') == title
        assert cell.locator('.contact-first').evaluate('''node => {
          const style = getComputedStyle(node);
          return style.textOverflow === 'ellipsis' && style.overflowX === 'hidden'
            && style.whiteSpace === 'nowrap' && node.scrollWidth > node.clientWidth;
        }''')
    # Range reports even text hidden by ellipsis. Intersect with actual clipping
    # ancestors so this compares painted text, without concealing visible overflow.
    overlaps = page.locator('.sheet tbody').evaluate('''body => {
      const textBounds = cell => {
        const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT), boxes = [];
        while (walker.nextNode()) {
          const text = walker.currentNode;
          if (!text.textContent.trim() || !text.parentElement.checkVisibility()) continue;
          const range = document.createRange(); range.selectNodeContents(text);
          const rect = range.getBoundingClientRect();
          let left = rect.left, right = rect.right;
          for (let node = text.parentElement; node && node !== cell; node = node.parentElement) {
            if (getComputedStyle(node).overflowX !== 'visible') {
              const clip = node.getBoundingClientRect();
              left = Math.max(left, clip.left); right = Math.min(right, clip.right);
            }
          }
          if (right > left && rect.height) boxes.push({left, right});
        }
        return boxes.length ? {left: Math.min(...boxes.map(b => b.left)), right: Math.max(...boxes.map(b => b.right))} : null;
      };
      return [...body.rows].flatMap(row => {
        const cells = [...row.cells], bounds = cells.map(textBounds);
        return bounds.flatMap((box, i) => {
          if (!box) return [];
          const cell = cells[i].getBoundingClientRect(), next = bounds[i + 1];
          return box.left < cell.left - 0.5 || box.right > cell.right + 0.5
            || (next && box.right > next.left + 0.5)
            ? [row.cells[0].innerText + ': ' + cells[i].className] : [];
        });
      });
    }''')
    assert overlaps == []
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [375, 390])
def test_people_mobile_phone_preview_wraps_with_its_label(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#c=people')
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
    page.evaluate(r'''() => {
      const r = byPath('people/mara-ostrowski.md');
      r.index = {...r.index, phone: '+61 0491570157 (mobile partnerships desk after hours); +61 0491570158 (work)'};
      r.text = (r.original || r.text).replace(/^- Phone:.*\n/gm, '');
      r.original = r.text;
      FACTS.delete(r.path); render();
    }''', isolated_context=False)
    phone = page.locator('.sheet tbody tr').filter(has_text='Mara Ostrowski').locator('.c-phone')
    assert phone.is_visible()
    assert phone.locator('.phone-more').inner_text() == '+1'
    assert phone.evaluate('''cell => {
      const preview = cell.querySelector('.phone-first'), values = cell.querySelector('.people-phones');
      const range = document.createRange(); range.selectNodeContents(preview);
      return getComputedStyle(values).display === 'inline'
        && getComputedStyle(preview).whiteSpace === 'normal'
        && Math.abs(range.getBoundingClientRect().top - cell.getBoundingClientRect().top)
          < parseFloat(getComputedStyle(cell).lineHeight);
    }''')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize("width", [375, 390])
def test_people_phone_cards_keep_contact_metadata_and_sorting(reader, width):
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(uri + "#c=people")
    page.evaluate(r'''() => {
      const r = byPath('people/mara-ostrowski.md');
      r.index = {...r.index, emails: ['long-address'.repeat(20) + '@fernhill.example', 'second@fernhill.example', 'third@fernhill.example']};
      r.text = (r.original || r.text).replace(/^- Email:.*\n/gm, '');
      r.original = r.text;
      FACTS.delete(r.path); render();
    }''', isolated_context=False)
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")
    row = page.locator('.sheet tbody tr').filter(has_text='Mara Ostrowski')
    assert row.locator('.name .nm a').is_visible()
    assert row.locator('.email-first').is_visible()
    assert row.locator('.email-more').inner_text() == '+2'
    assert row.locator('.people-emails a').count() == 1
    assert row.locator('.name .sum').is_visible()
    assert 'Fernhill' in row.locator('.people-card-meta').inner_text()
    assert row.locator('.name a').all_inner_texts() == ['Mara Ostrowski']
    meta = row.locator('.people-card-meta')
    assert meta.get_attribute('title') == meta.inner_text()
    assert meta.evaluate("e => getComputedStyle(e).webkitLineClamp") == '2'
    assert meta.evaluate("e => getComputedStyle(e).marginTop") == '14px'
    assert row.locator('.c-email').evaluate(r'''e => {
      const label = getComputedStyle(e, '::before');
      return !label.content.includes(':') && label.fontSize === '11px'
        && getComputedStyle(e.querySelector('.people-emails')).display === 'inline'
        && getComputedStyle(e.querySelector('.email-first')).display === 'inline';
    }''')
    assert row.locator('.people-card-meta .mono').is_visible()
    assert row.locator('.c-open').is_visible()
    assert not row.locator('.c-phone').is_visible()
    assert row.locator('.c-open').bounding_box()['y'] > row.locator('.name').bounding_box()['y']
    assert row.locator('.people-card-meta').bounding_box()['y'] > row.locator('.name').bounding_box()['y']
    assert page.locator('.sheet td.c-last .mono[title="Last contact in map"]').first.inner_text() == 'Sep 16'
    page.get_by_role('combobox', name='Sort by').select_option('last')
    assert page.locator('.sheet th.c-last').get_attribute('aria-sort') == 'descending'
    assert page.locator('.sheet-scroll').evaluate(r"e => e.scrollWidth <= e.clientWidth + 1")
    assert page.evaluate(r"document.documentElement.scrollWidth <= innerWidth")


def test_large_people_roster_keeps_mobile_controls_visible(reader, tmp_path, monkeypatch):
    from connectonion.rem import reader as rem_reader

    data = rem_reader.snapshot(tmp_path / "rem")
    example = next(r for r in data["records"] if r["title"] == "Quinn Alder")
    data["records"].extend({**example, "path": f"people/example-{i}.md",
                            "title": f"Alexandria Margaret Historical Correspondent {i:03d}"}
                           for i in range(570))
    monkeypatch.setattr(rem_reader, "snapshot", lambda _, local=False, today=False: data)
    path = tmp_path / "large-roster.html"
    path.write_text(rem_reader.render(tmp_path / "rem"), encoding="utf-8")

    page, _ = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(path.as_uri() + "#c=people")
    # Rows stay short: the recent group shows 14, then one button for the rest.
    assert page.locator(".r4 .row.prow").count() <= 14 + 9
    more = page.get_by_role("button", name=re.compile(r"Show all \d+ people"))
    assert more.is_visible()
    page.locator(".r4-find").fill("Correspondent 569")
    assert page.locator(".r4 .row.prow").count() == 1
    page.locator(".r4-find").fill("")
    directory = page.locator(".contact-directory summary")
    directory.focus()
    directory.press("Enter")
    assert page.locator(".contact-directory").get_attribute("open") is not None
    page.locator(".contact-directory").get_by_role("searchbox", name="Search other contacts").fill("Leah Bell")
    assert page.locator(".contact-directory tbody tr").count() == 1
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")
    sheet = page.locator(".sheet-scroll")
    assert page.locator(".sheet tbody tr").count() >= 575
    for _ in range(2):
        sheet.evaluate("e => e.scrollLeft = e.scrollWidth")
        assert page.locator('.sheet-scroll').evaluate(r"e => e.scrollWidth <= e.clientWidth + 1")
        assert page.get_by_role('combobox', name='Sort by').is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator('.sheet td.c-last .mono[title="Last contact in map"]').first.inner_text() == 'Sep 16'
        page.get_by_role('combobox', name='Sort by').select_option('last')
        assert page.locator(".sheet th.c-last").get_attribute("aria-sort") in ("ascending", "descending")


def test_first_map_shows_results_next_step_and_held_count_on_phone(reader, tmp_path, monkeypatch):
    from connectonion.rem import reader as rem_reader

    data = rem_reader.snapshot(tmp_path / "rem")
    data["logs"] = []
    data["status"] = {"state": "Not started — run `co rem start` to begin"}
    for record in data["records"]:
        record["written"] = False
    next(r for r in data["records"] if r["title"] == "Quinn Alder")["needs_review"] = True
    for counts in data["counts"].values():
        counts["written"] = 0
    visible_people = sum(r["category"] == "people" and r["path"] != data["owner"]
                         and not r.get("needs_review") and not r.get("service")
                         for r in data["records"])
    monkeypatch.setattr(rem_reader, "snapshot", lambda _, local=False, today=False: data)
    path = tmp_path / "first-map.html"
    path.write_text(rem_reader.render(tmp_path / "rem"), encoding="utf-8")

    page, _ = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(path.as_uri())
    assert page.locator('.night-card .count').is_visible()
    assert page.locator('.first-map').is_visible()
    assert page.locator(".first-map h2").inner_text().endswith(" records mapped")
    assert page.locator(".first-map .morning-time").inner_text() == "0 memories written"
    assert page.locator(".first-map-actions a").inner_text() == f"Browse {visible_people} people →"
    assert page.locator(".first-map-actions a").is_visible()
    assert page.locator(".first-map-actions span").inner_text() == 'Unwritten pages pending — background updates off'
    assert page.locator(".first-map-actions span").evaluate("e => e.getBoundingClientRect().bottom <= innerHeight")
    assert page.locator(".first-map-actions button, .first-map-actions code").count() == 0
    page.locator(".nav-toggle").click()
    page.locator(".settings-open").click()
    assert "Nightly updates are off." in page.locator(".reader-settings").inner_text()  # D-60 (build 3b review): Reader settings states things in words, never a command to copy.
    page.keyboard.press("Escape")  # closes the settings sheet and the 更多 sheet under it
    page.locator(".first-map-actions a").click()
    assert "1 possible contact" in page.locator(".held-note").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


# The ledger that opened this page is retired (owner, 2026-11-08, D-30): the record opens on who she is.
def test_a_person_opens_on_the_record_with_facts_disclosed(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    assert 'Head of Partnerships' in page.locator('.r4-sub').inner_text()
    assert page.locator('.r4-stats').inner_text().count('\n') >= 3
    assert page.locator('.r4-person #open-threads, .owe').count() == 0
    assert page.locator('.r4-fuse .rhythm').locator('i.l1, i.l2, i.l3').count() == 5  # one dark day per dated exchange
    assert page.locator('details.deep-note').get_attribute('open') is None
    assert not page.locator('.factlist').is_visible()
    page.locator('details.deep-note > summary').click()
    card = page.locator(".factlist")
    value = lambda label: card.locator(f"dt:text-is('{label}') + dd")  # noqa: E731
    assert "Head of Partnerships" in value("Role").inner_text()
    assert value("Phone").get_attribute("class") == "none" and "not found" in value("Phone").inner_text()
    role_source = value('Role').locator('.cite')
    assert role_source.inner_text() == 'Aug 22'
    assert role_source.get_attribute('aria-label') == 'Source: Outlook, Aug 22, original not in this snapshot'
    assert 'title and company in signature' in page.locator('#src-2').inner_text()
    role_source.click()
    assert "The original isn't in this snapshot." in page.locator('#evidence-panel').inner_text()
    page.get_by_role('button', name='Close source context').click()
    assert role_source.evaluate('e => e === document.activeElement')
    assert value("Email").locator(".qual").all_inner_texts() == ["work", "personal"]
    # Insight moved off the first screen into the full memory, still cited.
    assert page.locator(".block-insight li").count() == 4
    assert page.locator(".block-insight .cite.run").count() == 3  # Each adjacent pair or longer run shares one marker
    assert page.locator(".deep-note .block-threads").count() == 0
    assert page.locator(".timeline li").count() == 5
    assert page.locator(".tl .tl-e").count() == 5
    assert page.locator("#src-6").count() == 1


def test_grouped_citation_sources_are_each_openable_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.locator("details.deep-note > summary").click()
    assert page.locator(".block-insight .cite.run").count() == 3
    page.goto(uri + "#r=people%2Fmara-ostrowski.md&h=src-6")
    assert page.locator("details.deep-note").get_attribute("open") is not None
    page.locator("#src-6 .source-open").click()
    assert "Source 1 of 1 for this line" in page.locator("#evidence-panel .evidence-top").inner_text()
    assert page.locator("#evidence-panel .evidence-original").is_visible()
    target = page.locator("#src-6 .source-open").bounding_box()
    assert target["height"] >= 44 and target["width"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_adjacent_citation_chips_show_only_the_supporting_sentence(reader, width):
    page, uri = reader
    first = ("Mara is a professor involved in the RMIT ARC Research Hub proposal and invited your company "
             "to join as a Partner Organisation")
    second = ("You owe Mara the promised Letter of Support draft and contribution questions: "
              "“I'll come back to you shortly with a draft and a couple of questions about the contribution details.” "
              "(2026-10-14)")
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.evaluate(r"""text => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = '# Mara Ostrowski\n\n' + text + '\n\n## Facts' + r.text.split('## Facts')[1];
      KNOWN.clear(); FACTS.clear(); render();
    }""", first + " [2][6]. " + second + " [4].", isolated_context=False)
    page.locator("details.deep-note > summary").click()
    chips = page.locator(".deep-note .note > p").first.locator(".cite")
    assert chips.count() == 2
    for index, expected, other in ((0, first, second), (1, second, first)):
        chips.nth(index).click()
        claim = page.locator(".evidence-claim > div").inner_text()
        assert claim == expected  # the full memory keeps the prose date the person page used to trim
        assert other not in claim
        page.get_by_role("button", name="Close source context").click()


def test_evidence_sentence_boundaries_keep_quotes_and_short_claims_local(reader):
    page, _ = reader
    cases = {
        "Earlier finding! Dr. Mara gives examples, e.g. support letters [1].":
            "Dr. Mara gives examples, e.g. support letters",
        'Earlier question? A quoted promise: "I will send it. Please wait!" (2026-10-14) [1].':
            'A quoted promise: "I will send it. Please wait!" (2026-10-14)',
        "Earlier finding; A separate supported clause with enough words [1].":
            "A separate supported clause with enough words",
        "Previous sentence. Tiny [1]. Another sentence follows.": "Tiny.",
        "Previous sentence. Send [1] the promised draft. Another sentence follows.": "Send the promised draft.",
        "[1] Send the promised draft. Another sentence follows.": "Send the promised draft.",
        "[1]": "",
    }
    claims = page.evaluate("""texts => texts.map(text => {
      const line = document.createElement('p');
      line.innerHTML = inline(text, 'people/mara-ostrowski.md');
      return evidenceLine(line.querySelector('.cite')).text;
    })""", list(cases), isolated_context=False)
    assert claims == list(cases.values())


def test_pages_about_the_user_read_as_you_and_the_markdown_keeps_its_words(reader):
    page, _ = reader
    cases = {
        "The user has not signed it; with the user since 2026-09-22.": "You have not signed it; with you since 2026-09-22.",
        "the user's main contact": "your main contact",
        "Emrys owes the user its P115 proposal": "Emrys owes you its P115 proposal",
        "How the user writes to them": "How you write to them",
        "the user still owes Mara an answer": "you still owe Mara an answer",
        "the user is waiting; the user doesn't know": "you are waiting; you don't know",
        "the user should send a proposal": "you should send a proposal",
        "the user replies within a day": "you reply within a day",
        # 1.9.2b1 pages: an adverb before the verb, and a compound adjective.
        "Use when the user explicitly asks": "Use when you explicitly ask",
        "a user-facing request; the user-facing copy": "a user-facing request; the user-facing copy",
    }
    assert page.evaluate("cases => Object.keys(cases).map(youify)", cases, isolated_context=False) == list(cases.values())
    # 1.9.2b1: these said nothing was open and showed as OPEN, "open for N days"; a real thread stays open.
    calm = ["None identified as of 2026-10-01.", "None as of 2026-09-30 [2].", "No explicit open request in the material.",
            "Nothing owed either way [3].", "No outstanding items.", "Nothing open as of 2026-10-02."]
    still_open = ["No reply from Maren since 2026-09-12 [4].", "Unknown — whether Corin sent the invoice; Ellis asked 2026-09-30 [2]."]
    assert page.evaluate("t => t.map(isCalm)", calm + still_open, isolated_context=False) == [True] * 6 + [False] * 2
    # 1.9.2b1 skill pages: the finding after "Unknown — not verified." was hidden with the placeholder.
    record = {"path": "skills/catalog/x.md", "title": "x", "text": "# x\n\n## Current status\nUnknown — not verified. "
              "The latest session, 2026-06-09, proposed an npm CLI [1].\n\n## Limitations\nUnknown — not verified.\n"}
    kept = page.evaluate("r => known(r).kept.map(s => s.title)", record, isolated_context=False)
    assert kept == ["Current status"]
    # 1.9.2b1 History ranges: the end date leaked into the text or the gutter was blank.
    lines = "\n".join(["- 2026-08-26–2026-08-28: Quayside asked [1].", "- 2026-09-23 to 2026-10-09: Daily reports [2].",
                       "- 2026-08-10–11: Demos sent [3].", "- 2026-07-29–08-04: Trip [4].", "- 2025-10: Met at a meetup [5].", "- 2025-10–11: Term [6]."])
    got = page.evaluate("t => historyItems(t).map(i => [i.day, i.end, i.text.slice(0, 4)])", lines, isolated_context=False)
    assert got == [["2026-08-26", "2026-08-28", "Quay"], ["2026-09-23", "2026-10-09", "Dail"],
                   ["2026-08-10", "2026-08-11", "Demo"], ["2026-07-29", "2026-08-04", "Trip"], ["2025-10", "", "Met "], ["2025-10", "2025-11", "Term"]]
    assert page.evaluate("dayLabel({day: '2025-10', end: ''})", isolated_context=False) == "Oct 2025"
    assert page.evaluate("dayLabel({day: '2026-08-10', end: '2026-08-11'})", isolated_context=False).count("–") == 1
    # A thread addressed to the owner by name ("Avery: collect …") is the owner's to do.
    assert page.evaluate("direction('Avery: collect the swipe card from Security')", isolated_context=False) == "mine"
    page.locator('.others .waiting-more').click()
    home_threads = page.locator('.task-band .threads').first.inner_text()
    assert "you have owed them" in home_threads and "the user" not in home_threads.lower()
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    page.locator("details.deep-note > summary").click()
    main = page.locator("#main").inner_text()
    assert "the user" not in main.lower() and "you have not signed it" in main.lower()
    assert page.get_by_role("heading", name="How you write to them").count() == 1
    assert page.evaluate("REM.records.find(r => r.path === 'people/mara-ostrowski.md').text.includes('the user has not signed it')", isolated_context=False)


def test_a_compound_predicate_agrees_with_you_and_threads_name_the_right_debtor(reader):
    page, _ = reader
    # 1.9.2b1: "You run events there and has asked" — only the first verb agreed.
    cases = {
        "the user runs events there and has asked Mara for a deck": "you run events there and have asked Mara for a deck",
        "The user signed on 2026-09-02 but is waiting for the countersigned copy": "You signed on 2026-09-02 but are waiting for the countersigned copy",
        "the user sends invoices and receipts": "you send invoices and receipts",
        "Mara asked the user and has replied since": "Mara asked you and has replied since",
        "the user signed, and Tomas has asked for a copy": "you signed, and Tomas has asked for a copy",
    }
    assert page.evaluate("cases => Object.keys(cases).map(youify)", cases, isolated_context=False) == list(cases.values())
    # 1.9.2b1/b3 pages: who owes is the subject of the request, not the first name in the line.
    threads = {
        "User owes pickup of the replacement card at Gate 2 [1].": "mine",
        "Avery asked Mara on 2026-09-28 for a first reaction to the name; no reply [6].": "theirs",
        "Avery asked Tomas to arrange a call and provide a time [2].": "theirs",
        "Avery is awaiting Mara's answer to the 2026-08-19 question [10].": "theirs",
        "Mara asks Avery to choose a time for a 30-minute demo [8].": "mine",
        "Avery offered Mara a free two-week trial; acceptance is not shown [5].": "plain",
        "Avery offered to cover the $25 card fee [12].": "mine",
    }
    assert page.evaluate("t => t.map(direction)", list(threads), isolated_context=False) == list(threads.values())


def test_the_owner_focus_prefers_a_supported_change_to_a_generic_now(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Favery-lin.md")
    assert "Last active" in page.locator(".leadrow").inner_text()
    assert "Last contact" not in page.locator(".focus-facts").inner_text()
    assert "Wellington" in page.locator(".focus-facts").inner_text()
    selected = page.evaluate("""() => {
      const owner = REM.records.find(r => r.path === REM.owner);
      const insight = section(owner, 'insight');
      const original = insight.text;
      insight.text = '- Changed: Avery reversed the one-brief-per-person plan [2].\\n' + original;
      try {
        const focus = recordFocus(owner);
        return [memoryStatement(owner), focus.querySelector('.focus-next')?.textContent];
      } finally { insight.text = original; }
    }""", isolated_context=False)
    assert selected[0] == "Avery reversed the one-brief-per-person plan."
    assert "Next step" in selected[1] and "This month you shipped" in selected[1]
    assert "this month you shipped" in page.locator(".focus-statement").inner_text().lower()


def test_owner_next_step_keeps_its_source_and_private_label(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Favery-lin.md')
    page.evaluate("""() => {
      const owner = byPath(REM.owner);
      owner.text = owner.text.replace('## Insight\\n',
        '## Insight\\n- Changed: The brief plan changed [2].\\n- Now: Send the confidential draft [sensitive] [2].\\n');
      KNOWN.delete(owner.path); render();
    }""", isolated_context=False)
    step = page.locator('.focus-next')
    assert step.locator('.private').is_visible()
    assert step.locator('a.cite').count() == 1
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not step.locator('.private').is_visible()
    assert 'confidential draft' not in step.inner_text()


def test_focus_connects_project_people_org_and_archived_conversation(reader):
    page, uri = reader
    page.goto(uri + "#r=projects%2Fharbour.md")
    # This fixture names the pilot participants without linking their paths.
    # They remain available as text hints, behind progressive disclosure.
    page.locator('.mention-hints > summary').click()
    connected = page.locator(".related-records .relation-card")
    assert {name.strip() for name in connected.locator("strong").all_inner_texts()} >= {
        "Mara Ostrowski", "Fernhill Labs"}
    assert "what this project does" in page.locator('.focus-kicker').inner_text().lower()
    assert "command-line tool" in page.locator('.focus-statement').inner_text()
    assert not page.locator('.deep-note-limit').is_visible()
    page.locator('details.deep-note > summary').click()
    assert "did not confirm current project work" in page.locator('.deep-note-limit').inner_text()
    assert page.get_by_role("heading", name="Recorded direction").is_visible()
    assert page.get_by_role("heading", name="Full memory and sources").is_visible()
    page.get_by_role("link", name="View all decisions").click()
    assert page.locator(".deep-note #key-decisions").is_visible()
    page.goto(uri + "#r=projects%2Fharbour.md")
    assert page.get_by_role("heading", name="Full memory and sources").is_visible()
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.locator("details.deep-note > summary").click()
    page.locator(".conversation-open").first.click()
    dialog = page.locator("#conversation-dialog")
    assert dialog.is_visible() and "usage export" in dialog.inner_text()
    dialog.get_by_role("button", name="Close conversation").click()
    assert page.locator(".conversation-open").first.evaluate("e => document.activeElement === e")
    page.locator("a.cite[href*='src-5'] >> visible=true").first.click()
    evidence = page.locator("#evidence-panel")
    assert evidence.is_visible() and "I will send the usage export" in evidence.inner_text()


def test_conversations_precede_links_and_name_hints_keep_their_source_page(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      REM.records.push({path: 'notes/run.md', category: 'notes', title: 'Run note', text: '# Run note'});
      r.relations = [
        {path: 'skills/catalog/weekly-brief.md', kind: 'linked', basis: 'Use the brief', via: r.path, sources: ['5']},
        {path: 'notes/run.md', kind: 'linked', basis: 'Run evidence', via: r.path, sources: []},
        {path: 'orgs/fernhill-labs.md', kind: 'mentioned by', basis: 'Mara in a directory',
         via: 'orgs/fernhill-labs.md', sources: ['1']}
      ];
      render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    assert page.locator('.conversation-view').bounding_box()['y'] < page.locator('.related-records').bounding_box()['y']
    assert page.locator('.relation-card').filter(has_text='weekly-brief').is_visible()
    note = page.locator('.relation-card').filter(has_text='Run note')
    hint = page.locator('.relation-card').filter(has_text='Mara in a directory')
    assert not note.is_visible() and not hint.is_visible()
    page.locator('.notebook-links > summary').click()
    assert note.is_visible() and not hint.is_visible()
    page.locator('.mention-hints > summary').click()
    assert hint.is_visible()
    assert 'On Fernhill Labs' in hint.locator('..').inner_text()
    assert hint.locator('..').locator('a.cite').get_attribute('href') == '#r=orgs%2Ffernhill-labs.md&h=src-1'
    # Forward-link citations open the origin's original, not the destination's [5].
    page.locator('.related-records a.cite[href*="mara-ostrowski"]').first.click()
    assert 'I will send the usage export' in page.locator('#evidence-panel').inner_text()


def test_person_lead_shows_two_sentences_without_a_second_hero(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    text = "The user owes Mara a revised pilot agreement. She needs the usage export before Friday. A third sentence belongs in the full memory."
    page.evaluate("text => { const r = byPath('people/mara-ostrowski.md'); r.text = '# Mara Ostrowski\\n\\n' + text; KNOWN.clear(); FACTS.clear(); render(); }", text, isolated_context=False)
    assert page.locator('.focus-head, .contact-strip, .person-lead').count() == 0
    assert 'third sentence' not in page.locator('.r4-person').inner_text()
    page.locator('details.deep-note > summary').click()
    assert 'You owe Mara a revised pilot agreement.' in page.locator('.deep-note').inner_text()
    assert 'third sentence' in page.locator('.deep-note').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_record_dates_do_not_disagree_when_the_index_is_stale(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    expected = page.evaluate("known(byPath('people/mara-ostrowski.md')).last", isolated_context=False)
    page.evaluate("() => { byPath('people/mara-ostrowski.md').index = {last_contact: '2001-01-01'}; FACTS.clear(); render(); }", isolated_context=False)
    formatted = page.evaluate('date => threadDate(date)', expected, isolated_context=False)
    # The quiet contact line and disclosed facts share the page date.
    assert formatted in page.locator('.r4-stats').inner_text()
    assert '2001' not in page.locator('.r4-stats').inner_text()
    page.locator('details.deep-note > summary').click()
    fact_date = page.evaluate('date => fmtDate(date)', expected, isolated_context=False)
    assert fact_date in page.locator('.factlist dt:text-is("Last contact") + dd').inner_text()


def test_empty_mail_keeps_private_header_evidence_without_inventing_a_body_excerpt(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      Object.assign(REM.source_context['outlook:77c09ad1e3f0'], {
        source: 'outlook', excerpt: '', body_empty: true, truncated: false, subject: 'Accepted: Workshop',
        participants: {from: 'mara@example.org', to: ['owner@example.org'], cc: []}
      });
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        trigger = page.locator('.deep-note a.cite[href$="h=src-5"]').first
        trigger.click()
        dialog = page.locator('#evidence-panel')
        assert 'The retained message has no body text. Its headers are available.' in dialog.inner_text()
        assert dialog.locator('.evidence-empty-body').is_visible()
        assert 'Accepted: Workshop' in dialog.locator('.evidence-subject').inner_text()
        assert not dialog.locator('blockquote').count()
        assert not dialog.locator('.evidence-unavailable').count()
        # A message (#2106): the sender and their address head it, recipients follow.
        assert 'mara@example.org' in dialog.locator('.msg-head').inner_text()
        assert dialog.locator('.evidence-participants .msg-person').count() == 1
        page.evaluate('togglePrivate()', isolated_context=False)
        assert not dialog.locator('.evidence-original').is_visible()
        assert not dialog.locator('.evidence-subject').is_visible()
        page.evaluate('togglePrivate()', isolated_context=False)
        assert dialog.locator('.evidence-empty-body').is_visible()
        page.get_by_role('button', name='Close source context').click()
        assert trigger.evaluate('e => e === document.activeElement')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_project_first_seen_does_not_establish_an_unknown_start_date(reader):
    page, uri = reader
    page.goto(uri + "#r=projects%2Fharbour.md")
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = r.text.replace('# Harbour', '# Harbour\\n\\n## Facts\\n- Started: Unknown');
      FACTS.clear(); render();
    }""", isolated_context=False)
    assert page.evaluate("facts(byPath('projects/harbour.md')).first", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    started = page.locator('.factlist dt:text-is("Started") + dd')
    assert started.locator('.val').count() == 0
    assert 'not found' in started.inner_text()


def test_project_hero_leads_with_current_finding_before_historical_pattern(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Pattern: Historical send rule: verified recipient, approved text, screenshot, no retries. [1]\\n'
        + '- Changed: A later UI request corrected its wording. [2]\\n- Now: A release was requested in July. [3]';
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    for width in (1440, 768, 375):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.locator('.focus-statement').inner_text() == 'A release was requested in July.'


def test_project_hero_prefers_newest_where_it_stands_and_falls_back_to_insight(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Now: A release was requested in July. [1]\\n'
        + '- At stake: Keep the release evidence current. [2]\\n'
        + '\\n## Where it stands\\n- 2026-10-14 — An older release was prepared. [1]\\n'
        + '- 2026-10-16 – origin/main has a commit titled “1.9.3b5 release”. [2]\\n'
        + '- 2026-10-15 - The release checks passed. [3]';
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.locator('.focus-statement').inner_text() == 'origin/main has a commit titled “1.9.3b5 release”.'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = r.text.split('## Where it stands')[0] + '## Where it stands\\n- Unknown';
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.locator('.focus-statement').inner_text() == 'A release was requested in July.'


def test_unknown_repository_stays_unknown_and_the_workspace_path_stays_in_the_record(reader):
    # A machine path is not something the owner reads (D-60 spirit): it stays in the full
    # memory, never as a fact beside the session count or in the search's best match.
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Facts\\n- Repository: Unknown\\n- Started: Unknown\\n'
        + '\\n## Insight\\n- At stake: Keep the source folder intact. [1]\\n'
        + '\\n## Paths\\n- /tmp/session-workspace\\n- Sessions: 4\\n- First seen: 2026-07-18\\n- Last seen: 2026-07-20';
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    assert not page.locator('.focus-facts dt:text-is("Local path")').count()
    assert '/tmp/session-workspace' not in page.locator('.focus-facts').inner_text()
    assert not page.locator('.focus-facts dt:text-is("Repository")').count()
    page.locator('details.deep-note > summary').click()
    repository = page.locator('.factlist dt:text-is("Repository") + dd')
    assert not repository.locator('.val').count()
    assert 'not found' in repository.inner_text()
    assert '/tmp/session-workspace' in page.locator('details.deep-note').inner_text()
    page.evaluate("() => { location.hash = '#q=Harbour'; render(); }", isolated_context=False)
    assert not page.locator('.best-facts dt:text-is("Local path")').count()
    assert '/tmp/session-workspace' not in page.locator('.best-facts').inner_text()


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_a_session_summary_names_the_owner_you_not_owner(reader, language):
    # Session summaries are stored with the role word ("The owner asked…", "Owner 询问…"). The reader
    # says you / 你 only where that is the subject of a finished act; everything else is left alone.
    page, uri = reader
    cases = {
        "The owner asked Codex to clone Harbour.": "You asked Codex to clone Harbour.",
        "The owner approved the Harbour budget.": "You approved the Harbour budget.",
        "Owner 询问发布顺序，最终定稿。": "你询问发布顺序，最终定稿。",
        "Owner 要求重写摘要。": "你要求重写摘要。",
        "The owner wants a shorter brief.": "The owner wants a shorter brief.",
        "The owner doesn't want a call.": "The owner doesn't want a call.",
        "Owner asks for a review.": "Owner asks for a review.",
        "Quinn is the owner of the repo.": "Quinn is the owner of the repo.",
        "The owner of the listing, Ida, asked for photos.": "The owner of the listing, Ida, asked for photos.",
        "The owner Ida raised prices.": "The owner Ida raised prices.",
        "数据 owner 是 Mara。": "数据 owner 是 Mara。",
        "Mara（owner）负责发布。": "Mara（owner）负责发布。",
        "Mara is the Product Owner for Harbour.": "Mara is the Product Owner for Harbour.",
    }
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""([language, summaries]) => {
      const base = {category: 'sessions', session_project: 'projects/harbour.md', session_tags: [], session_turns: 1, text: ''};
      summaries.forEach((summary, n) => REM.records.push({...base, path: 'sessions/s' + n + '.md', title: 'Session ' + n,
        session_date: '2026-09-' + String(10 + n).padStart(2, '0'), session_summary: summary}));
      setInterfaceLanguage(language); render();
    }""", [language, list(cases)], isolated_context=False)
    shown = page.evaluate("summaries => summaries.map(s => ownerAsYou(s))", list(cases), isolated_context=False)
    assert dict(zip(cases, shown)) == cases
    rows = page.locator('.project-sessions .session-context-summary').all_inner_texts()
    assert "你要求重写摘要。" in rows and "Owner 要求重写摘要。" not in rows, rows
    page.evaluate("() => { location.hash = 'r=sessions%2Fs0.md'; }", isolated_context=False)
    assert page.locator('.session-summary .lede').inner_text() == "You asked Codex to clone Harbour."


def test_investigation_command_targets_the_notebook_being_viewed(reader):
    page, uri = reader
    # b1927e56: only private projects retain an explicit investigation command.
    page.goto(uri + "#r=projects%2Fharbour.md")
    page.evaluate(r'''() => {
      const r = byPath('projects/harbour.md');
      r.private_project = true; r.written = false;
      r.text = '# Harbour\n\n## Overview\nUnknown — not investigated yet\n';
      r.original = r.text; KNOWN.clear(); FACTS.clear(); render();
    }''', isolated_context=False)
    root = page.evaluate('REM.root', isolated_context=False)
    # D-60 (build 3b review): no investigation command anywhere, neither on the page nor in Reader settings.
    assert page.locator('.missing .cmd').count() == 0
    page.locator('.settings-open').click()
    assert page.locator('.reader-settings .cmd, .reader-settings code').count() == 0
    assert root not in page.locator('.reader-settings').inner_text()


def test_private_mode_hides_raw_sources_and_conversations_already_open(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.locator('details.deep-note').evaluate('d => d.open = true')
    page.locator('.conversation-open').first.click()
    messages = page.locator('#conversation-dialog .conversation-message')
    assert messages.first.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not messages.first.is_visible()
    assert page.locator('#conversation-dialog .private-hidden-notice').is_visible()
    page.get_by_role('button', name='Close conversation').click()
    page.locator("a.cite[href*='src-5'] >> visible=true").first.click()
    original = page.locator('#evidence-panel .evidence-original')
    assert original.count() == 1 and not original.is_visible()
    assert page.locator('#evidence-panel .private-hidden-notice').is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert original.is_visible() and 'I will send the usage export' in original.inner_text()


def test_private_project_summary_is_clear_on_desktop_and_phone(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Now: A hidden finding [personal].\\n'
        + '\\n## What it is\\n- A hidden description [personal].\\n'
        + '\\n## Key decisions\\n- A hidden decision [personal].\\n'
        + '\\n## Sources\\n- [1] codex:example — 2026-09-01\\n'
        + '\\nInvestigation: mapped 2026-09-01 · investigated 2026-10-01 (codex)';
      r.project_coverage = {inputs_read: 3, inputs_available: 5, days: 150, scope: 'archived'};
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        assert page.locator('.scope-note').count() == 0
        assert 'clamped' not in page.locator('.focus-statement').get_attribute('class')
        page.evaluate('togglePrivate()', isolated_context=False)
        assert page.locator('.focus-statement').inner_text() == 'Hidden labelled passage'
        assert page.locator('.project-purpose-preview').inner_text() == 'Hidden labelled passage'
        assert page.locator('.project-workspace').get_by_text('Hidden labelled passage').count() == 1
        assert page.locator('.project-workspace').get_by_text('Hidden labelled passage').first.is_visible()
        page.evaluate("() => { location.hash = '#c=projects'; render(); }", isolated_context=False)
        # The directory never quotes a page's purpose, so nothing private can leak into a row.
        assert page.locator('#main').get_by_role('link', name='Harbour', exact=True).first.is_visible()
        assert 'hidden description' not in page.locator('#main').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.evaluate("() => { location.hash = '#r=projects%2Fharbour.md'; render(); }", isolated_context=False)
        page.evaluate('togglePrivate()', isolated_context=False)


def test_project_without_a_current_insight_leads_with_purpose_and_input_limit(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Unknown\\n'
        + '\\n## What it is\\n- Harbour reads a local daily log. [1]\\n'
        + '\\n## Where it stands\\n- The checkout snapshot has a recent commit. [1]\\n'
        + '\\n## Sources\\n- [1] project-source:fixture — README snapshot\\n'
        + '\\nInvestigation: mapped 2026-09-01 · investigated 2026-10-01 (codex)';
      r.project_coverage = {inputs_read: 3, inputs_available: 5, days: 7, scope: 'archived'};
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    assert not page.locator('.deep-note-limit').is_visible()
    page.locator('details.deep-note > summary').click()
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        assert page.locator('.focus-kicker').first.inner_text() == 'What this project does'
        assert 'reads a local daily log' in page.locator('.focus-statement').inner_text()
        assert 'recent commit' not in page.locator('.focus-statement').inner_text()
        assert '7-day session sample did not confirm current project work' in page.locator('.deep-note-limit').inner_text()
        assert page.locator('.project-workspace').get_by_text('What this is').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.evaluate("() => { byPath('projects/harbour.md').project_coverage.inputs_read = 0; render(); }",
                  isolated_context=False)
    page.locator('details.deep-note > summary').click()
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        assert 'No coding-session input was assigned' in page.locator('.deep-note-limit').inner_text()
        assert page.locator('.scope-note').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_written_project_purpose_and_source_fit_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Now: The user asked to organize a folder in August; whether the requested work was completed is unknown. [1]\\n'
        + '\\n## What it is\\nA property lead workflow to collect contacts and ask owners whether they permit short stays. [1]\\n'
        + '\\n## Key decisions\\n- Collect property details before filtering. [1]\\n'
        + '\\n## Sources\\n- [1] codex:example — 2026-08-02\\n'
        + '\\nInvestigation: mapped 2026-10-03 · investigated 2026-10-04 (codex)';
      r.project_coverage = {inputs_read: 114, inputs_available: 116, days: 90, scope: 'archived'};
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    purpose = page.locator('.project-purpose-preview')
    assert 'property lead workflow' in purpose.inner_text()
    assert purpose.bounding_box()['y'] < 812
    assert page.locator('.scope-note').count() == 0
    purpose_source = page.locator('.project-purpose-cites a.cite').first
    assert purpose_source.get_attribute('aria-label').startswith('Source: Session, Aug 2')
    assert purpose_source.get_attribute('data-tip') is None
    sources = page.locator('.focus-source').bounding_box()
    assert sources['height'] >= 44 and sources['y'] + sources['height'] <= 812
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_long_project_purpose_keeps_a_source_in_the_phone_first_screen(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = r.original || r.text;
      const purpose = 'A shared-inbox tool for a team to review long threads, identify decisions and unresolved follow-ups, and prepare a weekly brief before a renewal call. '.repeat(2);
      r.text = r.text.replace(/## What it is\\n- [^\\n]+/, '## What it is\\n- ' + purpose + '[1].');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    statement = page.locator('.focus-statement')
    assert statement.evaluate('(node) => node.scrollHeight > node.clientHeight')
    assert statement.evaluate('(node) => getComputedStyle(node).webkitLineClamp') == '4'
    chip = page.locator('.project-purpose-cites a.cite').first
    source = page.locator('.focus-source')
    assert chip.bounding_box()['y'] + chip.bounding_box()['height'] <= 812
    assert source.bounding_box()['y'] + source.bounding_box()['height'] <= 812
    page.get_by_role('button', name='Read full purpose').wait_for()
    # Once open its label reads "Show less"; follow the button by what it controls.
    more = page.locator('button.focus-more[aria-controls="' + statement.get_attribute('id') + '"]')
    assert more.get_attribute('aria-expanded') == 'false'
    more.click()
    assert more.get_attribute('aria-expanded') == 'true'
    assert not statement.evaluate('(node) => node.scrollHeight > node.clientHeight')
    assert 'weekly brief before a renewal call' in statement.inner_text()
    assert statement.evaluate(r'''node => node.nextElementSibling.nextElementSibling.classList.contains('project-purpose-cites')''')
    more.click()
    assert more.get_attribute('aria-expanded') == 'false'
    assert statement.evaluate('(node) => node.scrollHeight > node.clientHeight')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('has_finding', [False, True])
def test_long_private_purpose_can_expand_after_revealing_passages(reader, has_finding):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate(r'''hasFinding => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\n\n## What it is\n- ' + 'A shared inbox tool for pilot review '.repeat(30)
        + '[personal] [1].\n\n' + (hasFinding ? '## Insight\n- Now: Pilot review is ready [1].\n\n' : '')
        + '## Sources\n- [1] codex:example — 2026-09-01\n';
      r.original = r.text;
      document.documentElement.classList.add('hide-private');
      KNOWN.clear(); FACTS.clear(); render();
    }''', has_finding, isolated_context=False)
    purpose = page.locator('.project-purpose-preview' if has_finding else '.focus-statement')
    more = page.locator('button.focus-more[aria-controls="' + purpose.get_attribute('id') + '"]')
    assert purpose.inner_text() == 'Hidden labelled passage'
    assert not more.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert more.is_visible()
    more.click()
    assert more.get_attribute('aria-expanded') == 'true'
    assert purpose.evaluate(r'''node => node.scrollHeight <= node.clientHeight + 1''')


def test_written_pages_show_the_complete_source_action_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    paths = ('people/avery-lin.md', 'orgs/fernhill-labs.md',
             'people/mara-ostrowski.md', 'projects/harbour.md',
             'skills/catalog/weekly-brief.md')
    for path in paths:
        page.goto(uri + '#r=' + path.replace('/', '%2F'))
        if path == 'skills/catalog/weekly-brief.md':
            page.evaluate("""() => {
              const r = byPath('skills/catalog/weekly-brief.md');
              r.text = '# weekly-brief\\n\\n## Insight\\nA saved draft needs a queue readback before it can be sent. [1]\\n'
                + '\\n## When to use\\nUse for a weekly brief. [1]\\n'
                + '\\n## Sources\\n- [1] skill-record:test — saved draft and queue readback.';
              KNOWN.delete(r.path); render();
            }""", isolated_context=False)
        if path == 'people/mara-ostrowski.md':
            assert page.locator('details.deep-note').get_attribute('open') is None
            page.locator('details.deep-note > summary').click()
            page.goto(uri + '#r=people%2Fmara-ostrowski.md&h=sources')
            page.locator('.deep-note .block-sources').wait_for(state='visible')
            continue
        link = page.get_by_role('link', name='View sources →')
        assert link.count() == 1, path
        box = link.bounding_box()
        assert box['height'] >= 44 and box['y'] + box['height'] <= 812, path
        assert page.get_by_role('heading', name='Full memory and sources').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        link.click()
        page.locator('.deep-note .block-sources').wait_for(state='visible')


def test_open_context_is_not_counted_as_waiting_on_other_people(reader):
    page, _ = reader
    # Open threads now consumes the shared Python projection, just as Today does.
    page.evaluate("async () => { const r = byPath('people/mara-ostrowski.md'); r.text = r.text.replace('## Open threads\\n', '## Open threads\\n- Completion evidence not recorded.\\n'); KNOWN.clear(); await refreshTodayQueue(); render(); }", isolated_context=False)
    page.locator('.others .waiting-more').click()
    others = page.locator('.task-band', has=page.get_by_role('heading', name='Waiting on others'))
    plain = page.locator('.task-band', has=page.get_by_role('heading', name='Other open context'))
    assert others.locator('.thread.theirs').count() > 0
    assert others.locator('.thread.plain').count() == 0
    assert 'Completion evidence not recorded' in plain.inner_text()


def test_changes_and_open_threads_are_actionable_destinations(reader):
    page, uri = reader
    page.goto(uri + "#view=changes")
    assert "Head of Partnerships" in page.locator(".claim-card").first.inner_text()
    page.locator(".claim-card a").first.click()
    page.get_by_role("heading", name="Mara Ostrowski", exact=True).wait_for()
    page.goto(uri + "#view=open")
    assert page.get_by_role("heading", name="Open threads").is_visible()
    assert page.locator(".task-band .thread").count() >= 2
    assert page.locator(".task-band a[href*='people']").count() >= 1


@pytest.mark.parametrize("mine,theirs", [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)])
def test_empty_and_partial_waiting_states_show_only_open_counts(reader, mine, theirs):
    page, _ = reader
    page.evaluate(r"""async ({mine, theirs}) => {
      for (const r of REM.records)
        r.text = r.text.replace(/(^## Open threads[^\n]*\n)[\s\S]*?(?=^## |^Investigation:|(?![\s\S]))/mi, '$1Unknown\n\n');
      const items = [
        ...Array.from({ length: mine }, (_, i) => '- You owe Mara reply ' + i + ' [1].'),
        ...Array.from({ length: theirs }, (_, i) => '- Mara owes you answer ' + i + ' [1].')
      ];
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace('## Open threads\nUnknown', '## Open threads\n' + (items.join('\n') || 'Unknown'));
      KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
    }""", {"mine": mine, "theirs": theirs}, isolated_context=False)
    primary = page.locator('#main')
    assert 'See all 0' not in primary.inner_text()
    assert page.locator('.waiting-intro').count() == 0
    assert page.locator('.qcard').count() == bool(mine)
    heading = page.locator('.night-card .count-line').inner_text()
    assert heading.split('\n') == ([str(mine), 'thing waiting on you', 'Start with this 1 person'] if mine else ['0', 'Nobody is waiting on you today.'])
    assert ' 0 ' not in primary.inner_text()
    # Your own total is the sidebar's number, not repeated here (TOP10 #9, polish); what others owe has its own widget.
    assert page.locator('.others .waiting-more').count() == bool(theirs or mine)  # what others owe, or everything open
    if theirs:
        assert page.locator('.others .waiting-more').inner_text() == f'See the {theirs} waiting on others →'
    assert 'Gone quiet (0)' not in page.locator('body').inner_text()
    if theirs or mine:
        page.locator('.others .waiting-more').click()
    else:
        page.evaluate("location.hash = 'view=open'", isolated_context=False)
    page.get_by_role('heading', name='Open threads', exact=True).wait_for()
    assert 'Nothing here.' not in page.locator('#main').inner_text()
    assert '0 waiting' not in page.locator('#main').inner_text()
    assert page.locator('.task-band').count() == bool(mine) + bool(theirs)
    if mine or theirs:
        parts = [f'{count} {label}' for count, label in [(mine, 'waiting on you'), (theirs, 'on someone else')] if count]
        assert page.locator('#main .lede').inner_text() == ', '.join(parts) + '. Newest and due first.'
    else:
        assert page.locator('#main .lede').count() == 0
        assert page.locator('#main .empty .lead').inner_text() == 'Nothing open'
    assert 'Gone quiet (0)' not in page.locator('body').inner_text()
    assert page.evaluate('quietThreads([{t: {quiet: true}}], 0) === null', isolated_context=False)


@pytest.mark.parametrize("count", [0, 1])
def test_changes_hide_zero_skill_usage(reader, count):
    page, _ = reader
    page.evaluate(r"""count => {
      const r = byPath('skills/catalog/weekly-brief.md');
      r.text = r.text.replace(/Invoked[^\n]*|No invocation found[^\n]*/, count
        ? 'Invoked once in the last 180 days; last on 2026-10-01.'
        : 'No invocation found in the last 180 days.');
      REM.logs.push({started_at: REM.as_of, changed: [r.path]});
      KNOWN.clear(); FACTS.clear(); location.hash = 'view=changes'; render();
    }""", count, isolated_context=False)
    skill = page.locator('.changed-pages li', has=page.get_by_role('link', name='weekly-brief', exact=True))
    assert skill.count() == 1
    assert skill.locator('.usage').count() == bool(count)
    assert '0 skill-name matches' not in page.locator('#main').inner_text()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_view_fits_a_phone(reader, theme):
    page, uri = reader
    page.emulate_media(color_scheme=theme)
    page.set_viewport_size({"width": 390, "height": 844})
    for view in VIEWS:
        page.goto(uri + (view or "#"))
        page.wait_for_timeout(120)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), view
        background = page.evaluate("getComputedStyle(document.body).backgroundColor")
        # One sheet: every view's dark paper is --paper (#0f110f); no page owns a palette.
        dark_background = "rgb(15, 17, 15)"
        assert (background == dark_background) == (theme == "dark"), (view, background)


def test_source_and_conversation_show_input_limits_and_hide_them_with_private_content(reader):
    page, uri = reader
    scope = 'Codex Desktop voice transcription; only explicit input, transcript delta omitted; recognition errors possible'
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("scope => { const c = REM.source_context['outlook:77c09ad1e3f0']; c.input_scope = scope; REM.conversations[c.thread].messages[0].input_scope = scope; }", scope, isolated_context=False)
    page.locator('details.deep-note').evaluate('d => d.open = true')  # N3: the record's widgets cite older mail behind 显示全部; the full note cites it all
    page.locator("a.cite[href*='src-5'] >> visible=true").first.click()
    note = page.locator('#evidence-panel .evidence-input-scope')
    assert note.is_visible() and 'Transcription may contain errors.' in note.inner_text() and 'transcript delta' not in note.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not note.is_visible()
    page.get_by_role('button', name='Close source context').click()
    page.evaluate('togglePrivate()', isolated_context=False)
    page.locator('details.deep-note').evaluate('d => d.open = true')
    page.locator('.conversation-open').first.click()
    note = page.locator('#conversation-dialog .evidence-input-scope')
    assert note.is_visible() and 'Transcription may contain errors.' in note.inner_text() and 'transcript delta' not in note.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not note.is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_recovered_mail_shows_participants_and_separate_archive_clock_privately(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      Object.assign(REM.source_context['outlook:77c09ad1e3f0'], {
        participants: {from: 'Mentor <mentor@example.org>', to: ['me@example.org'], cc: ['Guest <guest@example.org>']},
        captured_at: '', retained_at: '2026-10-01T10:00:00Z',
        body_format: 'provider-rendered text, not original MIME',
        excerpt: ('Mail body excerpt.' + String.fromCharCode(10)).repeat(30), truncated: true,
        input_scope: 'Historical citation recovery. Original retrieval time unknown; initial window unchanged.'
      });
    }""", isolated_context=False)
    page.locator('details.deep-note').evaluate('d => d.open = true')
    cite = page.locator("a.cite[href*='src-5'] >> visible=true").first
    cite.click()
    dialog = page.locator('#evidence-panel')
    participants = dialog.locator('.evidence-participants')
    assert participants.is_visible()
    head = dialog.locator('.msg-head').inner_text()
    assert 'Mentor' in head and 'mentor@example.org' in head
    assert 'Cc' in participants.inner_text() and 'Guest' in participants.inner_text()
    assert participants.locator('[title="guest@example.org"]').count() == 1
    assert 'Outlook' in dialog.locator('.msg-time').inner_text() and 'Archived ' in dialog.inner_text()
    assert 'Original retrieval time unknown' in dialog.inner_text()
    assert 'Retrieved ' not in dialog.inner_text()
    assert 'provider-rendered text, not original MIME' in dialog.inner_text()
    assert not participants.locator('mentor').count()
    for private in (True, False):
        page.evaluate('togglePrivate()', isolated_context=False)
        assert participants.is_visible() == (not private)
        assert dialog.locator('blockquote').is_visible() == (not private)
        assert dialog.locator('.evidence-input-scope').is_visible() == (not private)
    assert dialog.evaluate('e => e.scrollWidth <= e.clientWidth')
    dialog.locator('blockquote').scroll_into_view_if_needed()
    close = page.get_by_role('button', name='Close source context')
    box = close.bounding_box()
    assert box['height'] >= 44
    assert 0 <= box['y'] <= 812 - box['height']
    close.click()
    assert cite.evaluate('e => e === document.activeElement')


def test_native_conversation_shares_common_limits_and_keeps_voice_limits(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const c = REM.conversations[REM.source_context['outlook:77c09ad1e3f0'].thread];
      const common = 'Your input only. Assistant replies and tool results are not included, so this does not verify what was completed.';
      c.messages = [{id: 'example:1', excerpt: 'Approve the design.', input_scope: common},
        {id: 'example:2', excerpt: 'Make the title shorter.', input_scope: common},
        {id: 'example:3', excerpt: 'Voice request.', input_scope: 'Codex Desktop voice transcription; recognition errors possible'}];
      c.windows = {'outlook:77c09ad1e3f0': c.messages.map(m => m.id)};
      c.anchors = {'outlook:77c09ad1e3f0': 'example:2'};
      c.total = 3;
    }""", isolated_context=False)
    page.locator('details.deep-note').evaluate('d => d.open = true')
    page.locator('.conversation-open').first.click()
    dialog = page.locator('#conversation-dialog')
    assert dialog.locator(':scope > .evidence-input-scope').count() == 1
    assert dialog.locator('.conversation-message .evidence-input-scope').count() == 1
    assert 'Transcription may contain errors.' in dialog.inner_text()
    assert 'Approve the design.' in dialog.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not dialog.locator(':scope > .evidence-input-scope').is_visible()
    assert not dialog.locator('.conversation-message').first.is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_source_times_use_notebook_timezone_on_another_browser_timezone(reader):
    page, uri = reader
    other = page.context.browser.new_page(timezone_id='America/Los_Angeles', locale='en-US')
    other.goto(uri)
    other.evaluate("REM.status.timezone = 'Australia/Sydney'", isolated_context=False)
    assert 'Jul 31' in other.evaluate("fmtTime('2026-07-30T21:04:03Z')", isolated_context=False)
    assert 'Jul 30' in other.evaluate("new Date('2026-07-30T21:04:03Z').toLocaleDateString('en-US', {month:'short',day:'numeric'})")
    other.close()


def test_open_request_dates_keep_explicit_deadlines_on_the_notebook_calendar(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      REM.status.timezone = 'Australia/Sydney'; REM.as_of = '2026-10-02T14:30:00Z';
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/, '## Open threads' + String.fromCharCode(10) +
        '- You owe Mara a scope decision, requested 2026-10-01; due 2026-10-03 [5].' + String.fromCharCode(10));
      REM.source_context['outlook:77c09ad1e3f0'].time = '2026-10-01T10:00:00Z';
      KNOWN.clear(); render();
    }""", isolated_context=False)
    # The person page no longer lists it (D-30); the dates Today labels it by still come from the notebook calendar.
    first = "threads(byPath('people/mara-ostrowski.md')).items[0]"
    assert page.evaluate(f"dueLabel({first})", isolated_context=False) == 'due Today'
    page.evaluate("REM.as_of = '2026-10-03T14:30:00Z'; render()", isolated_context=False)
    assert page.evaluate(f"overdueDays({first})", isolated_context=False) == 1
    dates = page.evaluate("threads(byPath('people/mara-ostrowski.md')).items[0]", isolated_context=False)
    assert dates['since'] == '2026-10-01' and dates['due'] == '2026-10-03'
    dates = page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace('requested 2026-10-01; due 2026-10-03', 'requested 2026-10-01; meeting 2026-10-05');
      KNOWN.clear(); return threads(r).items[0];
    }""", isolated_context=False)
    assert dates['since'] == '2026-10-01' and dates['due'] == ''


def test_phone_open_preview_names_elapsed_age_and_keeps_the_full_thread(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      REM.status.timezone = 'Australia/Sydney'; REM.as_of = '2026-10-03T14:30:00Z';
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/, '## Open threads' + String.fromCharCode(10) +
        '- Mara asked Avery to confirm the scope on 2026-09-29, followed up twice, and offered several detailed ways to answer before a time-sensitive proposal, while the exact due day still needs confirmation [5].' + String.fromCharCode(10));
      REM.source_context['outlook:77c09ad1e3f0'].time = '2026-09-29T10:00:00Z';
      KNOWN.clear(); render();
    }""", isolated_context=False)
    item = page.evaluate("(() => { const t = threads(byPath('people/mara-ostrowski.md')).items[0]; return {age: age(t.since), text: t.text}; })()",
                         isolated_context=False)
    assert item['age'] == '5 days'
    assert 'exact due day still needs confirmation' in item['text']
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_dates_and_contact_age_use_notebook_calendar_on_another_browser_timezone(reader):
    page, uri = reader
    other = page.context.browser.new_page(timezone_id='America/Los_Angeles', locale='en-US')
    other.goto(uri + '#r=people%2Fmara-ostrowski.md')
    other.evaluate("""() => {
      REM.status.timezone = 'Australia/Sydney';
      REM.as_of = '2026-10-02T22:00:00Z';
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      r.last_activity = '2026-10-02';
      r.text = r.text.replace(/Last contact:[^\\n]+/g, 'Last contact: 2026-10-02 [1]');
      KNOWN.delete(r.path); FACTS.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Yesterday' in other.locator('.r4-stats').inner_text()
    assert other.evaluate("fmtDate('2026-07-31T23:03:58Z')", isolated_context=False) == 'Aug 1'
    assert other.evaluate("fmtDate('2026-07-31')", isolated_context=False) == 'Jul 31'
    other.evaluate("REM.as_of = '2026-12-31T14:00:00Z'", isolated_context=False)
    assert other.evaluate("shortDate('2026-12-31')", isolated_context=False) == 'Yesterday'  # notebook calendar, not the browser's
    other.evaluate("REM.as_of = '2026-10-03T15:30:00Z'", isolated_context=False)
    assert other.evaluate("daysSince('2026-10-03')", isolated_context=False) == 1
    other.close()


def test_phone_activity_shows_complete_rows_with_latest_first(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      const start = r.text.indexOf('## History'), end = r.text.indexOf('## ', start + 3);
      const rows = [2, 1, 4, 3].map(n => '- 2026-09-0' + n + ': ' + 'Confirmed the venue plan, with event completion unknown. '.repeat(5) + '[1]');
      r.text = r.text.slice(0, start) + '## History\\n' + rows.join('\\n') + '\\n' + r.text.slice(end);
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    assert page.locator('.tl-e .d').all_inner_texts() == ['9/4', '9/3', '9/2', '9/1']  # N3: month and day on each row
    assert all(text.count('Confirmed the venue plan') == 5 for text in page.locator('.tl-e .x').all_inner_texts())
    assert page.locator('.tl').evaluate('e => e.scrollHeight <= e.clientHeight')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('language, days', [('en', ['9/4', '12/24\n2025', '9/4\n2025']), ('zh', ['9/4', '12/24\n2025年', '9/4\n2025年'])])
def test_an_exchange_from_another_year_says_its_year(reader, language, days):
    """Review of #2929: the timeline gave month and day only, so last September read as this one. The notebook's
    as_of year is the current one (2026 here); an older entry carries its year under the day, inside the column."""
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""language => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      const start = r.text.indexOf('## History'), end = r.text.indexOf('## ', start + 3);
      const rows = ['2025-09-04', '2026-09-04', '2025-12-24'].map(day => '- ' + day + ': Confirmed the venue plan. [1]');
      r.text = r.text.slice(0, start) + '## History\\n' + rows.join('\\n') + '\\n' + r.text.slice(end);
      KNOWN.delete(r.path); setInterfaceLanguage(language);
    }""", language, isolated_context=False)
    assert page.locator('.tl-e .d').all_inner_texts() == days
    assert page.locator('.tl-e .d').evaluate_all('cells => cells.every(cell => cell.scrollWidth <= cell.clientWidth)')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_reviewed_role_and_unknown_company_override_older_index(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      r.text = r.text.replace(/^- Role:[^\\n]+/m, '- Role: Programme manager (historical current unknown) [1]')
        .replace(/^- Company:[^\\n]+/m, '- Company: Unknown');
      r.index = {...r.index, role: 'Current CEO', company: 'Old employer'};
      KNOWN.delete(r.path); FACTS.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Programme manager (historical current unknown)' in page.locator('.r4-sub').inner_text()
    assert 'Old employer' not in page.locator('.r4-sub').inner_text()
    page.evaluate("""() => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      r.text = r.text.replace(/^- Company:[^\\n]+\\n/m, '');
      KNOWN.delete(r.path); FACTS.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Old employer' in page.locator('.r4-sub').inner_text()


def test_instruction_excerpt_is_not_a_verified_result_and_respects_privacy(reader):
    page, uri = reader
    source = 'skill-source:' + 'a' * 16
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.evaluate("""source => {
      const r = REM.records.find(r => r.path === 'skills/catalog/weekly-brief.md');
      r.text = '# weekly-brief\\n\\n## What it does\\nCheck the actual artifact. [1]\\n\\n## Insight\\nVerify the artifact before claiming success. [1]\\n\\n## Sources\\n- [1] ' + source;
      REM.source_context[source] = {source: 'skill-source', excerpt: 'Check the actual artifact before claiming success.',
        input_scope: 'Skill instructions; intended behavior, not verified execution. Recovered from a file whose content matches the citation hash.',
        truncated: false};
      KNOWN.delete(r.path);
      render();
    }""", source, isolated_context=False)
    page.locator('a.cite').first.click()
    dialog = page.locator('#evidence-panel')
    assert 'instruction excerpt' in dialog.inner_text().lower()
    assert 'not a verified result' in dialog.inner_text()
    assert 'recovered from matching file content' in dialog.inner_text()
    assert dialog.locator('blockquote').inner_text() == 'Check the actual artifact before claiming success.'
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not dialog.locator('blockquote').is_visible()
    assert not dialog.locator('.evidence-input-scope').is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert dialog.locator('blockquote').is_visible()
    page.get_by_role('button', name='Close source context').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_long_skill_source_find_reaches_passages_and_keeps_original(reader):
    page, uri = reader
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
        page.evaluate("""() => {
          const r = byPath('skills/catalog/weekly-brief.md');
          const source = 'skill-record:' + 'b'.repeat(64);
          r.text = '# weekly-brief\\n\\n## Insight\\nA queue readback checked the saved draft. [1]'
            + '\\n\\n## Sources\\n- [1] ' + source;
          const part = ('{"step":"invented source"},\\n').repeat(650);
          REM.source_context[source] = {source: 'skill-record',
            excerpt: 'İstanbul\\n' + part + 'Queue readback checked the first draft.\\n' + part
              + 'Queue readback checked the second draft.\\n', truncated: true};
          KNOWN.delete(r.path);
          render();
        }""", isolated_context=False)
        cite = page.locator('a.cite').first
        cite.click()
        dialog = page.locator('#evidence-panel')
        find = dialog.get_by_role('searchbox', name='Find in archived source')
        assert find.is_visible()
        assert 'truncated' in dialog.inner_text().lower()
        original = dialog.locator('blockquote').inner_text()
        span = dialog.locator('.evidence-original mark.span').inner_text()
        assert span == 'Queue readback checked the'
        assert len(original) > 30000
        find.fill('Queue readback')
        assert dialog.locator('.evidence-original mark').inner_text() == 'Queue readback'
        assert 'Match 1 of 2' in dialog.locator('.evidence-find-status').inner_text()
        next_match = dialog.get_by_role('button', name='Next match')
        assert next_match.bounding_box()['height'] >= 44
        next_match.click()
        assert 'Match 2 of 2' in dialog.locator('.evidence-find-status').inner_text()
        assert dialog.locator('blockquote').inner_text() == original
        find.fill('not in this invented run')
        assert 'No match' in dialog.locator('.evidence-find-status').inner_text()
        assert not dialog.locator('.evidence-original mark').count()
        find.fill('.*')
        assert 'No match' in dialog.locator('.evidence-find-status').inner_text()
        find.fill('')
        assert dialog.locator('.evidence-find-status').inner_text() == ''
        assert dialog.locator('blockquote').inner_text() == original
        assert dialog.locator('.evidence-original mark.span').inner_text() == span
        assert find.is_visible()
        assert dialog.evaluate('e => e.scrollWidth <= e.clientWidth')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.evaluate('togglePrivate()', isolated_context=False)
        assert not find.is_visible()
        page.evaluate('togglePrivate()', isolated_context=False)
        assert find.is_visible()
        page.get_by_role('button', name='Close source context').click()
        assert cite.evaluate('e => e === document.activeElement')


def test_skill_opens_on_its_finding_and_keeps_usage_in_full_note(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.evaluate("""() => {
      const r = byPath('skills/catalog/weekly-brief.md');
      const source = 'skill-record:' + 'a'.repeat(64);
      r.text = '# weekly-brief\\n\\n## Insight\\nA saved draft still needs a queue readback. [1]\\n\\nMore detail belongs in the note. [1]\\n\\n## When to use\\nUse for a weekly brief. [1]\\n\\n## Sources\\n- [1] ' + source;
      REM.source_context[source] = {source: 'skill-record', excerpt: 'Recorded queue readback.', truncated: false};
      KNOWN.delete(r.path);
      render();
    }""", isolated_context=False)
    assert page.locator('.focus-statement').inner_text() == 'A saved draft still needs a queue readback.'
    assert page.locator('.focus-head .focus-kicker').inner_text() == 'Useful finding'
    assert not page.locator('.focus-more').is_visible()
    finding_source = page.locator('.skill-finding-cites a.cite').first
    assert finding_source.get_attribute('href').endswith('h=src-1')
    assert finding_source.bounding_box()['width'] >= 44
    assert finding_source.bounding_box()['height'] >= 44
    finding_source.click()
    assert page.locator('#evidence-panel blockquote').inner_text() == 'Recorded queue readback.'
    page.get_by_role('button', name='Close source context').click()
    assert finding_source.evaluate('e => e === document.activeElement')
    page.get_by_role('link', name='View sources →').click()
    page.locator('.deep-note .block-sources').wait_for(state='visible')
    assert page.locator('.deep-note .block-sources').is_visible()
    assert 'Use for a weekly brief.' in page.locator('.deep-note').inner_text()
    page.locator('.deep-note a.cite').first.click()
    assert page.locator('#evidence-panel .evidence-claim').evaluate('e => e.scrollWidth <= e.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Close source context').click()
    page.evaluate("""() => {
      const r = byPath('skills/catalog/weekly-brief.md');
      r.text = r.text.replace('A saved draft still needs a queue readback. [1]',
        'A saved draft still needs a queue readback. [personal] [1]');
      KNOWN.delete(r.path);
      render();
    }""", isolated_context=False)
    private_source = page.locator('.skill-finding-cites a.cite').first
    assert private_source.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not private_source.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert private_source.is_visible()


def test_skill_activity_uses_invocation_dates_instead_of_investigation_dates(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Ftalk-outline.md')
    assert page.locator('.focus-facts').count() == 0
    assert '0 skill-name matches' in page.locator('.lead-meta.usage').inner_text()
    assert 'last activity' not in page.locator('.eyebrow').inner_text()
    assert 'last name match' not in page.locator('.eyebrow').inner_text()
    page.set_viewport_size({'width': 1440, 'height': 1000})
    assert 'file updated' in page.locator('.eyebrow').inner_text()
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    assert page.locator('.focus-facts').count() == 0
    assert '14 skill-name matches' in page.locator('.lead-meta.usage').inner_text()
    assert 'last name match' not in page.locator('.eyebrow').inner_text()
    assert 'file updated' in page.locator('.eyebrow').inner_text()
    assert page.evaluate('known(byPath("skills/catalog/weekly-brief.md")).last === skillUsage(byPath("skills/catalog/weekly-brief.md")).last', isolated_context=False)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_skill_name_matches_are_not_presented_as_installed_version_runs(reader):
    page, uri = reader
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        page.goto(uri + '#r=skills%2Fcatalog%2Finvoice-check.md')
        page.evaluate("""() => {
          const r = byPath('skills/catalog/invoice-check.md');
          r.text = r.text.replace('## Source\\n',
            '## Run evidence\\n- Retained evaluation attempts: 0; installed version unverified.\\n\\n## Source\\n');
          KNOWN.delete(r.path);
          render();
        }""", isolated_context=False)
        assert page.locator('.focus-facts').count() == 0
        assert '3 skill-name matches' in page.locator('.lead-meta.usage').inner_text()
        assert 'retained eval attempts are counted separately' in page.locator('.usage-scope').inner_text()
        assert 'Neither confirms this installed version or task outcome' in page.locator('.usage-scope').inner_text()
        assert page.locator('.panel h3:text-is("Usage")').count() == 0
        assert page.locator('details.deep-note').get_attribute('open') is None
        page.locator('details.deep-note > summary').click()
        assert 'Claude Code 3' not in page.locator('.leadrow').inner_text()
        assert 'Retained evaluation attempts: 0' in page.locator('.deep-note').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Finvoice-check.md')
    assert page.locator('.missing.primary .lead').inner_text() == 'Page pending — background updates off'
    assert page.locator('.missing.primary button, .missing.primary code').count() == 0
    assert page.locator('.focus-command').count() == 0


def test_skill_roster_links_are_touch_sized_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#c=skills')
    links = page.locator('.skills-view :is(a.skill-card, a.skill-item, .skill-shape button):visible')
    assert links.count() > 0
    for link in links.all():
        box = link.bounding_box()
        assert box['width'] >= 44 and box['height'] >= 44
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    links.first.click()
    assert page.locator('.record-focus.skills').is_visible()


def test_written_unknown_sections_are_distinct_from_uninvestigated_pages(reader):
    page, uri = reader
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.evaluate("""() => {
      const r = byPath('skills/catalog/weekly-brief.md');
      r.written = true;
      r.text = '# weekly-brief\\n\\n## What it does\\nCheck the artifact.\\n\\n## Current status\\nUnknown — not verified\\n\\nInvestigation: investigated 2026-10-02';
      KNOWN.delete(r.path);
      render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    assert page.locator('.missing .names').inner_text() == 'Still unknown: Current status.'
    assert page.locator('.missing .lead').inner_text() == 'Page pending — background updates off'
    assert page.locator('.missing').get_attribute('class') == 'missing'
    page.evaluate("() => { REM.status.worker = {enabled: true}; render(); }", isolated_context=False)
    page.locator('details.deep-note > summary').click()  # render() closes the disclosure again
    assert page.locator('.missing .lead').inner_text() == 'Unresolved sections queued for a future pass'
    page.goto(uri + '#r=people%2Fquinn-alder.md')
    assert page.locator('.missing .names').inner_text().endswith('sections will be written when it is investigated.')
    assert page.locator('.missing .lead').inner_text() == 'Page queued for tonight'
    assert 'primary' in page.locator('.missing').get_attribute('class')


def test_mapped_person_distinguishes_map_date_from_missing_note_fact(reader):
    page, uri = reader
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        page.reload()
        page.goto(uri + '#r=people%2Fquinn-alder.md')
        page.get_by_role('heading', name='Quinn Alder', exact=True).wait_for()
        assert 'Sep 16' in page.locator('.r4-stats').inner_text()
        assert page.locator('.focus-facts').count() == 0
        assert page.locator('details.deep-note').get_attribute('open') is None
        assert page.locator('.deep-note .factlist').count() == 1
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if width == 375:
            status = page.locator('.missing.primary .lead').bounding_box()
            assert status['y'] >= 0 and status['y'] + status['height'] <= 812
            assert page.locator('.missing.primary button, .missing.primary code').count() == 0

        page.goto(uri + '#c=people')
        page.locator('.r4-people h1').wait_for()
        page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
        quinn = page.locator('.sheet tbody tr').filter(has_text='Quinn Alder')
        assert quinn.locator('.c-last .mono').inner_text() == 'Sep 16'
        assert quinn.locator('.c-last .mono').get_attribute('title') == 'Last contact in map'

        page.goto(uri + '#r=people%2Fmara-ostrowski.md')
        page.get_by_role('heading', name='Mara Ostrowski', exact=True).wait_for()
        assert 'Last contact in map' not in page.locator('.r4-person').inner_text()

        page.goto(uri + '#r=people%2Fquinn-alder.md')
        page.get_by_role('heading', name='Quinn Alder', exact=True).wait_for()
        page.evaluate("""() => {
          const r = byPath('people/quinn-alder.md');
          r.last_activity = ''; r.mail.last = '';
          KNOWN.delete(r.path); FACTS.delete(r.path); render();
        }""", isolated_context=False)
        assert 'Sep 16' not in page.locator('.r4-stats').inner_text()
        page.locator('details.deep-note > summary').click()
        assert '— not found' in page.locator('.factlist dt:text-is("Last contact") + dd').inner_text()


def test_unknown_open_status_is_not_a_current_exchange(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Open threads\\nUnknown. Historical requests do not establish currently pending work. [1]\\n\\n## Sources\\n- [1] test:historical';
      KNOWN.delete(r.path);
      render();
    }""", isolated_context=False)
    assert page.evaluate("threads(byPath('projects/harbour.md')).items.length", isolated_context=False) == 0
    assert page.get_by_role('heading', name='Next exchanges').count() == 0
    page.locator('details.deep-note > summary').click()
    note = page.locator('.deep-note')
    assert 'Historical requests do not establish currently pending work.' in note.inner_text()
    assert note.locator('a.cite[href$="h=src-1"]').first.is_visible()


def test_project_map_date_is_labelled_as_a_session_not_verified_activity(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.last_activity = '2026-09-16';
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Last mapped session' in page.locator('.leadrow').inner_text()
    assert 'Last mapped session' not in page.locator('.focus-facts').inner_text()
    assert 'last mapped session' not in page.locator('.eyebrow').inner_text()
    assert 'File updated' in page.locator('.deep-head').inner_text()
    assert 'Last active' not in page.locator('.leadrow').inner_text()
    # The directory's list shows the same mapped date as its latest activity.
    page.goto(uri + '#c=projects&v=list')
    page.evaluate('() => { pdQuietOpen = true; KNOWN.clear(); FACTS.clear(); render(); }', isolated_context=False)
    assert page.locator('.pd-lrow[data-path="projects/harbour.md"] .pd-when').inner_text().startswith('Sep 16')


def test_completed_delivery_is_conversation_instead_of_a_commitment(reader):
    page, url = reader
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      const start = r.text.indexOf('## History');
      const end = r.text.indexOf('\n## ', start + 1);
      r.text = r.text.slice(0, start) + '## History\n- 2026-09-25: You sent company introductions [1].\n- 2026-09-26: You promised to send the revised overview [1].\n' + r.text.slice(end);
      KNOWN.clear(); FACTS.clear();
    }""", isolated_context=False)
    page.goto(url + '#r=people%2Fmara-ostrowski.md')
    rows = page.locator('.tl .tl-e')
    delivered = rows.filter(has_text='You sent company introductions')
    promised = rows.filter(has_text='You promised to send')
    # Both are yours: a filled dot, newest first, no type filters on the person page.
    assert delivered.locator('i.me').count() == 1 and promised.locator('i.me').count() == 1
    assert rows.all_inner_texts()[0].endswith('You promised to send the revised overview.')
    assert delivered.is_visible() and promised.is_visible()
    assert page.locator('.r4-person .activity-filters').count() == 0


def test_marked_sentence_with_a_markdown_link_and_code_respects_private_mode(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text += '\n\n## Private context\nPublic setup. [Quinn](quinn-alder.md) shared confidential details in `case.txt` [sensitive] [1]. Public follow-up.\n';
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    sentence = page.locator('.deep-note .private').filter(has_text='confidential details')
    assert sentence.locator('.privacy-tag.sensitive').is_visible()
    assert sentence.locator('a:not(.cite)').inner_text() == 'Quinn'
    assert sentence.locator('code').inner_text() == 'case.txt'
    assert sentence.locator('a.cite').count() == 1
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not sentence.is_visible()
    assert not page.locator('.deep-note a').filter(has_text='Quinn').is_visible()
    assert not page.locator('.deep-note code').filter(has_text='case.txt').is_visible()
    assert page.get_by_text('Public setup.', exact=False).is_visible()
    assert 'Public follow-up.' in page.locator('.deep-note').inner_text()
    visible = page.locator('.deep-note p').filter(has_text='Public setup.').inner_text()
    assert ' '.join(visible.split()) == 'Public setup. Public follow-up.'
    page.evaluate('togglePrivate()', isolated_context=False)
    assert sentence.is_visible()


def test_consecutive_marked_sentences_hide_in_the_lead_and_full_note(reader):
    page, uri = reader
    page.goto(uri + '#r=orgs%2Ffernhill-labs.md')
    page.evaluate(r"""() => {
      const r = byPath('orgs/fernhill-labs.md');
      const paragraph = '## Our relationship\n' +
        'First confidential finding. [sensitive] [1][2][3] ' +
        'Second confidential finding. [sensitive] [1][2][3] ' +
        'Public result. [1] ' +
        '[Quinn](../people/quinn-alder.md) sent `secret-value`. [personal] [1]\n\n';
      r.text = r.text.replace('## Who they are', paragraph + '## Who they are');
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    # The first line may carry a labelled sentence, but only inside its own labelled span.
    sub = page.locator('.ov-sub')
    sub.evaluate("n => n.querySelectorAll('.private').forEach(p => p.remove())")
    assert 'confidential finding' not in sub.inner_text() and 'secret-value' not in sub.inner_text()
    page.evaluate('render()', isolated_context=False)
    page.locator('details.deep-note > summary').click()
    for selector in ('.deep-note',):
        area = page.locator(selector)
        assert area.locator('.private').count() == 3
        assert area.locator('.private').filter(has_text='Second confidential finding').count() == 1
    assert page.locator('.deep-note .private a.cite').count() == 3
    page.evaluate('togglePrivate()', isolated_context=False)
    for selector in ('.deep-note',):
        text = page.locator(selector).inner_text()
        assert 'confidential finding' not in text
        assert 'secret-value' not in text
        assert 'Public result.' in text
    assert 'confidential finding' not in page.locator('.ov-sub').inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert 'Second confidential finding' in page.locator('.deep-note').inner_text()
    assert page.locator('.deep-note .private code').is_visible()


def test_connected_context_hides_private_bases_including_expanded_connections(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.relations = Array.from({length: 7}, (_, n) => ({path: 'projects/harbour.md',
        kind: n === 6 ? 'mentioned by' : 'linked', private: n === 0 || n === 6,
        basis: n === 6 ? 'Private expanded context' : n === 0 ? 'Confidential background' : 'Public pilot context'}));
      render();
    }""", isolated_context=False)
    assert page.locator('details.deep-note').get_attribute('open') is None
    page.locator('details.deep-note > summary').click()
    page.locator('.more-relations > summary').first.click()
    bases = page.locator('.relation-basis.private')
    assert bases.count() == 2
    assert all(bases.nth(n).is_visible() for n in range(2))
    page.evaluate('togglePrivate()', isolated_context=False)
    assert all(not bases.nth(n).is_visible() for n in range(2))
    assert page.locator('.relation-basis').filter(has_text='Public pilot context').first.is_visible()
    assert page.locator('.relation-card strong').first.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert all(bases.nth(n).is_visible() for n in range(2))


@pytest.mark.parametrize('width', [390, 1440])
def test_failed_init_is_visible_and_keyboard_reachable(reader, tmp_path, monkeypatch, width):
    from connectonion.rem import reader as rem_reader

    page, _ = reader
    data = rem_reader.snapshot(tmp_path / 'rem')
    data['as_of'] = '2026-10-07T12:00:00+00:00'
    data['logs'] = [
        {'started_at': '2026-10-07T11:00:00+00:00', 'outcome': 'failed',
         'error': 'Failed to authenticate. API Error: 403 Request not allowed', 'changed': []},
        {'started_at': '2026-10-07T11:01:00+00:00', 'outcome': 'failed',
         'error': 'TimeoutError: private payload must not appear here', 'changed': []},
    ]
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False, today=False: data)
    path = tmp_path / 'blocked.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(path.as_uri())
    brief = page.locator('.overnight')
    assert '2 investigations failed' in brief.inner_text()
    assert 'Model access was refused' in brief.inner_text()
    assert 'A request timed out' in brief.inner_text()
    assert 'private payload' not in brief.inner_text()
    assert 'No memory pages were written' in brief.inner_text()
    assert 'Your notebook was just built' not in brief.inner_text()
    assert brief.locator('.cmd').count() == 0
    stopped = page.locator('.night-details .hypno .dot.woke')
    assert stopped.count() == 1
    assert '2 runs stopped early' in stopped.get_attribute('title')
    link = brief.get_by_role('link', name='Review failed runs →')
    assert link.bounding_box()['height'] >= 44
    link.focus()
    link.press('Enter')
    page.get_by_role('heading', name='Activity', exact=True).wait_for()
    assert page.locator('.activity-runs li.failed-run').count() == 2
    assert 'private payload' not in page.locator('.activity-runs').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_partial_pass_keeps_written_memory_beside_failure(reader, tmp_path, monkeypatch):
    from connectonion.rem import reader as rem_reader

    page, _ = reader
    data = rem_reader.snapshot(tmp_path / 'rem')
    data['logs'] = [
        {'started_at': data['as_of'], 'outcome': 'completed',
         'changed': ['people/mara-ostrowski.md']},
        {'started_at': data['as_of'], 'outcome': 'failed', 'error': 'TimeoutError', 'changed': []},
    ]
    # fbdd25e3: replacing the run window does not replace the notebook's age.
    data['first_run_at'] = data['as_of']
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False, today=False: data)
    path = tmp_path / 'partial.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.goto(path.as_uri())
    brief = page.locator('.overnight')
    assert '1 investigation failed' in brief.inner_text()
    assert 'Your notebook was just built.' in brief.inner_text()
    assert 'reworded; nothing new.' not in brief.inner_text()
    assert page.locator('.week-details summary').inner_text().startswith('Pages written in the first build (')
    page.locator('.week-details summary').click()
    assert page.locator('.week').get_by_role('link', name='Mara Ostrowski', exact=True).is_visible()
    assert page.locator('.qcard').count() > 0
    assert 'No memory pages were written' not in brief.inner_text()


WHOLE_WORDS = """([selector, words]) => words.every(word => [...document.querySelectorAll(selector)].every(node => {
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const text = walker.currentNode, at = text.data.indexOf(word);
    if (at < 0) continue;
    const range = document.createRange();
    range.setStart(text, at); range.setEnd(text, at + word.length);
    if (new Set([...range.getClientRects()].map(r => Math.round(r.top))).size > 1) return false;
  }
  return true;
}))"""


@pytest.mark.parametrize('width', [390, 1440])
def test_fact_labels_and_addresses_never_break_mid_word(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.locator('details.deep-note > summary').click()
    page.locator('.factlist dt').first.wait_for()
    assert page.evaluate(WHOLE_WORDS, ['.factlist dt', ['REPOSITORY', 'ORGANISATION', 'Repository', 'Organisation']])
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/- Email: [^\\n]+/, '- Email: 0x3c3ae74550@mail.openonion.ai [1]')
        .replace(/## Facts\\n/, '## Facts\\n- Handles: 0x3c3ae74550@mail.openonion.ai [1]\\n');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    page.locator('.factlist dd').first.wait_for()
    assert page.evaluate(WHOLE_WORDS, ['.factlist dd, .contact-strip dd', ['0x3c3ae74550', 'openonion', 'mail']])
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_long_hash_ids_are_shortened_with_the_full_id_on_hover(reader):
    page, uri = reader
    digest = '1831aa83d8a03a4013b38bf560ea93cc1279c281cee147ce426980c4028e4080'
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.evaluate("""(digest) => {
      const r = byPath('skills/catalog/weekly-brief.md');
      r.text = '# weekly-brief\\n\\n## Insight\\nA saved draft needs a queue readback. [1]\\n'
        + '\\n## Usage history\\n- 2026-10-09 · Run record `skill-record:' + digest + '`; output unavailable. [1]\\n'
        + '\\n## Sources\\n- [1] skill-record:' + digest + ' — 2026-10-09';
      KNOWN.delete(r.path); render();
    }""", digest, isolated_context=False)
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md&h=sources')
    page.locator('.deep-note .block-sources').wait_for(state='visible')
    note = page.locator('.deep-note').inner_text()
    assert digest not in note
    assert 'skill-record:1831aa83d8a0…' in note
    assert page.locator('.block-sources .id').first.get_attribute('title') == 'skill-record:' + digest
    assert page.locator('.deep-note code[title="skill-record:' + digest + '"]').count() == 1


# Owner, 2026-11-09: «我们的版本号是不是可以在侧边栏显示一下？顺便把侧边栏优化一下，现在看起来不是很好。»
# The sidebar keeps one number, the one that asks for action, and names the release in its footer.
SIDEBAR_ORDER = ['Today', 'Waiting on you', 'Memory changes', 'People', 'Organisations', 'Projects', 'Skills',
                 'Knowledge', 'Opportunities', 'Decisions', 'Principles', 'Works', 'Agenda', 'Agent sessions', 'All records']


def test_the_rail_counts_only_what_waits_on_you_and_keeps_the_rest_behind_more(reader):
    """D-132: seven places, each a picture with its word (today, waiting, people, orgs, projects, skills, all records),
    the rest one 更多 away."""
    page, _ = reader
    rows = page.locator('#nav > a')
    names = rows.evaluate_all("rows => rows.map(row => row.getAttribute('aria-label'))")
    assert names == ['Today', 'Waiting on you', 'People', 'Organisations', 'Projects', 'Skills', 'All records']  # D-01: the catch-all last
    assert [text.split('\n')[0].strip() for text in rows.all_inner_texts()] == ['Today', 'Waiting', 'People', 'Orgs', 'Projects', 'Skills', 'All']
    more = [text.strip() for text in page.locator('#rail-more a').all_inner_texts()]
    assert more[0] == 'Memory changes' and more[1:] == [name for name in SIDEBAR_ORDER if name in more[1:]]
    assert 'Skills' not in more and 'Decisions' in more  # Skills has its own place now; the rest stay behind 更多
    assert not {'Graph', 'Activity', 'Questions & connections'} & set(names + more)  # D-02, D-03
    # Only Waiting on you carries a number; a category's size is not a task.
    counted = page.locator('#nav a').evaluate_all("rows => rows.filter(row => row.querySelector('.n')).map(row => row.getAttribute('href'))")
    assert counted == ['#view=open']
    assert int(page.locator('#nav a[href="#view=open"] .n.waiting').inner_text()) > 0
    style = rows.evaluate_all("""rows => rows.map(row => {
      const s = getComputedStyle(row);
      return {current: row.getAttribute('aria-current'), color: s.color, shadow: s.boxShadow, width: row.getBoundingClientRect().width};
    })""")
    tokens = page.evaluate("""() => { const paint = name => { const probe = document.createElement('i'); probe.style.color = 'var(' + name + ')';
        document.body.append(probe); const value = getComputedStyle(probe).color; probe.remove(); return value; };
      return {ink: paint('--ink'), grey: paint('--grey')}; }""")
    assert {row['width'] for row in style} == {56}
    current = [row for row in style if row['current'] == 'page']
    assert len(current) == 1 and current[0]['color'] == tokens['ink'] and current[0]['shadow'] != 'none'  # the raised one
    assert all(row['color'] == tokens['grey'] and row['shadow'] == 'none' for row in style if row['current'] != 'page')


def test_the_settings_sheet_names_the_release_and_keeps_every_switch(reader):
    from connectonion import __version__
    page, _ = reader
    assert page.evaluate('REM.version', isolated_context=False) == __version__
    page.locator('.settings-open').click()
    foot = page.locator('#foot')
    version = foot.locator('.version')
    assert version.inner_text() == 'co ' + __version__
    assert 'Updated ' in foot.locator('.foot-line').inner_text()  # the render time (fast-open)
    for mode in ('dark', 'light', 'auto'):
        foot.locator('[role=radiogroup]').get_by_role('radio', name={'dark': 'Dark', 'light': 'Light', 'auto': 'Auto'}[mode]).click()
        assert page.evaluate('document.documentElement.dataset.theme || "auto"') == mode
    motion = foot.get_by_role('switch', name='Reduce motion')
    motion.click()
    assert page.evaluate('document.documentElement.classList.contains("calm")')
    foot.get_by_role('switch', name='Reduce motion').click()
    foot.locator('.language-switch').get_by_role('button', name='中文', exact=True).click()
    page.wait_for_function('document.documentElement.lang === "zh"')
    assert page.locator('#foot .version').inner_text() == 'co ' + __version__  # en and zh the same
    assert page.locator('#nav a[href="#view=open"]').inner_text().startswith('等你处理')
    page.locator('#foot .language-switch').get_by_role('button', name='EN', exact=True).click()
    page.wait_for_function('document.documentElement.lang === "en"')
    assert page.get_by_role('switch', name='Hide labelled passages').is_visible()
    page.keyboard.press('Escape')
    assert not page.locator('#settings').evaluate('d => d.open')
    page.evaluate("() => localStorage.removeItem('co-rem-ui-language')")


def test_the_sidebar_has_one_activity_entry_after_the_memory_categories(reader, tmp_path, monkeypatch):
    """Owner, 2026-10-15: "Run logs" and "AI notes" read as the same thing twice."""
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.files import Notebook

    page, _ = reader
    notebook = Notebook(tmp_path / 'rem')
    notebook.write('notes/reflection.md', '# A reflection\n\nWhat the last pass taught.\n')
    notebook.write('logs/people-map.md', '# People map\n\nWho writes to whom.\n')
    notebook.write('logs/skill-runs-0123456789ab.md', '# weekly-brief runs\n\nRun coverage.\n')
    path = tmp_path / 'activity.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.goto(path.as_uri())
    nav = page.locator('#nav a').all_inner_texts()
    assert not any('Run logs' in item or 'AI notes' in item for item in nav)
    labels = [item.split('\n')[0] for item in nav]
    # Owner, 2026-11-08: the catch-all goes last (N3: last of the rail's places). 2026-11-09: Activity is REM's run log, at the foot.
    assert page.locator('#nav > a').last.get_attribute('aria-label') == 'All records' and 'Activity' not in labels and 'Graph' not in labels
    assert page.locator('.rail a[href="#view=activity"]').count() == 0
    listed = page.evaluate('listedRecords().map(r => r.path)', isolated_context=False)
    assert not [path for path in listed if path.startswith(('logs/', 'notes/'))]
    # Owner, 2026-11-09 (sidebar in Fuse): All records keeps no count in the rail; only Waiting on you does.
    assert page.locator('#nav a[href="#c=all"] .n').count() == 0
    assert page.locator('.category-cards').count() == 0
    assert page.locator('.task-links').count() == 0  # the Find section is gone; the rail is the only navigation
    page.goto(path.as_uri() + '#q=coverage')
    assert 'weekly-brief runs' not in page.locator('#main').inner_text()
    page.goto(path.as_uri() + '#r=logs%2Fskill-runs-0123456789ab.md')
    assert page.get_by_role('heading', name='weekly-brief runs').is_visible()


@pytest.mark.parametrize('width', [375, 1440])
def test_activity_lists_each_run_with_pages_changed_and_refused(reader, tmp_path, monkeypatch, width):
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.files import Notebook

    page, _ = reader
    Notebook(tmp_path / 'rem').write('logs/people-map.md', '# People map\n\nWho writes to whom.\n')
    data = rem_reader.snapshot(tmp_path / 'rem')
    data['logs'] = [{'started_at': data['as_of'], 'outcome': 'completed', 'phase': 'daily-update', 'items': 40,
                     'usage': {'input_tokens': 1200, 'output_tokens': 300}, 'changed': ['people/mara-ostrowski.md'],
                     'refusals': [{'record': 'projects/harbour.md',
                                   'errors': ['Candidate rejected, kept at /private/c.md: Changed page has no numbered evidence references']}]}]
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False, today=False: data)
    path = tmp_path / 'runs.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(path.as_uri() + '#view=activity')
    run = page.locator('.activity-runs > li')
    assert run.count() == 1
    text = run.inner_text()
    assert 'daily-update' in text and '40 read' in text and '1,200 in / 300 out tokens' in text
    assert run.get_by_role('link', name='Mara Ostrowski').is_visible()
    assert run.get_by_role('link', name='Harbour').is_visible()
    assert 'Changed page has no numbered evidence references' in text and '/private/c.md' not in text
    maps = page.locator('details.activity-shelf')
    assert maps.inner_text().startswith('Maps · 1') and not maps.evaluate('(node) => node.open')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.goto(path.as_uri())
    assert page.locator('details.maint a[href="#view=activity"]').count() == 1


def test_citations_name_the_source_and_open_marked_margin_or_sheet(reader):
    page, uri = reader
    for width in (1400, 390, 375):
        page.set_viewport_size({'width': width, 'height': 844})
        page.goto(uri + '#r=people%2Fmara-ostrowski.md')
        page.evaluate("""() => {
          const r = byPath('people/mara-ostrowski.md');
          r.text = r.text.replace("the pilot's renewal depends on two things you each owe the other [4][5].",
            'Mara promised “I will send the usage export” by Friday. [5]');
          Object.assign(REM.source_context['outlook:77c09ad1e3f0'], {
            sender: 'Mara Ostrowski <mara@fernhill.example>', time: '2026-10-14T10:33:00Z',
            participants: {from: 'Mara Ostrowski <mara@fernhill.example>', to: ['Avery <avery@example.test>']},
            excerpt: 'Hello Avery,\\nI will   send the usage export by Friday. Thanks, Mara.'
          });
          KNOWN.clear(); FACTS.clear(); render();
        }""", isolated_context=False)
        page.locator('details.deep-note').evaluate('d => d.open = true')
        chip = page.locator('.block-insight a.cite[href$="src-5"]').first
        assert chip.inner_text() == 'Oct 14'  # The full memory labels the source by its date.
        assert 'Mara, Outlook, Oct 14' in chip.get_attribute('title')
        assert 'subject “Harbour renewal”' in chip.get_attribute('aria-label')
        assert 'data-tip' not in chip.evaluate('e => e.outerHTML')
        box = chip.bounding_box()
        assert chip.evaluate(r'''e => {
          const hit = getComputedStyle(e, '::before');
          return parseFloat(hit.minHeight) >= 24 && parseFloat(hit.minWidth) >= 24;
        }''')
        chip.click()
        panel = page.locator('#evidence-panel')
        assert panel.is_visible()
        assert 'Source 1 of 1 for this line' in panel.locator('.evidence-top').inner_text()
        assert panel.locator('.evidence-claim mark.span').inner_text() == 'I will send the usage export'
        assert panel.locator('.msg-body mark.span').inner_text() == 'I will   send the usage export'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        bounds = panel.bounding_box()
        assert panel.evaluate('e => e.scrollWidth <= e.clientWidth')
        if width >= 1100:
            assert bounds['width'] == 380 and bounds['y'] == 16
            assert panel.get_attribute('aria-modal') == 'false'
            assert chip.bounding_box()['x'] + chip.bounding_box()['width'] < bounds['x']
            assert not page.locator('.evidence-backdrop').is_visible()
        else:
            assert bounds['y'] > 0 and bounds['height'] <= 844 * .75 + 1
            assert abs(bounds['y'] + bounds['height'] - 844) <= 1
            assert panel.get_attribute('aria-modal') == 'true'
            assert page.locator('.evidence-handle').is_visible()
            page.keyboard.press('/')
            assert panel.evaluate('e => e.contains(document.activeElement)')
            page.keyboard.press('Shift+Tab')
            assert panel.evaluate('e => e.contains(document.activeElement)')
            page.keyboard.press('Tab')
            assert panel.evaluate('e => e.contains(document.activeElement)')
            page.locator('.evidence-backdrop').click(position={'x': 5, 'y': 5})
            assert not panel.is_visible()
            assert chip.evaluate('e => e === document.activeElement')
            chip.click()
        page.keyboard.press('Escape')
        assert not panel.is_visible()
        assert chip.evaluate('e => e === document.activeElement')
        assert page.locator('#evidence-panel').count() == 1


def test_citation_labels_fallback_and_grouped_sources_stay_honest(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    values = page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      const context = REM.source_context['outlook:77c09ad1e3f0'];
      const owner = byPath(REM.owner);
      owner.index = {...owner.index, emails: ['owner@example.test']};
      context.sender = 'Owner <owner@example.test>';
      context.participants = {};
      context.time = '2026-10-14T10:33:00Z';
      return [chipLabel(r, '5'), chipLabel(r, '1'), chipLabel(r, '99'),
        sourceChannel('claude-session'), sourceChannel('project-source'), sourceChannel('whatsapp')];
    }""", isolated_context=False)
    assert values == ['you, Outlook, Oct 14', 'Outlook, Aug 22', 'source 99', 'Session', 'Repo', 'WhatsApp']
    page.locator('details.deep-note > summary').click()
    missing = page.locator('.factlist a.cite[href$="src-1"]').first
    assert 'missing' in missing.get_attribute('class')
    assert 'original not in this snapshot' in missing.get_attribute('aria-label')
    missing.click()
    panel = page.locator('#evidence-panel')
    assert panel.locator('.evidence-unavailable').inner_text() == "The original isn't in this snapshot."
    page.get_by_role('button', name='Close source context').click()
    page.locator('details.deep-note').evaluate('d => d.open = true')
    grouped = page.locator('.block-insight .cite.run[data-sources="4 5 6"]')
    assert grouped.inner_text() == 'Sep 22 +2'
    assert grouped.get_attribute('data-sources') == '4 5 6'
    assert '3 sources for this line' in grouped.get_attribute('aria-label')
    grouped.click()
    assert 'Source 1 of 3 for this line' in panel.locator('.evidence-top').inner_text()
    panel.get_by_role('combobox', name='Source for this line').select_option('5')
    assert 'Source 2 of 3 for this line' in panel.locator('.evidence-top').inner_text()
    assert 'I will send the usage export' in panel.locator('.msg-body').inner_text()
    page.get_by_role('button', name='Close source context').click()
    assert grouped.evaluate('e => e === document.activeElement')
    page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      document.getElementById('main').appendChild(el('p', {id: 'missing-citation', html: inline('No original [99].', r.path)}));
    }""", isolated_context=False)
    absent = page.locator('#missing-citation a.cite')
    assert absent.inner_text() == 'source 99'
    assert absent.get_attribute('aria-label') == 'Source: source 99, original not in this snapshot'
    absent.click()
    assert panel.locator('.evidence-unavailable').inner_text() == "The original isn't in this snapshot."
    page.get_by_role('button', name='Close source context').click()
    assert absent.evaluate('e => e === document.activeElement')


def test_supporting_span_preserves_words_and_never_invents_a_match(reader):
    page, _ = reader
    result = page.evaluate("""() => [
      supportingSpan('She said “send the signed form”.', 'Please SEND  the signed form today.'),
      supportingSpan('Please send the signed form today.', 'Hello, send the signed form tomorrow.'),
      supportingSpan('She said "a missing quotation".', 'She said a different thing.'),
      supportingSpan('Send the form.', 'Send the form.'),
      markedSpan('<script>alert(1)</script>', [0, 8])
    ]""", isolated_context=False)
    assert result[0] == {'claim': [10, 30], 'source': [7, 28]}
    assert result[1] == {'claim': [7, 27], 'source': [7, 27]}
    assert result[2] is None and result[3] is None
    assert '<script>' not in result[4] and '&lt;script&gt;' in result[4]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [375, 390, 1400])
def test_person_threads_keep_their_dates_off_the_record_and_deep_hash_targets(reader, theme, width):
    """The rows left the person page (owner, 2026-11-08, D-30): what you owe her is one Today link.
    The thread data Today reads still parses her page: direction, due, age, quiet, and no third parties."""
    page, uri = reader
    page.emulate_media(color_scheme=theme)
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      REM.as_of = '2026-10-15T12:00:00Z'; REM.status.timezone = 'UTC';
      const r = byPath('people/mara-ostrowski.md');
      const rows = [
        '- The user owes Mara: a signed draft; since 2026-10-08 [4].',
        '- The user owes Mara a scope decision; due: 2026-10-22 [5].',
        '- The user owes Mara: an old receipt; since 2026-07-22 [6].',
        '- The user owes Mara: a fourth answer [1].',
        '- Mara owes the user: the usage export [5].',
        '- Quinn owes Tomás: a reimbursement [1].'
      ];
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/, '## Open threads\n' + rows.join('\n') + '\n');
      r.text = r.text.replace(/- Now:/, '- **Now**:').replace(/- At stake:/, '- **At stake**:');
      REM.source_context['outlook:e4a2c1907bd3'].time = '2026-10-08T10:00:00Z';
      REM.source_context['gmail:0f9be4c12a55'].time = '2026-07-22T10:00:00Z';
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    assert page.locator('.r4-person #open-threads, .owe').count() == 0
    rows = page.evaluate("""() => personEntries(byPath('people/mara-ostrowski.md')).map(({t}) =>
      ({text: t.text, dir: t.dir, due: t.due ? dueLabel(t) : '', age: age(t.since), quiet: t.quiet}))""", isolated_context=False)
    mine = [row for row in rows if row['dir'] == 'mine']
    assert len(mine) == 4 and len(rows) == 5
    pick = lambda words: next(row for row in mine if words in row['text'])  # noqa: E731
    assert pick('scope decision')['due'] == 'due Oct 22'
    assert pick('signed draft')['age'] == '7 days'
    assert pick('old receipt')['age'] == '85 days' and pick('old receipt')['quiet']
    assert sum('usage export' in row['text'] for row in rows) == 1
    assert not any('Quinn owes Tomás' in row['text'] for row in rows)
    # Four things owed, one quiet: three in Today, and the record says so once.
    assert page.locator('.r4-today').inner_text() == '3 items in Today'
    assert page.locator('.tl .tl-e').count() <= 12
    page.locator('details.deep-note').evaluate('d => d.open = true')
    assert page.locator('.block-insight li.ins-at-stake').count() == 1
    page.locator('details.deep-note').evaluate('d => d.open = false')
    assert page.locator('details.deep-note').get_attribute('open') is None
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.r4-src').click()
    assert page.locator('details.deep-note').get_attribute('open') is not None
    assert page.locator('#history').is_visible()
    page.goto(uri + '#r=people%2Fmara-ostrowski.md&h=src-6')
    assert page.locator('details.deep-note').get_attribute('open') is not None
    assert page.locator('#src-6').is_visible()


def test_morning_rows_quote_only_original_words_and_format_overdue_dates(reader):
    page, _ = reader
    values = page.evaluate(r"""() => {
      REM.as_of = '2026-10-15T12:00:00Z'; REM.status.timezone = 'UTC';
      const r = {title: 'Liesel Voss'};
      return [morningWords('The user owes Liesel Voss a draft; send questions afterward [5].', r),
        morningWords('You owe Liesel Voss a draft; due: 2026-10-22 [5].', r),
        morningWords('Liesel asked “Send the draft and questions.” [5].', r),
        morningWords('You owe Liesel Voss "ok" and a draft [5].', r),
        dueLabel({due: '2026-09-10'}), direction('You said you would send what Liesel owes the bank')];
    }""", isolated_context=False)
    assert values[0] == {'words': 'A draft; send questions afterward.', 'context': '[5]'}
    assert values[1] == {'words': 'A draft; due: 2026-10-22.', 'context': '[5]'}
    assert values[2] == {'words': 'Liesel asked “Send the draft and questions.”.', 'context': '[5]'}
    assert not values[3]['words'].startswith('“')
    assert values[4] == 'overdue · Sep 10'
    assert values[5] != 'third'


def test_morning_selection_keeps_distinct_pages_and_named_obligations(reader):
    page, _ = reader
    got = page.evaluate(r"""() => {
      const mara = byPath('people/mara-ostrowski.md'), tomas = byPath('people/tomas-reyes.md');
      const ines = byPath('people/ines-halvorsen.md'), project = byPath('projects/harbour.md');
      const item = (r, text) => ({r, t: {text, dir: 'mine', quiet: false}});
      const entries = [
        item(mara, 'You owe Tomás a talk abstract [1].'),
        item(mara, 'You owe Mara the signed draft [4].'),
        item(mara, 'You owe Mara a second answer [5].'),
        item(tomas, 'You owe Tomás the signed draft [1].'),
        item(project, 'You owe Tomás Reyes the signed draft [1].'),
        item(ines, 'You owe Inès the Q3 receipts [1].'),
        item(project, 'You owe Harbour a deployment [1].')
      ];
      REM.today_queue = [1, 3, 5].map(i => ({key: doneKey(entries[i]), section: 'morning'}));
      return morningEntries(entries).map(({r, t}) => [r.path, t.text]);
    }""", isolated_context=False)
    assert [row[0] for row in got] == ['people/mara-ostrowski.md', 'people/tomas-reyes.md', 'people/ines-halvorsen.md']
    assert 'signed draft' in got[1][1]


def test_project_focus_and_deep_note_do_not_repeat_purpose_or_threads(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate(r"""() => {
      const r = byPath('projects/harbour.md');
      r.text += '\n## Insight\n- Now: The pilot needs a release decision [1].\n';
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/,
        '## Open threads\n' + [1,2,3,4,5].map(n => '- You owe Mara obligation ' + n + ' [1].').join('\n') + '\n');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    assert page.locator('.lead-open').count() == 0
    assert page.locator('.next-exchanges .thread').count() == 3
    assert page.locator('#what-it-is').count() == 1
    assert page.locator('.project-workspace h2').filter(has_text='What this is').count() == 0
    page.locator('details.deep-note > summary').click()
    assert page.locator('.deep-note .block-threads .thread').count() == 2
    assert 'obligation 1' not in page.locator('.deep-note .block-threads').inner_text()
    assert page.locator('.deep-note #what-it-is').count() == 0
    page.goto(uri + '#r=projects%2Fharbour.md&h=what-it-is')
    assert page.locator('#what-it-is').is_visible()



@pytest.mark.parametrize("width", [375, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_shared_thread_appears_once_on_home_and_open_with_also_on(reader, tmp_path, width, theme):
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 1000})
    page.emulate_media(color_scheme=theme)
    page.evaluate(r"""async () => {
      const quote = "I'll come back to you shortly with a draft and a couple of questions about the contribution details.";
      for (const [path, n] of [['people/mara-ostrowski.md', '91'], ['people/tomas-reyes.md', 'W92']]) {
        const r = byPath(path);
        const words = n === '91' ? "We're preparing the letter and supporting documents now, and " + quote : quote;
        r.text = r.text.replace('## Open threads\n', '## Open threads\n' +
          '- The user owes [Tomás Reyes](../people/tomas-reyes.md): a Letter of Support draft; “' + words + '” [' + n + ']; due: 2026-10-01.\n');
        r.text = r.text.replace('## Sources\n', '## Sources\n- [' + n + '] gmail:27472b21b17e — Letter of Support promise\n');
      }
      KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
    }""", isolated_context=False)
    home = page.locator('.qitem').filter(has_text='Letter of Support draft')
    assert home.count() == 1
    assert page.locator('.qcard').filter(has=home).locator('.today-who').inner_text() == 'Mara Ostrowski'
    assert home.locator('.also-on').inner_text() == 'Also on Tomás Reyes'
    also = home.locator('.also-on a')
    assert also.get_attribute('href') == '#r=people%2Ftomas-reyes.md'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path / 'deduped-home.png'), full_page=True)
    # Hash navigation preserves the injected notebook records.
    page.evaluate("location.hash = 'view=open'", isolated_context=False)
    page.get_by_role('heading', name='Open threads', exact=True).wait_for()
    rows = page.locator('.task-band .thread.mine')
    shared = rows.filter(has_text='Letter of Support draft')
    assert shared.count() == 1
    assert shared.locator('.who a').inner_text() == 'Mara Ostrowski'
    assert shared.locator('.also-on').inner_text() == 'Also on Tomás Reyes'
    assert page.locator('#nav a[href="#view=open"] .n.waiting').inner_text() == str(rows.count())
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path / 'deduped-open.png'), full_page=True)
    shared.locator('.also-on a').click()
    page.get_by_role('heading', name='Tomás Reyes', exact=True).wait_for()

def test_morning_keeps_separate_people_with_the_same_kind_of_request(reader):
    page, _ = reader
    assert page.evaluate(r"""() => {
      const people = ['people/mara-ostrowski.md', 'people/tomas-reyes.md', 'people/ines-halvorsen.md'].map(byPath);
      const entries = people.map(r => ({r, t: {text: 'You owe ' + r.title + ' a reply [1].', dir: 'mine', quiet: false}}));
      REM.today_queue = entries.map(entry => ({key: doneKey(entry), section: 'morning'}));
      return morningEntries(entries).length;
    }""", isolated_context=False) == 3


@pytest.fixture
def session_reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem import reader as rem_reader

    root = tmp_path / "rem"
    prepare(root)
    book = Notebook(root)
    book.stub_project("projects/alpha.md", "Alpha", ["/work/alpha"])
    book.stub_project("projects/beta.md", "Beta", ["/work/beta"])
    sessions = [
        ("release", "Release the reader", "alpha", "Codex", "2026-10-16", "Ship the new list", "### Cloud SQL rollout\n> Configured the reader.",
         "Shipped a searchable reader with stable focus.", "reader, search", "done"),
        ("citations", "Plan source citations", "beta", "Claude Code", "2026-10-15", "Look at sources", "The citation plan is drafted.",
         "Outlined citations and their next steps.", "reader, notes", "partial"),
        ("chinese", "检查仓库", "alpha", "Claude Code", "2026-10-16", "整理仓库里的文件", "仓库已整理。", "", "", ""),
        ("late", "Check the deployment", "alpha", "Codex", "2026-10-12", "Verify deployment", "All good. " * 50 + "A late needle is searchable.", "", "", ""),
        ("older", "Review older notes", "beta", "Claude Code", "2026-09-01", "Review old notes", "The old notes are reviewed.", "", "", ""),
        ("loose", "Explore an idea", "", "Codex", "2026-10-11", "Explore an idea", "An idea worth revisiting.", "", "", ""),
    ]
    for key, title, project, agent, day, typed, reply, summary, tags, outcome in sessions:
        project_fact = f"[{project.title()}](../projects/{project}.md)" if project else "/work/scratch"
        structure = f"## Summary\n{summary}\n\n" if summary else ""
        facts = f"- Tags: {tags}\n- Outcome: {outcome}\n- Started with: {typed}\n" if summary else ""
        turns = 12 if key == "release" else 1
        conversation = f"### 09:12\n> {typed}\n"
        artifacts = ""
        if key == "release":
            conversation += "".join(
                f"### 09:{12 + i:02d}\n> " + ("Avery will check seventhneedle and <img src=x onerror=alert(1)> seventhneedle."
                                               if i == 6 else f"Reader message {i + 1}: keep the page useful.") + "\n\n"
                for i in range(1, 12)
            )
            reply = (reply + "\n" + "Detailed reader guidance. " * 130)[:3000]
            artifacts = ("## Decisions\n- “keep the page useful.” (09:13)\n\n"
                         "## Follow-ups\n- Ask [Avery](../people/avery.md) to check the reader.\n\n"
                         "## Artifacts\n- Pull requests: https://github.com/openonion/connectonion/pull/123\n"
                         "- Commits: `abc123def` Lead with the session summary (reader-structure)\n"
                         "- Branches: reader-structure\n- Files changed (3): reader.html, sessions.py, reader_test.py\n"
                         "- Commands: 2 run; notable: `gcloud sql instances list`; `python -m pytest`\n\n")
        book.write(f"sessions/{key}.md", f"# {title}\n\n{structure}## Facts\n- Date: {day}\n- Agent: {agent}\n"
                   f"- Project: {project_fact}\n- Folder: /work/{project or 'scratch'}\n- Session: {key}\n- Turns: {turns}\n{facts}\n"
                   f"{artifacts}## What you typed\n{conversation}\n## Final reply\n"
                   + "\n".join("> " + line for line in reply.split("\n")) + "\n\n## Sources\n- metadata-only-secret\n- codex:release:1\n")
    book.write("people/avery.md", "# Avery\n\n## Facts\n")
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    original = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        data = original(root, local)
        data["as_of"] = "2026-10-15T14:30:00+00:00"  # Already Friday in the notebook.
        data["status"]["timezone"] = "Australia/Sydney"
        next(r for r in data["records"] if r["path"] == "people/avery.md")["session_mentions"] = ["sessions/release.md", "sessions/citations.md"]
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path = tmp_path / "sessions.html"
    path.write_text(rem_reader.render(root), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(path.as_uri() + "#c=sessions")
        yield page, path.as_uri()
        browser.close()
        assert not errors, errors


@pytest.mark.parametrize("width", [1400, 375])
def test_sessions_search_keeps_focus_and_bookmarks_full_reply(session_reader, width):
    from urllib.parse import parse_qs
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 812})
    page.goto("about:blank")
    page.goto(uri + "#c=sessions")
    box = page.get_by_role("searchbox", name="Search sessions")
    assert box.evaluate("node => node === document.activeElement") == (width == 1400)
    expect(page.locator("h1")).to_have_text("6 sessions · What you worked on with your coding agents")
    expect(page.locator(".session-result-line")).to_have_count(0)
    assert "Imported" not in page.locator("#main").inner_text()
    box.press_sequentially("cloud sql", delay=150)
    expect(page).to_have_url(re.compile(r"find=cloud(?:%20|\+)sql$"))
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    assert box.evaluate("node => node === document.activeElement && node.selectionStart === 9")
    assert parse_qs(page.evaluate("location.hash.slice(1)"))["find"] == ["cloud sql"]
    assert page.locator(".session-excerpt mark").all_text_contents() == ["Cloud", "SQL"]
    expect(page.locator(".session-speaker")).to_have_text("Agent: ")
    assert "find=cloud%20sql" in page.locator(".session-title").get_attribute("href")
    page.reload()
    expect(box).to_have_value("cloud sql")
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    box.fill("仓库")
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    expect(page.locator(".session-title")).to_have_text("Still being summarised · 检查仓库")
    box.fill("整理 文件")
    expect(page.locator(".session-speaker")).to_have_text("You: ")
    assert page.locator(".session-excerpt mark").all_text_contents() == ["整理", "文件"]
    box.fill("searchable focus")
    expect(page.locator(".session-title")).to_have_text("Release the reader")
    expect(page.locator(".session-excerpt")).to_contain_text("Shipped a searchable reader with stable focus.")
    box.fill("late needle")
    expect(page.locator(".session-title")).to_have_text("Still being summarised · Check the deployment")
    expect(page.locator(".session-speaker")).to_have_text("Agent: ")
    box.fill("metadata-only-secret")
    expect(page.locator(".empty .lead")).to_have_text("No session matches")
    expect(page.locator(".empty p")).to_contain_text("metadata-only-secret")
    page.get_by_role("button", name="Clear", exact=True).click()
    expect(box).to_have_value("")
    expect(page.locator(".session-result-line")).to_have_count(0)
    expect(page.locator(".session-row")).to_have_count(6)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_sessions_link_filters_person_topic_project_and_dates_stay_honoured(session_reader):
    """Topic chips and date pickers left the list (one search, four tabs); links into it still filter."""
    from patchright.sync_api import expect

    page, uri = session_reader
    assert page.locator(".session-topics, .session-filter-panel, .session-tags").count() == 0
    expect(page.locator(".session-excerpt")).to_have_count(0)
    page.goto(uri + "#c=sessions&person=people%2Favery.md")
    expect(page.locator(".session-result-line")).to_contain_text("2 of 6 sessions")
    page.get_by_role("button", name="Mentioning Avery ×").click()
    expect(page.locator(".session-result-line")).to_have_count(0)
    assert "person=" not in page.url
    page.goto(uri + "#c=sessions&tag=search")
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    page.goto(uri + "#c=sessions&project=projects%2Falpha.md&agent=codex")
    expect(page.locator(".session-result-line")).to_contain_text("2 of 6 sessions")
    expect(page.locator(".session-tabs").get_by_role("button", name="Codex", exact=True)).to_have_attribute("aria-pressed", "true")
    page.goto(uri + "#c=sessions&when=week")
    expect(page.locator(".session-result-line")).to_contain_text("4 of 6 sessions")
    page.goto(uri + "#c=sessions&from=2026-10-11&to=2026-10-12")
    expect(page.locator(".session-result-line")).to_contain_text("2 of 6 sessions")
    expect(page.locator(".session-day")).to_have_count(2)
    page.goto(uri + "#c=sessions&project=none")
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    expect(page.locator(".session-meta")).to_have_text("work/scratch · 1 turn")
    page.get_by_role("button", name="Clear", exact=True).click()
    expect(page.locator(".session-row")).to_have_count(6)


def test_sessions_typing_renders_three_hundred_rows_under_fifty_ms(session_reader):
    from patchright.sync_api import expect

    page, _ = session_reader
    page.evaluate("""() => {
      const originals = REM.records.filter(r => r.category === 'sessions');
      for (let i = 0; i < 294; i++) REM.records.push({...originals[i % 6], path: 'sessions/copy-' + i + '.md', session_title: originals[i % 6].session_title + ' ' + i});
      render();
      window.sessionDurations = [];
      const replace = history.replaceState.bind(history);
      history.replaceState = (...args) => { window.sessionStarted = performance.now(); replace(...args); };
      new MutationObserver(() => {
        if (window.sessionStarted) {
          document.getElementById('session-results').getBoundingClientRect();
          sessionDurations.push(performance.now() - sessionStarted); window.sessionStarted = 0;
        }
      }).observe(document.getElementById('session-results'), {childList: true});
    }""", isolated_context=False)
    expect(page.locator(".session-row")).to_have_count(60)  # a page of rows; the rest one click away
    page.get_by_role("searchbox", name="Search sessions").press_sequentially("cloud sql", delay=160)
    expect(page).to_have_url(re.compile(r"find=cloud(?:%20|\+)sql$"))
    expect(page.locator(".session-result-line")).to_contain_text("50 of 300 sessions")
    durations = page.evaluate("sessionDurations", isolated_context=False)
    assert len(durations) == 9
    # The first keystroke builds each session's search text once.
    assert max(durations[1:]) < 50 and durations[0] < 200, durations


def test_sessions_unstructured_notebooks_say_they_are_still_being_summarised(session_reader):
    from patchright.sync_api import expect

    page, _ = session_reader
    page.evaluate("""() => {
      for (const r of REM.records.filter(r => r.category === 'sessions')) {
        r.session_summary = ''; r.session_tags = []; r.session_outcome = '';
      }
      render();
    }""", isolated_context=False)
    expect(page.locator(".session-row.pending")).to_have_count(6)
    expect(page.locator(".session-title").first).to_contain_text("Still being summarised · ")
    expect(page.locator(".session-stopped")).to_have_count(0)
    expect(page.get_by_role("searchbox", name="Search sessions")).to_be_visible()


@pytest.mark.parametrize("width", [1400, 375])
def test_session_page_structure_precedes_closed_conversation(session_reader, width):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 812})
    page.goto(uri + "#r=sessions%2Frelease.md")
    expect(page.locator("h1")).to_have_text("Release the reader")
    # f2484e00: the transcript is visible between the summary and structured outcomes.
    transcript = page.get_by_role("region", name="Codex session transcript")
    expect(transcript).to_be_visible()
    assert page.locator('.session-attachment, .session-outline').count() == 0
    for heading in ("Summary", "Decisions", "Follow-ups", "Artifacts"):
        node = page.get_by_role("heading", name=heading, exact=True)
        expect(node).to_be_visible()
        if heading == 'Summary':
            assert node.bounding_box()["y"] < transcript.bounding_box()["y"]
        else:
            assert node.bounding_box()["y"] > transcript.bounding_box()["y"] + transcript.bounding_box()["height"]
    expect(page.locator(".session-facts-line")).to_contain_text("09:12 · Codex · Alpha · 12 turns · Done")
    assert page.locator(".session-page .status, .session-page .toc, .session-page .record-focus").count() == 0
    expect(page.locator(".session-followups a")).to_have_attribute("href", "#r=people%2Favery.md")
    pr = page.locator(".session-artifacts a")
    expect(pr).to_have_attribute("target", "_blank")
    expect(pr).to_have_attribute("rel", "noopener")
    page.locator(".session-artifacts summary").filter(has_text="Files changed (3)").click()
    expect(page.locator(".session-artifacts details").first.locator("li")).to_have_count(3)
    page.get_by_role("link", name="09:13", exact=True).click()
    expect(page.locator('.session-turn.owner-turn')).to_have_count(12)
    expect(page.locator("#session-message-2")).to_be_in_viewport()
    expect(page.locator("#session-message-2")).to_have_class(re.compile(r'\bsession-cited\b'))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1400, 375])
def test_session_find_outline_and_long_reply(session_reader, width):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 812})
    page.goto(uri + "#r=sessions%2Frelease.md&find=seventhneedle")
    expect(page.locator(".session-find-status")).to_have_text("1 of 2")
    expect(page.locator('.session-device')).to_be_visible()
    expect(page.get_by_role("searchbox", name="Find in this conversation")).to_have_value("seventhneedle")
    expect(page.locator(".session-turn mark")).to_have_count(2)
    assert page.locator(".session-turn img").count() == 0
    current = page.locator("mark.current")
    expect(current).to_be_in_viewport()
    page.get_by_role("button", name="Next match", exact=True).click()
    expect(page.locator(".session-find-status")).to_have_text("2 of 2")
    box = page.get_by_role("searchbox", name="Find in this conversation")
    box.press("Shift+Enter")
    expect(page.locator(".session-find-status")).to_have_text("1 of 2")
    box.press("Enter")
    expect(page.locator(".session-find-status")).to_have_text("2 of 2")
    box.fill("guidance")
    expect(page.locator("#session-final mark").first).to_be_visible()
    box.press("Shift+Enter")
    expect(page.locator("#session-final mark.current")).to_be_in_viewport()
    assert len(page.locator("#session-final .session-quote").inner_text()) == 3000
    box.fill("")
    expect(page.locator(".session-transcript mark")).to_have_count(0)
    assert len(page.locator("#session-final .session-quote").inner_text()) == 3000
    # The visible transcript keeps complete replies and supports direct turn links.
    page.goto(uri + "#r=sessions%2Frelease.md")
    expect(page.get_by_role("button", name="Next match", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Previous match", exact=True)).to_be_disabled()
    expect(page.locator('.session-turn.owner-turn')).to_have_count(12)
    page.goto(uri + '#r=sessions%2Frelease.md&h=session-message-7')
    expect(page.locator('#session-message-7')).to_be_in_viewport()
    reply = page.locator("#session-final .session-quote")
    assert len(reply.inner_text()) == 3000
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_session_neighbours_and_remembered_list(session_reader):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.goto(uri + "#c=sessions&project=projects%2Falpha.md&tag=reader")
    saved = page.evaluate("location.hash")
    page.locator(".session-title").click()
    expect(page.locator(".session-page .eyebrow a").first).to_have_attribute("href", saved)
    page.locator(".session-neighbours a").filter(has_text="Older:").click()
    expect(page.locator("h1")).to_have_text("检查仓库")
    expect(page.locator(".session-neighbours")).to_contain_text("Older: Check the deployment")
    expect(page.locator(".session-neighbours")).to_contain_text("Newer: Release the reader")
    page.locator(".session-neighbours a").filter(has_text="Newer:").click()
    expect(page.locator("h1")).to_have_text("Release the reader")
    page.locator(".session-page .eyebrow a").first.click()
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    page.goto(uri + "#r=sessions%2Flate.md")
    expect(page.locator(".session-summary")).to_contain_text("Not summarised yet — Verify deployment")


def test_session_project_person_and_global_search_cross_links(session_reader):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.evaluate("""() => {
      const original = REM.records.find(r => r.path === 'sessions/release.md');
      for (let i = 0; i < 9; i++) REM.records.push({...original, path: 'sessions/extra-' + i + '.md'});
      REM.records.find(r => r.path === 'people/avery.md').session_mentions =
        REM.records.filter(r => r.category === 'sessions').map(r => r.path);
    }""", isolated_context=False)
    page.evaluate("location.hash = '#r=projects%2Falpha.md'", isolated_context=False)
    rows = page.locator(".project-sessions .session-context-row")
    expect(rows).to_have_count(10)
    expect(rows.first.locator(".session-context-summary")).to_have_text("Shipped a searchable reader with stable focus.")
    expect(rows.first.locator(".session-tags a")).to_have_count(2)
    page.locator(".project-sessions").get_by_role("link", name="All 12 sessions", exact=True).click()
    expect(page.locator(".session-result-line")).to_contain_text("12 of 15 sessions")
    assert "project=projects%2Falpha.md" in page.url
    page.evaluate("location.hash = '#r=people%2Favery.md'", isolated_context=False)
    mentions = page.locator(".person-sessions")  # under the timeline, not inside the full note
    expect(mentions.get_by_role("heading", name="Mentioned in sessions")).to_be_visible()
    expect(mentions.locator(".session-context-row")).to_have_count(3)  # a widget: three rows, then All 15 sessions
    expect(mentions.get_by_role("link", name="All 15 sessions", exact=True)).to_have_attribute("href", "#c=sessions&person=people%2Favery.md")
    mentions.locator(".session-context-row a").first.click()
    expect(page.get_by_role("searchbox", name="Find in this conversation")).to_have_value("Avery")
    page.evaluate("location.hash = '#q=seventhneedle'", isolated_context=False)
    group = page.locator("h2.group").filter(has_text="Agent sessions")
    expect(group).to_be_visible()
    expect(group.locator(".n")).to_have_text("10")
    expect(page.locator(".hits li")).to_have_count(8)
    all_hits = page.get_by_role("link", name="10 matching sessions →", exact=True)
    expect(all_hits).to_have_attribute("href", "#c=sessions&find=seventhneedle")
    expect(page.locator(".hits .t a").first).to_have_attribute("href", re.compile(r"&find=seventhneedle$"))
    all_hits.click()
    expect(page.locator(".session-result-line")).to_contain_text("10 of 15 sessions")


@pytest.mark.parametrize("width", [1400, 390])
def test_sessions_real_data_list_order_and_artifact_search(session_reader, width):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 844})
    page.goto(uri + "#c=sessions")
    search = page.get_by_role("searchbox", name="Search sessions")
    assert page.locator("h1").bounding_box()["y"] < search.bounding_box()["y"]
    assert page.locator(".session-tabs").bounding_box()["y"] >= search.bounding_box()["y"]
    search.fill("no-such-session")
    expect(page.locator(".empty .lead")).to_have_text("No session matches")
    for query in ("gcloud sql", "abc123def", "reader-structure", "github.com/openonion/connectonion/pull/123"):
        search.fill(query)
        expect(page.locator(".session-title")).to_have_text("Release the reader")
        expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_session_source_deep_link_reveals_details(session_reader):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.goto(uri + "#r=sessions%2Frelease.md&h=src-1")
    # f2484e00: an archived message source lands on its transcript turn.
    expect(page.locator('#session-message-1')).to_be_in_viewport()
    expect(page.locator('#session-message-1')).to_have_class(re.compile(r'\bsession-cited\b'))
    # Unmatched source rows still open Details instead of remaining hidden.
    page.goto(uri + '#r=sessions%2Frelease.md&h=src-99')
    assert not page.locator('.session-details').evaluate('node => node.open')
    page.evaluate("() => { byPath('sessions/release.md').session_messages.forEach(m => m.source = ''); }", isolated_context=False)
    page.goto(uri + '#r=sessions%2Frelease.md&h=src-1')
    expect(page.locator('#src-1')).to_be_in_viewport()
    assert page.locator('.session-details').evaluate('node => node.open')


def test_inline_quotes_keep_marks_sources_and_private_words(reader):
    page, _ = reader
    result = page.evaluate(r'''() => {
      const node = el('p', {html: inline('She said “send **the export** [1] today” [2]. Then "review this". `"leave code alone"`', 'people/mara-ostrowski.md')});
      document.getElementById('main').appendChild(node);
      const said = node.querySelector('.said');
      said.querySelector('strong').innerHTML = '<mark>the</mark> export';
      const prose = said.cloneNode(true); prose.querySelectorAll('.cite').forEach(c => c.remove());
      return [node.querySelectorAll('.said').length, prose.textContent.replace(/\u2060/g, ''), said.querySelectorAll('.cite').length,
        node.querySelectorAll('a.cite').length, said.querySelector('mark').textContent, node.querySelector('code .said') === null,
        supportingSpan('She said “send the signed form”.', 'Please send the signed form today.')];
    }''', isolated_context=False)
    assert result[:6] == [2, '“send the export today”', 1, 2, 'the', True]
    assert result[6] == {'claim': [10, 30], 'source': [7, 27]}


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_reader_settings_disclose_private_controls_and_wrap_command(reader, width, theme):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=people%2Favery-lin.md')
    page.evaluate('theme => document.documentElement.dataset.theme = theme', theme)
    if width == 390:
        assert page.locator('h1').bounding_box()['y'] <= 140
        page.locator('.nav-toggle').click()
    settings = page.locator('.reader-settings')
    assert not settings.evaluate('node => node.open')  # the settings sheet is closed until asked for
    assert not page.locator('#privacy-toggle').is_visible()
    assert 'Updated ' in page.locator('#foot').inner_text()  # the render time (2026-11-09; was "Snapshot")
    assert 'Background updates off' not in page.locator('#foot').inner_text()
    page.locator('.settings-open').click()
    assert settings.locator('code, .cmd').count() == 0  # D-60 (build 3b review): Reader settings states things in words, never a command to copy.
    assert page.locator('#privacy-toggle').is_visible()
    assert 'Nightly updates are off.' in settings.inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('labelled', ['Private conversation. [personal] [1]', 'Private conversation [personal]. [1]'])
def test_summary_omits_empty_relationship_history_and_unknown_facts(reader, labelled):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''labelled => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = '# Mara Ostrowski\n\nA fixture contact.\n\n## Facts\n- Phone: Unknown\n- Role: —\n- Location: unknown\n- First contact: Unknown\n- Last contact: Unknown\n'
        + '\n## Open threads\nNothing open as of 2026-10-01.\n'
        + '\n## Insight\n- Now: Confidential status. [sensitive] [1]\n'
        + '\n## History\n- 2026-09-25: ' + labelled + '\n- 2026-09-26: [1]\n'
        + '\n## Sources\n- [1] test:fixture\n';
      delete r.original; delete r.translations;
      delete r.mail; delete r.index; r.last_activity = '';
      r.organisations = []; r.units = []; r.facts = {};
      KNOWN.clear(); FACTS.clear(); render();
      document.documentElement.classList.add('hide-private');
    }''', labelled, isolated_context=False)
    assert page.locator('.r4-person #open-threads').count() == 0 and page.locator('.r4-today').count() == 0
    assert page.locator('.tl > li.tl-e:visible').count() == 0
    assert page.locator('#history-timeline .private-history-notice').inner_text() == '1 private entry hidden'
    assert page.locator('.hero-acts .round[aria-label^="Phone"]').count() == 0
    assert page.locator('.r4-sub').count() == 0  # Role "—" and no company: no invented subtitle
    assert page.locator('.r4-stats > div').count() == 0  # no mail and unknown dates: the first exchange sits under the rhythm
    page.locator('details.deep-note > summary').click()
    assert page.locator('.factlist').count() == 0
    assert page.locator('.timeline > li:visible').count() == 0
    assert page.locator('.block-history .private-history-notice').inner_text() == '1 private entry hidden'
    page.evaluate('togglePrivate()', isolated_context=False)
    assert page.locator('.tl > li.tl-e:visible').count() == 1
    assert not page.locator('#history-timeline .private-history-notice').is_visible()


def test_org_collapses_full_memory_and_omits_self_provenance(reader):
    page, uri = reader
    page.goto(uri + '#r=orgs%2Ffernhill-labs.md')
    page.evaluate('''() => {
      const r = byPath('orgs/fernhill-labs.md');
      r.relations = [{path: 'people/mara-ostrowski.md', via: r.path, kind: 'linked', basis: 'Pilot contact', sources: ['1']}];
      render();
    }''', isolated_context=False)
    assert not page.locator('details.deep-note').evaluate('node => node.open')
    assert re.search(r'\d+ sections · \d+ sources', page.locator('.deep-hint').inner_text())
    page.locator('details.deep-note > summary').click()
    provenance = page.locator('.relation-provenance')
    assert provenance.locator('a:not(.cite)').count() == 0
    assert provenance.locator('a.cite').count() == 1
    assert page.locator('.deep-note .note').is_visible()


@pytest.mark.parametrize('width', [1440, 390])
def test_last_pass_band_has_equal_insets_and_complete_trace_in_both_views(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    # More than 2,400 path units: the old fixed dash pattern cut off later runs.
    page.evaluate('''() => {
      REM.as_of = '2026-10-01T12:00:00Z';
      REM.logs = Array.from({length: 16}, (_, i) => ({
        run_id: 'fixture-' + i, started_at: new Date(Date.UTC(2026, 9, 1, 0, i * 30)).toISOString(),
        seconds: 60, outcome: 'done', items: 100, changed: ['people/avery-lin.md']
      })); render();
    }''', isolated_context=False)
    for fragment in ('', '#view=activity'):
        page.evaluate('fragment => { location.hash = fragment; render(); }', fragment, isolated_context=False)
        if not fragment:
            page.locator('#processing > summary').click()
        band = page.locator('.night').first
        main_box, box = page.locator('#main').bounding_box(), band.bounding_box()
        assert abs((box['x'] - main_box['x']) - (main_box['x'] + main_box['width'] - box['x'] - box['width'])) <= 1
        assert band.locator('.night-head a').count() == (0 if fragment else 1)
        trace = band.locator('.trace')
        assert trace.evaluate('node => node.getTotalLength()') > 2400
        assert trace.get_attribute('pathLength') == '1'
        assert trace.get_attribute('d').endswith('L996,14')
        # Finish its animation; normalised dashes must cover every path segment.
        trace.evaluate("node => node.getAnimations().forEach(a => a.finish())")
        assert trace.evaluate("node => getComputedStyle(node).strokeDashoffset") == '0px'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_search_marks_do_not_split_words_and_counts_align(reader, theme):
    page, uri = reader
    page.goto(uri + '#q=pilot')
    page.evaluate('theme => document.documentElement.dataset.theme = theme', theme)
    mark = page.locator('mark').first
    assert mark.evaluate('node => getComputedStyle(node).paddingLeft') == '0px'
    assert mark.evaluate('node => getComputedStyle(node).paddingRight') == '0px'
    for group in page.locator('.search-group').all():
        heading, results = group.locator('h2').bounding_box(), group.locator('.hits').bounding_box()
        assert abs(heading['x'] + heading['width'] - results['x'] - results['width']) <= 1


def test_project_has_one_boundary_rule_and_quiet_purpose_sources(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate(r"""() => { const r = byPath('projects/harbour.md'); r.text += '\n\n## Uncertainties\n- Pilot size is not confirmed. [1]'; KNOWN.clear(); render(); }""", isolated_context=False)
    assert page.locator('.record-focus.projects .focus-head').evaluate('node => getComputedStyle(node).borderBottomWidth') == '0px'
    for node in page.locator('.record-focus.projects .focus-facts, .record-focus.projects .thread:last-child').all():
        assert node.evaluate('node => getComputedStyle(node).borderBottomWidth') == '0px'
    sources = page.locator('.project-purpose-cites')
    assert sources.locator('.unsure').count() == 1
    chip = sources.locator('a.cite').first
    assert chip.evaluate('node => getComputedStyle(node).fontSize') == '11px'
    assert chip.evaluate('node => getComputedStyle(node).fontVariantCaps') == 'normal'
    assert chip.bounding_box()['height'] < 30


@pytest.mark.parametrize('last_word', ['citation', 'longword' * 80], ids=['ordinary-word', 'long-word'])
@pytest.mark.parametrize('context', ['prose', 'timeline', 'activity-list'])
def test_long_source_citation_tip_stays_inside_375px_viewport(reader, last_word, context):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate('''lastWord => {
      const r = byPath('people/mara-ostrowski.md');
      r.text += '\\n\\n## Long source\\n- [99] ' + 'unbroken'.repeat(80) + ':fixture';
      CITES.sources['99'] = 'unbroken'.repeat(80) + ':fixture';
      document.getElementById('main').prepend(el('p', {id: 'long-source', html: inline('A fixture ' + lastWord + ' [99].', r.path)}));
    }''', last_word, isolated_context=False)
    if context != 'prose':
        page.locator('#long-source').evaluate('(node, context) => node.className = context', context)
    cite = page.locator('#long-source .cite')
    assert cite.inner_text() == 'source 99'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    cite.focus()
    tip = page.locator('#citation-tip')
    assert tip.is_visible()
    box = tip.bounding_box()
    assert box['x'] >= 12 and box['x'] + box['width'] <= 363
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    cite.click()
    assert page.locator('#evidence-panel').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('context', ['timeline', 'activity-list'])
def test_long_dated_source_label_can_wrap_beside_its_word(reader, context):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate('''context => {
      const r = byPath('people/mara-ostrowski.md');
      const source = 'gmail:long-sender-fixture';
      CITES.sources['99'] = source;
      REM.source_context[source] = {source: 'gmail', time: '2026-10-01',
        sender: 'Longname'.repeat(80) + ' <fixture@example.test>'};
      document.getElementById('main').prepend(el('div', {id: 'long-dated-source', class: context}, [
        el('p', {html: inline('A fixture citation [99].', r.path)})]));
    }''', context, isolated_context=False)
    cite = page.locator('#long-dated-source .cite')
    assert len(cite.inner_text()) > 600  # Keep exercising a full dated label.
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    cite.focus()
    assert page.locator('#citation-tip').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    cite.click()
    assert page.locator('#evidence-panel').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_source_context_focus_loop_skips_disabled_hidden_and_negative_tabindex(reader):
    page, uri = reader
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.locator('details.deep-note').evaluate('d => d.open = true')
    page.locator('.block-insight .cite').first.click()
    page.evaluate('''() => {
      const panel = document.getElementById('evidence-panel');
      panel.insertAdjacentHTML('beforeend', '<button id="enabled-last">Enabled last</button>' +
        '<button disabled>Disabled</button><button tabindex="-1">Programmatic</button>' +
        '<button aria-hidden="true">Aria hidden</button><div aria-hidden="true"><button>Hidden ancestor</button></div>' +
        '<button hidden>Hidden</button><a>No href</a><input type="hidden"><button style="visibility:hidden">Invisible</button>');
    }''', isolated_context=False)
    close = page.get_by_role('button', name='Close source context')
    close.focus()
    page.keyboard.press('Shift+Tab')
    assert page.locator('#enabled-last').evaluate('node => node === document.activeElement')
    page.keyboard.press('Tab')
    assert close.evaluate('node => node === document.activeElement')


@pytest.mark.parametrize('path', ['people/avery-lin.md', 'people/mara-ostrowski.md', 'orgs/fernhill-labs.md', 'projects/harbour.md'])
@pytest.mark.parametrize('width', [375, 390])
def test_record_heading_is_visible_within_compact_mobile_chrome(reader, path, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=' + path.replace('/', '%2F'))
    assert page.locator('h1').bounding_box()['y'] <= 140
    assert page.locator('.nav-toggle').is_visible()
    assert page.locator('#tabbar .tab-search').is_visible()  # N3: search is a tab on a phone
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_quote_styling_preserves_private_boundaries_and_existing_marks(reader):
    page, _ = reader
    page.evaluate('''() => {
      const path = 'people/mara-ostrowski.md';
      const node = el('section', {id: 'quote-privacy-check'}, [
        el('p', {html: inline('She said “keep this confidential [1] please”. [personal] [2] Public follow-up.', path)}),
        el('p', {html: quoteSpans('“keep <mark>these</mark> original words”')}),
        el('p', {html: quoteSpans('<span class="private">“Private opening. </span>Public ending.”')})]);
      document.getElementById('main').appendChild(node);
    }''', isolated_context=False)
    quotes = page.locator('#quote-privacy-check')
    assert quotes.locator('.said mark').inner_text() == 'these'
    assert quotes.locator('p').first.locator('.said .cite').count() == 1
    page.evaluate("document.documentElement.classList.add('hide-private')")
    assert 'keep this confidential' not in quotes.inner_text()
    assert 'Public follow-up.' in quotes.inner_text()
    assert 'Public ending.' in quotes.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert 'keep this confidential' in quotes.inner_text()


@pytest.mark.parametrize('motion', ['no-preference', 'reduce'])
def test_activity_chart_line_is_complete_within_300ms(reader, motion):
    page, uri = reader
    page.emulate_media(reduced_motion=motion)
    page.goto(uri + '#view=activity', wait_until='domcontentloaded')
    page.wait_for_function('''() => {
      const path = document.querySelector('.hypno .trace');
      if (!path) return false;
      const style = getComputedStyle(path);
      return parseFloat(style.strokeDashoffset) === 0 && style.strokeDasharray === 'none';
    }''', timeout=300)
    assert page.locator('.hypno .trace').first.evaluate(
        "node => getComputedStyle(node).animationName") == 'none'


@pytest.mark.parametrize('path', ['orgs/fernhill-labs.md', 'projects/harbour.md'])
@pytest.mark.parametrize('width', [1440, 390])
def test_activity_discloses_five_complete_rows_and_filters(reader, path, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=' + path.replace('/', '%2F'))
    page.evaluate(r'''path => {
      const r = byPath(path);
      r.text = r.text.replace(/\n## History\n[\s\S]*?(?=\n## |\nInvestigation:|$)/, '');
      r.text += '\n## History\n' + Array.from({length: r.category === 'orgs' ? 12 : 8}, (_, i) =>
        '- 2026-09-' + String(i + 1).padStart(2, '0') + ': ' +
        (i < 6 ? 'Agreed the plan. ' : 'Discussed the plan. ') + 'Complete history text. '.repeat(8)).join('\n');
      if (r.category === 'orgs') r.people = [];
      KNOWN.clear(); render();
    }''', path, isolated_context=False)
    if path.startswith('orgs/'):
        # Org's new Lately timeline shows eight complete rows, with older rows disclosed.
        rows = page.locator('.ov-tl .ov-e')
        assert rows.count() == 8
        assert all(text.count('Complete history text.') == 8 for text in rows.all_inner_texts())
        assert not page.locator('.ov-tl').evaluate('node => node.scrollHeight > node.clientHeight')
        page.get_by_role('button', name='Show all 12 entries', exact=True).click()
        assert rows.count() == 12
        assert all(text.count('Complete history text.') == 8 for text in rows.all_inner_texts())
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        return
    activity = page.locator('.activity-view')
    rows = activity.locator('.activity-list > li:visible')
    assert rows.count() == 5
    assert activity.locator('.activity-list').evaluate('node => node.scrollHeight <= node.clientHeight')
    assert all(text.count('Complete history text.') == 8 for text in rows.all_inner_texts())
    activity.get_by_role('button', name='Show all 8', exact=True).click()
    assert rows.count() == 8
    activity.get_by_role('button', name='Show less', exact=True).click()
    assert rows.count() == 5
    activity.get_by_role('button', name='Decision 6', exact=True).click()
    assert rows.count() == 5
    activity.get_by_role('button', name='Show all 6', exact=True).click()
    assert rows.count() == 6
    activity.get_by_role('button', name='Conversation 2', exact=True).click()
    assert rows.count() == 2
    assert not activity.locator('.activity-more').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_project_threads_only_label_explicit_direction_and_deduplicate_date(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate(r'''() => {
      const r = byPath('projects/harbour.md');
      r.text = r.text.replace(/\n## Open threads\n[\s\S]*?(?=\n## )/,
        '\n## Open threads\n- 2026-09-13: You asked to revisit a title. [1]\n' +
        '- 2026-09-14: Avery promised to send the draft. [1]\n' +
        '- 2026-09-15: Mara owes you feedback. [1]\n');
      KNOWN.clear(); render();
    }''', isolated_context=False)
    rows = page.locator('.next-exchanges .thread')
    assert rows.locator('.dir').all_inner_texts() == ['Open', 'You owe', 'They owe']
    assert rows.first.locator('.what').inner_text().startswith('You asked to revisit')
    assert '2026-09-13' not in rows.first.locator('.what').inner_text()
    assert 'since Sep 13' in rows.first.locator('.when').get_attribute('title')


@pytest.mark.parametrize('path', ['people/quinn-alder.md', 'skills/catalog/weekly-brief.md'])
@pytest.mark.parametrize('width', [1440, 390])
def test_mapped_guidance_explains_before_command_with_secondary_copy(reader, path, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=' + path.replace('/', '%2F'))
    box = page.locator('.missing.primary')
    # b1927e56: metadata pages explain their queue state without manual copy controls.
    assert box.locator(':scope > *').evaluate_all('nodes => nodes.map(n => n.className)') == ['lead', 'names']
    assert box.locator('.lead').inner_text() == 'Page pending — background updates off'
    assert box.locator('.names').inner_text().endswith('sections will be written when it is investigated.')
    assert box.locator('button, code').count() == 0
    page.evaluate("() => { REM.status.worker = {enabled: true}; render(); }", isolated_context=False)
    assert box.locator('.lead').inner_text() == 'Page queued for tonight'
    assert not page.locator('.focus-command').count()
    if path.startswith('people/'):
        assert page.locator('details.deep-note').get_attribute('open') is None
        assert page.locator('.deep-note .factlist').count() == 1
    else:
        assert page.locator('details.deep-note').get_attribute('open') is None
        assert page.locator('.focus-facts').count() == 0
        assert page.locator('.lead-meta.usage').count() == 1
        assert page.locator('.panel h3:text-is("Usage")').count() == 0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_quotes_are_visually_distinct_from_search_marks(reader, theme):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate('''theme => {
      document.documentElement.dataset.theme = theme;
      document.getElementById('main').appendChild(el('p', {id: 'quote-colour',
        html: quoteSpans('“These are <mark>original</mark> words”')}));
    }''', theme, isolated_context=False)
    quote = page.locator('#quote-colour .said')
    mark = quote.locator('mark')
    quote_background = quote.evaluate('node => getComputedStyle(node).backgroundColor')
    assert quote_background != mark.evaluate('node => getComputedStyle(node).backgroundColor')
    if theme == 'dark':
        # No tint of its own in dark: the quote sits on the paper and only its underline marks it.
        assert quote_background == page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert quote.evaluate('node => getComputedStyle(node).textDecorationLine') == 'underline'


def test_org_context_citation_is_flush_and_uncertainty_has_an_icon_gap(reader):
    page, uri = reader
    page.goto(uri + '#r=orgs%2Ffernhill-labs.md')
    page.evaluate(r'''() => {
      const r = byPath('orgs/fernhill-labs.md');
      r.relations = [{path: 'people/mara-ostrowski.md', kind: 'linked', via: r.path, sources: ['1']}];
      r.text += '\n## Uncertainties\n- Timing is unconfirmed. [1]\n';
      KNOWN.clear(); render();
    }''', isolated_context=False)
    page.locator('details.deep-note > summary').click()
    cite = page.locator('.relation-provenance .cite').first
    assert abs(cite.bounding_box()['x'] - page.locator('.relation-card strong').first.bounding_box()['x']) <= 1
    assert 'Timing is unconfirmed' in page.locator('.deep-note .note').inner_text()
    assert page.locator('.deep-note .uncertain-marker').count() >= 1


def test_mobile_header_focus_and_touch_targets_on_every_view(reader):
    page, uri = reader
    page.set_viewport_size({'width': 390, 'height': 844})
    for view in VIEWS:
        page.goto(uri + (view or '#'))
        for selector in ('#tabbar .tab-search', '.nav-toggle', '#tabbar .tab >> nth=0'):
            target = page.locator(selector)
            assert target.is_visible(), (view, selector)
            assert target.bounding_box()['height'] >= 40, (view, selector)
            target.focus()
            page.keyboard.press('Tab')
            page.keyboard.press('Shift+Tab')
            target.focus()  # keyboard modality is set; the last tab may leave the page from the tab bar
            # Whenever the browser shows keyboard focus on it, the ring is drawn.
            assert target.evaluate("node => !node.matches(':focus-visible') || getComputedStyle(node).outlineStyle !== 'none'"), (view, selector)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), view


@pytest.mark.parametrize('body', [
    'Unheaded prose remains in the full memory.',
    '```markdown\nSources: literal metadata\n[Read the draft](/tmp/draft.md)\n```',
    '[Read the draft](/tmp/draft.md)',
])
def test_full_memory_keeps_unheaded_content_and_counts_it(reader, body):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''body => {
      const r = byPath('people/mara-ostrowski.md');
      r.relations = [];
      r.text = '# Mara Ostrowski\n\n' + body;
      KNOWN.clear(); FACTS.clear(); render();
    }''', body, isolated_context=False)
    assert page.locator('.deep-hint').inner_text() == '2 sections · 0 sources'  # body and Facts
    page.locator('details.deep-note > summary').click()
    assert page.locator('.deep-note .note').inner_text().strip()
    assert page.locator('.deep-note .factlist').is_visible()


def test_full_memory_counts_content_without_counting_toc_navigation(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''() => {
      const r = byPath('people/mara-ostrowski.md');
      r.relations = [];
      r.text = '# Mara Ostrowski\n\n' + Array.from({length: 4}, (_, i) =>
        '## Topic ' + i + '\nUseful content.').join('\n\n');
      KNOWN.clear(); FACTS.clear(); render();
    }''', isolated_context=False)
    assert page.locator('.deep-hint').inner_text() == '5 sections · 0 sources'  # four topics and Facts
    page.locator('details.deep-note > summary').click()
    assert page.locator('.deep-note .toc-panel').is_visible()


def test_partial_project_status_explains_the_uninvestigated_sections(reader):
    page, uri = reader
    page.goto(uri + '#c=projects')
    page.evaluate(r'''() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\n\nInvestigation: not investigated yet.\n\n'
        + '## Insight\n- Now: awaiting review.\n\n## Current status\nUnknown — not investigated yet.';
      r.written = true;
      KNOWN.clear(); FACTS.clear(); render();
    }''', isolated_context=False)
    tooltip = 'Some sections are filled from sources; the rest are not investigated yet.'
    page.goto(uri + '#c=projects&v=list')
    page.evaluate('() => { pdQuietOpen = true; render(); }', isolated_context=False)
    row = page.locator('.pd-lrow[data-path="projects/harbour.md"]')
    assert row.locator('.pd-note').count() == 0  # REM wrote no line for it, and none is invented
    row.get_by_role('link', name='Harbour', exact=True).click()
    assert page.locator('.eyebrow .pill.status').inner_text() == 'More to learn'
    assert page.locator('.eyebrow .pill.status').get_attribute('title') == tooltip


@pytest.mark.parametrize('width', [1440, 390])
def test_quiet_lead_citations_stay_with_words_and_reveal_sources(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.locator('details.deep-note').evaluate('d => d.open = true')
    lead = page.locator('.deep-note .note > p').first
    assert lead.locator('.cite').count() > 0
    assert lead.evaluate(r'''node => {
      for (const cite of node.querySelectorAll('.cite')) {
        const tether = cite.closest('.cite-tether');
        if (!tether || tether.getClientRects().length !== 1) return false;
        const walker = document.createTreeWalker(tether, NodeFilter.SHOW_TEXT);
        let previous;
        while (walker.nextNode() && !cite.contains(walker.currentNode)) previous = walker.currentNode;
        if (!previous || !previous.textContent.trim()) return false;
        const word = document.createRange(); word.selectNodeContents(previous);
        const text = word.getBoundingClientRect(), marker = cite.getBoundingClientRect();
        // Both occupy the same prose line box, despite the marker's smaller raised font.
        if (marker.top >= text.bottom || marker.bottom <= text.top) return false;
        const next = cite.nextSibling;
        if (next?.nodeType === Node.TEXT_NODE && next.textContent.startsWith('.')) {
          const dot = document.createRange(); dot.setStart(next, 0); dot.setEnd(next, 1);
          if (Math.abs(dot.getBoundingClientRect().top - text.top) > 1) return false;
        }
      }
      return !/\s+\./.test(node.textContent);
    }''')
    marker = lead.locator('.cite').last
    label = marker.get_attribute('title')
    assert 'Source:' in label
    assert marker.inner_text() != label
    # This citation moved into Full memory. Finish its scroll before hovering:
    # scrolling deliberately dismisses existing tooltips.
    marker.scroll_into_view_if_needed()
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    marker.hover()
    assert page.get_by_role('tooltip').inner_text() == label
    marker.focus()
    assert page.get_by_role('tooltip').inner_text() == label
    marker.click()
    assert page.locator('#evidence-panel').is_visible()
    page.get_by_role('button', name='Close source context').click()
    assert marker.evaluate(r'e => e === document.activeElement')


def test_cjk_citation_tethers_do_not_bind_a_whole_sentence(reader):
    page, uri = reader
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''() => {
      const node = document.querySelector('.r4-sub');
      node.innerHTML = inline('这是一句较长的中文记录，用来检查引用标记始终与前面的文字在一起，同时允许句子在手机上自然换行而不会撑开整个页面 [5] .', 'people/mara-ostrowski.md');
    }''', isolated_context=False)
    assert page.locator('.r4-sub .cite-tether').inner_text().startswith('面')
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('notebook_languages, browser_language', [(['zh', 'en'], 'en-AU'), (['en', 'zh'], 'en-AU'), ([], 'zh-CN')])
def test_chinese_interface_default_switch_and_persistence(reader, tmp_path, monkeypatch, width, notebook_languages, browser_language):
    from connectonion.rem import reader as rem_reader
    page, _ = reader
    data = rem_reader.snapshot(tmp_path / 'rem', local=True)
    data['your_languages'] = notebook_languages
    page.add_init_script("Object.defineProperty(navigator, 'language', {value: " + repr(browser_language) + "});")
    monkeypatch.setattr(rem_reader, 'snapshot', lambda root, local=False, today=False: data)
    path = tmp_path / 'chinese-reader.html'
    path.write_text(rem_reader.render(tmp_path / 'rem', local=True), encoding='utf-8')
    page.evaluate(r'''() => localStorage.removeItem('co-rem-ui-language')''')
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(path.as_uri() + '#r=people%2Fmara-ostrowski.md')
    page.wait_for_function(r'document.documentElement.lang === "zh"')
    if width < 600:
        page.locator('.nav-toggle').click()  # N3: the phone's 更多 tab opens every place
    assert page.locator('#nav a[href="#c=people"]').get_attribute('aria-label') == '人物'
    prose = r'''node => {
      const copy = node.cloneNode(true); copy.querySelectorAll('.cite').forEach(n => n.remove());
      return copy.textContent;
    }'''
    page.locator('details.deep-note').evaluate('d => d.open = true')
    original = page.locator('.deep-note .note > p').first.evaluate(prose)
    assert page.locator('.r4-said h2').inner_text().startswith('对方说过的话')  # never assumes the person's gender
    page.locator('.settings-open').click()
    page.locator('.language-switch').get_by_role('button', name='EN', exact=True).click()
    page.keyboard.press('Escape')
    assert page.locator('#nav a[href="#c=people"]').get_attribute('aria-label') == 'People'
    page.locator('details.deep-note').evaluate('d => d.open = true')
    assert page.locator('.deep-note .note > p').first.inner_text() != ''
    page.locator('details.deep-note').evaluate('d => d.open = true')
    assert page.locator('.deep-note .note > p').first.evaluate(prose) == original
    page.reload()
    page.wait_for_function(r'document.documentElement.lang === "en"')
    if width < 600:
        page.locator('.nav-toggle').click()
    page.locator('.settings-open').click()
    page.locator('.language-switch').get_by_role('button', name='中文', exact=True).click()
    page.keyboard.press('Escape')
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')
    if width < 600:
        page.locator('.nav-toggle').click()
    page.locator('#nav a[href="#c=people"]').click()
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')
    # Avoid sharing this deliberate preference with another file:// fixture test.
    page.evaluate(r'''() => localStorage.removeItem('co-rem-ui-language')''')


def test_org_avoids_repeating_header_threads_and_context_snippets(reader):
    page, uri = reader
    page.goto(uri + '#r=orgs%2Ffernhill-labs.md')
    page.evaluate(r'''() => {
      const r = byPath('orgs/fernhill-labs.md');
      r.relations = ['people/mara-ostrowski.md', 'people/quinn-alder.md', 'people/tomas-reyes.md'].map(path => ({
        path, kind: 'linked', basis: 'Your contacts: Mara, Quinn and Tomás.', via: r.path, sources: ['1']
      }));
      render();
    }''', isolated_context=False)
    assert page.locator('.leadrow .lead-open').count() == 0
    assert page.locator('.ov-page').is_visible()
    assert page.locator('.ov-today').is_visible()
    assert page.locator('.record-focus .next-exchanges').count() == 0
    page.locator('details.deep-note > summary').click()
    snippets = [value.strip().lower() for value in page.locator('.relation-basis').all_inner_texts() if value.strip()]
    assert len(snippets) == len(set(snippets))
    assert snippets.count('your contacts: mara, quinn and tomás.') == 1


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_empty_sessions_offer_one_copy_action_without_filters(reader, width, language):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#c=sessions')
    page.evaluate(r'''language => {
      REM.status = {worker: {enabled: true}};
      REM.default_root = true; setInterfaceLanguage(language);
    }''', language, isolated_context=False)
    # b1927e56: scheduled work shows queue status instead of a copy/import action.
    status = page.locator('#main > .quiet-line')
    assert status.inner_text() == ('智能体会话已排入今晚队列' if language == 'zh' else 'Agent sessions queued for tonight')
    assert page.locator('#main a, #main button, .session-filter-panel, #session-search').count() == 0
    page.evaluate(r'''() => {
      REM.status.worker.enabled = false;
      REM.default_root = false; REM.root_display = '/tmp/theo notebook'; render();
    }''', isolated_context=False)
    assert status.inner_text() == ('智能体会话待处理，后台更新未开启' if language == 'zh'
                                   else 'Agent sessions pending — background updates off')
    assert page.locator('#main a, #main button, .session-filter-panel, #session-search').count() == 0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 390])
def test_hidden_excerpt_keeps_identity_claim_and_inline_reveal(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''() => document.documentElement.classList.add('hide-private')''')
    page.locator('details.deep-note').evaluate('d => d.open = true')
    page.locator('.block-insight a.cite[href$="src-4"]').first.click()
    panel = page.locator('#evidence-panel')
    assert panel.locator('.evidence-claim').is_visible()
    assert panel.locator('.evidence-identity').is_visible()
    identity = panel.locator('.evidence-identity').inner_text()
    assert 'Outlook' in identity
    assert 'Mara' in identity
    assert not panel.locator('.evidence-original').is_visible()
    panel.get_by_role('button', name='Show labelled passages', exact=True).click()
    assert panel.locator('.evidence-original').is_visible()
    assert not panel.locator('.private-hidden-notice').is_visible()
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')


def test_people_columns_disclose_sort_and_remember_without_changing_phone_cards(reader):
    page, uri = reader
    page.goto(uri + '#c=people')
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
    assert page.locator('.sheet th:visible').all_text_contents() == [
        'Name↕', "What's open↕", 'Company↕', 'Last contact↕']
    assert page.locator('.sheet td.c-email').first.is_hidden()
    page.get_by_role('button', name='More columns', exact=True).click()
    assert page.locator('.sheet th.c-role').is_visible()
    page.locator('.sheet th.c-mails button').click()
    assert page.locator('.sheet th.c-mails').get_attribute('aria-sort') == 'descending'
    page.reload()
    assert page.get_by_role('button', name='Fewer columns', exact=True).get_attribute('aria-expanded') == 'true'
    page.get_by_role('button', name='Fewer columns', exact=True).click()
    page.reload()
    assert page.locator('.sheet th.c-role').is_hidden()
    page.set_viewport_size({'width': 375, 'height': 844})
    assert page.locator('.sheet tbody .c-email').first.is_visible()
    assert page.get_by_role('button', name='More columns', exact=True).is_hidden()
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 375])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_latest_pass_page_and_field_markers_and_uncertain_citations(reader, width, language):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''language => setInterfaceLanguage(language)''', language, isolated_context=False)
    label = '昨夜更新' if language == 'zh' else 'updated last night'
    assert page.locator('.eyebrow .updated-label, .hero-marks .updated-label').inner_text() == '●' + label
    role = page.locator('.page-head .changed-value, .r4-sub .changed-value').filter(has_text='Head of Partnerships')
    assert 'Head of Partnerships' in role.inner_text()
    assert role.get_attribute('title') == ('昨夜变更：Partnerships lead → Head of Partnerships' if language == 'zh'
                                         else 'Changed last night: Partnerships lead → Head of Partnerships')
    page.locator('details.deep-note > summary').click()
    assert page.locator('.factlist .changed-value').filter(has_text='Head of Partnerships').is_visible()
    marker = page.locator('.note .uncertain-marker')
    assert marker.count() == 1
    assert marker.inner_text() == '◌'
    assert marker.get_attribute('title') == ('来源未确认' if language == 'zh' else 'Not confirmed by the sources')
    assert marker.evaluate(r'''node => node.nextElementSibling.matches('a.cite')''')
    assert marker.evaluate(r'''node => node.nextSibling.textContent === '\u200a' ''')
    assert marker.evaluate(r'''node => getComputedStyle(node).fontSize === '11px' ''')
    page.goto(uri + '#r=people%2Ftomas-reyes.md')
    assert page.locator('.eyebrow .updated-label, .hero-marks .updated-label, .changed-value').count() == 0
    page.goto(uri + '#c=people')
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
    fresh = page.locator('.sheet tbody tr').filter(has_text='Mara Ostrowski').locator('.fresh-label')
    assert fresh.is_visible()
    assert fresh.inner_text() == ('昨夜' if language == 'zh' else 'last night')
    assert fresh.get_attribute('title') == ('昨夜整理时更新' if language == 'zh' else "Updated in last night's pass")
    assert fresh.evaluate(r'''node => getComputedStyle(node).fontSize === '11px' ''')
    assert page.locator('.sheet tbody .fresh-dot').count() == 0
    assert page.locator('.sheet tbody tr').filter(has_text='Tomás Reyes').locator('.fresh-label').count() == 0
    page.goto(uri + '#c=orgs')
    assert page.locator('.fresh-label').filter(has_text='昨夜' if language == 'zh' else 'last night').first.is_visible()
    page.goto(uri)
    page.locator('.week-details summary').click()
    assert page.locator('.week li').filter(has_text='Mara Ostrowski').locator('.fresh-label').is_visible()
    assert page.locator('.week li').filter(has_text='Tomás Reyes').locator('.fresh-label').count() == 0
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')


def test_uncertainty_is_sentence_specific_and_does_not_mark_uncited_prose(reader):
    page, _ = reader
    result = page.evaluate(r'''() => {
      const render = text => {
        const box = document.createElement('div');
        box.innerHTML = inline(text, 'people/mara-ostrowski.md');
        return [...box.querySelectorAll('.uncertain-marker')].map(marker => marker.nextElementSibling.dataset.sources);
      };
      return [render('The budget is unknown [1]. The pilot is agreed [2].'),
        render('The budget is unknown. The pilot is agreed [2].'),
        render('The budget is unknown.'), render('Timing is not established [1][2].'),
        render('Whether funding is approved remains unclear [1].')];
    }''', isolated_context=False)
    assert result == [['1'], [], [], ['1 2'], ['1']]


@pytest.mark.parametrize('text,ending', [
    ('The budget is unknown [1].', '.'), ('The budget is **unknown.** [1]', '.'),
    ('The budget is unknown. [1][2]', '.'), ('预算未知。[1]', '。'),
])
def test_uncertainty_precedes_the_citation_group_and_sentence_ending(reader, text, ending):
    page, _ = reader
    result = page.evaluate(r'''text => {
      const box = el('p', {html: inline(text, 'people/mara-ostrowski.md')});
      const marker = box.querySelector('.uncertain-marker'), cite = box.querySelector('a.cite');
      const before = document.createRange(); before.setStart(box, 0); before.setEndBefore(marker);
      return {before: before.toString().trim(), gap: marker.nextSibling.textContent,
        ending: cite.nextSibling.textContent, sources: cite.dataset.sources};
    }''', text, isolated_context=False)
    assert not result['before'].endswith(('.', '。'))
    assert result['gap'].replace('\u2060', '') == '\u200a'
    assert result['ending'].replace('\u2060', '') == ending
    assert result['sources'] == ('1 2' if '[2]' in text else '1')


@pytest.mark.parametrize('width', [1440, 375])
def test_connected_context_without_snippet_is_compact_and_top_aligned(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(uri + '#r=orgs%2Ffernhill-labs.md')
    page.evaluate(r'''() => {
      const r = byPath('orgs/fernhill-labs.md');
      r.relations = [
        {path: 'people/mara-ostrowski.md', kind: 'linked', via: r.path, basis: '', sources: ['1']},
        {path: 'projects/harbour.md', kind: 'linked', via: r.path,
          basis: 'The pilot renewal needs a decision before the next proposal is sent.', sources: ['2']}];
      render();
    }''', isolated_context=False)
    page.locator('details.deep-note > summary').click()
    entries = page.locator('.relation-list').first.locator('.relation-entry')
    assert entries.first.locator('.relation-basis').count() == 0
    assert entries.first.locator('.relation-provenance .cite').is_visible()
    assert entries.first.bounding_box()['height'] < entries.nth(1).bounding_box()['height']
    assert page.locator('.relation-list').first.evaluate(r'''node => getComputedStyle(node).alignItems''') == 'start'
    if width == 1440:
        assert abs(entries.first.bounding_box()['y'] - entries.nth(1).bounding_box()['y']) <= 1
    # Two snippet cards align their source dates, even with different title and
    # snippet lengths. A snippet-free neighbour never inherits their height.
    page.evaluate(r'''() => {
      const r = byPath('orgs/fernhill-labs.md');
      byPath('people/mara-ostrowski.md').title = 'Mara Ostrowski — pilot review and renewal follow-up';
      r.relations[0].basis = 'Pilot review.';
      render();
    }''', isolated_context=False)
    page.locator('details.deep-note').evaluate('node => node.open = true')
    if width == 1440:
        dates = entries.locator('.relation-provenance')
        assert abs(dates.first.bounding_box()['y'] - dates.nth(1).bounding_box()['y']) <= 1
    else:
        assert entries.first.evaluate(r'''node => getComputedStyle(node).alignSelf''') == 'auto'
    page.evaluate(r'''() => {
      byPath('people/mara-ostrowski.md').title = 'Mara Ostrowski';
      byPath('orgs/fernhill-labs.md').relations[0].private = true;
      render();
      document.documentElement.classList.add('hide-private');
    }''', isolated_context=False)
    page.locator('details.deep-note').evaluate('node => node.open = true')
    assert not entries.first.locator('.relation-basis').is_visible()
    assert entries.first.bounding_box()['height'] < entries.nth(1).bounding_box()['height']
    page.evaluate(r'''() => document.documentElement.classList.remove('hide-private')''')
    assert entries.first.locator('.relation-basis').is_visible()
    if width == 1440:
        dates = entries.locator('.relation-provenance')
        assert abs(dates.first.bounding_box()['y'] - dates.nth(1).bounding_box()['y']) <= 1
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_audited_lists_keep_chrome_concise_and_prose_as_written(reader, width, language):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#c=skills')
    original = page.evaluate(r'''language => {
      setInterfaceLanguage(language);
      return byPath('skills/catalog/weekly-brief.md').text;
    }''', language, isolated_context=False)
    assert page.locator('.lede').inner_text().startswith(
        '你的 agent 会做的事，最常用的在前 · ' if language == 'zh' else 'What your agents can do, the ones you use most first. ')
    assert page.locator('.lede .mono').inner_text() == ('3 个技能' if language == 'zh' else '3 skills')
    assert page.locator('.skills-view .bar').count() == 0
    assert page.locator('.skill-card .skill-uses').first.inner_text().endswith(
        '最近 昨天' if language == 'zh' else 'last Yesterday')
    assert page.evaluate(r"byPath('skills/catalog/weekly-brief.md').text", isolated_context=False) == original
    page.evaluate(r"""() => {
      const r = byPath('skills/catalog/weekly-brief.md');
      r.text += '\n## Open threads\n- You owe Avery Lin a revised weekly brief. [1]\n';
      KNOWN.delete(r.path);
    }""", isolated_context=False)
    for path in ['skills/catalog/weekly-brief.md', 'projects/harbour.md']:
        page.goto(uri + '#r=' + path.replace('/', '%2F'))
        assert page.locator('.leadrow .lead-open').count() == 0
        assert page.locator('.next-exchanges').is_visible()
    assert page.locator('.next-exchanges .dir').count() > 0  # mixed directions retain their tags
    page.goto(uri + '#view=open')
    assert page.locator('.task-band .thread .dir').count() == 0
    assert page.locator('.task-band .thread .when').count() > 0
    if language == 'zh':
        assert '等你处理' in page.locator('.lede').inner_text()
        assert 'Newest' not in page.locator('.lede').inner_text()
        assert page.locator('#nav a[href="#view=open"]').inner_text().startswith('等你处理')
    # The date sits beside the body on a desktop; on a phone it goes under the title so the body
    # keeps the full width (polish, 1.9.3).
    assert page.locator('.task-band .thread').first.evaluate(r'''(node, wide) => {
      const body = node.querySelector('.what').getBoundingClientRect();
      const date = node.querySelector('.when').getBoundingClientRect();
      return wide ? body.right <= date.left && getComputedStyle(node.querySelector('.when')).order === '0'
        : date.top >= body.bottom - 1 && body.width >= 320;
    }''', width > 600)
    page.goto(uri + '#q=pilot')
    assert page.locator('.search-group h2').first.evaluate(r'''node => {
      const title = node.firstElementChild.getBoundingClientRect(), count = node.lastElementChild.getBoundingClientRect();
      return Math.abs(title.top - count.top) < 12 && count.left > title.right;
    }''')
    page.goto(uri + '#view=changes')
    page.evaluate(r'''() => { for (const run of REM.logs) run.claim_changes = []; render(); }''', isolated_context=False)
    assert page.locator('.empty > a').inner_text() == ('浏览记忆 →' if language == 'zh' else 'Explore memory →')
    assert page.locator('.changed-pages .section .n').inner_text() == ('当前背景' if language == 'zh' else 'Current context')
    page.goto(uri + '#view=activity')
    page.evaluate(r'''() => {
      REM.logs[0].phase = 'daily-update';
      REM.logs[0].refusals = [{record: 'decisions/notebook-format.md', errors: ['Changed page has no numbered evidence references', 'Missing section: Facts']}];
      render();
    }''', isolated_context=False)
    assert page.locator('.run-head').first.inner_text().find('每日更新' if language == 'zh' else 'daily-update') >= 0
    assert page.locator('.why').first.inner_text() == (
        '改动的页面缺少编号来源引用；缺少章节：Facts' if language == 'zh'
        else 'Changed page has no numbered evidence references; Missing section: Facts')
    links = page.locator('.night .changes .page-names a')
    assert links.count() > 1
    assert links.first.evaluate(r"node => getComputedStyle(node).textDecorationLine === 'none'")
    assert page.locator('.night .changes .page-names').inner_text().count('、' if language == 'zh' else ', ') > 0
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_decision_memory_starts_collapsed_and_sources_use_readable_ids(reader, language):
    page, uri = reader
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(uri + '#r=decisions%2Fnotebook-format.md')
    source = 'claude-code:12345678-1234-1234-1234-123456789abc:295937556'
    page.evaluate(r'''({language, source}) => {
      const r = byPath('decisions/notebook-format.md');
      r.text = '# Notebook format\n\n## Decision\nKeep Markdown. [1]\n\n## Sources\n- [1] ' + source + ' — fixture decision.\n';
      REM.source_context[source] = {source: 'claude-code', time: '2026-09-03T12:00:00Z'};
      KNOWN.delete(r.path); setInterfaceLanguage(language);
    }''', {'language': language, 'source': source}, isolated_context=False)
    assert page.locator('details.deep-note').get_attribute('open') is None
    page.locator('details.deep-note > summary').click()
    chip = page.locator('.block-sources .id')
    assert chip.inner_text() == ('Claude Code 会话 · 9月3日' if language == 'zh' else 'Claude Code session · Sep 3')
    assert chip.get_attribute('title') == source
    page.evaluate(r'''source => { delete REM.source_context[source]; render(); }''', source, isolated_context=False)
    page.locator('details.deep-note > summary').click()
    assert page.locator('.block-sources .id').inner_text() == 'claude-code:12345678…:295937556'
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('motion', ['reduce', 'no-preference'])
def test_memory_markers_enter_once_per_page_view_and_respect_reduced_motion(reader, motion):
    page, uri = reader
    page.emulate_media(reduced_motion=motion)
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    field = page.locator('.page-head .changed-value, .r4-sub .changed-value').filter(has_text='Head of Partnerships')
    assert field.evaluate(r'node => getComputedStyle(node).animationName') == ('none' if motion == 'reduce' else 'memory-underline')
    assert page.locator('.eyebrow .updated-label, .hero-marks .updated-label').evaluate(r'node => getComputedStyle(node).animationName') == ('none' if motion == 'reduce' else 'memory-dawn')
    page.evaluate(r'() => render()', isolated_context=False)
    assert field.evaluate(r'node => getComputedStyle(node).animationName') == 'none'
    page.goto(uri + '#c=people')
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
    marker = page.locator('.fresh-label').first
    assert marker.evaluate(r'node => getComputedStyle(node).animationName') == ('none' if motion == 'reduce' else 'memory-dawn')
    page.locator('.sheet-find').fill('Mara')
    assert page.locator('.fresh-label').first.evaluate(r'node => getComputedStyle(node).animationName') == 'none'


@pytest.mark.parametrize('width', [375, 1440])
def test_cached_prose_follows_interface_and_page_override(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''() => {
      const r = byPath('people/mara-ostrowski.md');
      r.index = {...r.index, how_known: 'Original indexed relationship'};
      r.translations = {zh: r.text
        .replace(/(^#[^\n]*\n)[\s\S]*?(?=\n## )/, '$1\n中文人物摘要 [1].\n')
        .replace(/## Why they are here\n[^#]+/, '## Why they are here\n- 中文相识经过 [3].\n\n')
        .replace(/(## History\n)- [^\n]*/, '$1- 2026-09-30：Theo Park 发来中文合同 [3].')
        .replace(/Now:/g, 'Now：')
        .replace(/- \*\*Data-sharing addendum\*\*[^\n]*/, '- 你需要签署中文待办摘要；since 2026-09-22 [4].')};
      setInterfaceLanguage('zh');
    }''', isolated_context=False)
    assert '中文人物摘要' in page.locator('#main').text_content()
    assert 'Theo Park 发来中文合同' in page.locator('.tl').inner_text()
    assert page.locator('#history-timeline h2').inner_text().startswith('往来')
    page.locator('details.deep-note > summary').click()
    assert '中文相识经过' in page.locator('.deep-note').inner_text()
    assert 'Original indexed relationship' not in page.locator('#main').text_content()
    assert page.locator('.eyebrow [title="尚无中文译文，显示原文"]').count() == 0
    assert page.locator('.page-head .lang-bar').count() == 0
    assert page.locator('.page-foot .lang-bar select').is_visible()
    page.locator('.page-foot select').select_option('')
    assert '中文人物摘要' not in page.locator('#main').text_content()
    assert page.locator('.eyebrow [title="尚无中文译文，显示原文"]').count() == 0
    page.evaluate(r'''() => setInterfaceLanguage('en')''', isolated_context=False)
    assert '中文人物摘要' not in page.locator('#main').text_content()
    page.evaluate(r'''() => { setInterfaceLanguage('zh'); location.hash = 'c=people'; }''', isolated_context=False)
    assert '中文待办摘要' in page.locator('.r4 .row.prow').filter(has_text='Mara Ostrowski').inner_text()
    page.evaluate(r'''() => { location.hash = ''; }''', isolated_context=False)
    assert '中文待办摘要' in page.locator('.today-brief').text_content()  # every card, raised or waiting behind its face
    page.locator('.week-details > summary').click()
    assert '中文人物摘要' in page.locator('.week').inner_text()
    page.evaluate(r'''() => { location.hash = 'q=' + encodeURIComponent('中文人物摘要'); }''', isolated_context=False)
    assert '中文人物摘要' in page.locator('.search-group .hit').first.inner_text()
    page.evaluate(r'''() => { location.hash = 'r=people%2Fquinn-alder.md'; }''', isolated_context=False)
    assert page.locator('.hero-marks .lang-status').inner_text() == '原文'
    assert page.locator('.hero-marks .lang-status').get_attribute('title') == '翻译待处理，后台更新未开启'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('separator', ['；', ';', '：', ':', '—'])
def test_chinese_waiting_summary_splits_and_trims_detail(reader, separator):
    page, _ = reader
    result = page.evaluate(r'''separator => {
      setInterfaceLanguage('zh');
      return morningWords('请签署试点协议' + separator + ' ，、；：— 后续安排明天讨论 [4]', byPath('people/mara-ostrowski.md'));
    }''', separator, isolated_context=False)
    assert result == {'words': '请签署试点协议' + separator + ' ，、；：— 后续安排明天讨论', 'context': '[4]'}
    assert page.evaluate(r'''() => {
      setInterfaceLanguage('en');
      return morningWords('Review the draft: keep this clause — and this one; discuss tomorrow [4]', byPath('people/mara-ostrowski.md'));
    }''', isolated_context=False) == {
        'words': 'Review the draft: keep this clause — and this one; discuss tomorrow', 'context': '[4]'}


@pytest.mark.parametrize('width', [375, 1440])
def test_cached_facts_translate_subtitles_and_connected_context(reader, width):
    page, _ = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.evaluate(r'''() => {
      setInterfaceLanguage('en');
      const r = byPath('people/mara-ostrowski.md'), org = byPath('orgs/fernhill-labs.md');
      r.index = {...r.index, role: 'Indexed English role', company: 'Indexed English company'};
      r.translations = {zh: r.text
        .replace('Head of Partnerships', '理学院教授')
        .replace(/(- Company: )[^\n]+/, '$1[Fernhill Labs 科研团队](../orgs/fernhill-labs.md) [2]')
        .replace(/- \*\*Data-sharing addendum\*\*[^\n]*/, '- 你需要签署试点协议；后续安排明天讨论 [4]')};
      org.translations = {zh: org.text + '\n## Facts\n- What they do: 研究气候数据 [1]\n'};
      org.relations = [{path: r.path, via: r.path, kind: 'linked from', basis: 'Company: Fernhill Labs', sources: ['2']}];
      setInterfaceLanguage('zh');
    }''', isolated_context=False)
    waiting = page.locator('.qcard[data-path="people/mara-ostrowski.md"]')
    assert '理学院教授' in waiting.locator('.qhead .meta').get_attribute('title')  # N3: the role is the organisation chip's title
    assert 'Fernhill Labs 科研团队' in waiting.locator('.qhead .meta').text_content()
    if 'focal' not in waiting.get_attribute('class').split():
        page.locator('.deal[data-path="people/mara-ostrowski.md"]').click()  # N3: deal her card onto the desk
    assert waiting.locator('.words').first.inner_text() == '你需要签署试点协议；后续安排明天讨论4'
    assert waiting.locator('.words .cite').first.get_attribute('data-sources') == '4'
    assert waiting.locator('.context').count() == 0
    page.evaluate(r'''() => { location.hash = 'c=people'; }''', isolated_context=False)
    person_row = page.locator('.r4 .row.prow').filter(has_text='Mara Ostrowski')
    assert 'Fernhill Labs 科研团队' in person_row.locator('.org').text_content()
    assert person_row.locator('.org').is_visible() == (width >= 720)
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")
    row = page.locator('.people-sheet tbody tr').filter(has=page.get_by_role('link', name='Mara Ostrowski', exact=True))
    if width > 600:
        page.locator('.more-columns').click()
        assert row.locator('.c-role').inner_text() == '理学院教授'
        assert row.locator('.c-company').inner_text() == 'Fernhill Labs 科研团队'
    else:
        assert '理学院教授' in row.locator('.people-card-meta').inner_text()
        assert 'Fernhill Labs 科研团队' in row.locator('.people-card-meta').inner_text()
    page.evaluate(r'''() => { location.hash = 'c=orgs'; }''', isolated_context=False)
    org = page.locator('.ov-list .ov-row').filter(has_text='Fernhill Labs')
    assert org.count() == 1
    page.evaluate(r'''() => { location.hash = 'r=orgs%2Ffernhill-labs.md'; }''', isolated_context=False)
    assert '研究气候数据' in page.locator('.ov-about').inner_text()
    page.evaluate(r'''() => { location.hash = 'r=people%2Fmara-ostrowski.md'; }''', isolated_context=False)
    assert '理学院教授' in page.locator('.r4-sub').inner_text()
    assert 'Fernhill Labs 科研团队' in page.locator('.r4-sub').inner_text()
    assert page.evaluate(r'''() => {
      const r = byPath('people/mara-ostrowski.md'), first = parseFacts(r);
      if (parseFacts(r) !== first) return false;
      setInterfaceLanguage('en');
      const original = parseFacts(r);
      setInterfaceLanguage('zh');
      return parseFacts(r) === first && original !== first && original.get('Role')[0].value === 'Head of Partnerships';
    }''', isolated_context=False)
    page.evaluate(r'''() => { location.hash = 'r=orgs%2Ffernhill-labs.md'; }''', isolated_context=False)
    page.locator('details.deep-note > summary').click()
    assert 'Fernhill Labs 科研团队' in page.locator('.relation-basis').inner_text()
    assert page.evaluate(r'''document.documentElement.scrollWidth <= innerWidth''')
    page.evaluate(r'''() => setInterfaceLanguage('en')''', isolated_context=False)
    page.locator('details.deep-note > summary').click()
    assert page.locator('.relation-basis').inner_text() == 'Company: Fernhill Labs'
    page.evaluate(r'''() => { location.hash = 'r=people%2Fmara-ostrowski.md'; }''', isolated_context=False)
    assert 'Head of Partnerships' in page.locator('.r4-sub').inner_text()
    assert '理学院教授' not in page.locator('.r4-sub').inner_text()


@pytest.mark.parametrize('width', [375, 1440])
def test_chinese_cached_translation_never_exposes_labelled_words(tmp_path, monkeypatch, width):
    """A real cached fixture translation, including adjacent Chinese sentences."""
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.files import Notebook, atomic_write
    from connectonion.rem.translate import cached, checked, digest, translation_path

    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    root = build(tmp_path / 'rem', now)
    path = 'people/mara-ostrowski.md'
    original = '''# Mara Ostrowski

Public pilot context [1]. Secret proposed dates [personal] [1]. The user owes a secret follow-up [personal]. Public ending.

## Facts
- Email: mara@fernhill.example [1]
- Role: Partnerships lead [1]

## Insight
- Now: Public pilot status [1]. Secret status [sensitive].

## History
- 2026-09-30: Secret history [personal] [1].
- 2026-09-29: Public history [1].

## Open threads
- The user owes a public pilot reply; since 2026-09-30 [1]. Secret proposed dates [personal] [1]. The user owes a secret follow-up [personal].
- The user owes an entirely secret action [sensitive] [1].

## Private context
Public start. Secret question [personal]! Secret exclamation [personal]? Secret clause [personal]; Secret colon [personal]: Secret comma [personal], Secret final [personal]. Public end.
Secret amount 3.5 and secret@example.test [personal]. “秘密引语。秘密引语下半句” [sensitive].

## Sources
- [1] outlook:5c1e0a9b72d4 — invented pilot mail

Investigation: mapped 2026-09-01 · investigated 2026-10-01 (outlook)
'''
    translated = '''# Mara Ostrowski

公开试点背景 [1]。秘密提议日期[personal] [1]。用户还需进行秘密后续联系[personal]。公开结尾。

## Facts
- Email: mara@fernhill.example [1]
- Role: 合作负责人 [1]

## Insight
- Now: 公开试点状态 [1]。秘密状态［sensitive］。

## History
- 2026-09-30：秘密历史［personal］ [1]。
- 2026-09-29：公开历史 [1]。

## Open threads
- 用户需回复公开试点；since 2026-09-30 [1]。秘密提议日期[personal] [1]。用户还需进行秘密后续联系[personal]。
- 用户需执行全秘密行动[sensitive] [1]。

## Private context
公开开头。秘密问句[personal]！秘密感叹[personal]？秘密分句[personal]；秘密冒号[personal]：秘密逗号[personal]，秘密终句[personal]。公开结束。
秘密金额3.5和秘密地址secret@example.test[personal]。“秘密引语。秘密引语下半句”［sensitive］。

## Sources
- [1] outlook:5c1e0a9b72d4 — invented pilot mail

Investigation: mapped 2026-09-01 · investigated 2026-10-01 (outlook)
'''
    Notebook(root).write(path, original)
    atomic_write(translation_path(root, path, 'zh'),
                 f'<!-- co rem translation of {path} sha256:{digest(original)} -->\n' + checked(original, translated))
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    # b56eec48 rejects caches that rewrite Sources; this fixture must be a valid cache.
    assert cached(root, path, 'zh') == translated
    monkeypatch.setattr('connectonion.rem.languages.owner_languages', lambda root: {'languages': ['zh', 'en'], 'from': 'detected'})
    snapshot = rem_reader.snapshot

    def frozen_snapshot(root, local=False, today=False):
        data = snapshot(root, local, today=today)
        data['as_of'] = now.isoformat()
        data['shared'] = True  # Default hidden-labelled mode, without a local storage override.
        return data

    monkeypatch.setattr(rem_reader, 'snapshot', frozen_snapshot)
    html = tmp_path / 'reader.html'
    html.write_text(rem_reader.render(root, local=True))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': width, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(html.as_uri())
        page.locator('.night-card .count').wait_for()

        def no_private_words():
            visible = page.locator('body').inner_text()
            assert '秘密' not in visible
            assert '[personal]' not in visible and '［personal］' not in visible
            assert '[sensitive]' not in visible and '［sensitive］' not in visible
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

        assert page.evaluate("document.documentElement.classList.contains('hide-private')")
        assert '公开试点' in page.locator('.today-brief').text_content()  # every card, raised or waiting behind its face
        no_private_words()
        # Missing translations have no note in either home row type.
        page.locator('.week-details > summary').click()
        no_private_words()
        for selector in ('.today-brief', '.week'):
            assert page.locator(selector).locator('.lang-status').count() == 0
            # Missing archived mail is useful context, not a translation badge.
            assert '尚无中文译文，显示原文' not in page.locator(selector).inner_text()
        page.goto(html.as_uri() + '#view=open')
        page.locator('.task-band').first.wait_for()
        assert '公开试点' in page.locator('.task-band').first.inner_text()
        assert page.locator('.task-band .lang-status').count() == 0
        no_private_words()
        page.goto(html.as_uri() + '#r=people%2Fmara-ostrowski.md')
        page.locator('details.deep-note > summary').click()
        assert '公开历史' in page.locator('.timeline').inner_text()
        assert page.locator('.timeline .private-entry').count() == 1
        assert page.locator('.page-head .lang-bar').count() == 0
        assert page.locator('.page-foot .lang-bar select').is_visible()
        no_private_words()
        # Footer override remains functional for both original and cached prose.
        page.locator('.page-foot select').select_option('')
        page.locator('details.deep-note').evaluate('d => d.open = true')
        assert 'Public pilot context' in page.locator('.deep-note .note > p').first.inner_text()
        page.locator('details.deep-note').evaluate('d => d.open = true')
        page.locator('.page-foot select').select_option('zh')
        page.locator('details.deep-note').evaluate('d => d.open = true')
        assert '公开试点背景' in page.locator('.deep-note .note > p').first.inner_text()
        no_private_words()
        page.goto(html.as_uri() + '#q=' + '公开试点')
        assert page.locator('.search-group .hit').count() > 0
        no_private_words()
        page.goto(html.as_uri() + '#q=' + '秘密')
        assert page.locator('.search-group').count() == 0
        # The query itself is visible in the heading; it must have no result.
        assert '[personal]' not in page.locator('body').inner_text()
        page.evaluate('togglePrivate()', isolated_context=False)
        assert page.locator('.search-group .hit').count() > 0
        page.evaluate('togglePrivate()', isolated_context=False)
        assert page.locator('.search-group').count() == 0
        page.goto(html.as_uri() + '#r=people%2Fquinn-alder.md')
        assert page.locator('.hero-marks .lang-status').inner_text() == '原文'
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize('width', [390, 1440])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_round7_home_brief_today_limits_search_and_progressive_disclosure(reader, width, theme):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844 if width == 390 else 1000})
    page.emulate_media(color_scheme=theme)
    page.evaluate(r'''async () => {
      REM.as_of = '2026-10-20T12:00:00Z';
      for (const r of REM.records) {
        r.original = undefined;
        r.text = r.text.replace(/(^## Open threads[^\n]*\n)[\s\S]*?(?=^## |^Investigation:|(?![\s\S]))/mi, '$1Unknown\n\n');
      }
      const r = byPath('people/mara-ostrowski.md');
      const pairs = ['budget forecast', 'product outline', 'contract revision', 'receipt bundle', 'design proposal', 'renewal summary'];
      const lines = pairs.map((words, i) => '- You owe Mara a review of the ' + words + '; due ' + (i === 0 ? '2026-10-18' : '2026-10-20') + ' [4].');
      lines.push('- You owe Mara an access decision; since 2026-10-20 [4].');
      r.text = r.text.replace('## Open threads\nUnknown', '## Open threads\n' + lines.join('\n'));
      const pass = REM.logs.at(-1);
      REM.logs = [{...pass, started_at: '2026-10-18T12:00:00Z', claim_changes: []},
        {...pass, started_at: REM.as_of, claim_changes: Array.from({length: 4}, () => ({record: r.path,
        field: 'role', before: 'Partnerships lead', after: 'Head of Partnerships', sources: ['2']}))}];
      KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
    }''', isolated_context=False)
    assert page.locator('.night-strip').count() == 0
    assert page.locator('.overnight-change').count() == 3
    assert page.get_by_role('link', name='All 4 changes →').get_attribute('href') == '#view=changes'
    # Seven asks from one person are one card; the overdue one names the days late.
    assert page.locator('.qcard').count() == 1
    assert page.locator('.qcard .qitem').count() >= 5
    assert page.locator('.qcard .qage').inner_text() == '2 days overdue'
    assert page.locator('.night-card .count').text_content() == page.locator('#nav .n.waiting').inner_text()  # the badge's (sprint 14)
    assert page.locator('.night-card .count-of').text_content() == 'Start with this 1 person'
    assert page.locator('.deal .dd').inner_text() == '2 d'  # the face says its days overdue
    # The access decision cites [4], whose message predates its prose date; its age follows the evidence and it leaves Today.
    assert page.evaluate('todayEntries(threadEntries()).length', isolated_context=False) == 6
    assert page.locator('.others .waiting-more').get_attribute('href') == '#view=open'
    # A static, undrafted mail card opens its recorded provider thread; it
    # cannot promise a live Draft now action. Local completion stays available.
    assert page.locator('.qcard .card-acts a[target="_blank"]').count() == 1
    assert page.locator('.qcard .qdone').count() == page.locator('.qcard .qitem').count()
    assert page.locator('.qcard').get_by_role('button', name='Draft now', exact=True).count() == 0
    assert page.locator('#nav .n.waiting').inner_text() == '7'  # items, not people (TOP10 #9), said once: in the sidebar
    assert 'items waiting on you' not in page.locator('.waiting-more').inner_text()
    assert page.locator('.week-details').get_attribute('open') is None
    assert page.locator('.night-details').get_attribute('open') is None
    assert page.locator('.category-cards').count() == 0
    page.locator('#processing > summary').click()
    assert page.locator('.night-details').get_attribute('open') is not None
    assert page.locator('.night-details .night').is_visible()
    assert page.evaluate(r'''() => {
      const keys = [...document.querySelectorAll('.qcard .today-who')].map(a => a.textContent);
      return document.documentElement.scrollWidth <= innerWidth && keys.length === 1;
    }''')
    if page.locator('#tabbar .tab-search').is_visible():
        page.locator('#tabbar .tab-search').click()  # N3: search is a tab on a phone
    page.locator('#q').fill('pilot renewal')
    page.locator('#q').press('Enter')
    page.wait_for_url(uri + '#q=pilot%20renewal')
    assert 'pilot renewal' in page.locator('h1').inner_text()


def test_round7_local_done_copy_undo_reload_and_record_tag(reader):
    page, uri = reader
    page.goto(uri + '#view=open')
    target = page.locator('.task-band .thread').filter(has_text='Data-sharing addendum').first
    before = int(page.locator('#nav a[href="#view=open"] .n').inner_text())
    assert target.get_by_role('button', name='Mark done', exact=True).count() == 1
    assert target.get_by_role('link', name='Open the Gmail thread', exact=True).count() == 1
    assert target.get_by_role('button', name='Copy prompt').count() == 0
    target.get_by_role('button', name='Mark done', exact=True).click()
    assert page.locator('.task-band .thread').filter(has_text='Data-sharing addendum').count() == 0
    assert int(page.locator('#nav a[href="#view=open"] .n').inner_text()) == before - 1
    page.locator('#done-notice').get_by_role('button', name='Undo', exact=True).click()
    assert page.locator('.task-band .thread').filter(has_text='Data-sharing addendum').count() == 1
    page.locator('.task-band .thread').filter(has_text='Data-sharing addendum').get_by_role('button', name='Mark done').click()
    page.reload()
    page.locator('.done-details summary').wait_for()
    assert page.locator('.done-details').get_attribute('open') is None
    page.locator('.done-details summary').click()
    assert 'sync pending' in page.locator('.done-details').inner_text()
    assert page.locator('.done-details').get_by_role('button', name='Undo', exact=True).count() == 1
    # Her record follows the decision without a ledger of its own (D-30): nothing of hers is left in Today.
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    assert page.locator('.owe').count() == 0 and page.locator('.r4-today').count() == 0
    page.goto(uri + '#view=open')
    page.locator('.done-details summary').click()
    page.locator('.done-details').get_by_role('button', name='Undo', exact=True).click()
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    assert page.locator('.r4-today').inner_text() == '1 item in Today'
    page.goto(uri)
    assert 'Data-sharing addendum' in page.locator('.today-brief').text_content()  # every card, raised or waiting behind its face
    assert int(page.locator('#nav a[href="#view=open"] .n').inner_text()) == before


def test_round7_done_remains_usable_when_storage_is_blocked(reader):
    page, uri = reader
    page.add_init_script(r'''Object.defineProperty(window, 'localStorage', {
      get() { throw new Error('Storage blocked by this fixture'); }
    });''')
    page.goto(uri + '#view=open')
    page.reload()
    assert page.evaluate(r'''async () => {
      await readerStorage('fixture-probe', 'value');
      return readerStorage('fixture-probe');
    }''', isolated_context=False) is None
    page.locator('.task-band .thread').first.get_by_role('button', name='Mark done', exact=True).click()
    assert page.locator('.done-details summary').is_visible()
    page.goto(uri + '#')
    page.goto(uri + '#view=open')
    assert page.locator('.done-details summary').is_visible()
    page.locator('.done-details summary').click()
    page.locator('.done-details').get_by_role('button', name='Undo', exact=True).click()
    assert page.locator('.done-details').count() == 0


def test_round7_desktop_people_rows_are_light_and_phone_actions_stay_visible(reader):
    page, uri = reader
    page.goto(uri + '#c=people')
    assert page.evaluate(r'''() => [...document.querySelectorAll('.r4 .row.prow')].every(row => {
      const box = row.getBoundingClientRect(), meta = row.querySelector('.s');
      return box.height >= 56 && box.height <= 64 && (!meta || getComputedStyle(meta).whiteSpace === 'nowrap');
    })''')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate(r'''document.documentElement.scrollWidth <= innerWidth''')
    page.goto(uri)
    # The card's first action: its green step, or in a snapshot with no step the row's own tick (sprint 14).
    action = page.locator('.qcard.open :is(.card-acts .btn-act, .qitem .qdone)').first
    action.scroll_into_view_if_needed()
    assert action.is_visible() and action.bounding_box()['height'] >= 44
    action.focus()
    assert action.evaluate(r'''node => node === document.activeElement''')


@pytest.mark.parametrize('width', [390, 800, 1099, 1440])
@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round_eight_home_source_button_and_reading_order(reader, tmp_path, width, theme, language):
    from rem_reader_notebook import build
    from connectonion.rem.reader import render

    page, _ = reader
    path = tmp_path / 'round-eight.html'
    path.write_text(render(build(tmp_path / 'round-eight', datetime(2026, 10, 1, 12, tzinfo=timezone.utc), zh=True)))
    page.set_viewport_size({'width': width, 'height': 1000})
    page.goto(path.as_uri())
    page.evaluate(r'''({theme, language}) => {
      setTheme(theme);
      setInterfaceLanguage(language);
    }''', {'theme': theme, 'language': language}, isolated_context=False)
    rows = page.locator('.overnight-change')
    assert rows.count() == 1
    assert rows.locator('.supported').count() == 0
    source = rows.get_by_role('link', name='来源' if language == 'zh' else 'source', exact=True)
    assert source.count() == 1
    assert source.get_attribute('title') == ('有引用来源支持' if language == 'zh' else 'Supported by the cited source')
    assert source.get_attribute('href').endswith('h=src-2')
    if width < 1100:
        assert page.evaluate(r'''() => {
          const bottom = selector => document.querySelector(selector).getBoundingClientRect().bottom;
          const top = selector => document.querySelector(selector).getBoundingClientRect().top;
          // N3: the desk (the card and, beside it or under it on a phone, the side column), then the fold below it.
          return (innerWidth > 640 || bottom('.today-brief') <= top('.tgrid > .side'))
            && bottom('.today-brief') <= top('.overnight') && bottom('.tgrid > .side') <= top('.overnight')
            && (!document.querySelector('.gone-quiet') || bottom('.overnight') <= top('.gone-quiet'));
        }''')
    summaries = page.locator(':is(.gone-quiet, .week-details, .night-details, .done-details) > summary')
    for summary in summaries.all():
        assert summary.evaluate(r'''summary => {
          const css = getComputedStyle(summary);
          return css.display === 'list-item' && css.fontSize === '13px'
            && css.fontWeight === '400';  // N3: a fold's title is a quiet row (--s-ui)
        }''')
        if width == 390:
            assert summary.bounding_box()['height'] >= 44
    assert page.evaluate(r'''() => document.documentElement.scrollWidth <= innerWidth''')


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round_eight_fact_labels_and_phone_disclosure_alignment(reader, tmp_path, theme, language):
    from rem_reader_notebook import build
    from connectonion.rem.reader import render

    page, _ = reader
    path = tmp_path / 'round-eight-facts.html'
    path.write_text(render(build(tmp_path / 'round-eight-facts', datetime(2026, 10, 1, 12, tzinfo=timezone.utc), zh=True)))
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(path.as_uri())
    page.evaluate(r'''({theme, language}) => {
      setTheme(theme);
      setInterfaceLanguage(language);
    }''', {'theme': theme, 'language': language}, isolated_context=False)
    for record in ['people/mara-ostrowski.md', 'projects/harbour.md', 'orgs/fernhill-labs.md']:
        page.goto(path.as_uri() + '#r=' + record.replace('/', '%2F'))
        summary = page.locator('details.deep-note > summary')
        heading = summary.locator('h2').bounding_box()
        plus = summary.locator('.deep-toggle').bounding_box()
        assert abs(plus['y'] - heading['y']) <= 4
        assert plus['x'] > heading['x'] + heading['width']
        assert summary.locator('.deep-toggle').evaluate(r'''node => getComputedStyle(node, '::after').content''') == '"+"'
        summary.click()
        assert summary.locator('.deep-toggle').evaluate(r'''node => getComputedStyle(node, '::after').content''') == '"−"'
        facts = page.locator('.panel').filter(has=page.locator('.factlist'))
        assert facts.count() == 1
        if language == 'zh':
            assert facts.locator('h3').inner_text() == '资料'
            labels = facts.locator('.factlist dt').all_inner_texts()
            assert labels and all(not re.search('[A-Za-z]', label) for label in labels)
            assert '— not found' not in facts.inner_text()
            if record.startswith('people/'):
                assert set(labels) >= {'时区', '链接', '如何认识', '首次联系', '签约主体', '账号', '语言', '别名'}
                assert '— 未找到' in facts.inner_text()
        assert page.evaluate(r'''() => document.documentElement.scrollWidth <= innerWidth''')


@pytest.mark.parametrize('width', [390, 820, 821, 1440])
@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round_nine_ledger_and_record_threads_align_ages(reader, tmp_path, width, theme, language):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import render

    page, _ = reader
    path = tmp_path / 'round-nine.html'
    root = build(tmp_path / 'round-nine', datetime(2026, 10, 1, 12, tzinfo=timezone.utc), zh=True)
    book = Notebook(root)
    org = book.read('orgs/fernhill-labs.md').replace('## Open threads\n', '## Open threads\n'
        '- The user owes Fernhill a pilot review; since 2026-09-25 [1].\n'
        '- The user owes Fernhill an access decision [2].\n')
    book.write('orgs/fernhill-labs.md', org)
    path.write_text(render(root))
    page.set_viewport_size({'width': width, 'height': 1000})
    page.goto(path.as_uri())
    page.evaluate(r'''({theme, language}) => {
      setTheme(theme); setInterfaceLanguage(language);
    }''', {'theme': theme, 'language': language}, isolated_context=False)
    waiting_colour = page.locator('.qage').first.evaluate(r'''node => getComputedStyle(node).color''')
    page.goto(path.as_uri() + '#r=people%2Fmara-ostrowski.md')
    # The person page is a record with no open rows to align (owner, 2026-11-08, D-30).
    assert page.locator('#open-threads .owe').count() == 0
    assert waiting_colour
    for record in ['projects/harbour.md', 'orgs/fernhill-labs.md']:
        page.goto(path.as_uri() + '#r=' + record.replace('/', '%2F'))
        if record.startswith('orgs/'):
            # The organisation page is a record; its threads are one link to Today, with no ages to align.
            assert page.locator('.ov-owed .ov-owe').count() == 0
            assert page.locator('.ov-today').count() == 1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            continue
        rows = page.locator('.next-exchanges .thread')
        assert rows.count() > 0
        dated = 0
        for row in rows.all():
            dated += int(bool(row.locator('.when').inner_text().strip()))
            assert row.evaluate(r'''row => {
              const when = row.querySelector('.when'), dated = !!when.textContent.trim();
              const age = when.getBoundingClientRect();
              const label = row.querySelector('.dir').getBoundingClientRect();
              const text = row.querySelector('.what').getBoundingClientRect();
              // Undated fixture threads deliberately hide their empty age;
              // display:none has no box to align and must not invent a date.
              const ageAligned = dated
                ? Math.abs(row.getBoundingClientRect().right - age.right) <= 2 && Math.abs(label.top - age.top) <= 2
                : getComputedStyle(when).display === 'none';
              return ageAligned && Math.abs(row.getBoundingClientRect().left - label.left) <= 2
                && (innerWidth > 820
                  ? Math.abs(label.top - text.top) <= 2 && text.left >= label.right
                    && (!dated || text.right <= age.left)
                  : text.top >= Math.max(label.bottom, age.bottom));
            }''')
        assert 0 < dated < rows.count()
        assert page.evaluate(r'''() => document.documentElement.scrollWidth <= innerWidth''')


@pytest.mark.parametrize('width', [390, 1440])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round_nine_full_purpose_and_quiet_record_disclosures(reader, tmp_path, width, language):
    from rem_reader_notebook import build
    from connectonion.rem.reader import render

    page, _ = reader
    path = tmp_path / 'round-nine-disclosures.html'
    path.write_text(render(build(tmp_path / 'round-nine-disclosures', datetime(2026, 10, 1, 12, tzinfo=timezone.utc), zh=True)))
    page.set_viewport_size({'width': width, 'height': 812 if width == 390 else 1000})
    page.goto(path.as_uri() + '#r=projects%2Fharbour.md')
    expected = page.evaluate(r'''language => {
      const r = byPath('projects/harbour.md');
      r.text = r.original || r.text;
      const purpose = "A command-line tool that turns a team's shared inbox into a weekly brief, with searchable source records, clear ownership of open requests and a feedback loop for the pilot team. ".repeat(3).trim();
      const chinese = '把团队共享收件箱整理为每周简报，并提供可检索的来源记录、清晰的待办责任归属，以及供试点团队持续反馈的完整工作流程。'.repeat(3);
      r.text = r.text.replace(/## What it is\n[\s\S]*?(?=\n## )/, '## What it is\n- ' + purpose + ' [1]\n');
      r.text = r.text.replace('\n## Sources', '\n## Insight\n- Now: The pilot is ready for review [2].\n\n## Sources');
      r.translations.zh = r.translations.zh.replace(/## What it is\n[\s\S]*?(?=\n## )/, '## What it is\n- ' + chinese + ' [1]\n');
      r.translations.zh = r.translations.zh.replace('\n## Sources', '\n## Insight\n- 现在：试点已可供审阅 [2]。\n\n## Sources');
      r.original = r.text;
      // r.text now holds the edited original; let the language swap run again.
      r.shown = '';
      setInterfaceLanguage(language);
      KNOWN.clear(); FACTS.clear(); render();
      return language === 'zh' ? chinese : purpose;
    }''', language, isolated_context=False)
    purpose = page.locator('.project-purpose-preview')
    assert purpose.count() == 1
    if width == 390:
        assert purpose.evaluate(r'''node => getComputedStyle(node).webkitLineClamp === '4' && node.scrollHeight > node.clientHeight''')
        chip = page.locator('.project-purpose-cites a.cite').first.bounding_box()
        assert 0 <= chip['y'] and chip['y'] + chip['height'] <= 812
    page.get_by_role('button', name='展开用途' if language == 'zh' else 'Read full purpose', exact=True).wait_for()
    # Its label changes to "Show less" once open, so follow the button by what it controls.
    more = page.locator('button.focus-more[aria-controls="' + purpose.get_attribute('id') + '"]')
    assert more.get_attribute('aria-expanded') == 'false'
    more.click()
    assert more.get_attribute('aria-expanded') == 'true'
    assert purpose.inner_text() == expected
    assert purpose.evaluate(r'''node => node.scrollHeight <= node.clientHeight + 1 && getComputedStyle(node).overflow === 'visible' ''')
    assert purpose.evaluate(r'''node => node.nextElementSibling.nextElementSibling.classList.contains('project-purpose-cites')''')
    more.click()
    assert more.get_attribute('aria-expanded') == 'false'
    # a409b633 omits the redundant Investigated pill and its separator.
    assert page.evaluate("known(byPath('projects/harbour.md')).status", isolated_context=False) == 'Investigated'
    assert page.locator('.eyebrow .pill, .eyebrow .sep').count() == 0
    assert '文件更新于' not in page.locator('.eyebrow').inner_text()
    assert 'file updated' not in page.locator('.eyebrow').inner_text()
    assert ('文件更新于' if language == 'zh' else 'File updated') in page.locator('.deep-head').inner_text()
    # The same disclosure component serves all record categories, including the person's full note.
    for record in ['projects/harbour.md', 'orgs/fernhill-labs.md', 'people/mara-ostrowski.md']:
        page.goto(path.as_uri() + '#r=' + record.replace('/', '%2F'))
        page.evaluate(r'''path => {
          const r = byPath(path), links = [];
          for (let i = 0; i < 27; i++) {
            const other = {path: 'projects/harbour-link-' + i + '.md', title: 'Harbour ' + i, category: 'projects',
              text: '# Harbour ' + i, written: true};
            REM.records.push(other);
            links.push({path: other.path, via: r.path, kind: 'linked', basis: ''});
          }
          const note = {path: 'notes/pilot.md', title: 'Pilot note', category: 'notes', text: '# Pilot note'};
          REM.records.push(note);
          links.push({path: note.path, via: r.path, kind: 'linked', basis: ''});
          links.push({path: 'people/theo-park.md', via: r.path, kind: 'cited mention', basis: ''});
          if (!byPath('people/theo-park.md')) REM.records.push({path: 'people/theo-park.md', title: 'Theo Park', category: 'people', text: '# Theo Park'});
          r.relations = links;
          const sourceRows = Array.from({length: 6}, (_, i) => '- [' + (90 + i) + '] mail:pilot-conversation-' + i + ' — 2026-09-30');
          for (let i = 0; i < 6; i++) {
            const id = 'pilot-conversation-' + i;
            REM.source_context['mail:' + id] = {thread: id};
            // a409b633: only retained windows around this page's citations are shown.
            const source = 'mail:' + id, message = source + ':1';
            REM.conversations[id] = {subject: 'Pilot conversation ' + i, total: 1,
              windows: {[source]: [message]}, anchors: {[source]: message},
              messages: [{id: message, time: '2026-09-30', excerpt: 'Pilot review.'}]};
          }
          r.original = (r.original || r.text).replace('\n## Sources\n', '\n## Sources\n' + sourceRows.join('\n') + '\n');
          if (r.translations?.zh) r.translations.zh = r.translations.zh.replace('\n## Sources\n', '\n## Sources\n' + sourceRows.join('\n') + '\n');
          r.text = r.shown ? r.translations[r.shown] : r.original;
          KNOWN.clear(); FACTS.clear(); render();
        }''', record, isolated_context=False)
        if record.startswith(('people/', 'orgs/')):
            page.locator('details.deep-note > summary').click()
        summaries = page.locator('.more-relations > summary:visible')
        assert page.locator('.related-records > .more-relations > summary:visible').count() == 3
        assert page.locator('.conversation-view .more-relations > summary:visible').count() == 1
        assert summaries.count() == 4
        for summary in summaries.all():
            assert summary.evaluate(r'''node => {
              const css = getComputedStyle(node), probe = document.createElement('span');
              probe.style.color = 'var(--grey)'; node.appendChild(probe);
              const colour = getComputedStyle(probe).color; probe.remove();
              return css.display === 'list-item' && css.fontWeight === '400' && css.fontSize === '15px' && css.color === colour;
            }''')
            if width == 390:
                assert summary.bounding_box()['height'] >= 44
        assert page.locator('.related-records > .more-relations').first.evaluate(r'''node => {
          const next = node.nextElementSibling;
          return next && Math.abs(next.getBoundingClientRect().top - node.getBoundingClientRect().bottom - 8) <= 1;
        }''')
        summary = summaries.first
        summary.click()
        assert summary.locator('..').get_attribute('open') is not None
        summary.click()
        assert page.evaluate(r'''() => document.documentElement.scrollWidth <= innerWidth''')


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round_nine_fact_tails_preserve_nested_links_and_private_values(reader, tmp_path, language):
    from rem_reader_notebook import build
    from connectonion.rem.reader import render

    page, _ = reader
    path = tmp_path / 'round-nine-private-facts.html'
    path.write_text(render(build(tmp_path / 'round-nine-private-facts', datetime(2026, 10, 1, 12, tzinfo=timezone.utc), zh=True)))
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(path.as_uri() + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''language => {
      const r = byPath('people/mara-ostrowski.md');
      r.original = (r.original || r.text).replace('- Role: Head of Partnerships [2]',
        '- Role: Head of the [Pilot Programme](../projects/harbour.md) [2]')
        .replace(/^(- Location: [^\n\[]+) \[2\]$/m, '$1 [personal] [2]');
      r.translations.zh = r.translations.zh.replace('- Role: 合作负责人 [2]',
        '- Role: [试点项目负责人](../projects/harbour.md) [2]')
        .replace('- Location: 新西兰惠灵顿 [2]', '- Location: 新西兰惠灵顿 [personal] [2]');
      r.text = r.shown ? r.translations[r.shown] : r.original;
      setInterfaceLanguage(language); KNOWN.clear(); FACTS.clear(); render();
    }''', language, isolated_context=False)
    page.locator('details.deep-note > summary').click()
    role = page.locator('.factlist dt:text-is("' + ('职位' if language == 'zh' else 'Role') + '") + dd')
    tether = role.locator('.fact-tail')
    assert tether.count() == 1
    assert tether.locator('a[href*="projects%2Fharbour.md"]').count() == 1
    assert tether.locator('a.cite').count() == 1
    assert tether.evaluate(r'''(node, word) => {
      const link = node.querySelector('a:not(.cite)'), cite = node.querySelector('a.cite');
      return getComputedStyle(node).whiteSpace === 'nowrap' && link.textContent === word
        && Math.abs(link.getBoundingClientRect().top - cite.getBoundingClientRect().top) < 12;
    }''', '人' if language == 'zh' else 'Programme')
    location = page.locator('.factlist dt:text-is("' + ('位置' if language == 'zh' else 'Location') + '") + dd')
    assert location.locator('.private').count() > 0
    page.evaluate(r'''() => document.documentElement.classList.add('hide-private')''')
    assert not location.locator('.private').first.is_visible()
    assert ('惠灵顿' if language == 'zh' else 'Wellington') not in location.inner_text()
    assert page.evaluate(r'''() => document.documentElement.scrollWidth <= innerWidth''')


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round10_first_build_and_translation_notice(reader, tmp_path, language):
    from rem_reader_notebook import build
    from connectonion.rem.reader import render
    page, _ = reader
    path = tmp_path / 'round-ten.html'
    path.write_text(render(build(tmp_path / 'round-ten', datetime(2026, 10, 1, 12, tzinfo=timezone.utc), zh=True)))
    uri = path.as_uri()
    page.goto(uri)
    page.evaluate(r'''language => {
      REM.logs = [REM.logs.reduce((a, b) => runTime(a) > runTime(b) ? a : b)];
      // fbdd25e3 keeps this independent of the displayed (possibly truncated) logs.
      REM.first_run_at = REM.logs[0].started_at;
      REM.status = {state: 'Stopped — background maintenance is off'};
      REM.default_root = true;
      window.cachedPages = REM.records.filter(r => r.translations?.zh).map(r => ({...r, translations: {...r.translations}}));
      for (const r of REM.records) delete r.translations;
      setInterfaceLanguage(language);
      copyToClipboard = command => { window.copiedCommand = command; };
    }''', language, isolated_context=False)
    summary = page.locator('#processing .pass-summary').text_content()
    assert summary.startswith('今天建立：读取 ' if language == 'zh' else 'Built today: read ')
    assert ('夜间变化' if language == 'zh' else 'change overnight') not in page.locator('h1').inner_text()
    assert page.locator('.recall').count() == 0
    assert page.locator('.overnight .quiet-line').inner_text() == (
        '笔记本刚刚建立。下次更新后，这里会显示夜间变化。' if language == 'zh'
        else 'Your notebook was just built. Overnight changes appear here after the next update.')
    assert page.locator('.overnight .cmd').count() == 0  # commands left the primary surface
    page.locator('.settings-open').click()
    assert ('夜间更新已关闭。' if language == 'zh' else 'Nightly updates are off.') in page.locator('.reader-settings').inner_text()
    assert 'co rem' not in page.locator('.reader-settings').inner_text()  # D-60 (build 3b review): Reader settings states things in words, never a command to copy.
    page.keyboard.press('Escape')
    notice = page.locator('#main .desk-more > .translation-note')
    if language == 'zh':
        assert notice.inner_text() == '打开页面时会翻译成中文。'
        # The notice follows the queue: nothing about the reader's own upkeep sits above what needs you.
        assert notice.bounding_box()['y'] > page.locator('.today-brief').bounding_box()['y']
        assert notice.locator('button, code').count() == 0
    else:
        assert notice.count() == 0
    page.locator('#processing > summary').click()
    assert page.locator('.night-title').inner_text() == ('首次建立' if language == 'zh' else 'First build')
    assert ('昨夜' if language == 'zh' else 'Last night') not in page.locator('#processing').inner_text()
    page.goto(uri + '#view=changes')
    assert page.locator('.empty .lead').inner_text() == (
        '暂无变化 — 这是首次建立。' if language == 'zh' else 'No changes yet — this is the first build.')
    assert page.locator('.changed-pages, .claim-grid').count() == 0
    # A fragment change keeps this document and the edited snapshot; a bare uri would reload it.
    page.goto(uri + '#')
    page.evaluate(r'''() => {
      REM.status = {state: 'Running in background (launchd)', worker: {enabled: true}}; render();
    }''', isolated_context=False)
    assert page.locator('.overnight .cmd').count() == 0
    if language == 'zh':
        assert notice.inner_text() == '打开页面时会翻译成中文。'
    page.evaluate(r'''() => {
      REM.records = [...window.cachedPages.slice(0, 2), ...REM.records.filter(r => ['people', 'orgs', 'projects'].includes(r.category) && !window.cachedPages.some(c => c.path === r.path)).slice(0, 2)];
      render();
    }''', isolated_context=False)
    assert page.locator('#main .desk-more > .translation-note').count() == 0
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate(r'''() => {
      REM.default_root = false; REM.root = REM.root_display = '/tmp/' + 'invented notebook/'.repeat(12);
      for (const r of REM.records) { delete r.translations; r.shown = ''; }
      setInterfaceLanguage('zh');
    }''', isolated_context=False)
    assert page.locator('#main .desk-more > .translation-note').inner_text() == '打开页面时会翻译成中文。'
    assert page.locator('#main .desk-more > .translation-note button, #main > .translation-note code').count() == 0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round10_owner_is_your_page_in_today_waiting_and_open_threads(reader, language):
    page, uri = reader
    page.goto(uri)
    page.evaluate(r'''async language => {
      const owner = byPath(REM.owner);
      owner.title = 'Theo Park';
      REM.as_of = '2026-10-20T12:00:00Z';
      owner.text = '# Theo Park\n\n## Facts\n- Company: Northgate University\n- Role: Pilot lead\n'
        + '\n## Open threads\n- 2026-10-20: You owe a pilot review. Due 2026-10-21.\n'
        + '- 2026-10-16: You owe a second review.\n';
      for (const r of REM.records) if (r !== owner) {
        r.text = '# ' + r.title + '\n'; r.original = r.text; delete r.translations;
      }
      KNOWN.clear(); FACTS.clear(); OWING = null; await refreshTodayQueue();
      setInterfaceLanguage(language);
    }''', language, isolated_context=False)
    who = '你的页面' if language == 'zh' else 'Your page'
    # Build 3b review (PM): rows on your own page that name nobody are your notes, not a person waiting on you,
    # so Today leaves them out; Waiting on you still lists them under Your page.
    assert page.locator('.today-who').filter(has_text=who).count() == 0
    assert page.locator('.fuse .lane[data-path="people/avery-lin.md"]').count() == 0
    page.goto(uri + '#view=open')
    assert all(text == who for text in page.locator('.thread .who a').all_inner_texts())
    assert page.locator('.thread .who a').count() == 2


@pytest.mark.parametrize('width', [390, 1440])
def test_round10_calm_record_sections_and_unassigned_person_threads(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(uri)
    page.evaluate(r'''() => {
      REM.records.push({path: 'projects/quiet-pilot.md', category: 'projects', title: 'Quiet pilot', written: true,
        updated: '2026-10-20', relations: [], text: '# Quiet pilot\n\n## What it is\nA local pilot.\n'
          + '\n## Insight\nUnknown\n\n## Key decisions\nUnknown\n\n## Open threads\n'
          + '\nInvestigation: investigated 2026-10-20'});
      REM.records.push({path: 'people/mia-chen.md', category: 'people', title: 'Mia Chen', written: true,
        updated: '2026-10-20', relations: [], text: '# Mia Chen\n\n## Facts\n- Phone: Unknown\n'
          + '\n## Open threads\nNothing open as of 2026-10-17.\n\n## Insight\nUnknown\n\n## History\nUnknown\n'});
      REM.records.push({path: 'orgs/northgate-university.md', category: 'orgs', title: 'Northgate University', written: true,
        updated: '2026-10-20', relations: [], text: '# Northgate University\n\n## Open threads\n\n## People here\nNone identified.\n'});
      KNOWN.clear(); FACTS.clear();
    }''', isolated_context=False)
    styles = []
    for record, heading in [('projects/quiet-pilot.md', 'Open threads'), ('people/mia-chen.md', 'Still open between you'),
                            ('orgs/northgate-university.md', 'Open threads')]:
        page.goto(uri + '#r=' + record.replace('/', '%2F'))
        if record.startswith('people/'):
            # A person's page is a record (D-30): nothing owed means no Today line and no empty ledger.
            assert _name(page.locator('.r4-person h1')) == 'Mia Chen'
            assert page.locator('.r4-person #open-threads, .r4-today').count() == 0
            assert not page.get_by_role('heading', name=heading, exact=True).is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            continue
        if record.startswith('orgs/'):
            # Nothing owed: the record has no Today line and no ledger.
            assert _name(page.locator('.ov-say .ov-name')) == 'Northgate University'
            assert page.locator('.ov-today, .ov-owed').count() == 0
            assert not page.get_by_role('heading', name='Open threads', exact=True).is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            continue
        assert page.get_by_role('heading', name=heading, exact=True).is_visible()
        assert page.locator('.empty-line').count() == 1
        assert page.locator('.focus-section h2, #open-threads h2').all_inner_texts() == [heading]
        styles.append(page.locator('.empty-line').evaluate(r'''node => {
          const s = getComputedStyle(node);
          return [s.fontFamily, s.fontSize, s.color, s.borderTopWidth, s.marginTop];
        }'''))
        assert page.locator('.empty-line').inner_text() == 'Nothing open.'
        if record.startswith('projects/'):
            assert page.locator('.focus-head .deep-note-limit, .focus-limit').count() == 0
            assert page.locator('.deep-note-limit').count() == 1
            page.locator('.deep-note > summary').click()
            assert page.locator('.deep-note-limit').is_visible()
            assert page.locator('.deep-note-limit').evaluate(r'node => getComputedStyle(node).fontSize') == '11px'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # The compact quiet line remains readable without adding a card border.
    assert styles[0][1:] == ['15px', styles[0][2], '0px', '8px']
    page.goto(uri + '#r=people%2Fmia-chen.md')
    page.evaluate(r'''() => {
      const r = byPath('people/mia-chen.md');
      r.text = '# Mia Chen\n\n## Open threads\n- Discuss the pilot review with Theo Park.\n';
      KNOWN.clear(); FACTS.clear(); render();
    }''', isolated_context=False)
    # A thread that names no debtor is not Today's, and her page has no ledger (D-30): the record
    # keeps it as written in its full memory, so it is never lost.
    assert page.locator('.r4-person #open-threads, .r4-today').count() == 0
    # Unfolded, as a fact of the record (D-36), with nothing to click (D-30).
    topics = page.locator('.r4-person .r4-topics')
    assert 'Discuss the pilot review with Theo Park' in topics.inner_text()
    assert topics.locator('button, a.btn-act, .chip').count() == 0


def test_round10_list_empty_states_offer_one_working_next_action(reader):
    from patchright.sync_api import expect
    page, uri = reader
    for category in ('people', 'orgs', 'skills'):  # Projects is a board without a filter field
        page.goto(uri + '#c=' + category)
        page.locator('.sheet-find, .r4-find, .ov-find, .skills-find').first.fill('no-such-invented-page-zzzz')
        assert page.locator('.empty .lead').inner_text() == 'No matching pages'
        assert page.locator('.empty a').count() == 1
        page.locator('.empty a').click()
        assert page.locator('.empty').count() == 0
    page.goto(uri + '#q=no-such-invented-page-zzzz')
    assert page.locator('.empty .lead').inner_text() == 'No match'
    assert page.locator('.empty a').count() == 1
    page.locator('.empty a').click()
    expect(page.locator('#main h1')).to_have_text('All records')
    page.goto(uri + '#view=open')
    page.evaluate(r'''() => { REM.records = []; KNOWN.clear(); FACTS.clear(); render(); }''', isolated_context=False)
    assert page.locator('.empty .lead').inner_text() == 'Nothing open'
    assert page.locator('.empty a').count() == 1
    page.goto(uri + '#view=changes')
    assert page.locator('.empty a').count() == 1


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_round10_muted_text_contrast_status_roles_and_underlined_prose(reader, theme):
    page, uri = reader
    page.goto(uri)
    page.evaluate(r'''theme => setTheme(theme)''', theme, isolated_context=False)
    for route, selectors in [('#c=people', '.brand .sub, nav a .n, .r4 .row .s, .r4 .row .when, .r4 .grp, .r4 .chip, .r4-tabs i'),
                             ('#r=people%2Fmara-ostrowski.md', '.hero-marks, .r4-stats div, .fuse-ends span, .said-src, .tl-e .d, .wt h2'),
                             ('#r=projects%2Fharbour.md', '.brand .sub, .deep-note-limit, .deep-hint')]:
        page.goto(uri + route)
        if page.locator('details.deep-note').count():
            page.locator('details.deep-note > summary').click()
        values = page.locator(selectors).evaluate_all(r'''nodes => {
          const rgb = text => text.match(/[\d.]+/g).map(Number);
          const luminance = color => color.slice(0, 3).map(v => {
            v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
          }).reduce((n, v, i) => n + v * [.2126, .7152, .0722][i], 0);
          return nodes.filter(n => n.getClientRects().length && n.textContent.trim()).map(node => {
            const style = getComputedStyle(node);
            let parent = node, bg = [0, 0, 0, 0];
            while (parent && (bg[3] ?? 1) === 0) {
              bg = rgb(getComputedStyle(parent).backgroundColor); parent = parent.parentElement;
            }
            const a = luminance(rgb(style.color)), b = luminance(bg);
            return {text: node.textContent, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05), opacity: style.opacity};
          });
        }''')
        assert values and all(v['ratio'] >= 4.5 and v['opacity'] == '1' for v in values), values
        assert page.locator('span[aria-label]:not([role])').count() == 0
    page.goto(uri + '#c=people')
    page.evaluate("document.querySelector('.table-toggle[aria-pressed=false]')?.click()")  # the sheet is one toggle away from the rows
    assert page.locator('.st').count() > 0
    assert page.locator('.st').evaluate_all(r'nodes => nodes.every(n => n.getAttribute("role") === "img" && n.getAttribute("aria-label"))')
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace('You owe Mara', 'You owe [Mara](../people/mara-ostrowski.md)');
      KNOWN.clear(); FACTS.clear(); render();
    }''', isolated_context=False)
    page.locator('details.deep-note').evaluate('d => d.open = true')
    assert page.locator('.deep-note .note > p').first.locator('a:not(.cite)').evaluate_all(r'nodes => nodes.length > 0 && nodes.every(n => getComputedStyle(n).textDecorationLine.includes("underline"))')
    page.goto(uri)
    assert page.locator('.closed .link-btn').evaluate(r'n => getComputedStyle(n).textDecorationLine.includes("underline")')
    page.evaluate(r'''() => document.activeElement.blur()''')
    page.keyboard.press('Control+Home')
    page.locator('.skip').focus()
    assert page.locator('.skip').bounding_box()['y'] >= 0
    page.keyboard.press('Enter')
    assert page.locator('#main').evaluate(r'node => document.activeElement === node')
    page.evaluate(r'''() => setInterfaceLanguage('zh')''', isolated_context=False)
    assert page.locator('.skip').inner_text() == '跳到正文'


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round10_mapped_page_missing_sections_use_a_count(reader, language):
    page, uri = reader
    page.goto(uri + '#r=people%2Fquinn-alder.md')
    page.evaluate(r'''language => setInterfaceLanguage(language)''', language, isolated_context=False)
    count = page.evaluate(r'''() => known(byPath('people/quinn-alder.md')).missing.length''', isolated_context=False)
    assert count > 0
    assert page.locator('.missing .names').inner_text() == (
        f'调查后会写出 {count} 个章节。' if language == 'zh'
        else f'{count} sections will be written when it is investigated.')


@pytest.mark.parametrize('width', [1440, 375])
def test_round11_reader_languages_and_written_page_translation_fallback(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri)
    page.evaluate(r'''() => {
      REM.your_languages = ['zh', 'en']; REM.languages_from = 'detected';
      REM.default_root = false; REM.root_display = '~/.co/invented notebook/rem';
      copyToClipboard = command => { window.copiedCommand = command; };
      setInterfaceLanguage('en');
    }''', isolated_context=False)
    if width < 600:
        page.locator('.nav-toggle').click()
    settings = page.locator('.reader-settings')
    assert not settings.locator('.notebook-languages').is_visible()
    page.locator('.settings-open').click()
    assert settings.locator('.notebook-languages').inner_text().startswith('Notebook languages: 中文 · English — detected')
    # D-60/D-103 (build 3b review): REM detects the languages; settings shows them read-only, no command, no copy.
    assert settings.locator('.notebook-languages button, .notebook-languages code').count() == 0
    assert page.evaluate(r'''() => document.documentElement.scrollWidth <= innerWidth''')
    page.keyboard.press('Escape')
    if width < 600:
        page.locator('.nav-toggle').click()
    page.evaluate(r'''() => {
      REM.records = [
        {path: 'people/avery-lin.md', title: 'Avery Lin', category: 'people', written: true,
          text: '# Avery Lin\n\n## Facts\nA draft.\n', translations: {zh: '# Avery Lin\n\n## Facts\n草稿。\n'}},
        ...Array.from({length: 20}, (_, n) => ({path: 'projects/mapped-' + n + '.md',
          title: 'Mapped ' + n, category: 'projects', written: false, text: '# Mapped\n'}))];
      REM.logs = []; setInterfaceLanguage('zh');
    }''', isolated_context=False)
    notice = page.locator('#main .desk-more > .translation-note')
    assert notice.count() == 0  # Mapped-only stubs do not trigger the fallback.
    page.evaluate(r'''() => {
      delete REM.records[0].translations;
      render();
    }''', isolated_context=False)
    assert notice.inner_text() == '打开页面时会翻译成中文。'
    page.evaluate(r'''() => {
      REM.logs = [{phase: 'init-translation', pages: [{page: 'people/avery-lin.md', outcome: 'failed'}]}];
      render();
    }''', isolated_context=False)
    assert notice.inner_text().startswith('1 个页面未能翻译。')
    assert notice.inner_text() == '1 个页面未能翻译。 打开页面时会翻译成中文。'
    assert notice.locator('button, code').count() == 0
    page.evaluate("() => { REM.status.worker = {enabled: true}; render(); }", isolated_context=False)
    assert notice.inner_text() == '1 个页面未能翻译。 打开页面时会翻译成中文。'
    assert notice.locator('button, code').count() == 0
    assert page.evaluate(r'''() => document.documentElement.scrollWidth <= innerWidth''')


def test_cited_conversation_shows_only_this_pages_window_and_highlights_citation(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const source = 'outlook:77c09ad1e3f0', thread = REM.source_context[source].thread;
      REM.conversations[thread] = {subject: 'Example session', total: 1358,
        cited_ids: ['example:3', 'example:100'], anchors: {[source]: 'example:3'},
        windows: {[source]: ['example:1', 'example:2', 'example:3', 'example:4', 'example:5'],
          'codex:another-page:100': ['example:99', 'example:100']},
        messages: [1, 2, 3, 4, 5, 99, 100].map(i => ({id: 'example:' + i,
          sender: 'You', time: '2026-10-01T10:00:00Z', excerpt: 'Example turn ' + i + (i < 3 ? ' Example context.'.repeat(80) : '')}))};
      render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    page.locator('.conversation-open').first.click()
    dialog = page.locator('#conversation-dialog')
    assert dialog.locator('.conversation-message').count() == 5
    assert dialog.locator('.conversation-message.cited').count() == 1
    assert 'Example turn 3' in dialog.locator('.conversation-message.cited').inner_text()
    bounds, cited = dialog.bounding_box(), dialog.locator('.conversation-message.cited').bounding_box()
    assert bounds['y'] <= cited['y'] and cited['y'] + cited['height'] <= bounds['y'] + bounds['height']
    assert 'Example turn 99' not in dialog.inner_text() and 'Example turn 100' not in dialog.inner_text()
    assert 'people/' not in dialog.inner_text()
    assert 'You' in dialog.inner_text()
    assert 'Latest' not in dialog.inner_text()
    assert 'around' in dialog.locator('.evidence-summary').inner_text()
    assert '1358' not in dialog.locator('.evidence-summary').inner_text()
    # An unrelated thread may be embedded for another page, but cannot be opened here.
    page.get_by_role('button', name='Close conversation').click()
    page.evaluate("openConversation(byPath('people/mara-ostrowski.md'), 'session:uncited', document.body)", isolated_context=False)
    assert not dialog.is_visible()


def test_conversation_dialog_closes_on_page_navigation(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.locator('details.deep-note > summary').click()
    page.locator('.conversation-open').first.click()
    assert page.locator('#conversation-dialog').is_visible()
    page.evaluate("location.hash = '#r=projects%2Fharbour.md'")
    page.wait_for_function("document.querySelector('.page-head h1')?.textContent === 'Harbour'")
    assert not page.locator('#conversation-dialog').is_visible()
    assert page.locator('.page-head h1').inner_text() == 'Harbour'


@pytest.mark.parametrize('width', [1440, 390])
def test_mail_header_stays_visible_when_opening_and_finding_a_deep_highlight(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.emulate_media(reduced_motion='reduce')
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace("the pilot's renewal depends on two things you each owe the other [4][5].",
        'Mara promised “I will send the usage export” by Friday. [5]');
      REM.source_context['outlook:77c09ad1e3f0'].excerpt = 'Example background.\\n'.repeat(90)
        + 'I will send the usage export by Friday.\\n' + 'Example footer.\\n'.repeat(30);
      KNOWN.clear(); render();
    }""", isolated_context=False)
    page.locator('details.deep-note').evaluate('d => d.open = true')
    page.locator('.block-insight a.cite[href$="src-5"]').first.click()
    panel = page.locator('#evidence-panel')
    for finding in (False, True):
        if finding:
            panel.get_by_role('searchbox', name='Find in archived source').fill('Example footer')
        assert panel.locator('.msg-head').is_visible()
        assert panel.locator('.msg-subject').is_visible()
        assert panel.locator('.msg-time').is_visible()
        assert panel.locator('.msg-from').is_visible()
        bounds = panel.bounding_box()
        head = panel.locator('.msg-head').bounding_box()
        subject = panel.locator('.msg-subject').bounding_box()
        mark = panel.locator('.msg-body mark').first.bounding_box()
        assert bounds['y'] <= head['y'] < subject['y'] < mark['y']
        assert mark['y'] + mark['height'] <= bounds['y'] + bounds['height']
        assert head['y'] + head['height'] <= bounds['y'] + bounds['height']
        assert panel.evaluate('e => e.scrollWidth <= e.clientWidth')
    page.keyboard.press('Escape')
    assert not panel.is_visible()


def test_reader_copy_uses_one_local_date_format_and_omits_owner_and_redundant_badges(reader):
    page, uri = reader
    page.goto(uri + '#c=people')
    assert page.locator('main a[href="#r=people%2Favery-lin.md"]').count() == 0
    assert page.locator('.rail a.you[href="#r=people%2Favery-lin.md"]').count() == 1
    assert not page.locator('main .pill.status').filter(has_text=re.compile('^Investigated$')).count()
    values = page.evaluate("""() => {
      REM.status.timezone = 'Australia/Sydney'; REM.as_of = '2026-10-28T00:00:00Z';
      const r = byPath('people/mara-ostrowski.md');
      REM.source_context['outlook:77c09ad1e3f0'].time = '2026-10-26T13:17:00Z';
      return [fmtDate('2026-10-27'), shortDate('2026-10-27'), citationDate(r, '5'), chipLabel(r, '5'),
        fmtTime('2026-10-26T13:17:00Z'), messageMeta(REM.source_context['outlook:77c09ad1e3f0'])];
    }""", isolated_context=False)
    assert values[:3] == ['Yesterday'] * 3
    assert all('Yesterday' in text for text in values[3:])
    page.goto(uri + '#c=people')
    head = page.locator('.r4-people').inner_text()
    assert re.search(r'\d+ people', head)
    assert 'written of' not in head and 'qualifying correspondents' not in head


@pytest.mark.parametrize('width', [390, 1440])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_approve_all_sheet_slots_results_and_undo(reader, width, theme):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri)
    page.evaluate("""theme => {
      setTheme(theme); REM.live = true;
      REM.approval_outcomes = [
        {id:'reply:fern', kind:'reply', to:'fern@example.test', subject:'Pilot review', body:'Friday works.', blocked:false},
        {id:'reply:slot', kind:'reply', to:'elara@example.test', subject:'Review date', body:'【需要你：日期 — 未约定】', blocked:true},
        {id:'handled:fern', kind:'handled', title:'Fern Vale', text:'The invite is already sent.'},
        {id:'task:fern', kind:'task', title:'Fern Vale', text:'Review the pilot.'}];
      render();
    }""", theme, isolated_context=False)
    # File snapshots use mocked requests without a live mailbox.
    page.evaluate("""() => { window.approvalCalls = []; approvalRequest = async payload => {
      window.approvalCalls.push(payload);
      const release_at = new Date(Date.now() + 600000).toISOString();
      return {release_at, results: payload.ids.map(id => ({id, status: payload.action === 'undo' ? 'cancelled' : 'held', release_at}))};
    }; }""", isolated_context=False)
    page.locator('#approve-all').click()
    sheet = page.locator('#approval-sheet')
    assert sheet.is_visible()
    assert sheet.locator('input[type=checkbox]').count() == 4
    assert sheet.locator('input[type=checkbox]:checked').count() == 3
    assert sheet.locator('input[type=checkbox]:disabled').count() == 1
    assert 'fern@example.test' in sheet.inner_text() and 'Friday works.' in sheet.inner_text()
    slot = sheet.locator('textarea').nth(1)
    slot.fill('Tuesday works.')
    sheet.get_by_role('button', name='Save reply', exact=True).click()
    assert sheet.locator('input[type=checkbox]:checked').count() == 4
    shots = Path(os.environ.get('CO_REM_SHOTS', '/tmp/rem-rc60-approval-shots'))
    shots.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(shots / f'approval-ready-{theme}-{width}.png'), full_page=True)
    sheet.locator('#approval-confirm').click()
    assert sheet.locator('.approval-result').all_inner_texts() == ['Held for 10 minutes'] * 4
    assert page.evaluate('window.approvalCalls[0].bodies["reply:slot"]', isolated_context=False) == 'Tuesday works.'
    assert sheet.evaluate('n => n.scrollWidth <= n.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(shots / f'approval-held-{theme}-{width}.png'), full_page=True)
    sheet.get_by_role('button', name='Close', exact=True).click()
    page.locator('#approval-undo button').click()
    assert page.evaluate('window.approvalCalls[1].action', isolated_context=False) == 'undo'
    assert 'Cancelled' in page.locator('#approval-undo').inner_text()


def test_snapshot_approve_all_is_disabled_with_one_open_instruction(reader):
    page, uri = reader
    page.goto(uri)
    # A snapshot never gains outcomes later: no empty "Approve all 0" and no command for nothing to approve.
    assert page.locator('#approve-all').count() == 0
    assert page.locator('.approval-header code').count() == 0
    assert page.locator('.qcard a.btn-act[href^="https://"], .waiting-row a.btn-act[href^="https://"]').count() == 0


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_finished_task_card_shows_deliverable_and_owner_reply(tmp_path, monkeypatch, rem_clock, width, theme):
    """A real receipt supplies the Today card; model prose alone cannot finish it."""
    from patchright.sync_api import sync_playwright
    from connectonion.rem import night, tasks
    from connectonion.rem.config import prepare, read_config
    from connectonion.rem.files import Notebook, write_json
    from connectonion.rem.reader import render

    root = tmp_path / 'mara-rem'
    prepare(root)
    book = Notebook(root)
    book.stub_project('projects/pilot.md', 'Mara pilot', [])
    book.write('projects/pilot.md', book.read('projects/pilot.md').replace(
        '## Open threads\n', '## Open threads\n- You owe Mara a pilot review.\n'))
    night.prepare(root, read_config(root))
    receipt = tasks.reserve(root, night.listing(root)[0])
    Path(receipt['deliverable']).write_text('# Mara pilot review\nReviewed the fictional pilot.\n')
    Path(receipt['last_message']).write_text('Reviewed the Mara pilot.')
    write_json(Path(receipt['receipt']), {**receipt, 'result': 'completed', 'exit_code': 0,
                                         'started_at': '2026-09-07T10:00:00Z', 'finished_at': '2026-09-07T10:01:00Z'})
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    path = tmp_path / 'reader.html'
    path.write_text(render(root, local=True))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': width, 'height': 844})
        page.goto(path.as_uri())
        page.evaluate('theme => setTheme(theme)', theme, isolated_context=False)
        card = page.locator('.qcard').filter(has_text='Mara pilot')
        result = card.locator('.task-result')
        assert result.is_visible()
        assert 'Completed' in result.inner_text()
        assert page.locator('#approve-all').count() == 0  # nothing to approve in a snapshot
        assert receipt['deliverable'] in result.inner_text()
        assert result.locator('textarea').input_value() == f"REM 已经做完：Reviewed the Mara pilot. · 附：{receipt['deliverable']}"
        assert result.locator('textarea').get_attribute('readonly') is not None
        assert result.get_by_role('button', name='Copy prepared reply').is_visible()
        assert 'Send' not in result.locator('button').all_inner_texts()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(tmp_path / f'task-{theme}-{width}.png'), full_page=True)
        browser.close()


def _name(locator):
    """A display name as words: soft hyphens the reader adds where a word would not fit are layout, not text."""
    return locator.inner_text().replace("\xad", "")


def _green_primaries(page):
    """Visible elements filled with the Fresh green: the one primary per page."""
    return page.evaluate("""() => [...document.querySelectorAll('#main *')].filter(node => {
      const box = node.getBoundingClientRect(), fill = getComputedStyle(node).backgroundColor;
      return box.width > 0 && box.height > 0 && ['rgb(34, 210, 122)', 'rgb(59, 227, 143)'].includes(fill);
    }).map(node => node.textContent.trim())""", isolated_context=False)


# Visible Fresh-green fills; a collapsed "Full memory" note keeps its own controls out of sight.
GREEN = "() => [...document.querySelectorAll('#main *')].filter(node => node.checkVisibility() && ['rgb(34, 210, 122)', 'rgb(59, 227, 143)'].includes(getComputedStyle(node).backgroundColor)).length"


def _org_view(page, uri, hash_, width, theme):
    page.set_viewport_size({"width": width, "height": 844 if width < 600 else 900})
    page.emulate_media(color_scheme=theme)
    page.goto(uri + hash_)
    page.locator("#main .ov").wait_for()


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_person_page_leads_with_the_record_one_today_link_timeline_and_rail(reader, width, theme):
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.evaluate("theme => { setTheme(theme); setInterfaceLanguage('zh'); }", theme, isolated_context=False)
    assert _name(page.locator(".r4-person h1")) == "Mara Ostrowski"
    assert "Fernhill Labs" in page.locator(".r4-sub").inner_text()
    # The person page is her record; what you owe her is done from Today (owner, 2026-11-08).
    assert _green_primaries(page) == []
    today = page.locator(".r4-today")
    assert re.fullmatch(r"今天里有 \d+ 件", today.inner_text()) and today.get_attribute("href") == "#"
    assert today.bounding_box()["y"] + today.bounding_box()["height"] <= 844, "the Today link is on the first screen"
    assert page.locator(".r4-stats > div").count() >= 1  # mails, reply time, last word, as known (the first exchange is under the rhythm)
    assert page.locator(".r4-person #open-threads, .owe").count() == 0
    assert page.locator(".tl .tl-e .w i").count() >= 3
    # N3: how to reach her is the hero's round buttons; what REM is unsure of and the sources are cards that open more.
    assert page.locator(".hero-acts .round").count() >= 1
    assert "REM 还不确定" in page.locator(".unsure-open").inner_text()
    assert page.locator(".r4-src").inner_text().split() == ["6", "来源"]
    hero, rhythm = page.locator(".hero").bounding_box(), page.locator(".r4-fuse").bounding_box()
    assert hero["y"] + hero["height"] <= rhythm["y"], "the record's widgets sit under the hero"
    assert page.locator(".person-lead, .between-you, .relationship-stats").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


# The sheet's red, light and dark: on a record it may mean only "past due".
RED = ("rgb(192, 42, 23)", "rgb(255, 90, 60)")
RED_MARKS = r"""red => [...document.querySelectorAll('#main *')].filter(node => node.checkVisibility() && (() => {
  const s = getComputedStyle(node);
  return [s.color, s.backgroundColor, s.fill, s.stroke].some(c => red.includes(c));
})()).map(node => node.className.baseVal ?? node.className)"""


# Owner, 2026-11-08 (D-30): a person's page is their record. The fuse runs from the first
# exchange to today, one tick per dated exchange the record holds; nothing on it is a to-do.
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_person_page_is_a_record_drawn_as_a_fuse(reader, width, theme):
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.evaluate("theme => setTheme(theme)", theme, isolated_context=False)
    main = page.locator("#main")
    assert page.locator(".r4-person #open-threads, .owe").count() == 0
    assert "Mark done" not in main.inner_text() and "Still open between you" not in main.inner_text()
    page.evaluate("setInterfaceLanguage('zh')", isolated_context=False)
    assert "标为完成" not in main.inner_text()
    assert page.locator("#main a").filter(has_text=re.compile("今天里有")).count() == 1
    name = page.locator(".r4-person h1")
    assert name.evaluate("node => getComputedStyle(node).fontSize") == ("44px" if width > 640 else "36px")  # N3's one display size
    fuse = page.locator(".r4-fuse")
    dated = page.evaluate("historyItems(section(byPath('people/mara-ostrowski.md'), 'history').text).filter(i => i.day.length === 10).length",
                          isolated_context=False)
    assert dated == 5 and fuse.locator("i.l1, i.l2, i.l3").count() == dated
    # One cell per day from first contact (mail map: Aug 21) to today (Oct 1): the dark cells are the real dates, in order.
    days = fuse.locator("i.l1, i.l2, i.l3").evaluate_all("cells => cells.map(c => c.title.split(' · ')[0])")
    # The dark cells are exactly the record's dated exchanges, in calendar order.
    dates = page.evaluate("historyItems(section(byPath('people/mara-ostrowski.md'), 'history').text).filter(i => i.day.length === 10)"
                          ".map(i => i.day).sort().map(fmtDate)", isolated_context=False)
    assert days == dates and len(days) == 5 and fuse.locator(".rhythm i.today").count() == 1
    # Name and fuse lead the page, on the first screen of a phone too.
    box = fuse.bounding_box()
    assert box["y"] + box["height"] <= 844
    assert page.locator(".r4-stats .late").count() == 0 and page.evaluate(RED_MARKS, list(RED), isolated_context=False) == []
    assert page.evaluate(GREEN, isolated_context=False) == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


# A word split across lines must end its line with a hyphen: a soft hyphen the page placed, or the browser's own.
SPLIT_WORDS = r"""node => {
  const text = node.firstChild, splits = [];
  for (let i = 1; i < text.length; i++) {
    // The last client rect: a range at the start of a line also reports an empty box at the end of the one before.
    const top = (from, to) => { const r = document.createRange(); r.setStart(text, from); r.setEnd(text, to); return [...r.getClientRects()].at(-1)?.top ?? 0; };
    const a = top(i - 1, i), b = top(i, i + 1);
    if (b > a + 4 && /\S/.test(text.data[i - 1]) && /\S/.test(text.data[i])) splits.push(text.data[i - 1]);
  }
  return splits;
}"""


@pytest.mark.parametrize("name", ["Mara Ostrowski", "Tamsin Berryweather", "周泽凯", "Northgate-Universitätsverbund", "Ostrowski-Berryweather2026"])
def test_phone_display_name_hyphenates_and_never_widens_the_page(reader, name):
    page, uri = reader
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.evaluate("name => { byPath('people/mara-ostrowski.md').title = name; render(); }", name, isolated_context=False)
    h1 = page.locator(".r4-person h1")
    style = h1.evaluate("node => [node.lang, getComputedStyle(node).hyphens, getComputedStyle(node).overflowWrap]")
    assert style == ["zh" if name == "周泽凯" else "en", "auto", "break-word"]  # break-word only as the last resort
    assert h1.get_attribute("aria-label") == name
    assert h1.inner_text().replace("\xad", "") == name
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert h1.evaluate("node => node.scrollWidth <= node.clientWidth + 1")
    if name != "周泽凯":
        assert all(ch in "\xad-" for ch in h1.evaluate(SPLIT_WORDS)), "a Latin word only breaks at a hyphen"
    # A copied name is the name: the soft hyphens are layout.
    copied = h1.evaluate("""node => { const range = document.createRange(); range.selectNodeContents(node);
      getSelection().removeAllRanges(); getSelection().addRange(range);
      const data = new DataTransfer(); document.dispatchEvent(new ClipboardEvent('copy', {clipboardData: data, bubbles: true, cancelable: true}));
      return data.getData('text/plain') || String(getSelection()); }""")
    assert "\xad" not in copied and copied.replace("\n", " ").strip() == name


def test_person_fuse_burns_red_only_past_the_owners_usual_reply_time(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    rel = """([fromYou, replySeconds]) => { const r = byPath('people/mara-ostrowski.md');
      r.index = {...(r.index || {}), relationship: {last_mail: '2026-09-28T09:00:00Z', last_from_you: fromYou, reply_seconds_owner: replySeconds,
        weekly_messages: Array(52).fill(1)}}; render(); }"""
    page.evaluate(rel, [False, 3600], isolated_context=False)
    red = page.locator(".r4-stats .late")
    assert red.count() == 1
    assert red.inner_text().split("\n")[1] == "Mara wrote last"
    assert red.locator(".big").evaluate("node => getComputedStyle(node).color") in RED
    page.evaluate(rel, [True, 3600], isolated_context=False)
    assert page.locator(".r4-stats .late").count() == 0, "you wrote last: nothing is burning"
    page.evaluate(rel, [False, 10 * 86400], isolated_context=False)
    assert page.locator(".r4-stats .late").count() == 0, "still inside your usual reply time"
    page.evaluate(rel, [False, None], isolated_context=False)
    assert page.locator(".r4-stats .late").count() == 0, "no reply-time data, no red"


def test_person_fuse_without_dated_exchanges_draws_only_what_rem_knows(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.evaluate(r"""() => { const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/## History[\s\S]*?(?=\n## )/, '## History\n- Met at a meetup.\n'); KNOWN.clear(); FACTS.clear(); render(); }""",
                  isolated_context=False)
    fuse = page.locator(".r4-fuse")
    assert fuse.locator("i.l1, i.l2, i.l3").count() == 0
    assert "no dated exchanges" in fuse.locator(".rhythm").get_attribute("title")
    assert fuse.locator(".fuse-ends").inner_text().startswith("Aug 21")


@pytest.mark.parametrize("language", ["en", "zh"])
def test_person_open_topics_are_facts_without_actions(reader, language):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.evaluate("language => setInterfaceLanguage(language)", language, isolated_context=False)
    topics = page.locator(".r4-person .r4-topics")
    assert topics.locator("h2").inner_text() == ("还没结的话题" if language == "zh" else "Open topics")
    rows = topics.locator("li")
    assert rows.count() == 2
    assert "Data-sharing addendum" in topics.inner_text() and "Usage export" in topics.inner_text()
    assert rows.first.locator(".d").inner_text().strip()
    assert topics.locator("button, .chip, a.btn-act, input").count() == 0
    assert page.evaluate(GREEN, isolated_context=False) == 0


def test_today_not_done_yet_keeps_a_looks_handled_item_open_everywhere(reader):
    page, uri = reader
    page.goto(uri + "#")
    page.evaluate("""() => {
      // Your later mail looks like it settled her ask: REM would call it handled.
      const row = REM.today_queue.find(row => row.record === 'people/mara-ostrowski.md' && row.dir === 'mine');
      row.reply = {state: 'replied', since: REM.as_of.slice(0, 10), promise: 'Signed and attached.'};
      threadEntries.cached = null; render();
    }""", isolated_context=False)
    card = page.locator('.qcard[data-path="people/mara-ostrowski.md"]')
    assert card.get_attribute("data-step") == "done"
    page.locator('.deal[data-path="people/mara-ostrowski.md"]').click()  # N3: her face deals her card onto the desk
    card.get_by_role("button", name="Not done yet", exact=True).click()
    assert page.evaluate("notDoneKeys.size", isolated_context=False) == 1
    assert page.evaluate("readerStorage(notDoneStorageKey())", isolated_context=False)
    card = page.locator('.qcard[data-path="people/mara-ostrowski.md"]')
    assert card.get_attribute("data-step") != "done" and card.get_by_role("button", name="Not done yet").count() == 0
    page.goto(uri + "#c=people")
    row = page.locator(".r4 .row").filter(has_text="Mara Ostrowski")
    assert row.locator(".chip, .dot").count() >= 1, "still waiting on you in the People list"


def test_person_fuse_does_not_burn_once_today_has_it_handled(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.evaluate("""() => { const r = byPath('people/mara-ostrowski.md');
      r.index = {...(r.index || {}), relationship: {last_mail: '2026-09-28T09:00:00Z', last_from_you: false, reply_seconds_owner: 3600, weekly_messages: Array(52).fill(1)}};
      render(); }""", isolated_context=False)
    assert page.locator(".r4-stats .late").count() == 1
    page.evaluate("""() => { for (const e of personEntries(byPath('people/mara-ostrowski.md'))) threadStates[doneKey(e)] = {state: 'done', at: REM.as_of}; render(); }""",
                  isolated_context=False)
    assert page.locator(".r4-stats .late").count() == 0, "handled in Today"
    page.evaluate("""() => { for (const key of Object.keys(threadStates)) delete threadStates[key];
      window.threadDraft = () => ({status: 'no_reply', gist: 'Nothing to answer.'}); render(); }""", isolated_context=False)
    assert page.locator(".r4-stats .late").count() == 0, "no reply needed"


def test_questions_leave_the_sidebar_and_keep_their_route_and_one_quiet_door(reader):
    """Same change and test as sprint12/fuse-today 7b371a427, on this branch's fixture."""
    page, uri = reader
    page.evaluate("""() => { REM.reviews = [{id: 'r1', status: 'pending', kind: 'link', question: 'Is Mara at Fernhill Labs?',
      basis: 'Two cited mails.', subjects: ['people/mara-ostrowski.md']}]; render(); }""", isolated_context=False)
    assert page.locator('#nav a[href="#reviews=1"]').count() == 0
    assert "Questions & connections" not in page.locator("#nav").inner_text()
    page.goto(uri + "#view=changes")
    door = page.locator('#main a[href="#reviews=1"]')
    assert door.count() == 1 and door.evaluate("a => !!a.closest('#main')")
    door.click()
    page.get_by_role("heading", name="Questions & connections", exact=True).wait_for()


def test_person_quotes_carry_their_source_and_open_the_original(reader):
    from patchright.sync_api import expect
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    quotes = page.locator(".r4-said li")
    assert quotes.count() == 3
    assert "Could the renewal include a fourth seat?" in quotes.first.inner_text()
    assert "Gmail" in quotes.first.locator(".said-src").inner_text()
    cite = quotes.first.locator("a.cite")
    expect(cite).to_be_visible()
    assert "h=src-" in cite.get_attribute("href")
    cite.click()
    expect(page.locator("#evidence-panel")).to_be_visible()
    assert page.locator("details.deep-note").get_attribute("open") is None


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_people_are_a_record_list_with_search_few_tabs_and_one_quiet_today_link(reader, width, theme):
    """People is a record, not a to-do list: no waiting headline, no green, one quiet link to Today."""
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(uri + "#c=people")
    page.evaluate("theme => { setTheme(theme); setInterfaceLanguage('zh'); }", theme, isolated_context=False)
    assert re.fullmatch(r"\d+ 人", page.locator(".r4-people h1").inner_text().strip())
    today = page.locator(".r4-people .list-today")
    assert re.fullmatch(r"今天里有 \d+ 人在等你 →", today.inner_text()) and today.get_attribute("href") == "#"
    assert _green_primaries(page) == []
    assert page.locator(".r4-find").count() == 1
    assert page.locator(".r4-tabs button").count() <= 4
    groups = page.locator(".r4 .grp").all_inner_texts()
    assert groups[0].startswith("在等你") and groups[-1] == "最近联系"
    assert page.locator("table.sheet").count() == 0
    rows = page.locator(".r4 .row.prow")
    assert rows.count() >= 4
    assert all(box["height"] >= 56 for box in (rows.nth(i).bounding_box() for i in range(rows.count())))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator(".r4-find").fill("mara")
    assert page.locator(".r4 .row.prow .nm").all_inner_texts()[0] == "Mara Ostrowski"
    page.get_by_role("button", name="表格").click()
    assert page.locator("table.sheet").is_visible()
    page.get_by_role("button", name="列表").click()
    assert page.locator("table.sheet").count() == 0


def _visible_green_buttons(page):
    page.wait_for_timeout(300)  # let the theme's colour transition settle
    return page.evaluate("""() => [...document.querySelectorAll('#main *')].filter(node => {
      const style = getComputedStyle(node), box = node.getBoundingClientRect();
      return box.width && box.height && ['rgb(34, 210, 122)', 'rgb(59, 227, 143)'].includes(style.backgroundColor);
    }).length""")


# A notebook-sized set of invented projects (fixture date 2026-10-01), shaped like the snapshot's
# project data: health, priority reasons, open items by kind, written dates, a parent suggestion,
# a duplicate suggestion, coverage, cited Facts and session relations. Ported from the sprint-10
# project views and extended with what the 墨与铅 directory draws (ticks, coverage, facts).
PROJECT_SET = r"""() => {
  const quiet = byPath('projects/lantern.md');
  const owed = (who, text, extra = {}) => ({text, kind: 'owed', who, since: null, due: null, sources: [], promised: [], answer: null, ...extra});
  const reason = (text, points) => ({text, points, source: 'fixture', cite: null, path: 'fixture', sources: []});
  const link = path => ({path, kind: 'linked', basis: '', private: false, sources: ['1'], via: path});
  const sessions = (slug, days) => days.map(day => ({path: 'sessions/' + day + '-' + slug + '.md', kind: 'linked from', basis: 'Project', private: false, sources: [], via: ''}));
  const fact = value => [{value, qualifier: '', citations: ['1']}];
  const text = (slug, title, f) => '# ' + title + '\n\n## What it is\n- ' + f.what + ' [1].\n'
    + '\n## Open threads\n' + ((f.open || []).length ? f.open.map(item => '- ' + item.text).join('\n') : '- Nothing open.') + '\n'
    + '\n## Paths\n- /work/' + slug + ' [1]\n- Last seen: ' + f.last_activity + '\n'
    + '\n## Sources\n- [1] codex:' + slug + ' — project notes; observed ' + f.last_activity + '.\n'
    + '\nInvestigation: mapped 2026-08-20 · investigated 2026-09-30 (codex)\n';
  const project = (slug, title, f) => ({...quiet, path: 'projects/' + slug + '.md', title, written: true, relations: [], parent: null, same_as: [],
    promised: [], written_deadlines: [], pinned: false, open: [], kind_counts: {owed: 0, waiting: 0, agent: 0, answerable: 0}, reasons: [],
    facts: {Repository: fact(slug), Stack: [], Status: [], People: [], Organisation: [], Started: [], 'Last activity': fact(f.last_activity)},
    project_coverage: null, updated: '2026-09-30T08:00:00+00:00', date_sources: {last_activity: {cite: '1'}},
    ...f, text: text(slug, title, f)});
  const feedback = {date: '2026-09-17', text: 'Feedback for Tomas', source: 'fixture', cite: null, path: 'fixture'};
  const atlasDays = ['2026-09-08', '2026-09-12', '2026-09-16', '2026-09-22', '2026-09-26', '2026-09-30'];
  REM.records.push(
    project('fernhill-pilot', 'Fernhill pilot', {score: 22, priority: 1, health: 'at_risk', last_activity: '2026-09-28',
      what: 'A paid pilot of the weekly brief for Fernhill Labs', relations: [link('orgs/fernhill-labs.md'), ...sessions('fernhill', ['2026-09-20', '2026-09-28'])],
      facts: {Repository: fact('fernhill-pilot'), Stack: fact('Python'), Status: [], People: fact('Mara Ostrowski'), Organisation: [], Started: [], 'Last activity': fact('2026-09-28')},
      project_coverage: {inputs_read: 2, inputs_available: 40, days: 30, scope: 'archived'},
      open: [owed('people/mara-ostrowski.md', 'You owe Mara the weekly chart report [1].', {since: '2026-09-26'}),
             owed('people/mara-ostrowski.md', 'You owe Fernhill the handover bundle [1].', {since: '2026-09-28'}),
             {...owed(null, 'Ask Codex to rerun the import [1].'), kind: 'agent'}],
      kind_counts: {owed: 2, waiting: 0, agent: 1, answerable: 0},
      reasons: [reason('paying client: 5 × 1; You owe Mara the weekly chart report [1].', 5)]}),
    project('capstone-review', 'Capstone review', {score: 14, priority: 2, health: 'off_track', last_activity: '2026-09-21',
      what: 'Reviewing student capstone reports for the spring cohort', relations: sessions('capstone', ['2026-09-10', '2026-09-21']),
      overdue_days: 14, project_coverage: {inputs_read: 5, inputs_available: 5, days: 30, scope: 'archived'},
      open: [owed('people/tomas-reyes.md', 'You owe Tomas feedback by 2026-09-17 [1].', {since: '2026-09-10', due: '2026-09-17', promised: [feedback]}),
             ...['Rowan', 'Juniper', 'Sasha'].map(name => owed(null, name + ' waits for feedback on the report [1].', {since: '2026-09-17'}))],
      kind_counts: {owed: 4, waiting: 0, agent: 0, answerable: 0}, promised: [feedback],
      reasons: [reason('Overdue promise to Tomás Reyes: 14 days late; You owe Tomas feedback by 2026-09-17 [1].', 0)]}),
    project('grant', 'Grant application', {score: 8, priority: 3, health: 'at_risk', last_activity: '2026-09-15', what: 'A research grant with Fernhill Labs',
      open: [owed(null, 'You owe Fern the budget line [1].', {since: '2026-09-15'})], kind_counts: {owed: 1, waiting: 0, agent: 0, answerable: 0},
      written_deadlines: [{date: '2026-10-20', text: 'Letter of support due', source: 'fixture', cite: null, path: 'fixture'},
                          {date: '2026-10-20', text: 'Budget table due', source: 'fixture', cite: null, path: 'fixture'}]}),
    project('atlas', 'Atlas', {score: 6, priority: 3, health: 'on_track', last_activity: '2026-09-30', what: 'The shared mapping toolkit',
      relations: sessions('atlas', atlasDays), project_coverage: {inputs_read: 6, inputs_available: 6, days: 30, scope: 'archived'},
      open: [owed(null, 'You owe Fern a review of the tile format [1].', {since: '2026-09-29'})], kind_counts: {owed: 1, waiting: 0, agent: 0, answerable: 0}}),
    // Shares every Atlas session: a computed "may be one project" pair, as well as a sub-project.
    project('atlas-api', 'atlas-api', {score: 1, priority: 4, health: 'on_track', last_activity: '2026-09-29', what: 'The tile server behind Atlas',
      relations: sessions('atlas', atlasDays),
      parent: {path: 'projects/atlas.md', suggestion: true, reason: 'component repository', source: 'fixture', cite: null, via: 'projects/atlas-api.md'}}),
    // A sub-project that is off track: it counts, it has a column and a date, though the list nests it.
    project('atlas-docs', 'atlas-docs', {score: 0.5, priority: 4, health: 'off_track', last_activity: '2026-08-02', what: 'The Atlas handbook',
      open: [owed(null, 'You owe Fern the install chapter by 2026-09-24 [1].', {since: '2026-09-01', due: '2026-09-24', needs_review: false})],
      kind_counts: {owed: 1, waiting: 0, agent: 0, answerable: 0},
      parent: {path: 'projects/atlas.md', suggestion: true, reason: 'component repository', source: 'fixture', cite: null, via: 'projects/atlas-docs.md'}}),
    project('agent-only', 'Night jobs', {score: 0.5, priority: 4, health: 'on_track', last_activity: '2026-09-29', what: 'Scheduled clean-up jobs',
      open: [{...owed(null, 'Ask Claude to tidy the logs [1].'), kind: 'agent'}], kind_counts: {owed: 0, waiting: 0, agent: 1, answerable: 0}}),
    // A past date on something the owner waits for is drawn, but never as late.
    project('waiting-room', 'Waiting room', {score: 0.25, priority: 4, health: 'on_track', last_activity: '2026-09-27', what: 'Renting a studio room',
      open: [{...owed('people/quinn-alder.md', 'Waiting on Quinn for the contract [1].'), kind: 'waiting'}], kind_counts: {owed: 0, waiting: 1, agent: 0, answerable: 0},
      promised: [{date: '2026-09-20', text: 'Contract from Quinn', source: 'fixture', cite: null, path: 'fixture'}]}),
    // On track, but its last session was 29 days ago: the 30-day rule turns it quiet within the week.
    project('tidewater', 'Tidewater', {score: 0, priority: 4, health: 'on_track', last_activity: '2026-09-02', what: 'A tide-table widget'}),
    project('harbour-copy', 'harbour', {score: 0, priority: 0, health: 'quiet', last_activity: '2026-08-10', what: 'An older page for the shared-inbox tool',
      same_as: [{path: 'projects/harbour.md', suggestion: true, reason: 'same title', source: 'fixture', cite: null, via: 'projects/harbour-copy.md'}]}),
    project('workshop', 'Spring workshop', {score: 0, priority: 0, health: 'quiet', last_activity: '2026-07-18', what: 'A one-day workshop for founders',
      reasons: [reason('Project explicitly marked completed', 0)]}),
    ...['Moss archive', 'Tidepool', 'Lark notes', 'Juniper site', 'Hollow CLI', 'Birch dashboard', 'Quill export', 'Ember forms', 'Wren mail']
      .map((title, i) => ({...quiet, path: 'projects/mapped-' + i + '.md', title, text: quiet.text.replace(/^# .*/, '# ' + title)})));
  KNOWN.clear(); FACTS.clear(); render();
}"""


def _project_page(reader, view, width=1440, theme="light", extra=""):
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1440 else 844})
    page.emulate_media(color_scheme=theme, reduced_motion="reduce")
    page.goto(uri + "#c=projects&v=" + view + extra)
    page.evaluate(PROJECT_SET, isolated_context=False)
    return page


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("view", ["timeline", "list", "board"])
def test_project_directory_opens_on_one_rem_sentence_with_no_green_and_no_overflow(reader, view, width, theme):
    """墨与铅: one REM sentence in the reader's one sans, red only for the overdue promise, no green on the
    directory (none of its record actions can write yet), and no sideways scroll on a phone."""
    from patchright.sync_api import expect

    page = _project_page(reader, view, width, theme)
    expect(page.locator(".pd")).to_have_attribute("data-view", view)
    total = page.evaluate("inCategory('projects').length", isolated_context=False)
    expect(page.locator(".pd-count")).to_have_text(str(total))  # sub-projects count
    # Owner, 2026-11-09 (sidebar in Fuse): the rail carries no category counts; the title is the count's home.
    expect(page.locator('#nav a[href="#c=projects"] .n')).to_have_count(0)
    expect(page.locator(".pd-views [aria-current='page']")).to_have_text({"timeline": "Timeline", "list": "List", "board": "Board"}[view])
    lede = page.locator(".pd-lede")
    expect(lede).to_contain_text(f"{total} projects on record")
    tomas = page.evaluate("byPath('people/tomas-reyes.md').title", isolated_context=False)
    expect(lede.locator(".red")).to_have_text(f"On Capstone review, a promise to {tomas} is 14 days late.")
    assert "Songti" not in lede.evaluate("node => getComputedStyle(node).fontFamily")  # one typeface across the reader
    expect(page.locator(".pd-basis")).to_contain_text("made by rule")
    assert _visible_green_buttons(page) == 0
    # Nothing REM does not have is drawn: no families, no grouping or merge button, no per-project line.
    assert page.locator(".pd").get_by_text(re.compile(r"Accept|Merge|采用|合并")).count() == 0
    assert page.locator(".pd :is(button, a).btn-act").count() == 0
    assert "/home/user" not in page.locator("#main").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_project_timeline_draws_session_ticks_the_late_line_and_pencil_forecasts(reader, width):
    from patchright.sync_api import expect

    page = _project_page(reader, "timeline", width)
    row = lambda slug: page.locator(f'.pd-row[data-path="projects/{slug}.md"]')
    expect(row("atlas").locator(".pd-tick")).to_have_count(6)  # one per session day, the last activity among them
    expect(row("capstone-review").locator(".pd-late")).to_have_count(1)
    expect(row("capstone-review").locator(".pd-late-n")).to_have_text("14 days late")
    # Waiting on someone past their date is drawn as a past date, never as late.
    expect(row("waiting-room").locator(".pd-late")).to_have_count(0)
    # Pencil only right of today, only for on-track projects, and it names its rule.
    expect(row("atlas").locator(".pd-pencil")).to_have_attribute("title", "Turns quiet on Oct 31 by the 30-day rule if no session comes")
    expect(row("capstone-review").locator(".pd-pencil")).to_have_count(0)
    assert page.evaluate("""() => [...document.querySelectorAll('.pd-pencil')].every(node =>
      parseFloat(node.style.left) === parseFloat(node.parentNode.querySelector('.pd-now').style.left))""", isolated_context=False)
    # A sub-project sits right under its project.
    order = page.evaluate("[...document.querySelectorAll('.pd-row[data-path]')].map(n => n.dataset.path)", isolated_context=False)
    assert order.index("projects/atlas-api.md") == order.index("projects/atlas.md") + 1
    # REM's notes: rule-made, five at most; the overdue one is a fact in red, the duplicate a dashed inference.
    notes = page.locator(".pd-note")
    assert 1 <= notes.count() <= 5
    expect(row("capstone-review").locator(".pd-kicker")).to_have_text("Overdue")
    expect(row("capstone-review").locator(".pd-note")).to_contain_text("Feedback for Tomas. Due Sep 17, still open, 14 days late.")
    expect(row("fernhill-pilot").locator(".pd-kicker")).to_have_text("Read a corner")
    expect(row("tidewater").locator(".pd-note-pencil")).to_contain_text("Tidewater (Oct 3)")
    assert row("atlas-api").locator(".pd-note-inference .pd-inf").count() == 1
    # Quiet projects fold into one row that unfolds in place.
    fold = page.locator(".pd-row.pd-fold")
    expect(fold).to_contain_text(re.compile(r"\d+ quiet"))
    assert row("workshop").count() == 0
    fold.get_by_role("button", name="Show").click()
    expect(row("workshop")).to_be_visible()
    # REM's own row is the days it wrote pages.
    assert page.locator(".pd-rem-row .pd-ring").count() >= 1
    # Labels never sit on marks: the due label clears the strip, and a month label the today marker
    # covers is hidden (the scrum master read "今天 1月" with 11月 clipped on a phone).
    assert page.evaluate("""() => {
      const hit = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      const row = document.querySelector('.pd-row[data-path="projects/capstone-review.md"]');
      const label = row.querySelector('.pd-lbl.red').getBoundingClientRect();
      const marks = [...row.querySelectorAll('.pd-tick, .pd-late')].map(n => n.getBoundingClientRect());
      const today = document.querySelector('.pd-now-label').getBoundingClientRect();
      const months = [...document.querySelectorAll('.pd-col-label')].filter(n => getComputedStyle(n).visibility !== 'hidden').map(n => n.getBoundingClientRect());
      // Only the label the marker covers goes: every other month keeps its name.
      const hidden = [...document.querySelectorAll('.pd-col-label')].filter(n => getComputedStyle(n).visibility === 'hidden').length;
      return !marks.some(m => hit(label, m)) && !months.some(m => hit(today, m)) && hidden <= 1;
    }""", isolated_context=False)
    # Zoom rewrites the window and the sentence together.
    page.locator(".pd-seg").get_by_role("link", name="Week").click()
    expect(page.locator(".pd")).to_have_attribute("data-zoom", "week")
    expect(page.locator(".pd-lede")).to_contain_text(re.compile(r"projects? moved this week"))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("width", [1440, 390])
def test_project_timeline_month_headers_are_never_cut(reader, width, language):
    """At 1440 "Mostly ConnectOnion and browser · 106 session days" lost its last line to the
    header's fixed height. Every month header shows all of its text, at both widths."""
    page = _project_page(reader, "timeline", width)
    page.evaluate("""language => {
      if (language === 'zh') setInterfaceLanguage('zh');
      byPath('projects/atlas.md').title = 'ConnectOnion platform and agents';
      byPath('projects/atlas-api.md').title = 'browser automation (onionwright)';
      render();
    }""", language, isolated_context=False)
    cut = page.evaluate("""() => [...document.querySelectorAll('.pd-col')].filter(col => getComputedStyle(col).display !== 'none')
      .flatMap(col => [col, ...col.children]).filter(n => getComputedStyle(n).display !== 'none'
        && (n.scrollHeight > n.clientHeight + 1 || n.scrollWidth > n.clientWidth + 1)).map(n => n.className + ' ' + [n.scrollWidth, n.clientWidth, n.scrollHeight, n.clientHeight] + ': ' + n.textContent)""",
                        isolated_context=False)
    assert cut == []
    if width == 1440:  # the line is drawn there, so the check above is not vacuous
        assert "ConnectOnion" in page.locator(".pd-col-line").first.inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_project_list_names_what_is_on_file_instead_of_unlabelled_squares(reader, width):
    """P大 on the approved list mock: "那排小方块是啥？" Seven unlabelled squares made the reader
    decode which fact was missing. The cell now names the gap in words, keeps the full list on hover,
    and says when REM never investigated, which is why everything was empty."""
    from patchright.sync_api import expect

    page = _project_page(reader, "list", width)
    page.locator(".pd-fold").get_by_role("button", name="Show").click()  # mapped pages are quiet, so they fold
    row = lambda slug: page.locator(f'.pd-lrow[data-path="projects/{slug}.md"]')
    fernhill = row("fernhill-pilot").locator(".pd-lknown span")
    expect(fernhill).to_have_text("Missing: status, organisation, start")
    expect(fernhill).to_have_attribute("title", "On file: repository, stack, people, last activity. Not on file: status, organisation, start.")
    expect(row("atlas").locator(".pd-lknown span")).to_have_text("Only: repository, last activity")
    expect(row("mapped-0").locator(".pd-lknown")).to_have_text("Not investigated")
    assert page.locator(".pd-lknown i").count() == 0  # no squares left to decode
    if width == 1440:
        expect(page.locator(".pd-lhead")).to_contain_text("On file (7)")
    # An agent instruction is not owed, and it says who has it in the owner's words.
    expect(row("fernhill-pilot").locator(".pd-lopen")).to_have_text("You owe 2 · Handed to agents 1")
    expect(row("capstone-review").locator(".pd-lopen .red")).to_have_text("You owe 4")
    expect(row("fernhill-pilot").locator(".pd-lread .pd-partial")).to_have_text("2/40")
    expect(row("grant").locator(".pd-lread")).to_have_text("No record")
    expect(row("tidewater").locator(".pd-llast small")).to_have_text("No sessions")
    expect(row("atlas-api")).to_have_class(re.compile(r"\bkid\b"))
    expect(row("capstone-review").locator(".pd-lhealth")).to_contain_text("14 days late")
    page.evaluate("setInterfaceLanguage('zh')", isolated_context=False)
    expect(fernhill).to_have_text("缺 状态、组织、开始")
    expect(row("fernhill-pilot").locator(".pd-lopen")).to_have_text("你欠 2 · 交给智能体 1")
    expect(page.locator(".pd-views a")).to_have_text(["时间线", "列表", "看板"])
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_project_board_axis_is_a_question_and_each_answer_is_computed(reader, width):
    from patchright.sync_api import expect

    page = _project_page(reader, "board", width)
    cols = page.locator(".pd-colm h2 > span")
    expect(cols).to_have_text(["Off track", "At risk", "On track", "Quiet"])
    expect(page.locator(".pd-colm").first.locator(".pd-card")).to_have_count(2)  # atlas-docs, a sub-project, has its card
    expect(page.locator(".pd-pencil-box")).to_contain_text("Tidewater")
    expect(page.locator('.pd-card[data-path="projects/fernhill-pilot.md"]')).to_have_class(re.compile(r"\bweak\b"))  # read 2 of 40
    page.locator(".pd-asks").get_by_role("link", name="Who waits on whom").click()
    expect(page.locator(".pd-colm h2 > span")).to_have_text(["You owe others", "You wait on others", "Only with agents", "No open promise"])
    quinn = page.evaluate("byPath('people/quinn-alder.md').title", isolated_context=False)
    expect(page.locator('.pd-card[data-path="projects/waiting-room.md"] .pd-card-extra')).to_have_text("Waiting on: " + quinn)
    page.locator(".pd-asks").get_by_role("link", name="What may be one project").click()
    shared = page.locator(".pd-colm").nth(0).locator(".pd-pair")
    expect(shared).to_have_count(1)
    expect(shared).to_contain_text("6/6 sessions shared · may be one project")
    expect(page.locator(".pd-colm").nth(1).locator(".pd-pair")).to_contain_text("harbour")
    assert page.locator(".pd-pair .tag").count() == page.locator(".pd-pair").count()  # every pair is labelled an inference
    page.locator(".pd-asks").get_by_role("link", name="What can be set down").click()
    expect(page.locator(".pd-answer .pd-inf")).to_have_text("can be set down")
    assert _visible_green_buttons(page) == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_project_rank_breaks_ties_by_a_casefolded_name(reader):
    page, uri = reader
    page.goto(uri + "#c=projects")
    order = page.evaluate("""() => [{title: 'beta'}, {title: 'Ａlpha'}, {title: 'Gamma'}]
      .map(r => ({...r, score: 1, open: [], pinned: false})).sort(projectRank).map(r => r.title)""", isolated_context=False)
    assert order == ['Ａlpha', 'beta', 'Gamma']  # full-width Ａ folds to a, as casefold plus NFKC would


def test_project_marks_are_late_only_for_owed_due_and_keep_same_day_deadlines(reader):
    page = _project_page(reader, "timeline")
    marks = page.evaluate("""() => Object.fromEntries(['grant', 'waiting-room', 'capstone-review', 'atlas-docs']
      .map(slug => [slug, projectMarks(byPath('projects/' + slug + '.md')).map(m => [m.day, m.text, m.state])]))""", isolated_context=False)
    assert marks['waiting-room'] == [['2026-09-20', 'Contract from Quinn', 'past']]  # owed to you: drawn, never late
    assert marks['grant'] == [['2026-10-20', 'Budget table due', 'next'], ['2026-10-20', 'Letter of support due', 'next']]
    assert marks['capstone-review'] == [['2026-09-17', 'Feedback for Tomas', 'late']]  # the promise and its due item are one mark
    [(day, what, state)] = marks['atlas-docs']  # a due item without a named promise is labelled by its own words
    assert (day, state) == ('2026-09-24', 'late') and what.startswith('You owe Fern the install chapter')


def test_project_dates_fall_back_to_the_clock_without_a_snapshot_date(reader):
    page = _project_page(reader, "timeline")
    state = page.evaluate("""() => { REM.as_of = undefined;
      return projectMarks(byPath('projects/capstone-review.md')).map(m => m.state); }""", isolated_context=False)
    assert state == ['late']  # today is the clock's day, never an empty string that makes every date "next"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1400, 390])
def test_sessions_group_by_day_merge_repeats_curtain_private_work_and_lead_with_resume(session_reader, width, theme):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 844})
    page.evaluate("""theme => {
      setTheme(theme);
      const release = REM.records.find(r => r.path === 'sessions/release.md');
      REM.records.push({...release, path: 'sessions/release-again.md'});
      byPath('projects/beta.md').private_project = true;
      REM.records.find(r => r.path === 'sessions/release.md').session_outcome = 'partial';
      render();
    }""", theme, isolated_context=False)
    expect(page.locator("h1.page-state")).to_have_text(re.compile(r"^7 sessions"))
    resume = page.locator(".session-stopped")
    expect(resume.locator("h2")).to_have_text("Release the reader")
    expect(resume.locator(".session-stopped-todos li")).to_have_text(["Ask Avery to check the reader."])
    expect(resume.locator(".btn-act")).to_have_text("Continue in Codex")
    expect(resume.locator(".btn-act")).to_have_attribute("href", "#r=sessions%2Frelease.md&h=session-continue")
    assert _visible_green_buttons(page) == 1
    expect(page.locator(".session-tabs button")).to_have_count(4)
    expect(page.locator(".session-day").first).to_have_text("TodayFri")
    merged = page.locator(".session-row").filter(has_text="Release the reader")
    expect(merged).to_have_count(1)
    expect(merged.locator(".session-meta")).to_have_text("Alpha · 12 turns · 2 sessions · 1 to-do")
    curtains = page.locator(".session-curtain")
    expect(curtains).to_have_count(2)
    assert "Plan source citations" not in page.locator("#main").inner_text()
    assert "Review older notes" not in page.locator("#main").inner_text()
    assert "/work/" not in page.locator("#main").inner_text()
    curtains.first.get_by_role("button", name="Show", exact=True).click()
    expect(page.locator(".session-row").filter(has_text="Plan source citations")).to_have_count(1)
    if width == 390:
        box = resume.locator(".btn-act").bounding_box()
        assert box["y"] + box["height"] < 844
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_sessions_tabs_choose_unfinished_or_one_agent(session_reader):
    from patchright.sync_api import expect

    page, uri = session_reader
    tabs = page.locator(".session-tabs")
    expect(tabs.locator("button")).to_have_text(["All", "Unfinished 1", "Codex", "Claude Code"])
    tabs.get_by_role("button", name="Unfinished 1").click()
    assert "outcome=partial" in page.url
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    tabs.get_by_role("button", name="Codex", exact=True).click()
    assert "agent=codex" in page.url and "outcome=" not in page.url
    expect(page.locator(".session-result-line")).to_contain_text("3 of 6 sessions")
    expect(tabs.get_by_role("button", name="Codex", exact=True)).to_have_attribute("aria-pressed", "true")
    tabs.get_by_role("button", name="All", exact=True).click()
    expect(page.locator(".session-result-line")).to_have_count(0)
    page.evaluate("setInterfaceLanguage('zh')", isolated_context=False)
    expect(tabs.locator("button")).to_have_text(["全部", "没做完 1", "Codex", "Claude Code"])
    expect(page.locator("h1.page-state")).to_have_text("6 个会话 · 和编程 agent 一起做的事")


@pytest.mark.parametrize("width", [1400, 375])
def test_sessions_filters_notebook_calendar_and_groups(session_reader, width):
    """The simplified list keeps bookmarked project/date filters and day groups."""
    from patchright.sync_api import expect
    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 812})
    page.goto(uri + "#c=sessions&project=projects%2Falpha.md&agent=codex")
    expect(page.locator(".session-row")).to_have_count(2)
    expect(page.locator(".session-tabs").get_by_role("button", name="Codex", exact=True)).to_have_attribute("aria-pressed", "true")
    page.goto(uri + "#c=sessions&when=month")
    expect(page.locator(".session-result-line")).to_contain_text("5 of 6 sessions")
    page.goto(uri + "#c=sessions&from=2026-10-11&to=2026-10-12")
    expect(page.locator(".session-row")).to_have_count(2)
    expect(page.locator(".session-day")).to_have_count(2)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for node in page.locator(".sessions-view button:visible, .sessions-view input:visible").all():
        assert node.bounding_box()["height"] >= (40 if width == 375 else 32)


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_org_list_is_a_record_with_one_quiet_today_link_and_no_green(reader, width, theme):
    page, uri = reader
    _org_view(page, uri, "#c=orgs", width, theme)
    assert re.fullmatch(r"\d+ organisations", page.locator(".ov-list h1").inner_text().strip())
    assert page.locator(".ov-focal").count() == 0
    assert page.evaluate(GREEN) == 0
    assert page.locator(".ov-list .list-today").inner_text() == "1 organisation waiting in Today →"
    assert page.get_by_role("heading", name=re.compile(r"^Waiting on you · 1")).is_visible()
    row = page.locator(".ov-row").filter(has_text="Fernhill Labs")
    assert row.locator(".ov-tile").evaluate("node => getComputedStyle(node).borderRadius") != "50%"
    assert page.locator(".ov-tabs button").count() <= 4
    assert page.locator(".ov-find").count() == 1
    page.locator(".ov-find").fill("no such organisation")
    assert page.locator(".ov-row").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_org_page_answers_who_they_are_and_who_you_know(reader, width, theme):
    page, uri = reader
    _org_view(page, uri, "#r=orgs%2Ffernhill-labs.md", width, theme)
    # A record of the organisation: its name leads, what you owe is one quiet link to Today.
    assert _name(page.locator(".ov-say .ov-name")) == "Fernhill Labs"
    owed = page.evaluate("orgOwed(byPath('orgs/fernhill-labs.md')).length", isolated_context=False)
    today = page.locator(".ov-say .ov-today")
    assert today.inner_text() == f"{owed} things in Today involve Fernhill Labs →"
    assert today.bounding_box()["y"] + today.bounding_box()["height"] <= (844 if width < 600 else 900)
    assert page.evaluate(GREEN) == 0
    for selector in (".ov-xray .ov-node", ".ov-structure .ov-m", ".ov-people li", ".ov-coda .ov-src"):
        assert page.locator(selector).first.is_visible(), selector
    assert page.locator(".ov-owed, .ov-ball").count() == 0
    assert "Mara Ostrowski" in page.locator(".ov-people").inner_text()
    assert page.locator(".ov-coda").bounding_box()["y"] > page.locator(".ov-people").bounding_box()["y"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_org_with_nothing_owed_has_no_green_button(reader, width):
    page, uri = reader
    _org_view(page, uri, "#r=orgs%2Ffernhill-labs.md", width, "light")
    page.evaluate("() => { for (const r of REM.records) if (r.category === 'orgs') r.obligations = []; render(); }", isolated_context=False)
    assert page.evaluate(GREEN) == 0
    assert page.locator(".ov-primary").count() == 0
    assert page.locator(".ov-today").count() == 0
    page.evaluate("() => { location.hash = 'c=orgs'; }", isolated_context=False)
    page.locator(".ov-list").wait_for()
    assert page.locator(".ov-list .list-today").count() == 0
    assert page.evaluate(GREEN) == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_private_org_keeps_its_relationship_out_of_the_dom_until_shown(reader):
    page, uri = reader
    _org_view(page, uri, "#c=orgs", 1440, "light")
    page.evaluate("() => { byPath('orgs/fernhill-labs.md').private = true; render(); }", isolated_context=False)
    row = page.locator(".ov-row").filter(has_text="Fernhill Labs")
    assert "Personal · shown only on this Mac" in row.inner_text()
    assert page.locator(".ov-focal").count() == 0
    assert row.locator(".ov-dot, .ov-chip").count() == 1
    assert "pilot" not in page.locator("#main").inner_text().lower()
    page.evaluate("() => { location.hash = 'r=orgs%2Ffernhill-labs.md'; }", isolated_context=False)
    page.locator(".ov-curtain").wait_for()
    assert page.locator(".ov-primary").count() == 0
    assert "climate" not in page.locator("#main").inner_html().lower()
    page.get_by_role("button", name="Show", exact=True).click()
    assert page.locator(".ov-xray .ov-node").count() >= 2
    assert page.locator(".ov-today").count() == 1
    assert page.evaluate(GREEN) == 0


@pytest.mark.parametrize("width", [1440, 390])
def test_org_page_shows_each_labelled_passage_with_its_own_reveal(reader, width):
    # An organisation with labelled passages is a record like a person: each passage shows with its
    # label on the owner's Mac and hides alone when labelled passages are hidden. Before, the lead,
    # What they do and History dropped them silently, with nothing to say they were there.
    page, uri = reader
    _org_view(page, uri, "#r=orgs%2Ffernhill-labs.md", width, "light")
    page.evaluate("""() => { const org = byPath('orgs/fernhill-labs.md');
      org.to_you = 'Mara confided a family illness [personal]. Your first paying pilot.';
      org.text = org.text.replace('## Domains', '## Facts\\n- What they do: Climate data. Founder is in a lawsuit [sensitive] [1]\\n\\n'
        + '## History\\n- ' + REM.as_of.slice(0, 7) + '-02: Pilot kickoff with Mara [1]\\n- ' + REM.as_of.slice(0, 7) + '-03: Mara shared a diagnosis [personal] [1]\\n\\n## Domains');
      KNOWN.clear(); FACTS.clear(); render(); }""", isolated_context=False)
    sub, about, lately = page.locator(".ov-sub"), page.locator(".ov-about"), page.locator(".ov-tl")
    assert "Your first paying pilot." in sub.inner_text()
    for box, secret in ((sub, "family illness"), (about, "lawsuit"), (lately, "diagnosis")):
        assert secret in box.inner_text(), (secret, box.inner_text())
        assert box.locator(".private .privacy-tag").count() >= 1
    page.evaluate("togglePrivate()", isolated_context=False)
    for box, secret in ((sub, "family illness"), (about, "lawsuit"), (lately, "diagnosis")):
        assert secret not in box.inner_text()
    assert "Pilot kickoff" in lately.inner_text() and "Climate data." in about.inner_text()
    # The fuse's tooltips never carry a labelled exchange.
    assert "diagnosis" not in page.locator(".ov-time").inner_html()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_org_kind_and_teams_appear_when_the_page_records_them(reader):
    page, uri = reader
    _org_view(page, uri, "#r=orgs%2Ffernhill-labs.md", 1440, "light")
    assert "Client or partner" not in page.locator(".ov-sub").inner_text()
    assert page.locator(".ov-xray .ov-node[data-shape=circle]").count() == 0
    page.evaluate("""() => { const org = byPath('orgs/fernhill-labs.md');
      org.kind = 'client_partner'; org.to_you = 'Your first paying pilot.';
      byPath('people/mara-ostrowski.md').team = 'Pilot squad'; render(); }""", isolated_context=False)
    assert page.locator(".ov-sub").inner_text() == "Client or partner · Your first paying pilot."
    # A free-text team groups its people (a circle and a row) but never becomes a unit link.
    assert page.locator(".ov-xray .ov-node[data-shape=circle]").count() == 1
    team = page.locator(".ov-outline .ov-tn").filter(has_text="Pilot squad")
    assert team.count() == 1 and team.locator("a").count() == 0


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_org_hierarchy_links_nested_units_and_their_people_with_roles(reader, width, theme):
    from patchright.sync_api import expect
    page, uri = reader
    _org_view(page, uri, '#r=orgs%2Ffernhill-labs.md', width, theme)
    page.evaluate("""() => {
      const org = byPath('orgs/fernhill-labs.md'), mara = byPath('people/mara-ostrowski.md');
      const course = {...org, path: 'orgs/pilot-course.md', title: 'Pilot course', unit_kind: 'course', kind: '',
        text: '# Pilot course', children: ['orgs/pilot-squad.md'], people: [mara.path], obligations: [], private: false};
      const team = {...course, path: 'orgs/pilot-squad.md', title: 'Pilot squad', unit_kind: 'team',
        text: '# Pilot squad', children: [], people: [mara.path]};
      REM.records.push(course, team);
      org.children = [course.path]; org.people = org.people.filter(path => path !== mara.path);
      mara.units = [{path: course.path, role: 'Tutor'}, {path: team.path, role: 'Product Owner'}];
      org.obligations.forEach(row => row.units = [team.path]);
      render();
    }""", isolated_context=False)
    # The picture draws the course as a square and the team as a circle; the text outline links both.
    assert page.locator('.ov-xray .ov-node[data-shape=square]').count() == 1
    assert page.locator('.ov-xray .ov-node[data-shape=circle]').count() == 1
    course_link = page.locator('.ov-tn > a').filter(has_text='Pilot course')
    team_link = page.locator('.ov-tn > a').filter(has_text='Pilot squad')
    expect(course_link).to_be_visible()
    expect(team_link).to_be_visible()
    expect(team_link).to_have_attribute('href', '#r=orgs%2Fpilot-squad.md')
    mara = page.locator('.ov-outline .ov-m').filter(has_text='Mara Ostrowski')
    expect(mara).to_have_count(2)
    expect(mara.filter(has_text='Product Owner')).to_have_count(1)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    course_link.click()
    page.locator('.ov-page').wait_for()
    direct = page.locator('.ov-outline > .ov-m').filter(has_text='Mara Ostrowski')
    expect(direct).to_contain_text('Tutor')
    assert 'department not known yet' not in page.locator('.ov-outline').inner_text()
    direct.click()
    page.locator('.r4-person').wait_for()
    expect(page.locator('.r4-sub a[href="#r=orgs%2Fpilot-squad.md"]')).to_contain_text('Product Owner')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


# ---------- Organisation page, round 6 ("Bauhaus lightness") on an invented university ----------
ORG_TREE = "#r=orgs%2Ffernhill-university.md"
LATE = RED  # the sheet's red; the old literals had drifted from it, so this audit could not see red
# What competes on the first screen of #main (the art-direction audit, ported).
FIRST_SCREEN = r"""() => {
  const H = innerHeight, main = document.getElementById('main');
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (!(r.width > 0 && r.height > 0 && r.top < H && r.bottom > 0 && s.visibility !== 'hidden' && s.display !== 'none')) return false;
    for (let p = e; p && p !== document.body; p = p.parentElement) { const ps = getComputedStyle(p); if (+ps.opacity < 0.05) return false;
      if (p !== e && ps.overflow === 'hidden') { const pr = p.getBoundingClientRect(); if (r.top >= pr.bottom || r.bottom <= pr.top || pr.height < 1) return false; } }
    return true; };
  const all = [...main.querySelectorAll('*')].filter(vis);
  const textLeaves = all.filter(e => e.tagName !== 'text' && e.tagName !== 'tspan' && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
  const svgText = all.filter(e => (e.tagName === 'text' || e.tagName === 'tspan') && e.textContent.trim());
  const sizes = new Set(), weights = new Set();
  [...textLeaves, ...svgText].forEach(e => { const s = getComputedStyle(e); sizes.add(s.fontSize); weights.add(s.fontWeight); });
  // Picture marks carry button semantics for the keyboard; they are not drawn as buttons.
  const buttons = all.filter(e => e.matches('button, .ov-primary, .btn-act, .btn-quiet, .ov-btn') || e.matches('[role=button]') && !e.closest('svg'));
  const chips = all.filter(e => e.matches('.ov-chip, .chip, a.cite, .kind-badge'));
  const late = __LATE__;
  const red = all.filter(e => !e.closest('.ov-pulse') && [getComputedStyle(e).color, getComputedStyle(e).fill, getComputedStyle(e).stroke, getComputedStyle(e).backgroundColor]
    .some(c => late.includes(c)) && (e.tagName !== 'text' || late.includes(getComputedStyle(e).fill)) && !(e.childElementCount && !e.matches('svg *')));
  const marks = new Set(red.map(e => e.closest('[data-mark]') || e));
  return {text: textLeaves.length + svgText.length, sizes: [...sizes], weights: [...weights], buttons: buttons.map(e => e.textContent.trim()),
    chips: chips.length, red: marks.size, untagged: red.filter(e => !e.closest('[data-mark]')).map(e => e.outerHTML.slice(0, 80))};
}""".replace("__LATE__", repr(list(LATE)))


@pytest.fixture
def org_reader(tmp_path, monkeypatch):
    """Fernhill University, its course teams and people: structure the real snapshot derives."""
    from patchright.sync_api import sync_playwright
    from rem_org_tree_notebook import build
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.today import queue
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        data = snapshot(root, local, today=today)
        data["as_of"] = now.isoformat()
        data['today_queue'] = queue(root, records=data['records'], contexts=data['source_context'], states=data['threads'], as_of=now.date())
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path = tmp_path / "reader.html"
    path.write_text(rem_reader.render(build(tmp_path / "rem", now), local=True), encoding="utf-8")
    errors, contexts = [], []
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)

        def open_page(width, theme="light", motion="reduce", language="zh"):
            phone = width < 600
            context = browser.new_context(viewport={"width": width, "height": 844 if phone else 900}, is_mobile=phone, has_touch=phone,
                                          color_scheme=theme, reduced_motion=motion, locale="en-US")
            context.route("http*://**/*", lambda route: route.abort())
            contexts.append(context)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(path.as_uri())
            page.locator("#main").wait_for()
            page.evaluate("language => setInterfaceLanguage(language)", language, isolated_context=False)
            page.evaluate("hash => { location.hash = hash.slice(1); }", ORG_TREE, isolated_context=False)
            page.locator("#main .ov-r6").wait_for()
            return page

        yield open_page
        for context in contexts:
            context.close()
        browser.close()
    assert not errors, errors


def _people_known(page):
    """Distinct people the snapshot files under the university, its units included."""
    return page.evaluate("orgMembers(byPath('orgs/fernhill-university.md')).length", isolated_context=False)


# The page is a record of the organisation (owner, 2026-11-08): what it is, how it is built,
# who you know there and how long you have been in touch. To-dos live in Today.
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_org_first_screen_is_a_record_with_one_picture(org_reader, width, theme):
    page = org_reader(width, theme)
    name = page.locator(".ov-say h1.ov-name")
    assert _name(name) == "Fernhill University"
    # The organisation's name is what the page is about: --s-display (N3: 44, 36 on a phone).
    assert name.evaluate("node => getComputedStyle(node).fontSize") == ("44px" if width > 640 else "36px")
    facts = page.locator(".ov-say .ov-facts").inner_text()
    assert f"{_people_known(page)} 位你认识的人" in facts and "起有往来" in facts and "最近往来" in facts
    owed = page.evaluate("orgOwed(byPath('orgs/fernhill-university.md')).length", isolated_context=False)
    today = page.locator(".ov-say a.ov-today")
    assert today.inner_text() == f"今天里有 {owed} 件和 Fernhill University 有关的事 →" and today.get_attribute("href") == "#view=open"
    assert page.locator(".ov-key li").count() == 3
    audit = page.evaluate(FIRST_SCREEN, isolated_context=False)
    assert audit["text"] <= 70, audit
    assert audit["buttons"] == [], audit["buttons"]
    assert audit["chips"] == 0
    assert audit["red"] == 0, audit
    assert set(audit["weights"]) <= {"400", "600"}  # N3: regular and semibold, audit["weights"]
    assert page.evaluate(GREEN, isolated_context=False) <= 1
    # The picture: square = branch, circle = team or programme, sized by people you know there.
    assert page.locator(".ov-xray .ov-node[data-shape=square]").count() == 3
    assert page.locator(".ov-xray .ov-node[data-shape=circle]").count() == 9
    assert page.locator(".ov-xray .ov-node").first.is_visible()
    assert page.locator(".ov-time .ov-now").count() == 1
    # Nothing on the page is a to-do ledger.
    assert page.locator(".ov-ball, .ov-owed, .ov-primary").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_org_today_link_follows_the_data_and_there_is_no_green(org_reader):
    page = org_reader(1440, language="en")
    assert page.locator(".ov-today").inner_text() == "5 things in Today involve Fernhill University →"
    assert page.evaluate(GREEN, isolated_context=False) == 0
    page.evaluate("""() => { for (const r of REM.records) if (r.category === 'orgs') r.obligations = r.obligations.filter(row => row.dir !== 'mine'); render(); }""",
                  isolated_context=False)
    assert page.locator(".ov-today").count() == 0
    assert _name(page.locator(".ov-say h1")) == "Fernhill University"
    assert page.locator(".ov-xray .ov-node").count() == 13


@pytest.mark.parametrize("width", [1440, 390])
def test_org_reduced_motion_shows_the_still_end_state(org_reader, width):
    page = org_reader(width, motion="reduce")
    still = page.evaluate("""() => ({running: document.getAnimations().filter(a => a.playState === 'running').length,
      name: getComputedStyle(document.querySelector('.ov-say h1')).opacity,
      now: document.querySelector('.ov-now').getBoundingClientRect().x})""", isolated_context=False)
    assert still["running"] == 0
    assert still["name"] == "1"
    page.wait_for_timeout(600)
    assert page.evaluate("document.querySelector('.ov-now').getBoundingClientRect().x", isolated_context=False) == still["now"]
    moving = org_reader(width, motion="no-preference")
    moving.evaluate("orgFreeze(150)", isolated_context=False)
    assert float(moving.locator(".ov-say h1").evaluate("node => getComputedStyle(node).opacity")) < 1
    moving.evaluate("orgFreeze(4000)", isolated_context=False)
    assert moving.locator(".ov-say h1").evaluate("node => getComputedStyle(node).opacity") == "1"
    assert moving.evaluate("document.querySelector('.ov-now').getBoundingClientRect().x", isolated_context=False) == still["now"]


def test_org_missing_temperature_is_neutral_and_a_real_signal_shows_it(org_reader):
    page = org_reader(1440)
    temps = page.locator(".ov-xray .ov-node[data-depth='2']").evaluate_all("nodes => nodes.map(node => node.dataset.temp)")
    assert set(temps) == {"unknown"}
    legend = page.locator(".ov-legend").inner_text()
    assert "冷热还不知道" in legend and not re.search(r"\d{3,}", legend)
    page.evaluate("""() => { byPath('people/juno-hale.md').index = {relationship: {trend: 'cooling', last_mail: '2026-09-01',
      weekly_messages: Array(52).fill(0), change_percent: -60, quiet: false}}; render(); }""", isolated_context=False)
    wren = page.locator(".ov-xray .ov-node[aria-label*='Wren squad']")
    assert wren.get_attribute("data-temp") == "cooling"
    assert "在变冷" in page.locator(".ov-legend").inner_text()
    assert "Juno Hale" in page.locator(".ov-cool").inner_text()


@pytest.mark.parametrize("width", [1440, 390])
def test_org_units_and_people_are_listed_with_roles_and_links(org_reader, width):
    page = org_reader(width)
    section = page.locator(".ov-structure")
    assert section.locator(".ov-sh h2").inner_text() == "分支与团队"
    kestrel = section.locator(".ov-tn > a").filter(has_text="Kestrel squad")
    assert kestrel.get_attribute("href") == "#r=orgs%2Fteam-kestrel.md"
    fern = section.locator(".ov-m").filter(has_text="Fern Okafor")
    assert "Product Owner" in fern.inner_text()
    assert "Petra Lund" in section.locator(".ov-outline > .ov-meta").inner_text()
    assert "Basil Thorne" in page.locator(".ov-people").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_org_clicking_a_team_turns_the_tree_and_opens_its_panel(org_reader):
    page = org_reader(1440)
    node = page.locator(".ov-xray .ov-node[aria-label*='Osprey squad']")
    before = node.bounding_box()
    node.locator(".ov-shape").click()
    panel = page.locator(".ov-np")
    panel.wait_for(state="visible")
    assert "Osprey squad" in panel.inner_text()
    assert "Ilse Marr" in panel.inner_text() and "Theo Brand" in panel.inner_text()
    assert "null" not in panel.inner_text() and "undefined" not in panel.inner_text()
    assert panel.locator(".ov-btxt").evaluate("node => [getComputedStyle(node).fontSize, getComputedStyle(node).fontWeight]") == ["15px", "600"]
    after = node.bounding_box()
    assert abs(after["x"] - before["x"]) + abs(after["y"] - before["y"]) > 20
    page.keyboard.press("Escape")
    panel.wait_for(state="hidden")


# Round 2: keyboard use, large organisations, resize, the unit chain, and the whole scrolled page.
OVERLAPS = r"""() => {
  const texts = [...document.querySelectorAll('.ov-stage svg text')].filter(t => t.textContent.trim() && t.checkVisibility());
  const boxes = texts.map(t => [t.textContent, t.getBoundingClientRect()]);
  const lines = [...document.querySelectorAll('.ov-now-l')].map(l => l.getBoundingClientRect());
  const hits = [];
  for (let i = 0; i < boxes.length; i++) {
    const [a, r] = boxes[i];
    for (let j = i + 1; j < boxes.length; j++) { const [b, q] = boxes[j];
      if (r.left < q.right - 1 && r.right > q.left + 1 && r.top < q.bottom - 1 && r.bottom > q.top + 1) hits.push(a + ' / ' + b); }
    for (const l of lines) if (l.left > r.left && l.left < r.right && l.top < r.bottom && l.bottom > r.top) hits.push(a + ' / today line');
  }
  return hits;
}"""


@pytest.mark.parametrize("width", [1440, 390])
def test_org_fuse_ticks_real_dates_and_the_hierarchy_steps_down_for_the_keyboard(org_reader, width):
    page = org_reader(width, language="en")
    events = page.evaluate("orgCurrent.events.map(e => e.day)", isolated_context=False)
    ticks = page.locator(".ov-time .ov-ev")
    assert len(events) >= 6 and ticks.count() == len(events)
    # Linear in time from the first exchange to today: later is never further left.
    xs = ticks.evaluate_all("ticks => ticks.map(t => t.getBoundingClientRect().x)")
    assert xs == sorted(xs)
    assert page.locator(".ov-time .ov-axis").evaluate("node => getComputedStyle(node).strokeWidth") == "6px"
    assert page.evaluate(RED_MARKS, list(RED), isolated_context=False) == []
    # Each unit starts to the right of the unit it sits under.
    steps = page.evaluate("""() => [...document.querySelectorAll('.ov-outline .ov-unit .ov-unit')].map(unit => [
      unit.querySelector('.ov-tn').getBoundingClientRect().x, unit.parentElement.closest('.ov-unit').querySelector('.ov-tn').getBoundingClientRect().x])""",
                          isolated_context=False)
    assert steps and all(child > parent for child, parent in steps), steps
    # Every unit and person in it is a link, in reading order for Tab.
    links = page.locator(".ov-outline a")
    links.first.focus()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement === document.querySelectorAll('.ov-outline a')[1]", isolated_context=False)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_org_enter_on_a_unit_keeps_keyboard_focus_and_space_works(org_reader):
    page = org_reader(1440, motion="no-preference")
    page.wait_for_timeout(2200)
    osprey = page.locator(".ov-xray .ov-node[aria-label*='Osprey squad']")
    assert osprey.get_attribute("role") == "button"
    osprey.focus()
    page.keyboard.press("Enter")
    page.locator(".ov-np").wait_for(state="visible")
    page.wait_for_timeout(100)
    assert "Osprey squad" in page.evaluate("document.activeElement.getAttribute('aria-label') || ''", isolated_context=False)
    page.keyboard.press("Escape")
    page.locator(".ov-np").wait_for(state="hidden")
    page.wait_for_timeout(900)
    assert "Osprey squad" in page.evaluate("document.activeElement.getAttribute('aria-label') || ''", isolated_context=False)
    page.locator(".ov-xray .ov-node[aria-label*='Wren squad']").focus()
    page.keyboard.press(" ")
    page.locator(".ov-np").filter(has_text="Wren squad").wait_for(state="visible")
    # With a dialog open, Escape belongs to the dialog and the tree stays where it is.
    page.evaluate("() => { const d = document.createElement('dialog'); d.id = 'probe'; document.body.append(d); d.showModal(); }", isolated_context=False)
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    assert page.locator(".ov-np").is_visible()


@pytest.mark.parametrize("width", [1440, 390])
def test_org_focus_ring_shows_on_every_node(org_reader, width):
    page = org_reader(width)
    for node in page.locator(".ov-xray .ov-node[role=button]").all()[:4]:
        node.focus()
        assert node.locator(".ov-ring").evaluate("ring => getComputedStyle(ring).opacity") == "1"
    links = page.locator(".ov-structure .ov-tn > a")
    links.first.focus()
    assert page.evaluate("document.activeElement.closest('.ov-structure') !== null", isolated_context=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_org_large_organisation_caps_labels_and_keeps_them_on_screen(org_reader, width):
    page = org_reader(width)
    page.evaluate("""() => {
      const course = byPath('orgs/fieldwork-studio.md');
      for (let i = 1; i <= 32; i++) {
        const path = 'orgs/extra-squad-' + i + '.md';
        REM.records.push({path, category: 'orgs', title: 'Extra squad ' + i, unit_kind: 'team', kind: '', parent: course.path,
          children: [], people: [], obligations: [], private: false, text: '# Extra squad ' + i, relations: []});
        course.children.push(path);
      }
      render();
    }""", isolated_context=False)
    assert page.locator(".ov-xray .ov-node[data-depth='2']").count() >= 38
    audit = page.evaluate(FIRST_SCREEN, isolated_context=False)
    assert audit["text"] <= 70, audit
    outside = page.evaluate("""() => [...document.querySelectorAll('.ov-xsvg text')].filter(t => t.checkVisibility())
      .map(t => t.getBoundingClientRect()).filter(r => r.left < 0 || r.right > innerWidth).length""", isolated_context=False)
    assert outside == 0
    assert page.evaluate(OVERLAPS, isolated_context=False) == []
    assert page.evaluate("getComputedStyle(document.getElementById('main')).overflowX", isolated_context=False) != "clip"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_org_resize_keeps_the_still_frame_and_redraws_across_the_phone_width(org_reader):
    page = org_reader(1440, motion="no-preference")
    page.wait_for_timeout(2600)
    page.set_viewport_size({"width": 1200, "height": 900})
    page.wait_for_timeout(50)
    assert page.evaluate("[...document.querySelectorAll('.ov-time *')].filter(n => n.getAnimations().some(a => a.playState === 'running' && a.effect.getComputedTiming().iterations !== Infinity)).length",
                         isolated_context=False) == 0
    page.set_viewport_size({"width": 600, "height": 900})
    page.wait_for_timeout(50)
    assert page.locator(".ov-xsvg .ov-label").first.evaluate("node => node.style.fontSize") == "19.25px"  # --s-meta (11) × 21 / 12


def test_org_as_of_guard_and_unit_page_has_its_chain(org_reader):
    page = org_reader(1440)
    recent = page.locator(".ov-xray .ov-node[data-depth='2'][data-recent='1']")
    assert recent.count() == 3 and recent.locator(".ov-recent").count() == 3
    assert page.locator(".ov-xray .ov-node[data-depth='2'][data-recent='0'] .ov-recent").count() == 0
    assert "45 天内有往来" in page.locator(".ov-legend").inner_text()
    page.evaluate("() => { REM.as_of = ''; render(); }", isolated_context=False)
    assert page.evaluate("Number.isFinite(+document.querySelector('.ov-now').dataset.x)", isolated_context=False)
    page.evaluate("() => { location.hash = 'r=orgs%2Fteam-kestrel.md'; }", isolated_context=False)
    page.locator(".ov-crumb a").first.wait_for()
    links = page.locator(".ov-crumb a")
    assert links.all_inner_texts() == ["Fernhill University", "Fieldwork studio"]
    assert links.nth(1).get_attribute("href") == "#r=orgs%2Ffieldwork-studio.md"
    assert _name(page.locator(".ov-say .ov-name")) == "Kestrel squad"


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_org_full_page_reads_cleanly_to_the_bottom(org_reader, width, theme):
    page = org_reader(width, theme)
    # One event recorded on two pages is one entry.
    entries = page.locator(".ov-tl .ov-e").all_inner_texts()
    assert sum("confirmed the final demo week" in text for text in entries) == 1
    # No half-empty grid: two filled columns side by side, or one measured column.
    layout = page.evaluate("""() => [...document.querySelectorAll('.ov-two')].map(row => [...row.children].map(col => col.childElementCount))""",
                           isolated_context=False)
    assert all(len(cols) == 2 and all(cols) for cols in layout), layout
    # Branches and the units you are in touch with are named in the picture, phone included.
    for name in ("Fieldwork studio", "Founders programme", "Global office", "Kestrel squad", "Heron squad", "Wren squad"):
        label = page.locator(".ov-xray .ov-node", has_text=name).locator(".ov-label")
        assert label.count() == 1 and label.is_visible(), name
    # The time line speaks the interface language and shows its real dated items.
    times = page.locator(".ov-tsvg text").all_text_contents()
    assert not [text for text in times if re.search(r"[A-Za-z]{3,}", text)], times
    assert page.locator(".ov-tsvg .ov-ev:visible").count() >= 6
    assert page.evaluate(OVERLAPS, isolated_context=False) == []
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_project_page_open_items_are_a_record_without_green_or_self_links(reader, width):
    """Owner, 2026-11-08: a project page is a record. Its open items carry no green
    button, and never an "Open the page" button that points at the page you are on."""
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(uri + "#r=projects%2Fharbour.md")
    items = page.locator("#open-threads li.thread")
    assert items.count() >= 1
    assert page.evaluate(GREEN) == 0
    assert page.locator("#open-threads").get_by_text("Open the page", exact=True).count() == 0
    assert items.first.get_by_role("button", name="Mark done", exact=True).count() == 1


@pytest.mark.parametrize("width", [1440, 390])
def test_org_page_name_starts_at_the_top_and_each_role_sits_under_its_own_person(reader, width):
    """The name is not centred in an empty poster band, and a long role never wraps
    onto a line of its own where it reads as the next person's role."""
    page, uri = reader
    _org_view(page, uri, "#r=orgs%2Ffernhill-labs.md", width, "light")
    page.evaluate("""() => { const p = REM.records.find(r => r.category === 'people');
      p.text = p.text.replace(/^(- Role: ).*$/m, '$1Former sales and marketing intern for the pilot programme across three campuses'); render(); }""",
      isolated_context=False)
    assert page.locator(".ov-say h1").bounding_box()["y"] < 180  # under N3's 76px top bar
    for item in page.locator(".ov-key li").all():
        name, meta = item.locator("a").bounding_box(), item.locator(".ov-meta").bounding_box()
        assert meta["y"] >= name["y"] + name["height"] - 1, "the role starts below its name"
        assert abs(meta["x"] - name["x"]) < 1, "and on the same left edge"


@pytest.mark.parametrize("width", [1440, 390])
def test_today_says_what_rem_did_overnight_beside_who_is_waiting(reader, width):
    """P大: "这替我干了什么？" — at 1440 the right half says what REM did, naming whom for;
    on a phone the same block follows the queue. Duplicated outcomes count once."""
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(uri + "#")
    page.evaluate("""() => {
      const people = REM.records.filter(r => r.category === 'people' && r.path !== REM.owner).slice(0, 2);
      const o = (kind, r, n) => ({key: r.path + n, record: r.path, title: r.title, kind});
      REM.night_outcomes = [o('prepared', people[0], 1), o('prepared', people[0], 1), o('prepared', people[1], 2), o('no_reply', people[1], 3)];
      render();
    }""", isolated_context=False)
    done = page.locator("#night-sheet .night-done")
    line = page.locator(".side .closed")
    assert line.inner_text().startswith("REM handled 3 things overnight")
    line.locator(".link-btn").click()
    assert page.locator("#night-title").inner_text() == "What REM did overnight"
    # Each line counts items, so the lines add up to the side line's number (sprint 13); the people are named.
    assert done.locator("li b").all_inner_texts() == ["2 things have a reply drafted", "1 thing needs no reply"]
    assert done.locator("li").first.locator("a").count() == 2
    page.keyboard.press("Escape")
    cards, aside = page.locator(".today-brief").bounding_box(), line.bounding_box()
    if width == 1440:
        assert aside["x"] >= cards["x"] + cards["width"], "beside the queue, in the right half"
        assert aside["y"] + aside["height"] <= page.viewport_size["height"], "on the first screen"
    else:
        assert aside["y"] >= cards["y"] + cards["height"], "after the queue on a phone"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_focus_ring_shows_on_controls_but_not_on_main_or_the_today_card(reader):
    """Hairline outlines replaced rings; the focus ring must beat them without framing #main or a Today card."""
    page, uri = reader
    page.goto(uri + '#c=people')  # the person page has no buttons left (D-30); the People table toggle is an .r4-btn
    page.locator('.r4-btn').first.wait_for()
    page.keyboard.press('Tab')  # keyboard modality, so programmatic focus below counts as :focus-visible
    outline = "node => { node.focus(); const s = getComputedStyle(node); return [node.matches(':focus-visible'), s.outlineStyle, s.outlineWidth]; }"
    assert page.locator('.r4-btn').first.evaluate(outline) == [True, 'solid', '2px']
    # The skip link and every nav click move focus to #main (tabindex=-1): no frame around the page.
    assert page.locator('#main').evaluate(outline)[1] == 'none'
    page.goto(uri)
    page.keyboard.press('Tab')
    card = page.locator('.today-brief .qcard').first
    assert card.evaluate(outline)[1] == 'none'  # the card shows focus with its background, as its own rule says


def test_graph_kinds_differ_by_shape_and_private_records_carry_a_slash(reader):
    """Grey and pencil were the only difference between people and sessions; pencil means inference."""
    page, uri = reader
    page.goto(uri + '#view=graph')
    page.locator('.gx-map').wait_for()
    assert page.evaluate("Object.values(GRAPH_TONE).includes('--pencil')", isolated_context=False) is False
    outlines = page.evaluate("['people', 'sessions', 'orgs', 'projects', 'notes'].map(k => graphOutline(k, 0, 0, 5))", isolated_context=False)
    assert len(set(outlines)) == 5
    marks = page.evaluate("""() => [false, true].map(p => {
      const g = graphSvgMark('people', 7, 7, 5, p);
      return [g.querySelectorAll('path').length + (g.tagName === 'path' ? 1 : 0), g.getAttribute('fill') || g.firstChild.getAttribute('fill')];
    })""", isolated_context=False)
    assert marks[0] == [1, 'var(--grey)'] and marks[1][0] == 2 and marks[1][1] != 'var(--grey)'
    # Private knowledge keeps its centre dot, so it is not a private person; a private session stays big enough to read.
    assert page.evaluate("graphSvgMark('knowledge', 7, 7, 5, true).querySelectorAll('circle').length", isolated_context=False) == 1
    assert page.evaluate("graphSvgMark('people', 7, 7, 5, true).querySelectorAll('circle').length", isolated_context=False) == 0
    assert page.evaluate("graphSvgMark('sessions', 7, 7, 1.5, true).querySelector('path').getAttribute('d') === graphOutline('sessions', 7, 7, GRAPH_PRIVATE_MIN)", isolated_context=False)


# Sprint 13 (owner, 2026-11-13: «skills 处理一下»): one glance answers "what do I use most" and
# "what can my agents do". Before, 150 skills were one 760px column 12 000px tall, grouped by
# lowercase prefix, the 62-use skill below a "used in the last 30 days" group of one, with
# "recorded not installed" / "Source reviewed" chips and a tiny second search box.
SKILL_SET = [
    ('lark-mail', 40, 'Send and read Lark mail for you, with the reply checked in the sent folder.', ''),
    ('lark-doc', 2, 'Edit a Lark document; the change is read back.', ''),
    ('lark-calendar', 9, 'Book a Lark meeting room — rooms are checked for clashes first.', ''),
    ('lark-sheets', 0, 'Fill a Lark sheet from a table.', ''),
    ('deck-maker', 25, 'Guides creation of a bilingual, story-led pitch deck, with an HTML and PDF copy.',
     '- Installed description: 用故事化漫画讲客户案例——从大纲到成品。\n'),
    ('poster-cut', 0, 'Unknown — description not provided', ''),
] + [(f'tool-{i}', 0, f'Do small job number {i} for the notebook.', '') for i in range(12)]


def _add_skills(page):
    page.evaluate(r'''skills => {
      for (const [name, count, what, extra] of skills) REM.records.push({path: 'skills/catalog/' + name + '.md',
        category: 'skills', title: name, written: !what.startsWith('Unknown'), translations: {}, text: '# ' + name
          + '\n\n## What it does\n' + what + '\n\n## Usage history\n<!-- rem-usage -->\n- '
          + (count ? 'Invoked ' + count + ' times in your coding sessions in the last 180 days (412 session files: Codex), last on 2026-09-'
              + String(1 + count % 28).padStart(2, '0') + ' (Codex ' + count + ').'
            : 'No invocation found in your coding sessions in the last 180 days (412 session files: Codex).')
          + '\n<!-- /rem-usage -->\n\n## Source\n<!-- rem-installed-copies -->\n- File: /home/user/.codex/skills/' + name
          + '/SKILL.md\n' + extra + '<!-- /rem-installed-copies -->\n'});
      MAX_USAGE = null;
      render();
    }''', SKILL_SET, isolated_context=False)


@pytest.mark.parametrize('width', [1440, 390])
def test_skills_rank_what_you_use_and_fill_the_width(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(uri + '#c=skills')
    _add_skills(page)
    top = page.locator('.skills-top .skill-card .skill-name').all_inner_texts()
    assert top[:4] == ['lark-mail', 'deck-maker', 'weekly-brief', 'lark-calendar']  # by uses: 40, 25, 14, 9
    assert 'lark-sheets' not in top and 'tool-1' not in top  # never used: not in the top group
    assert '40 matches in 180 days' in page.locator('.skills-top .skill-card').first.inner_text()  # name matches, not "calls"
    families = page.locator('.skill-families')
    # Family names read as names ("Tool", not "tool"); a family left with fewer than three goes under Other.
    # A family's size counts the members shown in Most used too, so Lark keeps its group and its button.
    assert [h.split('\n')[0].rstrip('0123456789') for h in families.locator('h3').all_inner_texts()] == ['Tool', 'Lark', 'Other']
    assert page.locator('.skill-shape button').filter(has_text='Lark').count() == 1
    assert families.locator('.skill-name').filter(has_text='lark-mail').count() == 0  # shown once, in the top group
    boxes = [b for b in (families.locator('li').nth(i).bounding_box() for i in range(families.locator('li').count()))]
    main = page.locator('#main').bounding_box()
    lefts = {round(b['x']) for b in boxes}
    if width >= 1200:
        assert len(lefts) >= 3  # several columns, not one 760px list
        assert max(b['x'] + b['width'] for b in boxes) >= main['x'] + main['width'] - 80  # the right side is used
        assert page.locator('.skill-shape').bounding_box()['y'] < 900  # the shape of the rest is on the first screen
    else:
        assert len(lefts) == 1
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_skills_with_only_a_name_go_to_one_quiet_line(reader):
    page, uri = reader
    page.goto(uri + '#c=skills')
    _add_skills(page)
    assert page.locator('.skill-families .skill-name').filter(has_text='poster-cut').count() == 0
    assert page.locator('.skills-empty').inner_text() == '1 skill has only a name: poster-cut'
    assert page.locator('.skills-empty a').get_attribute('href') == '#r=skills%2Fcatalog%2Fposter-cut.md'


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_skills_say_what_each_does_in_one_plain_line(reader, language):
    page, uri = reader
    page.goto(uri + '#c=skills')
    _add_skills(page)
    page.evaluate('language => setInterfaceLanguage(language)', language, isolated_context=False)
    line = lambda name: page.locator('.skill-item, .skill-card').filter(has=page.locator('.skill-name', has_text=name)).locator('.skill-line').inner_text()
    assert line('deck-maker') == ('用故事化漫画讲客户案例' if language == 'zh' else 'Guides creation of a bilingual, story-led pitch deck')
    assert line('lark-calendar') == 'Book a Lark meeting room'
    assert line('lark-mail') == 'Send and read Lark mail for you'
    text = page.locator('#main').inner_text()
    for jargon in ['recorded not installed', 'Source reviewed', 'Getting to know them', 'More to learn', 'written of',
                   '仅记录，未安装', '已核对来源', '待了解', '有内容', 'version unverified', '版本未验证']:
        assert jargon not in text
    assert page.locator('.lede').inner_text() == ('你的 agent 会做的事，最常用的在前 · 21 个技能' if language == 'zh'
                                                  else 'What your agents can do, the ones you use most first. 21 skills')


def test_skills_have_one_search_that_is_big_enough_to_use(reader):
    page, uri = reader
    page.goto(uri + '#c=skills')
    _add_skills(page)
    search = page.locator('#main input[type=search]')
    assert search.count() == 1
    box = search.bounding_box()
    assert box['height'] >= 44 and box['width'] >= 320
    assert search.get_attribute('placeholder') == 'Find among 21 skills…'
    search.fill('meeting room')
    assert page.locator('#main .skill-name').all_inner_texts() == ['lark-calendar']
    assert page.locator('.skills-top').count() == 0


def test_skill_page_says_where_it_lives_in_words(reader):
    page, uri = reader
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.locator('details.deep-note > summary').click()
    source = page.locator('.panel').filter(has=page.locator('h3', has_text='Source'))
    assert 'Claude Code' in source.inner_text()
    assert 'claude-user' not in source.inner_text()
    assert source.locator('a').inner_text() == 'Open SKILL.md'
    assert page.locator('.pill.status').count() == 0  # no research-state chip the owner cannot act on


def test_skill_family_buttons_move_focus_to_their_group(reader):
    page, uri = reader
    page.goto(uri + '#c=skills')
    _add_skills(page)
    page.locator('.skill-shape button').filter(has_text='Tool').click()
    assert page.evaluate("document.activeElement.matches('.skill-family h3') && document.activeElement.textContent.startsWith('Tool')")


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_skill_rows_keep_last_night_and_installed_copies_and_say_matches(reader, language):
    page, uri = reader
    page.goto(uri + '#c=skills')
    _add_skills(page)
    page.evaluate(r'''language => {
      for (const run of REM.logs) (run.changed ||= []).push('skills/catalog/lark-sheets.md');  // last night's pass rewrote it
      byPath('skills/catalog/lark-sheets.md').installations = [{path: 'a'}, {path: 'b'}];
      setInterfaceLanguage(language);
    }''', language, isolated_context=False)
    item = page.locator('.skill-item').filter(has=page.locator('.skill-name', has_text='lark-sheets'))
    assert item.locator('.fresh-label').inner_text() == ('昨夜' if language == 'zh' else 'last night')
    assert ('2 份安装副本' if language == 'zh' else '2 installed copies') in item.inner_text()
    card = page.locator('.skill-card').filter(has=page.locator('.skill-name', has_text='lark-mail'))
    assert ('近 180 天用到 40 次' if language == 'zh' else '40 matches in 180 days') in card.inner_text()


def test_skill_line_reads_regional_chinese_and_windows_paths(reader):
    page, uri = reader
    page.goto(uri + '#c=skills')
    _add_skills(page)
    page.evaluate(r'''() => {
      byPath('skills/catalog/lark-sheets.md').translations = {'zh-CN': '# lark-sheets\n\n## What it does\n从表格填写飞书电子表格。\n'};
      setInterfaceLanguage('zh');
    }''', isolated_context=False)
    item = page.locator('.skill-item').filter(has=page.locator('.skill-name', has_text='lark-sheets'))
    assert item.locator('.skill-line').inner_text() == '从表格填写飞书电子表格'
    assert page.evaluate(r"skillHome('C:\\Users\\u\\.codex\\skills\\x\\SKILL.md')", isolated_context=False) == 'Codex'

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
            page = browser.new_page(viewport={"width": width, "height": 812})
            page.goto(path.as_uri() + "#r=projects%2Fjournal.md")
            statement = page.locator(".focus-statement").inner_text()
            assert "Automatic investigations skip this private project." in statement
            assert "Name this page to request a write." in statement
            assert "clamped" not in page.locator(".focus-statement").get_attribute("class")
            assert "/work/journal" not in statement
            assert "Needs your explicit request" in page.locator(".focus-kicker").inner_text()
            assert "Automatic investigation skips this private project." in page.locator(".missing").inner_text()
            assert "investigate 'projects/journal.md'" in page.locator(".missing .cmd").inner_text()
            assert page.get_by_role("button", name="Copy the command").is_visible()
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
            page = browser.new_page(viewport={"width": width, "height": 812})
            page.goto(path.as_uri() + "#r=projects%2Fbrowser.md")
            statement = page.locator(".focus-statement").inner_text()
            assert "/work/browser" not in statement
            assert statement == "Not written yet: 13 sessions, last on 2026-08-02."
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
    for selector in ('#q', '.nav-toggle'):
        assert page.locator(selector).bounding_box()['height'] >= 44
    assert page.locator('.eyebrow a').first.is_visible()
    assert page.get_by_role('heading', name='Full memory and sources').is_visible()
    assert page.locator('details.deep-note').get_attribute('open') is None
    page.locator('details.deep-note > summary').click()
    assert page.locator('.deep-note .note').is_visible()
    assert page.locator('.deep-note .note').bounding_box()['y'] < page.locator('.deep-note .side').bounding_box()['y']
    page.locator('.nav-toggle').click()
    page.locator('.reader-settings > summary').click()
    assert 'Snapshot ' in page.locator('#foot').inner_text()
    assert 'co rem start' in page.locator('.reader-settings').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.reload()
    page.locator('.reader-settings > summary').click()
    assert 'Background updates off' in page.locator('#foot').inner_text()
    assert 'Not started' not in page.locator('#foot').inner_text()
    assert '`' not in page.locator('#foot').inner_text()


@pytest.mark.parametrize('settings_open', [False, True])
def test_short_desktop_scrolls_the_whole_rail_without_clipping_links(reader, settings_open):
    page, uri = reader
    page.set_viewport_size({'width': 960, 'height': 540})
    page.goto(uri)
    if settings_open:
        page.locator('.reader-settings > summary').click()
    assert page.locator('.rail').evaluate("""rail => {
      const style = getComputedStyle(rail);
      const nav = rail.querySelector('#nav');
      const footerTop = rail.querySelector('.foot').getBoundingClientRect().top;
      const railTop = rail.getBoundingClientRect().top;
      const scrollable = style.overflowY === 'auto' && rail.scrollHeight > rail.clientHeight;
      return style.position === 'sticky' && style.top === '0px' && rail.clientHeight === 540
        && scrollable && getComputedStyle(nav).overflowY === 'visible'
        && [...nav.querySelectorAll('a')].every(link => {
          const box = link.getBoundingClientRect();
          return (box.bottom <= footerTop || scrollable)
            && box.bottom - railTop + rail.scrollTop <= rail.scrollHeight;
        });
    }""")
    for link in page.locator('#nav a').all():
        link.scroll_into_view_if_needed()
        assert link.evaluate("""link => {
          const box = link.getBoundingClientRect();
          const rail = link.closest('.rail').getBoundingClientRect();
          const footer = document.querySelector('.rail .foot').getBoundingClientRect();
          return box.top >= rail.top && box.bottom <= rail.bottom && box.bottom <= footer.top;
        }""")
    page.locator('.rail').evaluate('rail => rail.scrollTop = rail.scrollHeight')
    footer = page.locator('.rail .foot').bounding_box()
    assert footer['y'] + footer['height'] <= 540
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_mobile_browse_privacy_control_remains_a_full_touch_target(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.locator('.nav-toggle').click()
    page.locator('.reader-settings > summary').click()
    page.locator('#privacy-toggle').scroll_into_view_if_needed()
    privacy = page.get_by_role('button', name='Hide labelled passages')
    box = privacy.bounding_box()
    assert box['height'] >= 44 and box['width'] >= 44
    assert box['y'] >= 0 and box['y'] + box['height'] <= 812
    privacy.focus()
    privacy.press('Enter')
    shown = page.get_by_role('button', name='Show labelled passages')
    assert shown.get_attribute('aria-pressed') == 'true'
    assert shown.evaluate('(node) => node === document.activeElement')
    shown.press('Space')
    assert privacy.get_attribute('aria-pressed') == 'false'
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

    def fixed_snapshot(root, local=False):
        data = snapshot(root, local)
        data["as_of"] = frozen.isoformat()
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path.write_text(rem_reader.render(build(tmp_path / "rem", frozen), local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        page.locator(".morning-primary h1").wait_for()
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
    assert page.locator('.page-head h1').inner_text() == 'ConnectOnion'
    domain = page.locator('.page-head .section-sub')
    assert domain.inner_text() == 'connectonion.com'
    assert domain.is_visible()
    assert domain.bounding_box()['y'] >= page.locator('.page-head h1').bounding_box()['y']
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.goto(uri + '#c=orgs')
    row = page.get_by_role('row').filter(has=page.get_by_role('link', name='ConnectOnion', exact=True))
    assert row.get_by_role('cell', name='connectonion.com', exact=True).is_visible()
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
    band = page.locator('.night-strip')
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
    # One count everywhere: the heading says what "See all" and the sidebar say; the rows are the top three.
    total = page.locator('.waiting-more a').inner_text().split()[2]
    assert page.locator('.morning-primary h1').inner_text() == f'{total} things are waiting on you'
    assert page.locator('.waiting-ledger > li').count() == 3
    assert page.locator('.waiting-person a').all_inner_texts() == ['Mara Ostrowski', 'Inès Halvorsen', 'Fernhill Labs']
    assert 'Data-sharing addendum' in page.locator('.waiting-ask .words').first.inner_text()
    changes = page.locator('.overnight .claim-card')
    assert changes.count() == 1
    assert 'Head of Partnerships' in changes.inner_text()
    assert changes.get_by_role('link', name='Open the page and source →').get_attribute('href').endswith('h=src-2')
    assert set(page.locator('.week a').all_inner_texts()) >= {'Mara Ostrowski', 'Harbour', 'Fernhill Labs'}
    recall = page.locator(".recall")
    assert recall.count() == 1
    assert not recall.locator(".recall-answer").is_visible()
    recall.get_by_role("button", name="Reveal the context").focus()
    page.keyboard.press("Enter")
    assert recall.locator(".recall-answer").is_visible()
    assert recall.get_by_role("button", name="Hide the context").get_attribute("aria-expanded") == "true"
    assert recall.get_by_role("button", name="Hide the context").get_attribute("aria-controls") == "recall-answer"
    assert page.locator(".night-details").count() == 1
    page.locator(".night-details summary").click()
    night = page.locator(".night-details .night")
    assert "46 items" in night.inner_text() and "4 pages" in night.inner_text()
    assert night.locator(".hypno .dot.changed").count() == 1
    assert night.locator('.hypno .dot.dawn').count() == 1
    assert set(night.locator(".changes a").all_inner_texts()) == {"Mara Ostrowski", "Harbour", "Fernhill Labs", "Avery Lin"}  # runs, and stamps of the night
    # The full ledger keeps both directions, yours first.
    page.locator('.waiting-more a').click()
    directions = [d.upper() for d in page.locator("ul.threads .dir").all_inner_texts()]
    assert directions[0] == "YOU OWE" and "THEY OWE" in directions
    assert directions == sorted(directions, key=["YOU OWE", "THEY OWE", "OPEN"].index)


def test_people_open_as_a_sheet_that_sorts_filters_and_opens_a_row(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    sheet = page.locator("table.sheet")
    assert sheet.locator("tbody tr").count() == 6
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
    directory.get_by_role("button", name="Show the command to prepare a memory for Leah Bell").click()
    assert "stub person" in directory.locator(".directory-action code").inner_text()
    assert directory.locator("tbody tr").first.evaluate(
        "row => row.nextElementSibling.classList.contains('directory-action')")
    page.set_viewport_size({"width": 390, "height": 844})
    assert directory.locator("tbody tr").first.evaluate(
        "row => getComputedStyle(row).display === 'grid'")
    assert directory.get_by_role("button", name="Show the command to prepare a memory for Leah Bell").bounding_box()["height"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_the_people_sheet_fits_1440_and_says_when_it_is_cut(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    scroller = page.locator(".sheet-scroll")
    # Every column is visible at 1440, What's open included; nothing waits to the right.
    assert scroller.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    assert page.locator("th.c-open").evaluate("e => e.getBoundingClientRect().right <= innerWidth")
    assert "clip-right" not in page.locator(".sheet-box").get_attribute("class")
    # Narrower, the sheet scrolls inside itself, the cut edge shades, the name stays put.
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
    page.evaluate('''() => {
      const r = byPath('people/mara-ostrowski.md');
      r.index = {...r.index,
        emails: ['jerryl_shijie.seow@some-long-domain.example', 'second@example.test', 'third@example.test'],
        phone: '+61 0493941028 (mobile); +61 0493941029 (work)'};
      FACTS.delete(r.path); render();
    }''', isolated_context=False)
    row = page.locator('.sheet tbody tr').filter(has_text='Mara Ostrowski')
    for kind, first, count, title in [
        ('email', 'jerryl_shijie.seow@some-long-domain.example', '+2',
         'jerryl_shijie.seow@some-long-domain.example; second@example.test; third@example.test'),
        ('phone', '+61 0493941028 (mobile)', '+1',
         '+61 0493941028 (mobile); +61 0493941029 (work)'),
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
    page.evaluate('''() => {
      const r = byPath('people/mara-ostrowski.md');
      r.index = {...r.index, phone: '+61 0493941028 (mobile); +61 0493941029 (work)'};
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
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.index = {...r.index, emails: ['long-address'.repeat(20) + '@fernhill.example', 'second@fernhill.example', 'third@fernhill.example']};
      FACTS.delete(r.path); render();
    }""", isolated_context=False)
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
    assert any("· map" in date for date in page.locator(".sheet td.c-last").all_inner_texts())
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
    monkeypatch.setattr(rem_reader, "snapshot", lambda _, local=False: data)
    path = tmp_path / "large-roster.html"
    path.write_text(rem_reader.render(tmp_path / "rem"), encoding="utf-8")

    page, _ = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(path.as_uri() + "#c=people")
    sheet = page.locator(".sheet-scroll")
    assert page.locator(".sheet tbody tr").count() >= 575
    directory = page.locator(".contact-directory summary")
    assert 0 <= directory.bounding_box()["y"] < 812
    assert directory.bounding_box()["y"] < sheet.bounding_box()["y"]
    directory.focus()
    directory.press("Enter")
    assert page.locator(".contact-directory").get_attribute("open") is not None
    page.locator(".contact-directory").get_by_role("searchbox", name="Search other contacts").fill("Leah Bell")
    assert page.locator(".contact-directory tbody tr").count() == 1
    for _ in range(2):
        sheet.evaluate("e => e.scrollLeft = e.scrollWidth")
        assert page.locator('.sheet-scroll').evaluate(r"e => e.scrollWidth <= e.clientWidth + 1")
        assert page.get_by_role('combobox', name='Sort by').is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert any("· map" in text for text in page.locator(".sheet td.c-last .mono").all_inner_texts())
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
    visible_people = sum(r["category"] == "people" and not r.get("needs_review") and not r.get("service")
                         for r in data["records"])
    monkeypatch.setattr(rem_reader, "snapshot", lambda _, local=False: data)
    path = tmp_path / "first-map.html"
    path.write_text(rem_reader.render(tmp_path / "rem"), encoding="utf-8")

    page, _ = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(path.as_uri())
    assert page.locator('.morning-primary h1').is_visible()
    assert page.locator('.first-map').is_visible()
    assert page.locator(".first-map h2").inner_text().endswith(" records mapped")
    assert page.locator(".first-map .morning-time").inner_text() == "0 memories written"
    assert page.locator(".first-map-actions a").inner_text() == f"Browse {visible_people} people →"
    assert page.locator(".first-map-actions a").is_visible()
    assert page.locator(".first-map-actions button").evaluate("e => e.getBoundingClientRect().bottom <= innerHeight")
    page.locator(".nav-toggle").click()
    page.locator(".reader-settings > summary").click()
    assert "Background updates off" in page.locator(".reader-settings").inner_text()
    page.locator(".nav-toggle").click()
    page.locator(".first-map-actions a").click()
    assert "1 possible contact" in page.locator(".held-note").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_a_person_opens_on_the_relationship_ledger_with_facts_disclosed(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    assert page.locator('.person-lead').is_visible()
    assert 'Last contact' in page.locator('.contact-line').inner_text()
    assert page.locator('.ledger-column.mine h3 > span').first.inner_text() == 'You owe Mara'
    assert page.locator('.ledger-column.mine .ledger-count').inner_text() == '1'
    assert page.locator('.ledger-column.mine .ledger-meta').inner_text() == '9 days'
    assert page.locator('details.deep-note').get_attribute('open') is None
    assert not page.locator('.factlist').is_visible()
    page.locator('details.deep-note > summary').click()
    card = page.locator(".factlist")
    value = lambda label: card.locator(f"dt:text-is('{label}') + dd")  # noqa: E731
    assert "Head of Partnerships" in value("Role").inner_text()
    assert value("Phone").get_attribute("class") == "none" and "not found" in value("Phone").inner_text()
    role_source = value('Role').locator('.cite')
    assert role_source.inner_text() == '22 Aug'
    assert role_source.get_attribute('aria-label') == 'Source: Outlook, 22 Aug, original not in this snapshot'
    assert 'title and company in signature' in page.locator('#src-2').inner_text()
    role_source.click()
    assert "The original isn't in this snapshot." in page.locator('#evidence-panel').inner_text()
    page.get_by_role('button', name='Close source context').click()
    assert role_source.evaluate('e => e === document.activeElement')
    assert value("Email").locator(".qual").all_inner_texts() == ["work", "personal"]
    assert [b.upper() for b in page.locator(".person-insight dt").all_inner_texts()] == ["NOW", "AT STAKE", "CHANGED", "PATTERN"]
    assert page.locator(".person-insight .cite.run").count() == 3  # Each adjacent pair or longer run shares one marker
    assert page.locator(".ledger-column.mine .ledger-row").count() == 1
    assert page.locator(".deep-note .block-threads, .deep-note .block-insight").count() == 0
    assert page.locator(".timeline li").count() == 5
    assert page.locator("#src-6").count() == 1


def test_grouped_citation_sources_are_each_openable_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    assert page.locator(".person-insight .cite.run").count() == 3
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
    chips = page.locator(".person-lead .cite")
    assert chips.count() == 2
    for index, expected, other in ((0, first, second), (1, second, first)):
        chips.nth(index).click()
        claim = page.locator(".evidence-claim > div").inner_text()
        assert claim == expected
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
        "Richard owes the user its P115 proposal": "Richard owes you its P115 proposal",
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
    still_open = ["No reply from Lisa since 2026-09-12 [4].", "Unknown — whether Ody sent the invoice; Aaron asked 2026-09-30 [2]."]
    assert page.evaluate("t => t.map(isCalm)", calm + still_open, isolated_context=False) == [True] * 6 + [False] * 2
    # 1.9.2b1 skill pages: the finding after "Unknown — not verified." was hidden with the placeholder.
    record = {"path": "skills/catalog/x.md", "title": "x", "text": "# x\n\n## Current status\nUnknown — not verified. "
              "The latest session, 2026-06-09, proposed an npm CLI [1].\n\n## Limitations\nUnknown — not verified.\n"}
    kept = page.evaluate("r => known(r).kept.map(s => s.title)", record, isolated_context=False)
    assert kept == ["Current status"]
    # 1.9.2b1 History ranges: the end date leaked into the text or the gutter was blank.
    lines = "\n".join(["- 2026-08-26–2026-08-28: Town asked [1].", "- 2026-09-23 to 2026-10-09: Daily reports [2].",
                       "- 2026-08-10–11: Demos sent [3].", "- 2026-07-29–08-04: Trip [4].", "- 2025-10: Met at a meetup [5].", "- 2025-10–11: Term [6]."])
    got = page.evaluate("t => historyItems(t).map(i => [i.day, i.end, i.text.slice(0, 4)])", lines, isolated_context=False)
    assert got == [["2026-08-26", "2026-08-28", "Town"], ["2026-09-23", "2026-10-09", "Dail"],
                   ["2026-08-10", "2026-08-11", "Demo"], ["2026-07-29", "2026-08-04", "Trip"], ["2025-10", "", "Met "], ["2025-10", "2025-11", "Term"]]
    assert page.evaluate("dayLabel({day: '2025-10', end: ''})", isolated_context=False) == "Oct 2025"
    assert page.evaluate("dayLabel({day: '2026-08-10', end: '2026-08-11'})", isolated_context=False).count("–") == 1
    # A thread addressed to the owner by name ("Avery: collect …") is the owner's to do.
    assert page.evaluate("direction('Avery: collect the swipe card from Security')", isolated_context=False) == "mine"
    page.locator('.waiting-more a').click()
    home_threads = page.locator('.task-band .threads').first.inner_text()
    assert "you have owed them" in home_threads and "the user" not in home_threads.lower()
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    page.locator("details.deep-note > summary").click()
    main = page.locator("#main").inner_text()
    assert "the user" not in main.lower() and "you have not signed it" in main
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
    assert "did not confirm current project work" in page.locator('.focus-limit').inner_text()
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
    page.locator("a.cite[href*='src-5']").first.click()
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
    assert page.locator('.person-lead').inner_text() == 'You owe Mara a revised pilot agreement. She needs the usage export before Friday.'
    assert page.locator('.focus-head, .contact-strip').count() == 0
    assert 'third sentence' not in page.locator('.person-lead').inner_text()
    page.locator('details.deep-note > summary').click()
    assert 'third sentence' in page.locator('.deep-note').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_record_dates_do_not_disagree_when_the_index_is_stale(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    expected = page.evaluate("known(byPath('people/mara-ostrowski.md')).last", isolated_context=False)
    page.evaluate("() => { byPath('people/mara-ostrowski.md').index = {last_contact: '2001-01-01'}; FACTS.clear(); render(); }", isolated_context=False)
    formatted = page.evaluate('date => threadDate(date)', expected, isolated_context=False)
    # The quiet contact line and disclosed facts share the page date.
    assert formatted in page.locator('.lead-meta').inner_text()
    assert '2001' not in page.locator('.lead-meta').inner_text()
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


def test_unknown_repository_stays_unknown_while_workspace_path_remains_visible(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Facts\\n- Repository: Unknown\\n- Started: Unknown\\n'
        + '\\n## Insight\\n- At stake: Keep the source folder intact. [1]\\n'
        + '\\n## Paths\\n- /tmp/session-workspace\\n- Sessions: 4\\n- First seen: 2026-07-18\\n- Last seen: 2026-07-20';
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    assert page.locator('.focus-facts dt:text-is("Local path") + dd').inner_text() == '/tmp/session-workspace'
    assert not page.locator('.focus-facts dt:text-is("Repository")').count()
    page.locator('details.deep-note > summary').click()
    repository = page.locator('.factlist dt:text-is("Repository") + dd')
    assert not repository.locator('.val').count()
    assert 'not found' in repository.inner_text()
    page.evaluate("() => { location.hash = '#q=Harbour'; render(); }", isolated_context=False)
    assert page.locator('.best-facts dt:text-is("Local path") + dd').inner_text() == '/tmp/session-workspace'
    assert not page.locator('.best-facts dt:text-is("Repository")').count()


def test_investigation_command_targets_the_notebook_being_viewed(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fquinn-alder.md")
    root = page.evaluate('REM.root', isolated_context=False)
    command = page.locator('.missing .cmd code').inner_text()
    assert '--root' in command and root in command
    assert "investigate 'people/quinn-alder.md'" in command


def test_private_mode_hides_raw_sources_and_conversations_already_open(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.locator('details.deep-note:not([open]) > summary').click()
    page.locator('.conversation-open').first.click()
    messages = page.locator('#conversation-dialog .conversation-message')
    assert messages.first.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not messages.first.is_visible()
    assert page.locator('#conversation-dialog .private-hidden-notice').is_visible()
    page.get_by_role('button', name='Close conversation').click()
    page.locator("a.cite[href*='src-5']").first.click()
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
        row = page.locator('tr', has=page.get_by_role('link', name='Harbour'))
        cell = row.locator('td').nth(1)
        assert cell.inner_text() == 'Hidden labelled passage'
        assert cell.locator('.clamp').get_attribute('title') == ''
        if width == 375:
            assert row.locator('.mobile-status-label').inner_text() == 'Investigated'
            assert row.locator('.mobile-status-label').is_visible()
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
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        assert page.locator('.focus-kicker').first.inner_text() == 'What this project does'
        assert 'reads a local daily log' in page.locator('.focus-statement').inner_text()
        assert 'recent commit' not in page.locator('.focus-statement').inner_text()
        assert '7-day session sample did not confirm current project work' in page.locator('.focus-limit').inner_text()
        assert page.locator('.project-workspace').get_by_text('What this is').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.evaluate("() => { byPath('projects/harbour.md').project_coverage.inputs_read = 0; render(); }",
                  isolated_context=False)
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        assert 'No coding-session input was assigned' in page.locator('.focus-limit').inner_text()
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
    assert purpose_source.get_attribute('aria-label').startswith('Source: Session, 2 Aug')
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
      const purpose = 'A shared-inbox tool for a team to review long threads, identify decisions and unresolved follow-ups, and prepare a weekly brief before a renewal call. '.repeat(2);
      r.text = r.text.replace(/## What it is\\n- [^\\n]+/, '## What it is\\n- ' + purpose + '[1].');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    statement = page.locator('.focus-statement')
    assert statement.evaluate('(node) => node.scrollHeight > node.clientHeight')
    chip = page.locator('.project-purpose-cites a.cite').first
    source = page.locator('.focus-source')
    assert chip.bounding_box()['y'] + chip.bounding_box()['height'] <= 812
    assert source.bounding_box()['y'] + source.bounding_box()['height'] <= 812
    page.get_by_role('button', name='Read full purpose').click()
    assert not statement.evaluate('(node) => node.scrollHeight > node.clientHeight')
    assert 'weekly brief before a renewal call' in statement.inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


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
    page.evaluate("() => { const r = byPath('people/mara-ostrowski.md'); r.text = r.text.replace('## Open threads\\n', '## Open threads\\n- Completion evidence not recorded.\\n'); KNOWN.clear(); render(); }", isolated_context=False)
    page.locator('.waiting-more a').click()
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
    page.evaluate(r"""({mine, theirs}) => {
      for (const r of REM.records)
        r.text = r.text.replace(/(^## Open threads[^\n]*\n)[\s\S]*?(?=^## |^Investigation:|(?![\s\S]))/mi, '$1Unknown\n\n');
      const items = [
        ...Array.from({ length: mine }, (_, i) => '- You owe Mara reply ' + i + ' [1].'),
        ...Array.from({ length: theirs }, (_, i) => '- Mara owes you answer ' + i + ' [1].')
      ];
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace('## Open threads\nUnknown', '## Open threads\n' + (items.join('\n') || 'Unknown'));
      KNOWN.clear(); FACTS.clear(); render();
    }""", {"mine": mine, "theirs": theirs}, isolated_context=False)
    primary = page.locator('.morning-primary')
    assert 'See all 0' not in primary.inner_text()
    assert ' 0 ' not in primary.inner_text()
    assert page.locator('.waiting-intro').count() == bool(mine)
    assert page.locator('.waiting-ledger').count() == bool(mine)
    assert page.locator('.waiting-ledger li').count() == mine
    if not mine:
        assert primary.locator('h1').inner_text() == 'Nothing is waiting on you'
    if mine or theirs:
        text = f'See all {mine} waiting on you' if mine else f'{theirs} waiting on someone else →'
        if mine and theirs:
            text += f' and {theirs} {"is" if theirs == 1 else "are"} waiting on someone else'
        assert primary.locator('.waiting-more').inner_text() == text
    else:
        assert primary.locator('.waiting-more').count() == 0
        assert primary.locator('.quiet-line', has_text='Nothing is open between you and anyone right now.').count() == 1
    assert 'Gone quiet (0)' not in page.locator('body').inner_text()
    if mine or theirs:
        primary.locator('.waiting-more a').click()
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
        assert (background == "rgb(14, 17, 32)") == (theme == "dark"), (view, background)


def test_source_and_conversation_show_input_limits_and_hide_them_with_private_content(reader):
    page, uri = reader
    scope = 'Codex Desktop voice transcription; only explicit input, transcript delta omitted; recognition errors possible'
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("scope => { const c = REM.source_context['outlook:77c09ad1e3f0']; c.input_scope = scope; REM.conversations[c.thread].messages[0].input_scope = scope; }", scope, isolated_context=False)
    page.locator("a.cite[href*='src-5']").first.click()
    note = page.locator('#evidence-panel .evidence-input-scope')
    assert note.is_visible() and 'Transcription may contain errors.' in note.inner_text() and 'transcript delta' not in note.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not note.is_visible()
    page.get_by_role('button', name='Close source context').click()
    page.evaluate('togglePrivate()', isolated_context=False)
    page.locator('details.deep-note:not([open]) > summary').click()
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
    cite = page.locator("a.cite[href*='src-5']").first
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
      c.messages = [{excerpt: 'Approve the design.', input_scope: common},
        {excerpt: 'Make the title shorter.', input_scope: common},
        {excerpt: 'Voice request.', input_scope: 'Codex Desktop voice transcription; recognition errors possible'}];
      c.total = 3;
    }""", isolated_context=False)
    page.locator('details.deep-note:not([open]) > summary').click()
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
      KNOWN.clear(); render();
    }""", isolated_context=False)
    row = page.locator('.ledger-column.mine .ledger-row').first
    assert row.locator('.ledger-meta').inner_text() == 'due 3 Oct'
    page.evaluate("REM.as_of = '2026-10-03T14:30:00Z'; render()", isolated_context=False)
    assert page.locator('.ledger-column.mine .ledger-meta').first.inner_text() == 'overdue · 3 Oct'
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
      KNOWN.clear(); render();
    }""", isolated_context=False)
    ledger = page.locator('.ledger-column.mine')
    assert ledger.locator('.ledger-meta').inner_text() == '5 days'
    assert 'exact due day still needs confirmation' in ledger.inner_text()
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
    assert 'Last contact 2 Oct' in other.locator('.contact-line').inner_text()
    assert other.evaluate("fmtDate('2026-07-31T23:03:58Z')", isolated_context=False) == 'Aug 1, 2026'
    assert other.evaluate("fmtDate('2026-07-31')", isolated_context=False) == 'Jul 31, 2026'
    other.evaluate("REM.as_of = '2026-12-31T14:00:00Z'", isolated_context=False)
    assert other.evaluate("shortDate('2026-12-31')", isolated_context=False) == 'Dec 31, 2026'
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
    assert page.locator('.activity-day').all_inner_texts() == ['4 Sep', '3 Sep', '2 Sep', '1 Sep']
    assert page.locator('.activity-text').count() == 4
    assert all(text.count('Confirmed the venue plan') == 5 for text in page.locator('.activity-text').all_inner_texts())
    assert page.locator('.activity-list').evaluate('e => e.scrollHeight <= e.clientHeight')
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
    assert 'Programme manager (historical current unknown)' in page.locator('.contact-line').inner_text()
    assert 'Old employer' not in page.locator('.contact-line').inner_text()
    page.evaluate("""() => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      r.text = r.text.replace(/^- Company:[^\\n]+\\n/m, '');
      KNOWN.delete(r.path); FACTS.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Old employer' in page.locator('.contact-line').inner_text()


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
    action = page.get_by_role('button', name='Copy the command')
    action.scroll_into_view_if_needed()
    assert action.bounding_box()['height'] >= 44
    assert page.locator('.missing.primary button').count() == 1
    assert page.locator('.focus-command').count() == 0


def test_skill_roster_links_are_touch_sized_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#c=skills')
    for link in page.locator('.hits.skills .t a').all():
        box = link.bounding_box()
        assert box['width'] >= 44 and box['height'] >= 44
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.hits.skills .t a').first.click()
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
    assert 'unresolved section' in page.locator('.missing .lead').inner_text().lower()
    page.goto(uri + '#r=people%2Fquinn-alder.md')
    assert page.locator('.missing .names').inner_text().startswith('Not investigated yet:')
    assert page.locator('.missing .lead').inner_text().lower() == 'only mapped so far'


def test_mapped_person_distinguishes_map_date_from_missing_note_fact(reader):
    page, uri = reader
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        page.reload()
        page.goto(uri + '#r=people%2Fquinn-alder.md')
        page.get_by_role('heading', name='Quinn Alder', exact=True).wait_for()
        assert 'Last contact in map' in page.locator('.leadrow').inner_text()
        assert page.locator('.focus-facts').count() == 0
        assert page.locator('details.deep-note').get_attribute('open') is None
        assert page.locator('.deep-note .factlist').count() == 1
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if width == 375:
            button = page.locator('.missing.primary .btn-action').bounding_box()
            assert button['height'] >= 44
            assert button['y'] + button['height'] <= 812

        page.goto(uri + '#c=people')
        page.get_by_role('heading', name='People', exact=True).wait_for()
        quinn = page.locator('.sheet tbody tr').filter(has_text='Quinn Alder')
        assert 'map' in quinn.locator('.c-last').inner_text()

        page.goto(uri + '#r=people%2Fmara-ostrowski.md')
        page.get_by_role('heading', name='Mara Ostrowski', exact=True).wait_for()
        assert 'Last contact in map' not in page.locator('.leadrow').inner_text()

        page.goto(uri + '#r=people%2Fquinn-alder.md')
        page.get_by_role('heading', name='Quinn Alder', exact=True).wait_for()
        page.evaluate("""() => {
          const r = byPath('people/quinn-alder.md');
          r.last_activity = ''; r.mail.last = '';
          KNOWN.delete(r.path); FACTS.delete(r.path); render();
        }""", isolated_context=False)
        assert 'Last contact in map' not in page.locator('.leadrow').inner_text()
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
    assert 'Last mapped session' not in page.locator('.leadrow').inner_text()
    assert 'Last mapped session' in page.locator('.focus-facts').inner_text()
    assert 'last mapped session' in page.locator('.eyebrow').inner_text()
    assert 'Last active' not in page.locator('.leadrow').inner_text()
    page.goto(uri + '#c=projects')
    assert 'Last mapped session' in page.locator('.sheet thead').inner_text()


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
    rows = page.locator('.activity-list li')
    delivered = rows.filter(has_text='You sent company introductions')
    promised = rows.filter(has_text='You promised to send')
    assert delivered.get_attribute('data-type') == 'Conversation'
    assert promised.get_attribute('data-type') == 'Commitment'
    assert delivered.is_visible() and promised.is_visible()
    assert page.locator('.recent-activity .activity-filters').count() == 0


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
    for selector in ('.focus-statement', '.deep-note'):
        area = page.locator(selector)
        assert area.locator('.private').count() == 3
        assert area.locator('.private').filter(has_text='Second confidential finding').count() == 1
    assert page.locator('.deep-note .private a.cite').count() == 3
    page.evaluate('togglePrivate()', isolated_context=False)
    for selector in ('.focus-statement', '.deep-note'):
        text = page.locator(selector).inner_text()
        assert 'confidential finding' not in text
        assert 'secret-value' not in text
        assert 'Public result.' in text
    page.evaluate('togglePrivate()', isolated_context=False)
    assert 'Second confidential finding' in page.locator('.focus-statement').inner_text()
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
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False: data)
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
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False: data)
    path = tmp_path / 'partial.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.goto(path.as_uri())
    brief = page.locator('.overnight')
    assert '1 investigation failed' in brief.inner_text()
    assert 'reworded; nothing new.' in brief.inner_text()
    assert page.locator('.week').get_by_role('link', name='Mara Ostrowski', exact=True).is_visible()
    assert page.locator('.waiting-ledger > li').count() > 0
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
    assert labels[-1] == 'Activity' and labels.index('All records') < labels.index('Activity')
    listed = page.evaluate('listedRecords().map(r => r.path)', isolated_context=False)
    assert not [path for path in listed if path.startswith(('logs/', 'notes/'))]
    assert page.locator('#nav a[href="#c=all"] .n').inner_text() == str(len(listed))
    assert 'Maps' not in page.locator('.category-cards').inner_text()
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
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False: data)
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
        chip = page.locator('.person-insight a.cite[href$="src-5"]').first
        assert chip.inner_text() == '14 Oct'
        assert 'Mara, Outlook, 14 Oct' in chip.get_attribute('title')
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
    assert values == ['you, Outlook, 14 Oct', 'Outlook, 22 Aug', 'source 99', 'Session', 'Repo', 'WhatsApp']
    page.locator('details.deep-note > summary').click()
    missing = page.locator('.factlist a.cite[href$="src-1"]').first
    assert 'missing' in missing.get_attribute('class')
    assert 'original not in this snapshot' in missing.get_attribute('aria-label')
    missing.click()
    panel = page.locator('#evidence-panel')
    assert panel.locator('.evidence-unavailable').inner_text() == "The original isn't in this snapshot."
    page.get_by_role('button', name='Close source context').click()
    grouped = page.locator('.person-insight .cite.run[data-sources="4 5 6"]')
    assert grouped.inner_text().endswith(' +2')
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
def test_person_ledger_discloses_extra_rows_and_deep_hash_targets(reader, theme, width):
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
        '- Yu owes Ody: a reimbursement [1].'
      ];
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/, '## Open threads\n' + rows.join('\n') + '\n');
      r.text = r.text.replace(/- Now:/, '- **Now**:').replace(/- At stake:/, '- **At stake**:');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    mine = page.locator('.ledger-column.mine')
    assert mine.locator('.ledger-count').inner_text() == '4'
    assert mine.locator('.ledger-rows').first.locator(':scope > li').count() == 3
    assert mine.locator('.ledger-row').filter(has_text='fourth answer').is_visible() is False
    assert 'You owe' not in mine.locator('.ledger-row p').first.inner_text()
    assert 'A scope decision; due:' in mine.inner_text()
    assert '7 days' in mine.inner_text() and '85 days, gone quiet' in mine.inner_text()
    assert page.locator('.ledger-column.theirs .ledger-count').inner_text() == '1'
    assert 'Yu owes Ody' not in page.locator('.between-you').inner_text()
    mine.locator('.ledger-more > summary').click()
    assert mine.locator('.ledger-row').filter(has_text='fourth answer').is_visible()
    assert page.locator('.person-insight dt.at-stake').inner_text() == 'At stake'
    assert page.locator('.person-insight dt').count() <= 4
    assert page.locator('.recent-activity .activity-list > li').count() <= 5
    assert page.locator('.deep-note .block-threads, .deep-note .block-insight').count() == 0
    assert page.locator('details.deep-note').get_attribute('open') is None
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.recent-activity .activity-head a').click()
    assert page.locator('details.deep-note').get_attribute('open') is not None
    assert page.locator('#history').is_visible()
    page.goto(uri + '#r=people%2Fmara-ostrowski.md&h=src-6')
    assert page.locator('details.deep-note').get_attribute('open') is not None
    assert page.locator('#src-6').is_visible()


def test_morning_rows_quote_only_original_words_and_format_overdue_dates(reader):
    page, _ = reader
    values = page.evaluate(r"""() => {
      REM.as_of = '2026-10-15T12:00:00Z'; REM.status.timezone = 'UTC';
      const r = {title: 'Weiwei Lei'};
      return [morningWords('The user owes Weiwei Lei a draft; send questions afterward [5].', r),
        morningWords('You owe Weiwei Lei a draft; due: 2026-10-22 [5].', r),
        morningWords('Weiwei asked “Send the draft and questions.” [5].', r),
        morningWords('You owe Weiwei Lei "ok" and a draft [5].', r),
        dueLabel({due: '2026-09-10'}), direction('You said you would send what Weiwei owes the bank')];
    }""", isolated_context=False)
    assert values[0] == {'words': 'A draft', 'context': 'send questions afterward. [5]'}
    assert values[1]['words'] == 'A draft' and 'due: 2026-10-22' in values[1]['context']
    assert values[2]['words'] == '“Send the draft and questions.”' and '[5]' in values[2]['context']
    assert not values[3]['words'].startswith('“')
    assert values[4] == 'overdue · 10 Sep'
    assert values[5] != 'third'


def test_morning_selection_keeps_distinct_pages_and_named_obligations(reader):
    page, _ = reader
    got = page.evaluate(r"""() => {
      const mara = byPath('people/mara-ostrowski.md'), tomas = byPath('people/tomas-reyes.md');
      const ines = byPath('people/ines-halvorsen.md'), project = byPath('projects/harbour.md');
      const item = (r, text) => ({r, t: {text, dir: 'mine', quiet: false}});
      return morningEntries([
        item(mara, 'You owe Tomás a talk abstract [1].'),
        item(mara, 'You owe Mara the signed draft [4].'),
        item(mara, 'You owe Mara a second answer [5].'),
        item(tomas, 'You owe Tomás the signed draft [1].'),
        item(project, 'You owe Tomás Reyes the signed draft [1].'),
        item(ines, 'You owe Inès the Q3 receipts [1].'),
        item(project, 'You owe Harbour a deployment [1].')
      ]).map(({r, t}) => [r.path, t.text]);
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
    page.evaluate(r"""() => {
      const quote = "I'll come back to you shortly with a draft and a couple of questions about the contribution details.";
      for (const [path, n] of [['people/mara-ostrowski.md', '91'], ['people/tomas-reyes.md', 'W92']]) {
        const r = byPath(path);
        const words = n === '91' ? "We're preparing the letter and supporting documents now, and " + quote : quote;
        r.text = r.text.replace('## Open threads\n', '## Open threads\n' +
          '- The user owes [Tomás Reyes](../people/tomas-reyes.md): a Letter of Support draft; “' + words + '” [' + n + ']; due: 2026-10-01.\n');
        r.text = r.text.replace('## Sources\n', '## Sources\n- [' + n + '] gmail:27472b21b17e — Letter of Support promise\n');
      }
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    home = page.locator('.waiting-ledger > li').filter(has_text='Letter of Support draft')
    assert home.count() == 1
    assert home.locator('.waiting-person a').inner_text() == 'Tomás Reyes'
    assert home.locator('.also-on').inner_text() == 'Also on Mara Ostrowski'
    also = home.locator('.also-on a')
    assert also.get_attribute('href') == '#r=people%2Fmara-ostrowski.md'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path / 'deduped-home.png'), full_page=True)
    # Hash navigation preserves the injected notebook records.
    page.evaluate("location.hash = 'view=open'", isolated_context=False)
    page.get_by_role('heading', name='Open threads', exact=True).wait_for()
    rows = page.locator('.task-band .thread.mine')
    shared = rows.filter(has_text='Letter of Support draft')
    assert shared.count() == 1
    assert shared.locator('.who a').inner_text() == 'Tomás Reyes'
    assert shared.locator('.also-on').inner_text() == 'Also on Mara Ostrowski'
    assert page.locator('#nav a[href="#view=open"] .n.waiting').inner_text() == str(rows.count())
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path / 'deduped-open.png'), full_page=True)
    shared.locator('.also-on a').click()
    page.get_by_role('heading', name='Mara Ostrowski', exact=True).wait_for()

def test_morning_keeps_separate_people_with_the_same_kind_of_request(reader):
    page, _ = reader
    assert page.evaluate(r"""() => {
      const people = ['people/mara-ostrowski.md', 'people/tomas-reyes.md', 'people/ines-halvorsen.md'].map(byPath);
      return morningEntries(people.map(r => ({r, t: {text: 'You owe ' + r.title + ' a reply [1].', dir: 'mine', quiet: false}}))).length;
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

    def fixed_snapshot(root, local=False):
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
    expect(page.locator("h1")).to_have_text("Agent sessions")
    expect(page.locator(".session-result-line")).to_have_text("6 sessions")
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
    expect(page.locator(".session-title")).to_have_text("检查仓库")
    box.fill("整理 文件")
    expect(page.locator(".session-speaker")).to_have_text("You: ")
    assert page.locator(".session-excerpt mark").all_text_contents() == ["整理", "文件"]
    box.fill("searchable focus")
    expect(page.locator(".session-title")).to_have_text("Release the reader")
    expect(page.locator(".session-excerpt")).to_contain_text("Shipped a searchable reader with stable focus.")
    box.fill("late needle")
    expect(page.locator(".session-title")).to_have_text("Check the deployment")
    expect(page.locator(".session-speaker")).to_have_text("Agent: ")
    box.fill("metadata-only-secret")
    expect(page.locator(".empty .lead")).to_have_text("No session matches")
    expect(page.locator(".empty p")).to_contain_text("metadata-only-secret")
    page.get_by_role("button", name="Clear", exact=True).click()
    expect(box).to_have_value("")
    expect(page.locator(".session-result-line")).to_have_text("6 sessions")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_sessions_topics_summaries_outcomes_and_person(session_reader):
    from patchright.sync_api import expect

    page, uri = session_reader
    topics = page.locator(".session-topics")
    expect(topics.get_by_role("button", name="reader 2", exact=True)).to_be_visible()
    expect(topics).to_contain_text("Not summarised 4")
    expect(page.locator(".session-excerpt").filter(has_text="Shipped a searchable reader")).to_be_visible()
    assert "Ship the new list" not in page.locator("#session-results").inner_text()
    topic = topics.get_by_role("button", name="reader 2", exact=True)
    topic.focus()
    topic.press("Enter")
    assert topic.evaluate("node => node === document.activeElement")
    assert "tag=reader" in page.url
    expect(page.locator(".session-result-line")).to_contain_text("2 of 6 sessions")
    expect(topics.get_by_role("button", name="reader 2", exact=True)).to_have_attribute("aria-pressed", "true")
    topics.get_by_role("button", name="Done 1", exact=True).click()
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    assert "outcome=done" in page.url
    expect(page.locator(".session-tags")).to_contain_text("Done")
    page.get_by_role("button", name="Clear", exact=True).click()
    page.locator(".session-tags a").filter(has_text="search").click()
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    assert "tag=search" in page.url
    page.goto(uri + "#c=sessions&person=people%2Favery.md")
    expect(page.locator(".session-result-line")).to_contain_text("2 of 6 sessions")
    page.get_by_role("button", name="Mentioning Avery ×").click()
    expect(page.locator(".session-result-line")).to_have_text("6 sessions")
    assert "person=" not in page.url


@pytest.mark.parametrize("width", [1400, 375])
def test_sessions_filters_notebook_calendar_and_groups(session_reader, width):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 812})
    page.goto("about:blank")
    page.goto(uri + "#c=sessions")
    panel = page.locator(".session-filter-panel")
    toggle = page.get_by_role("button", name="Filter", exact=True)
    if width == 375:
        expect(panel).not_to_be_visible()
        expect(page.get_by_role("searchbox", name="Search sessions")).to_be_visible()
        expect(page.locator(".session-result-line")).to_be_visible()
        toggle.click()
        expect(panel).to_be_visible()
    project = page.get_by_label("Project", exact=True)
    assert project.locator("option").all_text_contents() == ["All projects", "Alpha · 3", "Beta · 2", "No project · 1"]
    project.select_option("projects/alpha.md")
    page.get_by_role("group", name="Agent", exact=True).get_by_role("button", name="Codex", exact=True).click()
    expect(page.locator(".session-result-line")).to_contain_text("2 of 6 sessions")
    expect(page.locator(".session-topics")).to_contain_text("reader 1")
    if width == 375:
        expect(page.get_by_role("button", name="Filter · 2", exact=True)).to_be_visible()
    page.get_by_role("button", name="By project", exact=True).click()
    expect(page.locator(".session-group > summary")).to_have_text(["Alpha2"])
    expect(page.locator(".session-meta").first).to_contain_text("Oct")
    page.get_by_role("button", name="Clear", exact=True).click()
    expect(page.locator(".session-group > summary")).to_have_text(["Alpha3", "Beta2", "No project1"])
    assert "by=project" in page.url
    page.get_by_role("group", name="Time", exact=True).get_by_role("button", name="Today", exact=True).click()
    expect(page.locator(".session-result-line")).to_contain_text("2 of 6 sessions")
    assert "when=today" in page.url
    page.get_by_role("button", name="This week", exact=True).click()
    expect(page.locator(".session-result-line")).to_contain_text("4 of 6 sessions")
    page.get_by_role("button", name="This month", exact=True).click()
    expect(page.locator(".session-result-line")).to_contain_text("5 of 6 sessions")
    page.locator(".session-dates summary").click()
    page.locator('input[aria-label="From"]').fill("2026-10-11")
    page.locator('input[aria-label="To"]').fill("2026-10-12")
    expect(page.locator(".session-result-line")).to_contain_text("2 of 6 sessions")
    assert "when=" not in page.url
    page.get_by_role("button", name="By day", exact=True).click()
    expect(page.locator(".session-day .session-count")).to_have_text(["1", "1"])
    page.goto(uri + "#c=sessions&project=none")
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    expect(page.locator(".session-meta")).to_contain_text("scratch · Codex · 09:12 · 1 turn")
    assert page.locator('.session-meta span[title="/work/scratch"]').count() == 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if width == 375:
        page.get_by_role("button", name="Filter · 1").click()
        for node in page.locator(".sessions-view button:visible, .sessions-view input:visible, .sessions-view select:visible, .sessions-view summary:visible").all():
            assert node.bounding_box()["height"] >= 40


def test_sessions_typing_renders_three_hundred_rows_under_fifty_ms(session_reader):
    from patchright.sync_api import expect

    page, _ = session_reader
    page.evaluate("""() => {
      const originals = REM.records.filter(r => r.category === 'sessions');
      for (let i = 0; i < 294; i++) REM.records.push({...originals[i % 6], path: 'sessions/copy-' + i + '.md'});
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
    expect(page.locator(".session-row")).to_have_count(300)
    page.get_by_role("searchbox", name="Search sessions").press_sequentially("cloud sql", delay=160)
    expect(page).to_have_url(re.compile(r"find=cloud(?:%20|\+)sql$"))
    expect(page.locator(".session-result-line")).to_contain_text("50 of 300 sessions")
    durations = page.evaluate("sessionDurations", isolated_context=False)
    assert len(durations) == 9
    # The first keystroke builds each session's search text once.
    assert max(durations[1:]) < 50 and durations[0] < 200, durations


def test_sessions_more_topics_and_unstructured_notebooks(session_reader):
    from patchright.sync_api import expect

    page, _ = session_reader
    page.evaluate("""() => {
      REM.records.find(r => r.path === 'sessions/release.md').session_tags =
        Array.from({length: 20}, (_, i) => 'topic-' + String(i).padStart(2, '0'));
      render();
    }""", isolated_context=False)
    buttons = page.locator(".session-topic-buttons button:visible")
    expect(buttons).to_have_count(16)
    page.get_by_text("More topics", exact=True).click()
    expect(buttons).to_have_count(22)
    topic = page.get_by_role("button", name="topic-19 1", exact=True)
    topic.focus()
    topic.press("Enter")
    expect(topic).to_have_attribute("aria-pressed", "true")
    assert topic.evaluate("node => node === document.activeElement")
    expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    # A full hash render reveals an active topic beyond the initial sixteen.
    page.evaluate("render()", isolated_context=False)
    expect(topic).to_be_visible()
    expect(topic).to_have_attribute("aria-pressed", "true")
    page.get_by_role("button", name="Clear", exact=True).click()
    page.evaluate("""() => {
      for (const r of REM.records.filter(r => r.category === 'sessions')) {
        r.session_summary = ''; r.session_tags = []; r.session_outcome = '';
      }
      render();
    }""", isolated_context=False)
    expect(page.locator(".session-topics")).not_to_be_visible()
    expect(page.locator(".session-row")).to_have_count(6)
    expect(page.get_by_role("searchbox", name="Search sessions")).to_be_visible()


@pytest.mark.parametrize("width", [1400, 375])
def test_session_page_structure_precedes_closed_conversation(session_reader, width):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 812})
    page.goto(uri + "#r=sessions%2Frelease.md")
    expect(page.locator("h1")).to_have_text("Release the reader")
    attachment = page.locator(".session-attachment")
    assert not attachment.evaluate("node => node.open")
    for heading in ("Summary", "Decisions", "Follow-ups", "Artifacts"):
        node = page.get_by_role("heading", name=heading, exact=True)
        expect(node).to_be_visible()
        assert node.bounding_box()["y"] < attachment.bounding_box()["y"]
    expect(page.locator(".session-facts-line")).to_contain_text("09:12 · Codex · Alpha · 12 turns · Done")
    assert page.locator(".session-page .status, .session-page .toc, .session-page .record-focus").count() == 0
    expect(page.locator(".session-followups a")).to_have_attribute("href", "#r=people%2Favery.md")
    pr = page.locator(".session-artifacts a")
    expect(pr).to_have_attribute("target", "_blank")
    expect(pr).to_have_attribute("rel", "noopener")
    page.locator(".session-artifacts summary").filter(has_text="Files changed (3)").click()
    expect(page.locator(".session-artifacts details").first.locator("li")).to_have_count(3)
    page.get_by_role("link", name="09:13", exact=True).click()
    assert attachment.evaluate("node => node.open")
    expect(page.locator(".session-outline li")).to_have_count(12)
    assert page.locator("#session-message-2").bounding_box()["y"] < 100
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1400, 375])
def test_session_find_outline_and_long_reply(session_reader, width):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 812})
    page.goto(uri + "#r=sessions%2Frelease.md&find=seventhneedle")
    expect(page.locator(".session-find-status")).to_have_text("1 of 2")
    assert page.locator(".session-attachment").evaluate("node => node.open")
    expect(page.get_by_role("searchbox", name="Find in this conversation")).to_have_value("seventhneedle")
    expect(page.locator(".session-message mark")).to_have_count(2)
    assert page.locator(".session-message img").count() == 0
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
    expect(page.locator(".session-final mark").first).to_be_visible()
    box.press("Shift+Enter")
    expect(page.locator(".session-final mark.current")).to_be_in_viewport()
    assert len(page.locator(".session-final .session-quote").inner_text()) == 3000
    box.fill("")
    expect(page.locator(".session-messages mark")).to_have_count(0)
    assert len(page.locator(".session-final .session-quote").inner_text()) < 650
    # Outline navigation also works when the attachment was initially closed.
    page.goto(uri + "#r=sessions%2Frelease.md")
    page.locator(".session-attachment > summary").click()
    expect(page.get_by_role("button", name="Next match", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Previous match", exact=True)).to_be_disabled()
    outline = page.locator(".session-outline li a")
    expect(outline).to_have_count(12)
    outline.nth(6).click()
    assert 0 <= page.locator("#session-message-7").bounding_box()["y"] < 100
    reply = page.locator(".session-final .session-quote")
    assert len(reply.inner_text()) < 650
    page.get_by_role("button", name="Show all", exact=True).click()
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
    mentions = page.locator(".person-sessions")  # beside Recently, not inside the full note
    expect(mentions.get_by_role("heading", name="Mentioned in sessions")).to_be_visible()
    expect(mentions.locator(".session-context-row")).to_have_count(5)
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
def test_sessions_real_data_list_order_artifact_search_and_topic_limits(session_reader, width):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1400 else 844})
    page.goto(uri + "#c=sessions")
    page.evaluate("""() => {
      REM.records.find(r => r.path === 'sessions/release.md').session_tags =
        Array.from({length: 20}, (_, i) => 'topic-' + i);
      render();
    }""", isolated_context=False)
    search = page.get_by_role("searchbox", name="Search sessions")
    expect(page.locator("#main > .lede")).to_have_text("What you worked on with your coding agents")
    assert page.locator("h1").bounding_box()["y"] < search.bounding_box()["y"]
    assert search.bounding_box()["y"] < page.locator(".session-topics").bounding_box()["y"]
    assert search.bounding_box()["y"] + search.bounding_box()["height"] < (900 if width == 1400 else 844)
    expect(page.locator(".session-topic-buttons button:visible")).to_have_count(16 if width == 1400 else 6)
    if width == 1400:
        controls = page.locator(".session-filter-panel > .session-filter")
        bottoms = [node.bounding_box()["y"] + node.bounding_box()["height"] for node in controls.all()]
        assert max(bottoms) - min(bottoms) <= 1
        assert len({round(node.bounding_box()["y"]) for node in controls.all()}) == 1
    if width == 390:
        expect(page.locator(".session-outcomes")).not_to_be_visible()
        page.get_by_role("button", name="Filter", exact=True).click()
        expect(page.locator(".session-filter-panel .session-outcomes")).to_be_visible()
    search.fill("no-such-session")
    expect(page.locator(".empty .lead")).to_have_text("No session matches")
    expect(page.locator(".session-topics")).not_to_be_visible()
    for query in ("gcloud sql", "abc123def", "reader-structure", "github.com/openonion/connectonion/pull/123"):
        search.fill(query)
        expect(page.locator(".session-title")).to_have_text("Release the reader")
        expect(page.locator(".session-result-line")).to_contain_text("1 of 6 sessions")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_session_source_deep_link_reveals_details(session_reader):
    from patchright.sync_api import expect

    page, uri = session_reader
    page.goto(uri + "#r=sessions%2Frelease.md&h=src-1")
    expect(page.locator("#src-1")).to_be_in_viewport()
    assert page.locator(".session-details").evaluate("node => node.open")
    assert not page.locator(".session-attachment").evaluate("node => node.open")


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
    assert not settings.evaluate('node => node.open')
    assert not page.locator('#privacy-toggle').is_visible()
    assert 'Snapshot ' in page.locator('#foot').inner_text()
    assert 'Background updates off' not in page.locator('#foot').inner_text()
    settings.locator('summary').click()
    assert settings.locator('code').count() == 1
    assert ' open re-renders' in settings.locator('code').inner_text()
    assert page.locator('#privacy-toggle').is_visible()
    assert 'Background updates off' in settings.inner_text()
    page.evaluate("document.querySelector('.reader-settings code').textContent = 'co rem --root /' + 'longpath'.repeat(60) + ' open'")
    assert settings.locator('code').evaluate('node => node.scrollWidth <= node.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('labelled', ['Private conversation. [personal] [1]', 'Private conversation [personal]. [1]'])
def test_summary_omits_empty_relationship_history_and_unknown_facts(reader, labelled):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''labelled => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = '# Mara Ostrowski\n\nA fixture contact.\n\n## Facts\n- Phone: Unknown\n- Role: —\n- Location: unknown\n'
        + '\n## Open threads\nNothing open as of 2026-10-01.\n'
        + '\n## Insight\n- Now: Confidential status. [sensitive] [1]\n'
        + '\n## History\n- 2026-09-25: ' + labelled + '\n- 2026-09-26: [1]\n'
        + '\n## Sources\n- [1] test:fixture\n';
      KNOWN.clear(); FACTS.clear(); render();
      document.documentElement.classList.add('hide-private');
    }''', labelled, isolated_context=False)
    assert page.locator('.between-you').count() == 0
    assert page.locator('.activity-list > li:visible').count() == 0
    assert page.locator('.recent-activity .private-history-notice').inner_text() == '1 private entry hidden'
    assert page.locator('.contact-strip dt').filter(has_text='Phone').count() == 0
    assert page.locator('.contact-strip dt').filter(has_text='Role').count() == 0
    hidden = page.locator('.person-insight dd.privacy-only')
    assert hidden.inner_text() == 'Hidden labelled passage'
    assert hidden.evaluate('node => parseFloat(getComputedStyle(node).fontSize) <= 13')
    page.locator('details.deep-note > summary').click()
    assert 'Unknown' in page.locator('.factlist').inner_text() or 'not found' in page.locator('.factlist').inner_text()
    assert page.locator('.timeline > li:visible').count() == 0
    assert page.locator('.block-history .private-history-notice').inner_text() == '1 private entry hidden'
    page.evaluate('togglePrivate()', isolated_context=False)
    assert page.locator('.activity-list > li:visible').count() == 1
    assert not page.locator('.recent-activity .private-history-notice').is_visible()


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
    provenance = page.locator('.relation-provenance')
    assert provenance.locator('a:not(.cite)').count() == 0
    assert provenance.locator('a.cite').count() == 1
    page.locator('details.deep-note > summary').click()
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
    page.locator('.person-insight .cite').first.click()
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
    assert page.locator('#q').is_visible()
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
      r.text += '\n## History\n' + Array.from({length: 8}, (_, i) =>
        '- 2026-09-' + String(i + 1).padStart(2, '0') + ': ' +
        (i < 6 ? 'Agreed the plan. ' : 'Discussed the plan. ') + 'Complete history text. '.repeat(8)).join('\n');
      KNOWN.clear(); render();
    }''', path, isolated_context=False)
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
    assert 'since 13 Sep' in rows.first.locator('.when').get_attribute('title')


@pytest.mark.parametrize('path', ['people/quinn-alder.md', 'skills/catalog/weekly-brief.md'])
@pytest.mark.parametrize('width', [1440, 390])
def test_mapped_guidance_explains_before_command_with_secondary_copy(reader, path, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=' + path.replace('/', '%2F'))
    box = page.locator('.missing.primary')
    assert box.locator(':scope > *').evaluate_all('nodes => nodes.map(n => n.className)') == [
        'lead', 'why', 'cmd', 'names']
    assert box.locator('.why').inner_text() == (
        "co rem has this page from your sources' metadata, not from reading them. "
        'One investigation reads the material and fills it in.')
    copy = box.get_by_role('button', name='Copy the command', exact=True)
    assert 'btn-primary' not in copy.get_attribute('class')
    assert copy.bounding_box()['height'] >= 32
    command = box.locator('code').bounding_box()
    button = copy.bounding_box()
    assert button['x'] >= command['x'] + command['width']
    assert abs((button['y'] + button['height'] / 2) - (command['y'] + command['height'] / 2)) < 2
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
        assert float(quote_background.removesuffix(')').split(',')[-1]) <= .08
        assert quote.evaluate('node => getComputedStyle(node).textDecorationLine') == 'underline'


@pytest.mark.parametrize('width', [1440, 390])
def test_project_path_wraps_at_slashes_and_keeps_segments_readable(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate('''() => {
      const r = byPath('projects/harbour.md');
      r.text = r.text.replace('/home/user/code/harbour', '/Users/avery/landpages/LayeredVisions');
      FACTS.clear(); render();
    }''', isolated_context=False)
    path = page.locator('.focus-facts .local-path')
    assert path.inner_text() == '/Users/avery/landpages/LayeredVisions'
    assert path.locator('wbr').count() == 4
    segment = path.locator('.path-segment').last
    assert segment.evaluate('node => { const r = document.createRange(); r.selectNodeContents(node); return r.getClientRects().length; }') == 1
    page.evaluate("document.querySelector('.path-segment:last-child').textContent = 'folder'.repeat(100)")
    assert path.evaluate('node => node.scrollWidth <= node.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_org_context_citation_is_flush_and_uncertainty_has_an_icon_gap(reader):
    page, uri = reader
    page.goto(uri + '#r=orgs%2Ffernhill-labs.md')
    page.evaluate(r'''() => {
      const r = byPath('orgs/fernhill-labs.md');
      r.relations = [{path: 'people/mara-ostrowski.md', kind: 'linked', via: r.path, sources: ['1']}];
      r.text += '\n## Uncertainties\n- Timing is unconfirmed. [1]\n';
      KNOWN.clear(); render();
    }''', isolated_context=False)
    cite = page.locator('.relation-provenance .cite').first
    assert abs(cite.bounding_box()['x'] - page.locator('.relation-card strong').first.bounding_box()['x']) <= 1
    assert page.locator('.unsure-icon').inner_text() == '?'
    assert page.locator('.unsure').evaluate('node => parseFloat(getComputedStyle(node).columnGap)') >= 4


def test_mobile_header_focus_and_touch_targets_on_every_view(reader):
    page, uri = reader
    page.set_viewport_size({'width': 390, 'height': 844})
    for view in VIEWS:
        page.goto(uri + (view or '#'))
        for selector in ('#q', '.nav-toggle', '.brand'):
            target = page.locator(selector)
            assert target.is_visible(), (view, selector)
            assert target.bounding_box()['height'] >= 40, (view, selector)
            target.focus()
            page.keyboard.press('Tab')
            page.keyboard.press('Shift+Tab')
            assert target.evaluate('node => getComputedStyle(node).outlineStyle') != 'none', (view, selector)
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
    row = page.locator('.sheet tbody tr').filter(has_text='Harbour')
    assert row.locator('.pill.status').inner_text() == 'Partly investigated'
    assert row.locator('.pill.status').get_attribute('title') == tooltip
    row.get_by_role('link', name='Harbour', exact=True).click()
    assert page.locator('.eyebrow .pill.status').inner_text() == 'Partly investigated'
    assert page.locator('.eyebrow .pill.status').get_attribute('title') == tooltip


@pytest.mark.parametrize('width', [1440, 390])
def test_quiet_lead_citations_stay_with_words_and_reveal_sources(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    lead = page.locator('.person-lead')
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
      const node = document.querySelector('.person-lead');
      node.innerHTML = inline('这是一句较长的中文记录，用来检查引用标记始终与前面的文字在一起，同时允许句子在手机上自然换行而不会撑开整个页面 [5] .', 'people/mara-ostrowski.md');
    }''', isolated_context=False)
    assert page.locator('.person-lead .cite-tether').inner_text().startswith('面')
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('notebook_languages, browser_language', [(['zh', 'en'], 'en-AU'), ([], 'zh-CN')])
def test_chinese_interface_default_switch_and_persistence(reader, tmp_path, monkeypatch, width, notebook_languages, browser_language):
    from connectonion.rem import reader as rem_reader
    page, _ = reader
    data = rem_reader.snapshot(tmp_path / 'rem', local=True)
    data['your_languages'] = notebook_languages
    page.add_init_script("Object.defineProperty(navigator, 'language', {value: " + repr(browser_language) + "});")
    monkeypatch.setattr(rem_reader, 'snapshot', lambda root, local=False: data)
    path = tmp_path / 'chinese-reader.html'
    path.write_text(rem_reader.render(tmp_path / 'rem', local=True), encoding='utf-8')
    page.evaluate(r'''() => localStorage.removeItem('co-rem-ui-language')''')
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(path.as_uri() + '#r=people%2Fmara-ostrowski.md')
    page.wait_for_function(r'document.documentElement.lang === "zh"')
    if width < 600:
        page.get_by_role('button', name='浏览笔记库').click()
    assert page.locator('#nav a[href="#c=people"]').inner_text().startswith('人物')
    prose = r'''node => {
      const copy = node.cloneNode(true); copy.querySelectorAll('.cite').forEach(n => n.remove());
      return copy.textContent;
    }'''
    original = page.locator('.person-lead').evaluate(prose)
    assert page.locator('.between-you h2').inner_text() == '我们之间'
    page.locator('.language-switch').get_by_role('button', name='EN', exact=True).click()
    assert page.locator('#nav a[href="#c=people"]').inner_text().startswith('People')
    assert page.locator('.person-lead').inner_text() != ''
    assert page.locator('.person-lead').evaluate(prose) == original
    page.reload()
    page.wait_for_function(r'document.documentElement.lang === "en"')
    if width < 600:
        page.get_by_role('button', name='Browse notebook').click()
    page.locator('.language-switch').get_by_role('button', name='中文', exact=True).click()
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')
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
    assert page.locator('.record-focus .next-exchanges').is_visible()
    snippets = [value.strip().lower() for value in page.locator('.relation-basis').all_inner_texts() if value.strip()]
    assert len(snippets) == len(set(snippets))
    assert snippets.count('your contacts: mara, quinn and tomás.') == 1


@pytest.mark.parametrize('width', [1440, 390])
def test_empty_sessions_offer_small_copyable_commands_without_filters(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#c=sessions')
    page.evaluate(r'''() => { REM.default_root = true; render(); }''', isolated_context=False)
    assert page.locator('.sessions-empty h2').inner_text() == 'No agent sessions yet'
    assert page.locator('.session-filter-panel, #session-search').count() == 0
    assert page.locator('.sessions-empty code').all_inner_texts() == ['co rem sources', 'co rem import sessions']
    assert page.locator('.sessions-empty button[aria-label="Copy the command"]').count() == 2
    assert page.evaluate(r'document.documentElement.scrollWidth <= innerWidth')
    page.evaluate(r'''() => { REM.default_root = false; REM.root = '/tmp/avery notebook'; render(); }''', isolated_context=False)
    assert "--root '/tmp/avery notebook'" in page.locator('.sessions-empty code').first.inner_text()
    page.evaluate(r"""() => { REM.root = '/tmp/' + 'long notebook path/'.repeat(12); render(); }""", isolated_context=False)
    command = page.locator('.sessions-empty code').last
    assert command.inner_text().endswith('import sessions')
    assert command.evaluate('node => node.scrollWidth <= node.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [1440, 390])
def test_hidden_excerpt_keeps_identity_claim_and_inline_reveal(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r'''() => document.documentElement.classList.add('hide-private')''')
    page.locator('.person-insight a.cite[href$="src-4"]').first.click()
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

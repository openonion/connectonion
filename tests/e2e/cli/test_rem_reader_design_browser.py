"""The redesigned reader on a realistic notebook, in a real browser (opt in).

The fixture (tests/fixtures/rem_reader_notebook.py) is invented but shaped like
real pages: cited leads, Contact fields, open threads in both directions, a
dated History, numbered Sources, an ASCII Overview, a skill's usage, a week of
run logs. Each view is checked for what a returning reader came for, and every
view must fit a phone without sideways scrolling, in both themes.
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

VIEWS = ["", "#c=people", "#c=orgs", "#c=projects", "#c=skills", "#r=people%2Fmara-ostrowski.md",
         "#r=people%2Fquinn-alder.md", "#r=projects%2Fharbour.md", "#r=orgs%2Ffernhill-labs.md",
         "#r=skills%2Fcatalog%2Fweekly-brief.md", "#q=pilot", "#q=mara", "#r=people%2Favery-lin.md", "#c=opportunities", "#reviews=1"]


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

    def fixed_snapshot(root):
        data = snapshot(root)
        data["as_of"] = frozen.isoformat()
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path.write_text(rem_reader.render(build(tmp_path / "rem", frozen)), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        page.get_by_role("heading", name="What REM carried forward").wait_for()
        yield page, path.as_uri()
        browser.close()
        assert not errors, errors
        assert not requests, requests


def test_home_opens_on_what_to_remember_and_what_is_owed(reader):
    page, _ = reader
    memories = page.locator(".memory-card")
    assert memories.count() >= 3
    assert "Mara Ostrowski" in memories.all_inner_texts()[0]
    assert "pilot" in " ".join(memories.all_inner_texts()).lower()
    assert page.locator(".memory-connection a").count() >= 2
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
    night = page.locator(".night")
    assert "46 items" in night.inner_text() and "4 pages" in night.inner_text()
    assert night.locator(".hypno .dot.woke").count() == 1  # the night that stopped early
    assert set(night.locator(".changes a").all_inner_texts()) == {"Mara Ostrowski", "Harbour", "Fernhill Labs", "Avery Lin"}  # runs, and stamps of the night
    # Yours first, then what others owe you.
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
    page.locator("th", has_text="Mails").locator("button").click()
    assert sheet.locator("tbody .name a").first.inner_text() == "Mara Ostrowski"
    assert page.locator("th", has_text="Mails").get_attribute("aria-sort") == "descending"
    page.locator(".sheet-find").fill("ledgerline")
    assert sheet.locator("tbody .name a").all_inner_texts() == ["Inès Halvorsen"]
    sheet.locator("tbody tr").first.locator("td").nth(5).click()
    page.get_by_role("heading", name="Inès Halvorsen", exact=True).wait_for()


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


def test_a_person_opens_on_a_fact_card_with_cited_values(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    # Under the title: what you owe and for how long.
    lead = page.locator(".leadrow .lead-open")
    assert lead.locator(".dir").inner_text().upper() == "YOU OWE" and lead.locator(".age").inner_text() == "9 days"
    page.locator(".deep-note > summary").click()
    card = page.locator(".factlist")
    value = lambda label: card.locator(f"dt:text-is('{label}') + dd")  # noqa: E731
    assert "Head of Partnerships" in value("Role").inner_text()
    assert value("Phone").get_attribute("class") == "none" and "not found" in value("Phone").inner_text()
    assert "title and company in signature" in value("Role").locator(".cite").get_attribute("data-tip")
    assert value("Email").locator(".qual").all_inner_texts() == ["work", "personal"]
    assert [b.upper() for b in page.locator(".insight .badge").all_inner_texts()] == ["NOW", "AT STAKE", "CHANGED", "PATTERN"]
    assert page.locator(".insight .cite.run").count() == 1  # [4][5][6] read as "3 sources"
    assert page.locator(".block-threads .thread.mine").count() == 1
    assert page.locator(".timeline li").count() == 5
    assert page.locator("#src-6").count() == 1


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
    }
    assert page.evaluate("cases => Object.keys(cases).map(youify)", cases, isolated_context=False) == list(cases.values())
    # A thread addressed to the owner by name ("Avery: collect …") is the owner's to do.
    assert page.evaluate("direction('Avery: collect the swipe card from Security')", isolated_context=False) == "mine"
    home_threads = page.locator("ul.threads").first.inner_text()
    assert "you have owed them" in home_threads and "the user" not in home_threads.lower()
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    main = page.locator("#main").inner_text()
    assert "the user" not in main.lower() and "you have not signed it" in main
    page.locator(".deep-note > summary").click()
    assert page.get_by_role("heading", name="How you write to them").count() == 1
    assert page.evaluate("REM.records.find(r => r.path === 'people/mara-ostrowski.md').text.includes('the user has not signed it')", isolated_context=False)


def test_focus_connects_project_people_org_and_archived_conversation(reader):
    page, uri = reader
    page.goto(uri + "#r=projects%2Fharbour.md")
    connected = page.locator(".related-records .relation-card")
    assert {name.strip() for name in connected.locator("strong").all_inner_texts()} >= {
        "Mara Ostrowski", "Fernhill Labs"}
    assert page.get_by_role("heading", name="What this is").is_visible()
    assert page.get_by_role("heading", name="A recorded decision").is_visible()
    page.get_by_role("link", name="View all decisions").click()
    assert page.locator(".deep-note").get_attribute("open") is not None
    page.goto(uri + "#r=projects%2Fharbour.md")
    assert page.locator(".deep-note").get_attribute("open") is None
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.locator(".conversation-open").first.click()
    dialog = page.locator("#conversation-dialog")
    assert dialog.is_visible() and "usage export" in dialog.inner_text()
    dialog.get_by_role("button", name="Close conversation").click()
    assert page.locator(".conversation-open").first.evaluate("e => document.activeElement === e")
    page.locator(".deep-note > summary").click()
    page.locator("a.cite[href*='src-5']").first.click()
    evidence = page.locator("#evidence-dialog")
    assert evidence.is_visible() and "I will send the usage export" in evidence.inner_text()


def test_short_focus_text_clipped_on_phone_can_expand_and_collapse(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    statement = "Mara needs the revised pilot agreement before deciding whether her team can renew, including the usage export and the pricing proposal."
    assert len(statement) < 180
    page.evaluate("text => { const r = byPath('people/mara-ostrowski.md'); r.text = '# Mara Ostrowski\\n\\n' + text; KNOWN.clear(); FACTS.clear(); render(); }", statement, isolated_context=False)
    lead = page.locator('.focus-statement')
    assert lead.evaluate('e => e.scrollHeight > e.clientHeight')
    more = page.locator('.focus-more')
    assert more.is_visible()
    more.click()
    assert more.get_attribute('aria-expanded') == 'true'
    assert lead.evaluate('e => e.scrollHeight <= e.clientHeight + 1')
    page.get_by_role('button', name='Show less', exact=True).click()
    assert more.get_attribute('aria-expanded') == 'false'
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.wait_for_function("document.querySelector('.focus-more').hidden")


def test_record_dates_do_not_disagree_when_the_index_is_stale(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    expected = page.evaluate("known(byPath('people/mara-ostrowski.md')).last", isolated_context=False)
    page.evaluate("() => { byPath('people/mara-ostrowski.md').index = {last_contact: '2001-01-01'}; FACTS.clear(); render(); }", isolated_context=False)
    assert expected in page.locator('.focus-facts').inner_text()
    assert '2001' not in page.locator('.focus-facts').inner_text()
    page.locator('.deep-note > summary').click()
    formatted = page.evaluate('date => fmtDate(date)', expected, isolated_context=False)
    assert formatted in page.locator('.factlist dt:text-is("Last contact") + dd').inner_text()


def test_project_first_seen_does_not_establish_an_unknown_start_date(reader):
    page, uri = reader
    page.goto(uri + "#r=projects%2Fharbour.md")
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = r.text.replace('# Harbour', '# Harbour\\n\\n## Facts\\n- Started: Unknown');
      FACTS.clear(); render();
    }""", isolated_context=False)
    assert page.evaluate("facts(byPath('projects/harbour.md')).first", isolated_context=False)
    page.locator('.deep-note > summary').click()
    started = page.locator('.factlist dt:text-is("Started") + dd')
    assert started.locator('.val').count() == 0
    assert 'not found' in started.inner_text()


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
    page.locator('.conversation-open').first.click()
    messages = page.locator('#conversation-dialog .conversation-message')
    assert messages.first.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not messages.first.is_visible()
    assert page.locator('#conversation-dialog .private-hidden-notice').is_visible()
    page.get_by_role('button', name='Close conversation').click()
    page.locator('.deep-note > summary').click()
    page.locator("a.cite[href*='src-5']").first.click()
    original = page.locator('#evidence-dialog .evidence-original')
    assert original.count() == 1 and not original.is_visible()
    assert page.locator('#evidence-dialog .private-hidden-notice').is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert original.is_visible() and 'I will send the usage export' in original.inner_text()


def test_open_context_is_not_counted_as_waiting_on_other_people(reader):
    page, _ = reader
    page.evaluate("() => { const r = byPath('people/mara-ostrowski.md'); r.text = r.text.replace('## Open threads\\n', '## Open threads\\n- Completion evidence not recorded.\\n'); KNOWN.clear(); render(); }", isolated_context=False)
    others = page.locator('.band', has=page.locator('h3 span:text-is("Waiting on others")'))
    plain = page.locator('.band', has=page.locator('h3 span:text-is("Other open context")'))
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
        assert (background == "rgb(13, 16, 26)") == (theme == "dark"), (view, background)


def test_source_and_conversation_show_input_limits_and_hide_them_with_private_content(reader):
    page, uri = reader
    scope = 'Codex Desktop voice transcription; only explicit input, transcript delta omitted; recognition errors possible'
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("scope => { const c = REM.source_context['outlook:77c09ad1e3f0']; c.input_scope = scope; REM.conversations[c.thread].messages[0].input_scope = scope; }", scope, isolated_context=False)
    page.locator('.deep-note > summary').click()
    page.locator("a.cite[href*='src-5']").first.click()
    note = page.locator('#evidence-dialog .evidence-input-scope')
    assert note.is_visible() and 'Transcription may contain errors.' in note.inner_text() and 'transcript delta' not in note.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not note.is_visible()
    page.get_by_role('button', name='Close source context').click()
    page.evaluate('togglePrivate()', isolated_context=False)
    page.locator('.conversation-open').first.click()
    note = page.locator('#conversation-dialog .evidence-input-scope')
    assert note.is_visible() and 'Transcription may contain errors.' in note.inner_text() and 'transcript delta' not in note.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not note.is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


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
    page.locator('.deep-note > summary').click()
    page.locator('a.cite').first.click()
    dialog = page.locator('#evidence-dialog')
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


def test_skill_activity_uses_invocation_dates_instead_of_investigation_dates(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Ftalk-outline.md')
    assert 'RECORDED INVOCATIONS\n0' in page.locator('.focus-facts').inner_text()
    assert 'LAST ACTIVE' not in page.locator('.focus-facts').inner_text()
    assert 'LAST INVOCATION' not in page.locator('.focus-facts').inner_text()
    assert 'last activity' not in page.locator('.eyebrow').inner_text()
    assert 'last invocation' not in page.locator('.eyebrow').inner_text()
    assert 'file updated' in page.locator('.eyebrow').inner_text()
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    assert 'LAST INVOCATION' in page.locator('.focus-facts').inner_text()
    assert 'last invocation' in page.locator('.eyebrow').inner_text()
    assert page.evaluate('known(byPath("skills/catalog/weekly-brief.md")).last === skillUsage(byPath("skills/catalog/weekly-brief.md")).last', isolated_context=False)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


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
    page.locator('.deep-note > summary').click()
    assert page.locator('.missing .names').inner_text() == 'Still unknown: Current status.'
    assert 'unresolved section' in page.locator('.missing .lead').inner_text().lower()
    page.goto(uri + '#r=people%2Fquinn-alder.md')
    assert page.locator('.missing .names').inner_text().startswith('Not investigated yet:')
    assert page.locator('.missing .lead').inner_text().lower() == 'only mapped so far'


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
    page.get_by_role('button', name='Commitment 1', exact=True).click()
    assert not delivered.is_visible() and promised.is_visible()

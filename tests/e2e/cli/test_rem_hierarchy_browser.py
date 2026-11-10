"""Hierarchy by disclosure (direction D, 2026-11-10), in a real browser (opt in).

The owner: 「功能应该在你需要的时候出现，不需要的时候不出现。每个地方它有层次感，功能不能少」.
Each test checks one function's level: hidden at rest, then reachable through its trigger, and still doing its job.
"""
import os

import pytest

from tests.e2e.cli.test_rem_reader_design_browser import reader  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

UNIT = r'''() => {
  const parent = byPath('orgs/fernhill-labs.md');
  parent.children = ['orgs/pilot-squad.md'];
  REM.records.push({path: 'orgs/pilot-squad.md', title: 'Pilot squad', category: 'orgs', parent: parent.path, unit_kind: 'team',
    people: ['people/mara-ostrowski.md'], text: '# Pilot squad\n\nThe team that runs the pilot.\n'});
  orgTable.open = null;
  location.hash = 'c=orgs';
}'''


def _visible(page, selector):
    return page.locator(selector).first.is_visible()


def test_today_at_rest_keeps_the_lists_and_approve_all_behind_page_more(reader):
    page, _ = reader
    for selector in ("#approve-all", ".snapshot-line", ".night-done", "#processing", ".recall-toggle"):
        assert not page.locator(selector).first.is_visible(), selector
    assert page.locator("details#night > summary").is_visible()
    page.locator(".brief-header .d-more-btn").click()
    menu = page.locator(".brief-header .d-pop[role=menu]")
    assert menu.locator("a[href='#reviews=1']").is_visible()
    assert menu.locator(".snapshot-line").is_visible()
    menu.get_by_role("menuitem", name="Keyboard shortcuts").click()
    assert page.locator("dialog#shortcuts").is_visible()


def test_the_overnight_fold_holds_what_rem_did_and_the_rarer_lists(reader):
    page, _ = reader
    page.locator("details#night > summary").click()
    assert _visible(page, "#night .d-night-body")
    assert page.locator("#night #processing").count() == 1 and page.locator("#night details.maint").count() == 1


def test_a_lane_brings_that_persons_card_forward(reader):
    page, _ = reader
    lanes = page.locator(".fuse .lane")
    if lanes.count() < 2:
        pytest.skip("the fixture has one person waiting")
    second = lanes.nth(1).get_attribute("data-path")
    lanes.nth(1).locator("button.who").click()
    assert page.locator(".qcard.focal").get_attribute("data-path") == second
    assert page.locator(".fuse .lane.current").get_attribute("data-path") == second


def test_item_actions_arrive_on_hover_and_expand_opens_the_context(reader):
    page, _ = reader
    item = page.locator(".qcard.focal .qitem").first
    acts = item.locator(".d-acts")
    assert acts.evaluate("node => getComputedStyle(node).opacity") == "0"
    item.hover()
    page.wait_for_function("node => getComputedStyle(node).opacity === '1'", arg=acts.element_handle())
    expand = item.locator(".d-expand")
    expand.click()
    assert expand.get_attribute("aria-expanded") == "true"
    assert item.locator(".qmore").is_visible()


def test_the_letter_keeps_send_at_rest_and_says_what_an_empty_send_needs(reader):
    page, _ = reader
    page.evaluate(r'''() => {
      REM.live = true;
      const card = replyDraftCard({id: 'fern-demo', provider: 'gmail', to: 'fern@example.test', from: 'owner@example.test',
        subject: 'Demo', body: 'Hello Fern. 【需要你：演示时间 — date not agreed】', gist: '约演示时间。', why: 'Fern asked twice.'});
      document.getElementById('main').prepend(card);
    }''', isolated_context=False)
    card = page.locator("section.mailcard").first
    assert not card.locator(".choose-hint").is_visible()
    assert not card.locator(".mail-why").is_visible() and not card.locator(".mail-gist").is_visible()
    card.locator(".btn-act").click()
    assert card.locator(".choose-hint").is_visible()
    assert page.evaluate("document.activeElement.matches('.mail-choices input')", isolated_context=False)
    card.locator(".mail-actions .d-more-btn").click()
    card.get_by_role("menuitem", name="Why this reply").click()
    assert card.locator(".mail-why").is_visible()
    card.locator(".mail-actions .d-more-btn").click()
    card.get_by_role("menuitem", name="In your words").click()
    assert card.locator(".mail-gist").is_visible()
    card.locator(".mail-actions .d-more-btn").click()
    assert card.get_by_role("menuitem", name="Reply with Lark").is_visible()


def test_rail_more_and_settings_hold_the_rarer_rooms_and_preferences(reader):
    page, _ = reader
    assert not page.locator("#nav a[href='#view=changes']").is_visible()
    page.locator("#nav-more-btn").click()
    assert page.locator("#nav a[href='#view=changes']").is_visible()
    assert not page.locator("#privacy-toggle").is_visible()
    page.locator("#settings-btn").click()
    assert page.locator(".rail .language-switch").is_visible() and page.locator(".rail .theme-switch[role=radiogroup]").is_visible()
    page.locator(".rail .theme-switch [role=radio]").filter(has_text="Dark").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.locator(".search .kbd").click()
    assert page.locator("dialog#palette").is_visible()


def test_orgs_list_is_a_hierarchy_that_opens_closes_sorts_and_walks_by_keys(reader):
    page, _ = reader
    page.evaluate(UNIT, isolated_context=False)
    parent = page.locator("#org-rows .d-tr[aria-level='1']").filter(has_text="Fernhill Labs")
    assert parent.get_attribute("aria-expanded") == "true"  # the top level shows its units on the first visit
    assert page.locator("#org-rows .d-tr[aria-level='2']").filter(has_text="Pilot squad").count() == 1
    parent.locator(".d-tog").click()
    assert page.locator("#org-rows .d-tr[aria-level='2']").count() == 0
    page.locator("#org-rows .d-tr").filter(has_text="Fernhill Labs").locator(".d-oname").focus()
    page.keyboard.press("ArrowRight")
    assert page.locator("#org-rows .d-tr[aria-level='2']").count() == 1
    page.locator(".d-sort[data-sort=name]").click()
    assert page.locator(".d-th [aria-sort=ascending] .d-sort").inner_text() == "Organisation"
    page.locator(".ov-list .d-head .d-more-btn").click()
    page.get_by_role("menuitem", name="Collapse all").click()
    assert page.locator("#org-rows .d-tr[aria-level='2']").count() == 0


def test_an_org_row_says_its_newest_contact_from_its_people(reader):
    page, _ = reader
    page.evaluate(UNIT, isolated_context=False)
    shown = page.locator("#org-rows .d-tr").filter(has_text="Fernhill Labs").locator(".d-c-when").inner_text()
    newest = page.evaluate('''() => { const r = byPath('orgs/fernhill-labs.md');
      return fmtDate([known(r).last, ...orgMembers(r).map(orgLast)].filter(Boolean).sort().at(-1)); }''', isolated_context=False)
    assert shown == newest


def test_person_record_keeps_open_topics_in_today_and_quotes_one_click_away(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.locator(".r4-name").wait_for()
    assert page.locator(".r4-topics.d-todo-link a[href='#view=open']").count() == page.locator(".r4-topics").count()
    assert page.locator(".r4-topics li").count() == 0
    note = page.locator(".r4-fuse .fuse-note")
    if note.count():
        assert not note.is_visible()
        page.locator(".r4-fuse").hover()
        assert note.is_visible()
    later = page.locator(".r4-said li.later")
    if later.count():
        assert not later.first.is_visible()
        page.locator(".r4-said .d-showall").click()
        assert later.first.is_visible()


def test_org_record_folds_the_outline_and_says_one_line_name(reader):
    page, uri = reader
    page.goto(uri + "#r=orgs%2Ffernhill-labs.md")
    page.locator(".ov-say .ov-name").wait_for()
    outline = page.locator("details.ov-structure")
    assert outline.count() == 1 and outline.get_attribute("open") is None
    outline.locator("summary").click()
    assert page.locator(".ov-structure .ov-m").first.is_visible()
    assert not page.locator(".ov-legend").is_visible()
    page.locator(".ov-xray").hover()
    assert page.locator(".ov-legend").is_visible()

"""Today in a real browser: one card per person, keyboard-first, and the ⌘K palette (opt in)."""
import os

import pytest

from tests.e2e.cli.test_rem_reader_design_browser import reader  # noqa: F401  (fixture)
from tests.e2e.cli.test_rem_today_fuse_browser import OVERDUE, today  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

TWO_ASKS = r'''async () => {
  REM.as_of = '2026-10-20T12:00:00Z';
  const r = byPath('people/mara-ostrowski.md');
  r.original = undefined;
  r.text = r.text.replace(/(^## Open threads[^\n]*\n)/mi,
    '$1- You owe Mara a review of the budget forecast; due 2026-10-18 [4].\n- You owe Mara an access decision; due 2026-10-21 [4].\n');
  KNOWN.clear(); FACTS.clear(); await refreshTodayQueue(); render();
}'''


def _cards(page):
    return page.locator('#main .qcard')


def test_today_is_one_card_per_person_with_one_green_action(reader):
    page, _ = reader
    page.evaluate(TWO_ASKS, isolated_context=False)
    paths = _cards(page).evaluate_all('cards => cards.map(card => card.dataset.path)')
    assert paths and len(paths) == len(set(paths))
    mara = page.locator('.qcard[data-path="people/mara-ostrowski.md"]')
    assert mara.locator('.qitem').count() >= 2
    # Ranking stays Python's: the person's card sits where their first row was ranked.
    first = page.evaluate('todayGroups(threadEntries().filter(e => !isDone(e)))[0].r.path', isolated_context=False)
    assert paths[0] == first
    visible_green = page.evaluate('''() => [...document.querySelectorAll('#main button, #main a')]
      .filter(node => node.getClientRects().length && /rgb\\((34, 210, 122|59, 227, 143)\\)/.test(getComputedStyle(node).backgroundColor)).length''', isolated_context=False)
    # One primary per card (sprint 14): green, or the row's lead in bold where the card has no green step.
    lead = page.locator('#main .qcard.focal .strip-lead').evaluate_all('nodes => nodes.filter(node => node.getClientRects().length).length')
    assert visible_green + lead == 1
    assert page.locator('.night-card .count-words').inner_text().endswith('waiting on you')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth', isolated_context=False)


def test_today_keys_move_close_undo_and_never_steal_typing(reader):
    page, _ = reader
    page.evaluate(TWO_ASKS, isolated_context=False)
    count = _cards(page).count()
    assert count >= 2
    # N3: J/K deal the next or previous card onto the desk, in the faces' order; E closes the raised one.
    raised = 'document.querySelector("#main .qcard.focal")?.dataset.path || null'
    faces = page.locator('.deal').evaluate_all('faces => faces.map(face => face.dataset.path)')
    start = page.evaluate(raised, isolated_context=False)
    at = faces.index(start)
    page.locator('body').press('j')
    assert page.evaluate(raised, isolated_context=False) == faces[(at + 1) % len(faces)]
    page.keyboard.press('k')
    assert page.evaluate(raised, isolated_context=False) == start
    page.keyboard.press('e')
    page.locator('#done-notice').wait_for()
    assert page.locator(f'.qcard[data-path="{start}"]').count() == 0
    assert page.evaluate(raised, isolated_context=False) not in (None, start)
    page.locator('#done-notice').get_by_role('button', name='Undo', exact=True).click()
    page.locator(f'.qcard[data-path="{start}"]').wait_for()
    page.keyboard.press('?')
    sheet = page.locator('#shortcuts')
    assert sheet.is_visible() and 'Mark done' in sheet.inner_text()
    page.keyboard.press('j')  # a dialog is open: Today keys are inert
    page.keyboard.press('Escape')
    # Escape closes the sheet at once; its node leaves in the "close" event a task later, so wait for that.
    assert not page.evaluate('!!document.querySelector("#shortcuts")?.open', isolated_context=False)
    sheet.wait_for(state='detached')
    page.locator('#q').focus()
    page.keyboard.type('jk?')
    assert page.locator('#q').input_value() == 'jk?'
    assert page.locator('#shortcuts').count() == 0


@pytest.mark.parametrize('chord', ['Meta+k', 'Control+k'])
def test_palette_searches_runs_actions_and_remembers(reader, chord):
    page, uri = reader
    page.evaluate(TWO_ASKS, isolated_context=False)
    page.keyboard.press(chord)
    palette = page.locator('#palette')
    assert palette.is_visible()
    page.keyboard.type('mark mara done')
    assert page.locator('#palette [aria-selected="true"]').inner_text().startswith('Mark Mara Ostrowski done')
    page.keyboard.press('Enter')
    page.locator('#done-notice').wait_for()
    assert page.locator('.qcard[data-path="people/mara-ostrowski.md"]').count() == 0
    page.keyboard.press(chord)
    page.keyboard.type('ines')
    page.keyboard.press('ArrowDown')
    page.keyboard.press('ArrowUp')
    assert 'Inès' in page.locator('#palette [aria-selected="true"]').inner_text()
    page.keyboard.press('Enter')
    page.wait_for_url('**#r=people%2F*')
    page.keyboard.press(chord)
    first = page.locator('#palette li[role="option"]').first
    assert 'Recent' in first.inner_text()
    page.keyboard.press('Escape')
    assert not page.evaluate('!!document.querySelector("#palette")?.open', isolated_context=False)
    palette.wait_for(state='detached')


def test_a_dialog_opens_again_before_the_closed_one_has_left(reader):
    """⌘K right after a pick or Esc did nothing: the closed palette was still in the page until its close event."""
    page, _ = reader
    for opener, id_ in (('openPalette', 'palette'), ('openShortcuts', 'shortcuts')):
        # One task: the first dialog's close event cannot have run yet.
        state = page.evaluate(f'''() => {{ {opener}(); document.getElementById("{id_}").close(); {opener}();
            const all = document.querySelectorAll("#{id_}");
            return [all.length, all[0].open]; }}''', isolated_context=False)
        assert state == [1, True], id_
        page.keyboard.press('Escape')
        page.locator(f'#{id_}').wait_for(state='detached')


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_palette_is_a_bottom_sheet_on_a_phone(reader, theme):
    page, _ = reader
    page.set_viewport_size({'width': 390, 'height': 844})
    page.emulate_media(color_scheme=theme, reduced_motion='reduce')
    page.evaluate('openPalette()', isolated_context=False)
    box = page.locator('#palette').bounding_box()
    assert abs(box['y'] + box['height'] - 844) <= 1 and box['width'] >= 389
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth', isolated_context=False)


def test_a_stray_e_never_closes_the_raised_card(reader):
    """Review of #2929: E marked the raised card done from anywhere on Today. It acts only with focus in that card."""
    page, _ = reader
    page.evaluate(TWO_ASKS, isolated_context=False)
    raised = page.locator('#main .qcard.focal').get_attribute('data-path')
    page.evaluate('document.activeElement.blur()', isolated_context=False)
    page.keyboard.press('e')
    page.wait_for_timeout(400)
    assert page.locator('#done-notice').count() == 0
    assert page.locator('#main .qcard.focal').get_attribute('data-path') == raised
    page.locator('#main .qcard.focal').focus()
    page.keyboard.press('e')
    page.locator('#done-notice').wait_for()


IN_RAISED = '!!document.activeElement.closest("#main .qcard.focal")'


def test_a_card_dealt_from_the_palette_keeps_the_focus(reader):
    """Review of #2929: the palette put the focus back where it was before it opened (here a face in the deck's
    row), after the command had already moved it to the card it dealt, so the next E did nothing. Closing
    without a command still returns it."""
    page, _ = reader
    page.evaluate(TWO_ASKS, isolated_context=False)
    raised = page.locator('#main .qcard.focal').get_attribute('data-path')
    other = next(path for path in page.locator('.deal').evaluate_all('faces => faces.map(face => face.dataset.path)') if path != raised)
    # Dealing is what is under test; what the reply step then opens (a writer, a mail app) is not.
    name = page.evaluate("""path => { document.querySelector('.qcard[data-path="' + path + '"]').reply = () => {};
      return threadWho(byPath(path)); }""", other, isolated_context=False)
    page.locator(f'.deal[data-path="{raised}"]').focus()
    page.keyboard.press('Control+k')
    page.keyboard.press('Escape')
    page.locator('#palette').wait_for(state='detached')
    assert page.evaluate('document.activeElement.dataset.path', isolated_context=False) == raised
    assert page.evaluate('document.activeElement.matches(".deal")', isolated_context=False)
    page.keyboard.press('Control+k')
    page.keyboard.type('draft a reply to ' + name)
    assert page.locator('#palette [aria-selected="true"]').inner_text().startswith('Draft a reply to ' + name)
    page.keyboard.press('Enter')
    page.locator('#palette').wait_for(state='detached')
    assert page.locator('#main .qcard.focal').get_attribute('data-path') == other
    assert page.evaluate(IN_RAISED, isolated_context=False)


def test_j_steps_through_the_cards_in_the_page_when_the_notebook_moved_on(reader):
    """Review of #2929: J, K and S stepped through the people worked out from the data. When someone new was
    waiting and the page had not drawn them yet (a redraw waits while you type), the step named a card that was
    not there and nothing moved again."""
    page, _ = reader
    page.evaluate(TWO_ASKS, isolated_context=False)
    cards = _cards(page).evaluate_all('cards => cards.map(card => card.dataset.path)')
    assert len(cards) >= 2 and 'people/tomas-reyes.md' not in cards
    page.evaluate(r'''async () => {
      const r = byPath('people/tomas-reyes.md');
      r.original = undefined;
      r.text = r.text.replace(/(^## Open threads[^\n]*\n)[^\n]*/mi, '$1- You owe Tomas the abstract; due 2026-10-18 [2].');
      KNOWN.clear(); FACTS.clear(); await refreshTodayQueue();
    }''', isolated_context=False)
    waiting = page.evaluate('todayGroups(threadEntries().filter(e => !isDone(e))).map(group => group.r.path)', isolated_context=False)
    assert 'people/tomas-reyes.md' in waiting and _cards(page).count() == len(cards)  # in the data, not in the page
    raised = 'document.querySelector("#main .qcard.focal").dataset.path'
    seen = []
    for _ in cards:
        page.keyboard.press('j')
        seen.append(page.evaluate(raised, isolated_context=False))
    assert seen == cards[1:] + cards[:1]


def test_the_readers_own_reduce_motion_closes_a_card_without_the_wait(reader):
    """Review of #2929: only the system's setting skipped the wait for the leaving card; the reader's own
    Reduce motion switch, which already stills the animation, did not."""
    page, _ = reader
    page.emulate_media(reduced_motion='no-preference')
    page.evaluate(TWO_ASKS, isolated_context=False)
    page.evaluate("""() => { document.documentElement.classList.add('calm'); window.waits = [];
      const timer = window.setTimeout;
      window.setTimeout = (run, wait, ...rest) => { window.waits.push(wait); return timer(run, wait, ...rest); }; }""", isolated_context=False)
    page.locator('#main .qcard.focal').focus()
    page.keyboard.press('e')
    page.locator('#done-notice').wait_for()
    waits = page.evaluate('window.waits', isolated_context=False)
    assert 0 in waits and 240 not in waits, waits


def _live_deck(today):
    """Today served by a Host that answers a save with the decision it kept (threads.set_state), with the
    leave in motion and the focus in the raised card."""
    page, calls, answers = today
    answers["/rem/thread"] = lambda body: (200, {"state": body["state"], "at": "2026-10-08T12:00:00+00:00", "device": body["device"], "keys": body["keys"]})
    page.emulate_media(reduced_motion='no-preference')  # the leaving card takes its 240ms
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate('() => { REM.live = true; render(); }', isolated_context=False)
    assert _cards(page).count() >= 3
    page.locator('#main .qcard.focal').focus()
    return page, lambda: [body for path, body in calls if path == '/rem/thread'], _cards(page).count()


def _one_card_closed_and_saved_once(page, saves, count, raised):
    page.locator(f'.qcard[data-path="{raised}"]').wait_for(state='detached')
    page.wait_for_timeout(700)  # past the leave of any card a further E would have closed
    page.evaluate('threadWrite', isolated_context=False)
    assert _cards(page).count() == count - 1
    assert [body['state'] for body in saves()] == ['done']


def test_a_held_e_closes_one_card_and_saves_it_once(today):
    """Review of #2929: a held E repeated, and every repeat closed another card while Undo brings back only the
    last one. A held key is one press: one card closed, one save sent to the Host."""
    page, saves, count = _live_deck(today)
    raised = page.locator('#main .qcard.focal').get_attribute('data-path')
    for _ in range(12):  # every down after the first is the keyboard's own repeat
        page.keyboard.down('e')
        page.wait_for_timeout(60)
    page.keyboard.up('e')
    _one_card_closed_and_saved_once(page, saves, count, raised)


def test_e_again_while_the_card_is_leaving_closes_it_once(today):
    """Review of #2929: a second E while the card was still sliding away closed it again: two timers and two
    saves for one card. The presses are sent from the page so both land inside the 240ms leave."""
    page, saves, count = _live_deck(today)
    raised = page.locator('#main .qcard.focal').get_attribute('data-path')
    page.evaluate("""() => { for (const press of [1, 2])
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {key: 'e', bubbles: true, cancelable: true})); }""", isolated_context=False)
    _one_card_closed_and_saved_once(page, saves, count, raised)

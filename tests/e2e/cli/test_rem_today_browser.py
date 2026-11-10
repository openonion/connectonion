"""Today in a real browser: one card per person, keyboard-first, and the ⌘K palette (opt in)."""
import os

import pytest

from tests.e2e.cli.test_rem_reader_design_browser import reader  # noqa: F401  (fixture)

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
    assert visible_green == 1
    assert page.locator('.night-card .count-line').inner_text().endswith('waiting on you')
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
    assert page.locator('#shortcuts').count() == 0
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
    assert page.locator('#palette').count() == 0


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_palette_is_a_bottom_sheet_on_a_phone(reader, theme):
    page, _ = reader
    page.set_viewport_size({'width': 390, 'height': 844})
    page.emulate_media(color_scheme=theme, reduced_motion='reduce')
    page.evaluate('openPalette()', isolated_context=False)
    box = page.locator('#palette').bounding_box()
    assert abs(box['y'] + box['height'] - 844) <= 1 and box['width'] >= 389
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth', isolated_context=False)

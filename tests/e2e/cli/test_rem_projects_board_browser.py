"""Projects read like the clearest project tools (#2993, refs #2841): the directory opens on a board
by state, and a project page leads with its state. Since #3096 a card and a record hold what is known
(a sentence, the weeks, the last date); the next steps and who holds them are Today's.

Owner, 2026-11-13: «项目页面：里面的内容让人觉得 overwhelm。整个项目的设计没有像 Asana 或者其他一些工具那样足够清晰。»
and «不要写字告诉我，要让我通过 UI 之类就能一目了然地判断出来»: the layout carries the meaning, so these
tests read what is on the first screen (inner_text) rather than any sentence explaining it.
"""

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_reader_design_browser import PROJECT_SET, reader  # noqa: E402,F401

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)


def _open(reader, hash_, width):
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1440 else 844})
    page.goto(uri + hash_)
    page.evaluate(PROJECT_SET, isolated_context=False)
    return page


def _column(page, name):
    return page.locator(".pd-colm").filter(has=page.locator("h2 > span", has_text=name))


@pytest.mark.parametrize("width", [1440, 390])
def test_projects_open_on_a_board_by_state_and_a_card_says_what_the_project_is(reader, width):
    from patchright.sync_api import expect

    page = _open(reader, "#c=projects", width)
    expect(page.locator(".pd")).to_have_attribute("data-view", "board")
    expect(page.locator(".pd-colm h2 > span")).to_have_text(["Active", "Waiting", "Quiet", "Done"])
    # Each column says how many it holds; the board needs no sentence above it.
    main = page.locator("#main").inner_text()
    assert "projects on record" not in main and "The board's axis is a question" not in main
    assert page.locator(".pd-lede").count() == 0
    active, waiting = _column(page, "Active"), _column(page, "Waiting")
    # The owner owes a step: active, and a promise past its date is red on the card.
    capstone = active.locator('.pd-card[data-path="projects/capstone-review.md"]')
    expect(capstone).to_have_class(re.compile(r"\blate\b"))
    expect(capstone.locator(".pd-card-when .red")).to_have_text("14 days late")
    fernhill = active.locator('.pd-card[data-path="projects/fernhill-pilot.md"]')
    expect(fernhill.locator(".pa-say")).to_have_text("A paid pilot of the weekly brief for Fernhill Labs.")
    # Only someone else or an agent holds the next step: waiting. The step itself is Today's, not the card's (#3096).
    expect(waiting.locator('.pd-card[data-path="projects/waiting-room.md"]')).to_have_count(1)
    expect(waiting.locator('.pd-card[data-path="projects/agent-only.md"]')).to_have_count(1)
    assert page.locator(".pd-step, .pd-owner").count() == 0
    expect(_column(page, "Done").locator(".pd-card")).to_contain_text(["Spring workshop"])
    # Every card carries its last activity.
    expect(fernhill.locator(".pd-when")).not_to_have_text("")
    # Quiet folds past six cards and opens in place.
    quiet = _column(page, "Quiet")
    hidden = quiet.locator(".pd-card").count()
    quiet.get_by_role("button").click()
    assert _column(page, "Quiet").locator(".pd-card").count() > hidden
    assert _column(page, "Quiet").locator('.pd-card[data-path="projects/harbour-copy.md"]').count() == 1
    if width == 390:  # stacked columns, never sideways
        xs = page.evaluate("[...document.querySelectorAll('.pd-colm')].map(n => Math.round(n.getBoundingClientRect().left))",
                           isolated_context=False)
        assert len(set(xs)) == 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.evaluate("setInterfaceLanguage('zh')", isolated_context=False)
    expect(page.locator(".pd-colm h2 > span")).to_have_text(["进行中", "等待", "安静", "完成"])


@pytest.mark.parametrize("width", [1440, 390])
def test_a_project_page_leads_with_state_what_it_is_its_weeks_and_sessions_and_folds_the_rest(reader, width):
    page = _open(reader, "#r=projects%2Ffernhill-pilot.md", width)
    page.evaluate("""() => {
      const base = {category: 'sessions', session_project: 'projects/fernhill-pilot.md', session_tags: ['pilot'], session_turns: 1, text: ''};
      ['2026-09-20', '2026-09-24', '2026-09-26', '2026-09-28'].forEach((day, i) => REM.records.push({...base,
        path: 'sessions/' + day + '-fernhill.md', title: 'Pilot session ' + (i + 1), session_date: day}));
      render();
    }""", isolated_context=False)
    state = page.locator(".project-state")
    assert state.inner_text().startswith("Active")
    what, weeks, recent = page.locator(".project-what"), page.locator(".project-weeks"), page.locator(".project-recent")
    assert what.inner_text() == "A paid pilot of the weekly brief for Fernhill Labs."
    assert recent.locator("li a").all_inner_texts() == ["Pilot session 4", "Pilot session 3", "Pilot session 2", "Pilot session 1"]
    # One order: state, what it is, its weeks, its sessions. No step rows: open work is Today's (#3096).
    tops = [box["y"] for box in (state.bounding_box(), what.bounding_box(), weeks.bounding_box(), recent.locator("li").first.bounding_box())]
    assert tops == sorted(tops), tops
    assert page.locator(".next-exchanges, .project-step").count() == 0
    # Everything else is in Full memory under the lead, never beside it; Full memory is open on arrival (#3104).
    for selector in (".focus-facts", ".related-records", ".project-context", ".project-sessions"):
        assert all(node.evaluate("n => !!n.closest('.deep-note')") for node in page.locator(selector).all()), selector
    assert page.locator("details.deep-note").get_attribute("open") is not None
    assert page.locator(".deep-note .related-records").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_full_size_board_renders_in_one_second_and_opens_project_and_citation(reader, width):
    from patchright.sync_api import expect

    page = _open(reader, "#c=projects", width)
    elapsed = page.evaluate("""() => {
      const sample = byPath('projects/fernhill-pilot.md');
      // The synthetic project must carry a retained source, not just a source definition.
      REM.source_context['codex:fernhill-pilot'] = {source: 'codex',
        time: '2026-09-28T10:00:00Z', excerpt: 'Project notes: You owe Mara the weekly chart report.'};
      REM.records = REM.records.filter(r => r.category !== 'projects');
      for (let i = 0; i < 500; i++) REM.records.push({...sample, path: 'projects/pilot-' + i + '.md',
        title: 'Pilot ' + i, score: 0, relations: [], health: 'on_track'});
      KNOWN.clear(); FACTS.clear();
      const start = performance.now(); render();
      document.querySelector('.pd').getBoundingClientRect();
      return performance.now() - start;
    }""", isolated_context=False)
    assert elapsed < 1000, f"500 projects took {elapsed:.0f} ms"
    expect(page.locator('.pd-count')).to_have_text('500')
    expect(page.locator('.pd-state-col[data-state="active"] h2 small')).to_have_text('500')
    page.locator('.pd-state-col[data-state="active"]').get_by_role('button').click()
    expect(page.locator('.pd-state-card')).to_have_count(500)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator('.pd-state-card .pd-card-name').first.click()
    expect(page.locator('.project-state')).to_contain_text('Active')
    expect(page.locator('.project-what')).to_have_text('A paid pilot of the weekly brief for Fernhill Labs.')
    # The steps are in the full memory as written (open on arrival, #3104), and a citation there still opens its evidence.
    page.locator('.deep-note .person-threads a.cite').first.click()
    expect(page.locator('#evidence-panel')).to_be_visible()
    expect(page.locator('#evidence-panel')).to_contain_text('Project notes: You owe Mara the weekly chart report.')


@pytest.mark.parametrize("width", [1440, 390])
def test_board_switch_clears_column_headers_and_empty_states_keep_only_a_narrow_header(reader, width):
    from patchright.sync_api import expect

    page = _open(reader, "#c=projects", width)
    # Use the owner's interface language and an empty Done state, as in the reported screenshot.
    page.evaluate("""() => {
      REM.records = REM.records.filter(r => r.category !== 'projects' || projectState(r) !== 'done');
      KNOWN.clear(); FACTS.clear(); setInterfaceLanguage('zh');
    }""", isolated_context=False)
    switch = page.locator('.pd-asks').bounding_box()
    for heading in page.locator('.pd-colm h2').all():
        box = heading.bounding_box()
        assert (switch['y'] + switch['height'] <= box['y'] or
                box['y'] + box['height'] <= switch['y'] or
                switch['x'] + switch['width'] <= box['x'] or
                box['x'] + box['width'] <= switch['x']), (switch, box)
    done = page.locator('.pd-state-col[data-state="done"]')
    expect(done.locator('h2')).to_contain_text('完成')
    expect(done.locator('h2 small')).to_have_text('0')
    expect(done.locator('.pd-card')).to_have_count(0)
    if width == 1440:
        active = page.locator('.pd-state-col[data-state="active"]')
        assert done.bounding_box()['width'] <= 100
        assert active.bounding_box()['width'] > done.bounding_box()['width'] * 2
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

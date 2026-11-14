"""Projects read like the clearest project tools (#2993, refs #2841): the directory opens on a board
by state, and a project page leads with its state, the next steps and who holds each one.

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
def test_projects_open_on_a_board_by_state_with_the_next_step_and_who_holds_it(reader, width):
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
    expect(capstone.locator(".pd-step-who")).to_contain_text("14 days late")
    fernhill = active.locator('.pd-card[data-path="projects/fernhill-pilot.md"]')
    expect(fernhill.locator(".pd-step-what")).to_have_text("You owe Mara the weekly chart report")
    expect(fernhill.locator(".pd-owner")).to_have_text("You owe")
    # Only someone else or an agent holds the next step: waiting, and the card names who.
    quinn = page.evaluate("byPath('people/quinn-alder.md').title", isolated_context=False)
    room = waiting.locator('.pd-card[data-path="projects/waiting-room.md"]')
    expect(room.locator(".pd-step-what")).to_have_text("Waiting on Quinn for the contract")
    expect(room.locator(".pd-owner")).to_have_text(quinn)
    expect(waiting.locator('.pd-card[data-path="projects/agent-only.md"] .pd-owner')).to_have_text("Agent")
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
def test_a_project_page_leads_with_state_next_steps_and_recent_sessions_and_folds_the_rest(reader, width):
    page = _open(reader, "#r=projects%2Ffernhill-pilot.md", width)
    page.evaluate("""() => {
      const base = {category: 'sessions', session_project: 'projects/fernhill-pilot.md', session_tags: ['pilot'], session_turns: 1, text: ''};
      ['2026-09-20', '2026-09-24', '2026-09-26', '2026-09-28'].forEach((day, i) => REM.records.push({...base,
        path: 'sessions/' + day + '-fernhill.md', title: 'Pilot session ' + (i + 1), session_date: day}));
      render();
    }""", isolated_context=False)
    height = page.viewport_size["height"]
    state = page.locator(".project-state")
    assert state.inner_text().startswith("Active")
    steps = page.locator(".next-exchanges .thread")
    assert steps.locator(".dir").all_inner_texts() == ["You owe", "You owe", "Agent"]
    assert steps.first.locator(".what").inner_text().startswith("You owe Mara the weekly chart report")
    recent = page.locator(".project-recent")
    assert recent.locator("li a").all_inner_texts() == ["Pilot session 4", "Pilot session 3", "Pilot session 2"]
    # One order: state, then next steps, then recent sessions, and all of it on the first screen.
    tops = [box["y"] for box in (state.bounding_box(), steps.first.bounding_box(), recent.locator("li").first.bounding_box())]
    assert tops == sorted(tops) and tops[-1] < height, tops
    # Everything else is one fold away, never beside the lead.
    for selector in (".focus-facts", ".related-records", ".project-workspace", ".project-sessions"):
        assert all(not node.is_visible() for node in page.locator(selector).all()), selector
    page.locator("details.deep-note > summary").click()
    assert page.locator(".deep-note .related-records").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

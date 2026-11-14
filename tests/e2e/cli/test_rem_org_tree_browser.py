"""An organisation reads as a tree (issue #2992), in a real browser (opt in).

Owner, 2026-11-13: «Organization 页面：那应该是一个树状图吧» — the radial picture of
units and people read as scattered dots. The page now draws the organisation as an
indented tree, org → units → people, most active branch first, each level collapsible
from the keyboard; the list folds units into the organisation they belong to and shows
each organisation's shape as a small icicle. Fernhill University is invented
(tests/fixtures/rem_org_tree_notebook.py): three branches, six squads, twelve people.
"""

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_reader_design_browser import org_reader  # noqa: E402,F401

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

TREE = ".ov-org-tree [role=tree]"


def _item(page, name, level):
    """The tree item at this level whose own row carries this name."""
    return page.locator(f"{TREE} [role=treeitem][aria-level='{level}']").filter(
        has=page.locator(":scope > .ov-trow .ov-tl1 > a, :scope > .ov-trow .ov-tl1 > b").filter(has_text=re.compile("^" + re.escape(name) + "$")))


def _row(item):
    return item.locator(":scope > .ov-trow")


def _count(item):
    return str(item.locator('[role=group] .ov-trow[data-kind=person]').count())


def _focused(page):
    return page.evaluate("document.activeElement.querySelector(':scope > .ov-trow')?.innerText || ''", isolated_context=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_org_page_tree_levels_and_counts_match_the_data(org_reader, width):
    page = org_reader(width, language="en")
    assert page.locator(".ov-xsvg, .ov-node").count() == 0, "the radial picture is gone"
    tree = page.locator(TREE)
    assert tree.is_visible()
    if width == 1440:  # beside the name, on the first screen
        assert tree.bounding_box()["y"] < 900
    root = _item(page, "Fernhill University", 1)
    assert root.get_attribute("aria-expanded") == "true"
    assert "You know 12 people here." in page.locator(".ov-opening").inner_text()
    assert _count(root) == "12" == str(page.evaluate("orgMembers(byPath('orgs/fernhill-university.md')).length", isolated_context=False))
    branches = [_row(item).locator("a, b").first.inner_text() for item in page.locator(f"{TREE} [aria-level='2']").all()]
    # The most active branch leads; people with no known unit are the last row, never a branch of their own.
    assert branches[0] == "Fieldwork studio" and set(branches[1:3]) == {"Founders programme", "Global office"}
    assert branches[3] == "Department not known yet"
    assert [_count(_item(page, name, 2)) for name in ("Fieldwork studio", "Founders programme", "Global office")] == ["8", "2", "1"]
    loose = _item(page, "Department not known yet", 2)
    assert _count(loose) == "1" and loose.get_attribute("aria-expanded") == "false"
    assert not loose.get_by_text("Petra Lund").is_visible()
    studio = _item(page, "Fieldwork studio", 2)
    under = [_row(item).inner_text().split("\n")[0] for item in studio.locator(":scope > [role=group] > [role=treeitem]").all()]
    assert len(under) == 7 and "Basil Thorne" in under[0] and sum("squad" in name for name in under) == 6
    osprey = _item(page, "Osprey squad", 3)
    assert _count(osprey) == "2"
    people = osprey.locator(":scope > [role=group] > [role=treeitem]").all_inner_texts()
    assert any("Ilse Marr" in text for text in people) and any("Theo Brand" in text for text in people)
    assert "Developer" in osprey.inner_text()
    assert _row(osprey).locator("a").get_attribute("href") == "#r=orgs%2Fteam-osprey.md"
    # Audit every recorded unit against the tree data, including nested/empty units.
    units = page.evaluate("""() => {
      const rows = [];
      const visit = (u, level) => { for (const child of u.units) {
        rows.push({name: child.name, level, count: unitPeople(child).length});
        visit(child, level + 1);
      }};
      visit(orgCurrent.tree, 2);
      return rows;
    }""", isolated_context=False)
    assert len(units) == 12
    for unit in units:
        item = _item(page, unit["name"], unit["level"])
        assert item.count() == 1 and _count(item) == str(unit["count"]), unit
    text = tree.inner_text()
    assert "undefined" not in text and "null" not in text
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_org_tree_expands_and_collapses_from_the_keyboard(org_reader):
    page = org_reader(1440, language="en")
    # One stop for Tab: the tree keeps a single focusable item (roving tabindex).
    assert page.locator(f"{TREE} [role=treeitem][tabindex='0']").count() == 1
    root = _item(page, "Fernhill University", 1)
    root.focus()
    page.keyboard.press("ArrowDown")
    assert "Fieldwork studio" in _focused(page)
    studio = _item(page, "Fieldwork studio", 2)
    kestrel = _row(_item(page, "Kestrel squad", 3))
    assert kestrel.is_visible()
    page.keyboard.press("ArrowLeft")
    assert studio.get_attribute("aria-expanded") == "false" and not kestrel.is_visible()
    page.keyboard.press("ArrowLeft")
    assert "Fernhill University" in _focused(page), "Left on a closed branch goes to its parent"
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowRight")
    assert studio.get_attribute("aria-expanded") == "true" and kestrel.is_visible()
    page.keyboard.press("ArrowRight")
    assert "Basil Thorne" in _focused(page), "Right on an open branch steps into its first child"
    page.keyboard.press("End")
    assert "Department not known yet" in _focused(page)
    page.keyboard.press(" ")
    assert page.get_by_text("Petra Lund").first.is_visible()
    assert page.locator(f"{TREE} [role=treeitem][tabindex='0']").count() == 1
    # A mouse click on the row toggles too; the name is a link.
    _row(studio).locator(".ov-twisty").click()
    assert studio.get_attribute("aria-expanded") == "false"
    page.keyboard.press("Home")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_function("location.hash === '#r=orgs%2Ffieldwork-studio.md'")
    page.locator(f"{TREE} [aria-level='1']").filter(has_text="Fieldwork studio").wait_for()
    assert _count(_item(page, "Fieldwork studio", 1)) == "8"


@pytest.mark.parametrize("width", [1440, 390])
def test_org_list_folds_units_into_their_organisation_and_expands_indented_rows(org_reader, width):
    page = org_reader(width, language="en")
    page.evaluate("() => { location.hash = 'c=orgs'; }", isolated_context=False)
    page.locator(".ov-list .org-table-row").first.wait_for()
    tops = page.evaluate("inCategory('orgs').filter(r => !r.parent).length", isolated_context=False)
    assert page.locator(".ov-list h1").inner_text() == f"{tops} organisations"
    rows = page.locator(".ov-list .org-table-row")
    page.locator(".ov-more").evaluate_all("buttons => buttons.forEach(b => b.click())")
    assert rows.filter(has_text="Kestrel squad").count() == 0 and rows.filter(has_text="Fieldwork studio").count() == 0
    uni = rows.filter(has_text="Fernhill University")
    toggle = uni.locator('.org-disclosure')
    assert toggle.get_attribute('aria-expanded') == 'false'
    toggle.click()
    assert rows.filter(has_text='Fieldwork studio').count() == 1
    assert rows.filter(has_text='Fieldwork studio').locator('.org-table-name').evaluate('e => parseInt(e.style.paddingLeft)') == 18
    toggle.click()
    assert rows.filter(has_text='Fieldwork studio').count() == 0
    assert rows.filter(has_text="Fernhill Labs").locator('.org-disclosure').count() == 0
    # A unit's name still finds its organisation.
    page.locator(".org-directory .people-find").fill("Kestrel")
    assert rows.filter(has_text="Fernhill University").count() == 1
    unit = rows.filter(has_text="Kestrel squad")
    assert unit.count() == 1
    assert unit.locator('.org-table-name').evaluate('e => parseInt(e.style.paddingLeft)') > 0
    assert rows.filter(has_text="Fernhill Labs").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

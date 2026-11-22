"""Keys (#3137) in the reader (opt in): a list of what each secret is, a page per key, Copy and Show through the
Host on this computer only, and a snapshot that never shows a value. Served like test_rem_today_fuse_browser.py."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
SHOTS = Path("/private/tmp/claude-501/-Users-changxing-projects-connectonion/5e15bb44-2240-42c5-8595-673a9dbd14c9/scratchpad/pr-shots/rc31")
SECRET = "Tr0ub4dor&3-horse-Battery"
PAGE = ("# GitHub\n\n## Facts\n- Service: GitHub\n- Account: mara@example.test\n- Purpose: push to the pilot repo\n"
        "- Who else has it: Unknown\n- Used in: projects/pilot.md\n- Created: 2026-11-19\n- Rotated: Unknown\n- Expires: Unknown\n"
        "- Link: https://github.com/login\n- Vault: macOS Keychain (co-rem:github-mara-example-test)\n\n## Notes\nThe secret is in this Mac's Keychain.\n")


def _with_keys(page, width, live=True):
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate("""([text, live]) => {
      REM.live = live;
      REM.records.push({path: 'keys/github-mara-example-test.md', category: 'keys', title: 'GitHub', text, written: true},
                       {path: 'keys/stripe-billing.md', category: 'keys', title: 'Stripe', written: true,
                        text: '# Stripe\\n\\n## Facts\\n- Service: Stripe\\n- Account: billing\\n- Purpose: invoices\\n'});
      if (!REM.categories.includes('keys')) REM.categories.push('keys');
      window.copied = null;
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: text => { window.copied = text; return Promise.resolve(); } } });
      KNOWN.clear(); FACTS.clear(); location.hash = '#c=keys'; render();
    }""", [PAGE, live], isolated_context=False)


def _shot(page, name, width):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"keys-{name}-{width}.png"))


@pytest.mark.parametrize("width", [1440, 390])
def test_the_keys_list_says_what_each_secret_is_and_never_its_value(today, width):
    page, calls, answers = today
    _with_keys(page, width)
    assert page.locator(".rail a[href='#c=keys'], #nav a[href='#c=keys']").count() >= 1 or width < 400
    table = page.locator(".keys-sheet table")
    assert table.locator("tbody tr").count() == 2
    assert "push to the pilot repo" in table.inner_text() and SECRET not in page.content()
    page.locator(".key-adder > summary").click()
    answers["/rem/keys/add"] = lambda body: (200, {"page": "keys/notion-me.md"})
    form = page.locator(".key-add")
    form.locator("input[name=Service]").fill("Notion")
    form.locator("input[name=Account]").fill("me")
    form.locator("input[type=password]").fill(SECRET)
    _shot(page, "list", width)
    form.locator("button[type=submit]").click()
    page.locator(".key-status", has_text="Keychain").wait_for()
    assert calls[-1][0] == "/rem/keys/add" and calls[-1][1]["secret"] == SECRET
    assert form.locator("input[type=password]").input_value() == ""  # the value leaves the page once sent
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_a_key_page_copies_and_shows_through_the_host_and_forgets_the_value(today, width):
    page, calls, answers = today
    _with_keys(page, width)
    answers["/rem/keys/reveal"] = lambda body: (200, {"secret": SECRET})
    page.locator(".keys-sheet a", has_text="GitHub").click()
    head = page.locator(".key-page .page-head")
    head.wait_for()
    assert "mara@example.test" in page.locator(".key-facts").inner_text() and SECRET not in page.content()
    head.get_by_role("button", name="Copy").click()
    page.wait_for_function("window.copied !== null")
    assert page.evaluate("window.copied", isolated_context=False) == SECRET
    assert calls[-1] == ("/rem/keys/reveal", {"page": "keys/github-mara-example-test.md"})
    head.get_by_role("button", name="Show").click()
    page.locator(".key-value", has_text=SECRET).wait_for()
    _shot(page, "page", width)
    head.get_by_role("button", name="Hide").click()
    assert SECRET not in page.locator(".key-page").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_a_snapshot_shows_the_rows_and_says_where_the_value_is(today):
    page, calls, _ = today
    _with_keys(page, 390, live=False)
    assert page.locator(".key-adder").count() == 0
    assert "Keychain" in page.locator("#main").inner_text()
    page.locator(".keys-sheet a", has_text="GitHub").click()
    assert page.locator(".key-page .page-head button").count() == 0
    assert "Copy it from the reader on this Mac" in page.locator(".key-page").inner_text()
    _shot(page, "snapshot", 390)
    assert not [path for path, _ in calls if path.startswith("/rem/keys/")]


def _empty_keys(page, width=1440, live=True):
    page.set_viewport_size({"width": width, "height": 900})
    page.evaluate("""([live]) => {
      REM.live = live;
      REM.records = REM.records.filter(r => r.category !== 'keys');  // a notebook with no keys yet
      if (!REM.categories.includes('keys')) REM.categories.push('keys');
      KNOWN.clear(); FACTS.clear(); location.hash = '#c=keys'; render();
    }""", [live], isolated_context=False)


def test_the_import_buttons_are_visible_on_an_empty_keys_page(today):
    # P大 opened Keys with no keys and saw no button — they were hidden in a collapsed "Add a key" disclosure.
    page, calls, answers = today
    _empty_keys(page)
    adder = page.locator(".key-adder")
    assert adder.count() == 1
    assert adder.evaluate("el => el.open") is True  # open by default when there are no keys
    chrome = page.locator(".key-importers button", has_text="Chrome")
    assert chrome.is_visible()  # seen without clicking the summary
    # He wants to click, not type: the one-click importers lead, the manual form sits below them.
    chrome_y = chrome.bounding_box()["y"]
    form_y = page.locator(".key-add input[name=Service]").bounding_box()["y"]
    assert chrome_y < form_y, (chrome_y, form_y)
    assert page.locator(".key-import-primary").is_visible()
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / "keys-empty-open-1440.png"))


def test_the_adder_stays_collapsed_once_there_are_keys(today):
    # With keys present the adder is a quiet disclosure, not a nag: collapsed, import buttons hidden until asked for.
    page, calls, answers = today
    _with_keys(page, 1440)
    adder = page.locator(".key-adder")
    assert not adder.evaluate("el => el.open")  # collapsed by default
    assert not page.locator(".key-importers button", has_text="Chrome").is_visible()


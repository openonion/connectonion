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
    # P大 opened Keys with no keys and saw no button (#3287); then wanted ONE 一键导入 that offers the sources (#3305).
    page, calls, answers = today
    _empty_keys(page)
    adder = page.locator(".key-adder")
    assert adder.count() == 1
    assert adder.evaluate("el => el.open") is True  # open by default when there are no keys
    trigger = page.locator(".key-import-open")
    assert trigger.is_visible()  # seen without clicking the summary
    # He wants to click, not type: the one-click import leads, the manual form sits below it.
    assert trigger.bounding_box()["y"] < page.locator(".key-add input[name=Service]").bounding_box()["y"]
    assert page.locator(".key-import-primary").is_visible()
    assert not page.locator(".key-source", has_text="Chrome").is_visible()
    trigger.click()
    for name in ("Chrome", "Edge", "Brave"):
        assert page.locator(".key-source", has_text=name).is_visible()
    assert page.locator(".key-source[data-source=keychain]").is_visible()
    assert page.locator(".key-source[data-source=apple]").is_visible()
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / "keys-empty-open-1440.png"))


def test_the_adder_stays_collapsed_once_there_are_keys(today):
    # With keys present the adder is a quiet disclosure, not a nag: collapsed, import buttons hidden until asked for.
    page, calls, answers = today
    _with_keys(page, 1440)
    adder = page.locator(".key-adder")
    assert not adder.evaluate("el => el.open")  # collapsed by default
    assert not page.locator(".key-import-open").is_visible()



IMPORT_SHOTS = SHOTS.parent / "keys-import"


def _held_import(page):
    """hostPost for /rem/keys/import waits until the test answers, so the wait on the system prompt can be seen."""
    page.evaluate("""() => {
      const real = hostPost;
      window.importAnswer = null;
      hostPost = (url, body) => url !== '/rem/keys/import' ? real(url, body)
        : new Promise(resolve => { window.importBody = body; window.importAnswer = resolve; });
    }""", isolated_context=False)


def _import_shot(page, name, width):
    IMPORT_SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(IMPORT_SHOTS / f"{name}-{width}.png"))


@pytest.mark.parametrize("width", [1440, 390])
def test_choosing_chrome_shows_the_wait_on_the_keychain_prompt_then_what_was_imported(today, width):
    page, calls, answers = today
    _empty_keys(page, width)
    _held_import(page)
    page.locator(".key-import-open").click()
    page.locator(".key-source", has_text="Chrome").click()
    wait = page.locator(".key-import-wait")
    wait.wait_for()
    assert wait.is_visible() and wait.locator(".key-spin").count() == 1
    assert wait.locator("button").is_visible()  # a cancel
    assert page.evaluate("window.importBody", isolated_context=False) == {"source": "chrome"}
    _import_shot(page, "waiting", width)
    page.evaluate("window.importAnswer({ok: true, code: 200, filed: 3, skipped: 1, sites: ['bank.example.test', 'mail.example.test', 'nas.example.test']})",
                  isolated_context=False)
    result = page.locator(".key-import-result.ok")
    result.wait_for()
    assert "mail.example.test" in result.inner_text() and "null" not in result.inner_text() and not wait.is_visible()
    _import_shot(page, "imported", width)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_a_host_outside_the_login_session_says_so_prominently_with_the_one_fix(today, width):
    page, calls, answers = today
    _empty_keys(page, width)
    _held_import(page)
    page.locator(".key-import-open").click()
    page.locator(".key-source", has_text="Chrome").click()
    page.locator(".key-import-wait").wait_for()
    page.evaluate("window.importAnswer({ok: false, code: 409, reason: 'no_gui', error: 'outside your login session'})", isolated_context=False)
    error = page.locator(".key-import-result.error")
    error.wait_for()
    assert error.get_attribute("role") == "alert"
    assert error.locator(".key-import-fix").inner_text() == "co rem open"
    box = error.bounding_box()
    assert box["height"] >= 40 and box["width"] >= 200  # a block, not a one-line status he misses
    _import_shot(page, "no-session", width)


def test_cancel_returns_to_the_sources_and_a_late_answer_is_ignored(today):
    page, calls, answers = today
    _empty_keys(page)
    _held_import(page)
    page.locator(".key-import-open").click()
    page.locator(".key-source", has_text="Brave").click()
    page.locator(".key-import-wait button").click()
    assert page.locator(".key-source", has_text="Brave").is_visible() and not page.locator(".key-import-wait").is_visible()
    page.evaluate("window.importAnswer({ok: true, code: 200, filed: 1, skipped: 0, sites: ['x.example.test']})", isolated_context=False)
    page.wait_for_timeout(100)
    assert page.locator(".key-import-result.ok").count() == 0 or not page.locator(".key-import-result.ok").is_visible()


def test_apple_passwords_says_how_to_export_and_offers_the_file(today):
    page, calls, answers = today
    _empty_keys(page)
    page.locator(".key-import-open").click()
    page.locator(".key-source[data-source=apple]").click()
    panel = page.locator(".key-import-csv")
    panel.wait_for()
    assert panel.locator("input[type=file]").count() == 1
    assert calls == [] or all(c[0] != "/rem/keys/import" for c in calls)  # nothing is read by pretending
    _import_shot(page, "apple", 1440)


def test_cos_own_keys_env_names_are_listed_without_values(today):
    page, calls, answers = today
    answers["/rem/keys/env"] = lambda body: (200, {"where": "~/.co/keys.env", "names": ["OPENAI_API_KEY", "OPENONION_API_KEY"]})
    _with_keys(page, 1440)
    section = page.locator(".keys-env")
    section.wait_for()
    assert section.locator(".keys-env-name").all_inner_texts() == ["OPENAI_API_KEY", "OPENONION_API_KEY"]
    assert "~/.co/keys.env" in section.inner_text() and "null" not in section.inner_text()
    _import_shot(page, "keys-env", 1440)

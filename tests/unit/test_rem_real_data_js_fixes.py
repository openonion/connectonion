"""Red-first JS & interaction regression tests for real-data REM Reader fixes."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest

from connectonion.rem import reader as rem_reader
from connectonion.rem.files import Notebook

REAL_PW_BROWSERS = Path.home() / ".cache" / "ms-playwright"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from rem_reader_notebook import build as build_fixture_notebook  # noqa: E402


def _build_js_fixture(root: Path) -> None:
    build_fixture_notebook(root, datetime(2026, 11, 26, tzinfo=timezone.utc))
    book = Notebook(root)
    # Add a [sensitive] obligation with a verbatim quote to verify privacy redaction on #view=open
    book.write(
        "people/carolyn-tax.md",
        "# Carolyn Tax\n\nAuditor [1].\n\n## Facts\n- Email: carolyn@tax.example\n\n"
        "## Open threads\n- The user owes Carolyn Tax: respond to Question 1: "
        "“We intend to respond with the requested tax records by 9 December 2026.” (2026-11-20) [sensitive] [1] — due 2026-12-09.\n\n"
        "## Sources\n1. outlook:msg-carolyn-1\n",
    )
    book.write(
        "knowledge/dmg-order-workflow.md",
        "# DMG order workflow\n\n## Insight\n- Orders validate against v1.4 schema before dispatch [1].\n\n"
        "## Sources\n1. codex:sess-dmg:12\n",
    )
    book.write(
        "notes/unsw-founders.md",
        "# UNSW Founders\n\nCohort notes [1].\n\n## Open\n- Follow up on pitch deck — due 2026-11-28 [1].\n\n"
        "## Sources\n1. outlook:thread:abc\n",
    )
    book.write(
        "agenda/guest-stays.md",
        "# Guest inquiries\n\nAirbnb check-in schedule [1].\n\n## Open threads\n- Confirm check-in instructions — due 2026-11-27 [1].\n\n"
        "## Sources\n1. outlook:thread: stays-1\n",
    )
    book.write(
        "keys/openonion-chat.md",
        "# chat.openonion.ai\n\n## Facts\n- Service: chat.openonion.ai\n- Account: aaron@openonion.ai\n"
        "- Vault: macOS Keychain (co-rem:openonion-chat)\n\n## Notes\nShared staging login.\n",
    )
    # Add 130 stub contacts to test People pagination
    for idx in range(130):
        book.write(f"people/stub-{idx:03d}.md", f"# Stub Contact {idx:03d}\n")


def _launch_browser():
    from patchright.sync_api import sync_playwright

    if REAL_PW_BROWSERS.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(REAL_PW_BROWSERS))
    pw = sync_playwright().start()
    kwargs = {"headless": True}
    if Path("/opt/google/chrome/chrome").exists():
        kwargs["channel"] = "chrome"
    return pw, pw.chromium.launch(**kwargs)


@pytest.fixture(scope="module")
def js_browser(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rem_js_fixes")
    root = tmp / "rem"
    _build_js_fixture(root)
    html_path = tmp / "reader.html"
    html_path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    pw, browser = _launch_browser()
    try:
        yield browser, html_path
    finally:
        browser.close()
        pw.stop()


def _open(browser, html_path: Path, width: int = 1440, height: int = 900):
    ctx = browser.new_context(viewport={"width": width, "height": height}, locale="en-US")
    page = ctx.new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(html_path.as_uri())
    return ctx, page


def test_el_null_disabled_and_open_batch_and_detail_buttons(js_browser):
    browser, html_path = js_browser
    ctx, page = _open(browser, html_path)
    try:
        res = page.evaluate(
            """() => {
              REM.live = true;
              const btn = el('button', { disabled: null, 'aria-current': null, title: null, text: 'Click' });
              location.hash = '#view=open';
              render();
              document.querySelector('.bau-mode-btn').click();
              const boxes = [...document.querySelectorAll('.bau-open.multi .bau-selbox')];
              boxes.slice(0, 2).forEach(b => b.click());
              const batchBtns = [...document.querySelectorAll('.bau-batchbar .bau-bb-btn:not(.exit)')].filter(b => !b.textContent.includes('Codex'));
              const disabledNullCount = [...document.querySelectorAll('[disabled=\"null\"], [aria-current=\"null\"], [title=\"null\"]')].length;
              const batchEnabled = batchBtns.every(b => !b.disabled);

              openMultiMode = false;
              openSelected.clear();
              const entries = threadEntries().filter(e => waitingOnYou(e));
              location.hash = openHref({ item: doneKey(entries[1] || entries[0]) });
              render();
              const navBtns = [...document.querySelectorAll('.bau-detail .bau-dnav button, .bau-detail .agent-dock button')];
              const anyDetailNullDisabled = navBtns.some(b => b.getAttribute('disabled') === 'null');
              return {
                btnDisabled: btn.disabled,
                btnHasAria: btn.hasAttribute('aria-current'),
                disabledNullCount,
                batchCount: batchBtns.length,
                batchEnabled,
                anyDetailNullDisabled
              };
            }""",
            isolated_context=False,
        )
        assert res["btnDisabled"] is False and res["btnHasAria"] is False, res
        assert res["disabledNullCount"] == 0, res
        assert res["batchCount"] >= 4 and res["batchEnabled"] is True, res
        assert res["anyDetailNullDisabled"] is False, res
    finally:
        ctx.close()


def test_privacy_cover_and_public_redact_quotes_and_zombie_rows_in_open_view(js_browser):
    browser, html_path = js_browser
    ctx, page = _open(browser, html_path)
    try:
        res = page.evaluate(
            """() => {
              setPrivacy('cover');
              location.hash = '#view=open';
              render();
              const carolynEntry = threadEntries().find(e => e.r.path === 'people/carolyn-tax.md');
              const snipLeaksCover = [...document.querySelectorAll('.bau-snip')].some(
                n => n.textContent.includes('requested tax records') && !n.closest('.curtain') && !n.querySelector('.curtain')
              );
              location.hash = openHref({ item: doneKey(carolynEntry) });
              render();
              const hashHasSecret = decodeURIComponent(location.hash).includes('requested tax records');
              const qv = document.querySelector('.bau-qv');
              const qvLeaksCover = qv && qv.textContent.includes('requested tax records')
                && !qv.classList.contains('curtain') && !qv.querySelector('.curtain');

              setPrivacy('public');
              location.hash = '#view=open';
              render();
              const bodyPublic = document.getElementById('main').textContent;
              const emptyRowsPublic = [...document.querySelectorAll('.bau-row .what')].filter(w => !w.textContent.trim()).length;
              return { snipLeaksCover, hashHasSecret, qvLeaksCover, publicLeaks: bodyPublic.includes('requested tax records'), emptyRowsPublic };
            }""",
            isolated_context=False,
        )
        assert res["snipLeaksCover"] is False, res
        assert res["hashHasSecret"] is False, res
        assert res["qvLeaksCover"] is False, res
        assert res["publicLeaks"] is False, res
        assert res["emptyRowsPublic"] == 0, res
    finally:
        ctx.close()


def test_text_cleaning_preserves_pr_numbers_and_fixes_double_period(js_browser):
    browser, html_path = js_browser
    ctx, page = _open(browser, html_path)
    try:
        res = page.evaluate(
            """() => ({
              pr: plainLine('Review PR #58 and issue #1886 (90 of #2–#92 open) [1]'),
              heading: plainLine('## Heading title'),
              dblPeriod: cleanStitchedTitle(withoutDateClutter('Feedback: “I will send notes tomorrow.” (2026-11-02).', { since: '2026-11-02' })),
              rowJoin: rowWords('Check API: “Long quoted message over twenty four chars.” Next sentence starts here.'),
              emptyOutlook: threadUrl({ provider: 'outlook', source: '', thread: '' }, { mail: true, kind: 'outlook' })
            })""",
            isolated_context=False,
        )
        assert "#58" in res["pr"] and "#1886" in res["pr"] and "#2" in res["pr"], res
        assert res["heading"] == "Heading title", res
        assert not res["dblPeriod"].endswith('.”.'), res
        assert res["emptyOutlook"] is None, res
    finally:
        ctx.close()


def test_people_pagination_logs_notes_routing_agenda_dedup_and_palette_knowledge(js_browser):
    browser, html_path = js_browser
    ctx, page = _open(browser, html_path)
    try:
        res = page.evaluate(
            """() => {
              // 1. People pagination (> 100 contacts renders first page + Show more button)
              location.hash = '#c=people';
              render();
              const trCount = document.querySelectorAll('.people-table tbody tr').length;
              const moreBtn = !!document.querySelector('.people-more');

              // 2. #c=notes and #c=logs do not say 'No pages yet'
              location.hash = '#c=notes';
              render();
              const notesEmpty = document.getElementById('main').textContent.includes('No pages yet');

              // 3. Agenda record page does not duplicate Open threads twice, and keyPage renders ## Notes
              location.hash = '#r=agenda%2Fguest-stays.md';
              render();
              const agendaMatches = (document.getElementById('main').textContent.match(/Confirm check-in instructions/g) || []).length;

              location.hash = '#r=keys%2Fopenonion-chat.md';
              render();
              const keyHasNotes = document.getElementById('main').textContent.includes('Shared staging login');

              // 4. Command Palette includes knowledge/*.md pages and responds to ArrowDown on dialog
              const items = paletteItems();
              const hasDmgKnowledge = items.some(i => i.id === 'r:knowledge/dmg-order-workflow.md');

              return { trCount, moreBtn, notesEmpty, agendaMatches, keyHasNotes, hasDmgKnowledge };
            }""",
            isolated_context=False,
        )
        assert res["trCount"] <= 100 and res["moreBtn"] is True, res
        assert res["notesEmpty"] is False, res
        assert res["agendaMatches"] == 1, res
        assert res["keyHasNotes"] is True, res
        assert res["hasDmgKnowledge"] is True, res
    finally:
        ctx.close()

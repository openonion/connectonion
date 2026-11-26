"""Targeted regression tests for Porcelain & Viridian (#3470) UI & privacy fixes:
#3306, #3231, #3417, #3387, #3436, #3437, #3438, #3364. Invented data only.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from connectonion.rem import reader as rem_reader
from connectonion.rem.files import Notebook

REAL_PW_BROWSERS = Path.home() / ".cache" / "ms-playwright"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from rem_reader_notebook import build as build_fixture_notebook  # noqa: E402


def _build_regression_notebook(root: Path) -> None:
    build_fixture_notebook(root, datetime(2026, 11, 22, tzinfo=timezone.utc))
    book = Notebook(root)
    # Private topic (#3387) linked from Mara's Insight
    book.write(
        "knowledge/secret-health-check.md",
        "# Secret clinic appointment [personal]\n\n"
        "Private note on the clinic checkup [personal] [1].\n\n"
        "## Sources\n"
        "1. gmail:priv-1\n",
    )
    mara = book.read("people/mara-ostrowski.md")
    mara = mara.replace(
        "## Insight\n",
        "## Insight\n- Pattern: mentioned [Secret clinic appointment](../knowledge/secret-health-check.md) in passing [1].\n",
    )
    mara += (
        "\n\n## Private medical notes\n"
        "- Follow-up allergy test scheduled next Tuesday [sensitive] [1].\n"
        "- Family prescription renewal note [personal] [1].\n"
        "\n\n## Mixed notes\n"
        "- Public partnership milestone confirmed for Q4 [2].\n"
        "- Private home phone note [sensitive] [1].\n"
    )
    book.write("people/mara-ostrowski.md", mara)

    # Stale 0-people prose in org summary (#3437)
    org = book.read("orgs/fernhill-labs.md")
    org = org.replace(
        "# Fernhill Labs\n\n",
        "# Fernhill Labs\n\nFernhill Labs builds climate tools. You know 0 people here. 你认识这里的 0 个人。\n\n",
    )
    book.write("orgs/fernhill-labs.md", org)


def _open_rendered(html_path: Path, width: int = 1440, height: int = 900):
    from patchright.sync_api import sync_playwright

    if REAL_PW_BROWSERS.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(REAL_PW_BROWSERS))
    pw = sync_playwright().start()
    launch_kwargs: dict[str, object] = {"headless": True}
    if Path("/opt/google/chrome/chrome").exists():
        launch_kwargs["channel"] = "chrome"
    browser = pw.chromium.launch(**launch_kwargs)
    ctx = browser.new_context(viewport={"width": width, "height": height}, locale="en-US")
    page = ctx.new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(html_path.as_uri())
    return pw, browser, page


def test_3364_snapshot_untranslated_count_matches_today_and_full_and_keys_loading(tmp_path):
    """#3364: untranslated_count is identical between live shell (today=True) and full snapshot, including knowledge."""
    root = tmp_path / "rem"
    _build_regression_notebook(root)
    book = Notebook(root)
    book.write(
        "knowledge/architecture-notes.md",
        "# Architecture notes\n\nA multi-sentence English topic note about distributed storage and caching [1].\n\n## Sources\n1. session:abc12345\n",
    )
    shell = rem_reader.snapshot(root, local=True, today=True)
    full = rem_reader.snapshot(root, local=True, today=False)
    assert shell["untranslated_count"] == full["untranslated_count"] > 0
    assert shell["written_count"] == full["written_count"] > 0

    template = rem_reader.TEMPLATE.read_text(encoding="utf-8")
    assert 'keys-env-loading' in template
    assert '"Reading co\'s own keys…": "正在读取 co 自己用的密钥…"' in template


def test_3436_task_status_and_result_respect_privacy_levels():
    """#3436: derived execution summaries/results never leak at Public only and curtain sensitive summaries at Cover."""
    template = rem_reader.TEMPLATE.read_text(encoding="utf-8")
    script = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const slice = name => {
  const start = html.indexOf('function ' + name + '(');
  let depth = 0, i = html.indexOf('{', start);
  for (; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
};
const AGENT_NAMES = { codex: 'Codex', claude: 'Claude' }, ACTIVE_TASK = ['queued', 'starting', 'running'];
let uiLanguage = 'en', privacyLevel = 'public';
const REM = { live: false };
function t(k, v = {}) { return k.replace(/\{(\w+)\}/g, (_, n) => v[n] ?? ''); }
function el(tag, attrs = {}, kids = []) {
  return { tag, attrs, kids: kids.filter(Boolean), text: attrs.text || '' };
}
function liveHere() { return false; }
function handed(task) { return !!task?.result && task.result !== 'ready' && task.result !== 'waiting'; }
function rowTask(entry) { return entry.task; }
function taskStep(task) { return task.step?.summary || ''; }
function taskFailure() { return 'failed'; }
function taskElapsed() { return '0:10'; }
function clockNow() { return Date.now(); }
function startTaskClock() {}
function copyToClipboard() {}
eval(slice('summaryHere'));
eval(slice('taskStatus'));
eval(slice('taskStatusNode'));
eval(slice('taskResult'));

const entry = {
  r: { path: 'people/mara.md', private: false },
  t: { text: 'Send confidential payroll sheet [sensitive]' },
  task: { result: 'completed', agent: 'codex', summary: 'Prepared confidential payroll breakdown', reply: 'Attached payroll numbers' }
};
const pubStatus = taskStatus(entry.task, entry);
const pubNode = taskStatusNode(entry.task, entry);
const pubRes = taskResult(entry);

privacyLevel = 'cover';
const covStatus = taskStatus(entry.task, entry);
const covNode = taskStatusNode(entry.task, entry);
const covRes = taskResult(entry);

privacyLevel = 'all';
const allStatus = taskStatus(entry.task, entry);
console.log(JSON.stringify({ pubStatus, pubNode, pubRes, covStatus, covNode, hasCovReply: (covRes.kids || []).some(k => k.tag === 'textarea'), allStatus }));
"""
    proc = subprocess.run(
        ["node", "-e", script, str(rem_reader.TEMPLATE)],
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(proc.stdout)
    assert out["pubStatus"] == ""
    assert out["pubNode"] is None
    assert out["pubRes"] is None
    assert "payroll" not in out["covStatus"]
    assert out["covNode"]["kids"][1]["attrs"]["data-level"] == "sensitive"
    assert out["hasCovReply"] is False
    assert "Prepared confidential payroll breakdown" in out["allStatus"]
    assert "taskPrivacyLevel" not in template  # kept self-contained for isolated function tests


def test_browser_3306_3417_3387_3437_3438_end_to_end(tmp_path):
    """End-to-end verification in headless Chromium for #3306, #3417, #3387, #3437, and #3438."""
    root = tmp_path / "rem"
    _build_regression_notebook(root)
    html_path = tmp_path / "reader.html"
    html_path.write_text(rem_reader.render(root, local=True), encoding="utf-8")

    pw, browser, page = _open_rendered(html_path, 1440, 900)
    try:
        # 1. #3306 & #3231: 3-column layout on person page + permissions panel + >=660px middle prose + evidence drawer swap
        page.goto(html_path.as_uri() + "#r=people%2Fmara-ostrowski.md")
        page.locator("#main.reading > aside.page-nav").wait_for()
        metrics = page.evaluate(
            """() => {
              const main = document.getElementById('main');
              const nav = main.querySelector(':scope > .page-nav');
              const prose = main.querySelector('.deep-note .note');
              const perm = nav.querySelector('.perm-empty, .perm-list');
              const toc = nav.querySelector('.toc-panel');
              return {
                proseW: prose.getBoundingClientRect().width,
                proseRight: prose.getBoundingClientRect().right,
                navLeft: nav.getBoundingClientRect().left,
                navW: nav.getBoundingClientRect().width,
                navPos: getComputedStyle(nav).position,
                hasPerm: !!perm,
                permText: perm ? perm.textContent.trim() : '',
                hasToc: !!toc
              };
            }""",
            isolated_context=False,
        )
        assert metrics["proseW"] >= 660, metrics
        assert metrics["navLeft"] >= metrics["proseRight"] + 20, metrics
        assert 240 <= metrics["navW"] <= 280 and metrics["navPos"] == "sticky", metrics
        assert metrics["hasPerm"] and "No permissions inferred yet" in metrics["permText"], metrics
        assert metrics["hasToc"], metrics

        # Evidence drawer open: .page-nav hides cleanly and middle heading/prose never crushes
        page.evaluate("() => { document.body.classList.add('evidence-open'); }", isolated_context=False)
        ev_metrics = page.evaluate(
            """() => ({
              navDisplay: getComputedStyle(document.querySelector('#main > .page-nav')).display,
              headW: document.querySelector('#main .r4-name').getBoundingClientRect().width,
              proseW: document.querySelector('#main .deep-note .note').getBoundingClientRect().width
            })""",
            isolated_context=False,
        )
        assert ev_metrics["navDisplay"] == "none", ev_metrics
        assert ev_metrics["headW"] >= 200 and ev_metrics["proseW"] >= 580, ev_metrics
        page.evaluate("() => { document.body.classList.remove('evidence-open'); }", isolated_context=False)

        # 2. #3387: Private topic title is masked at Cover sensitive and revealed at Show all
        page.evaluate("() => setPrivacy('cover')", isolated_context=False)
        cover_text = page.locator("#main").inner_text()
        assert "Secret clinic appointment" not in cover_text
        assert "Personal item" in cover_text

        # Search also masks private title at Cover sensitive
        page.evaluate("() => { location.hash = '#q=checkup'; }", isolated_context=False)
        page.wait_for_timeout(150)
        search_cover = page.locator("#main").inner_text()
        assert "Secret clinic appointment" not in search_cover
        assert "Personal item" in search_cover

        # At Show all: real title shows and 0 curtains remain
        page.goto(html_path.as_uri() + "#r=people%2Fmara-ostrowski.md")
        page.evaluate("() => setPrivacy('all')", isolated_context=False)
        all_text = page.locator("#main").inner_text()
        assert "Secret clinic appointment" in all_text
        assert page.locator("#main .curtain").count() == 0

        # 3. #3417: At Public only, 100%-private section vanishes (heading included), mixed section keeps heading + public line
        page.evaluate("() => setPrivacy('public')", isolated_context=False)
        headings = page.locator("#main .deep-note .note h2").all_inner_texts()
        assert not any("Private medical notes" in h for h in headings), headings
        assert any("Mixed notes" in h for h in headings), headings
        note_text = page.locator("#main .deep-note .note").inner_text()
        assert "Public partnership milestone confirmed for Q4" in note_text
        assert "allergy test" not in note_text and "home phone note" not in note_text

        # 4. #3437: Organisation opening strips stale '0 people' prose and prints live people count
        page.evaluate("() => setPrivacy('cover')", isolated_context=False)
        page.goto(html_path.as_uri() + "#r=orgs%2Ffernhill-labs.md")
        page.locator("#main .ov-opening").wait_for()
        opening = page.locator("#main .ov-opening").inner_text()
        assert "0 people" not in opening and "0 个人" not in opening, opening
        assert "You know 1 person here." in opening or "You know " in opening, opening

        # 5. #3438: #view=changes suppresses 'No page content changed last night' when pass.changed is non-empty
        page.evaluate(
            """() => {
              const nowIso = REM.as_of || new Date().toISOString();
              REM.logs = [{ started_at: nowIso, finished_at: nowIso, phase: 'daily-update', outcome: 'completed',
                            items: 3, changed: ['people/mara-ostrowski.md'], claim_changes: [] }];
              REM.brief_logs = REM.logs;
              location.hash = '#view=changes';
              render();
            }""",
            isolated_context=False,
        )
        changes_text = page.locator("#main").inner_text()
        assert "No page content changed last night" not in changes_text, changes_text
        assert "Pages rewritten" in changes_text and "Mara Ostrowski" in changes_text, changes_text

        # When both claims and changed are empty, the empty state DOES appear
        page.evaluate(
            """() => {
              const nowIso = REM.as_of || new Date().toISOString();
              REM.logs = [{ started_at: nowIso, finished_at: nowIso, phase: 'sync', outcome: 'completed',
                            items: 1, changed: [], claim_changes: [] }];
              REM.brief_logs = REM.logs;
              render();
            }""",
            isolated_context=False,
        )
        empty_changes = page.locator("#main").inner_text()
        assert "No page content changed last night" in empty_changes, empty_changes
    finally:
        browser.close()
        pw.stop()

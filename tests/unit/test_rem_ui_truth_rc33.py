"""Strict TDD regression suite for REM UI & data-truthfulness fixes (#3479, #3439, #3438, #3437, #3364).

All test fixtures use invented data only.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import pytest

from connectonion.rem import day_plan, owner_today, reader as rem_reader, service
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, state_path, write_json

REAL_PW_BROWSERS = Path.home() / ".cache" / "ms-playwright"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from rem_reader_notebook import build as build_fixture_notebook  # noqa: E402


def _open_rendered(html_path: Path, width: int = 1440, height: int = 900, locale: str = "en-US"):
    from patchright.sync_api import sync_playwright

    if REAL_PW_BROWSERS.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(REAL_PW_BROWSERS))
    pw = sync_playwright().start()
    launch_kwargs: dict[str, object] = {"headless": True}
    if Path("/opt/google/chrome/chrome").exists():
        launch_kwargs["channel"] = "chrome"
    try:
        browser = pw.chromium.launch(**launch_kwargs)
    except Exception as exc:
        pw.stop()
        pytest.skip(f"headless browser unavailable: {exc}")
    ctx = browser.new_context(viewport={"width": width, "height": height}, locale=locale)
    page = ctx.new_page()
    html_body = html_path.read_text(encoding="utf-8")

    def _route(route):
        url = route.request.url
        if url.startswith("http://rem.test/reader.html"):
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html_body)
        elif url.startswith("http://rem.test/rem/"):
            route.fulfill(status=200, content_type="application/json", body='{"ok": true}')
        else:
            route.abort()

    page.route("http*://**/*", _route)
    page.goto("http://rem.test/reader.html")
    return pw, browser, page


def _build_rc33_notebook(root: Path) -> None:
    build_fixture_notebook(root, datetime(2026, 11, 22, 14, 30, tzinfo=timezone.utc))
    book = Notebook(root)
    book.write(
        "knowledge/caching-notes.md",
        "# Caching notes\n\nDetailed architecture summary about multi-tier cache invalidation [1].\n\n## Sources\n1. session:cache-1\n",
    )
    # Parent org with stale 0-people prose + child unit with extra members (#3437)
    org = book.read("orgs/fernhill-labs.md")
    org = org.replace(
        "# Fernhill Labs\n\n",
        "# Fernhill Labs\n\nFernhill Labs builds climate tools (0 people). Has 0 contacts recorded. 暂无联系人。\n\n",
    )
    book.write("orgs/fernhill-labs.md", org)
    book.write(
        "orgs/fernhill-research.md",
        "# Fernhill Research\n\n"
        "## Facts\n"
        "- Kind: lab [1]\n"
        "- Parent: [[orgs/fernhill-labs.md]] [1]\n\n"
        "## Sources\n"
        "1. gmail:fr-1\n\n"
        "Investigation: investigated 2026-11-18\n",
    )
    book.write(
        "people/clara-quinn.md",
        "# Clara Quinn\n\n"
        "## Facts\n"
        "- Email: clara@fernhill.test [1]\n"
        "- Unit: [[orgs/fernhill-research.md]] [1]\n"
        "- Role: Lead Scientist [1]\n\n"
        "## Sources\n"
        "1. gmail:cq-1\n\n"
        "Investigation: investigated 2026-11-18\n",
    )
    book.write(
        "people/devon-hart.md",
        "# Devon Hart\n\n"
        "## Facts\n"
        "- Email: devon@fernhill.test [1]\n"
        "- Unit: [[orgs/fernhill-research.md]] [1]\n"
        "- Role: Systems Engineer [1]\n\n"
        "## Sources\n"
        "1. gmail:dh-1\n\n"
        "Investigation: investigated 2026-11-18\n",
    )


def test_3439_python_elapsed_appointment_demoted_in_day_plan_and_owner_today(tmp_path, monkeypatch):
    """#3439 Python layer: elapsed same-day appointments are detected, demoted in day_plan, and noted in owner_today."""
    config = default_config()
    config["schedule"]["timezone"] = "UTC"
    moment = datetime(2026, 11, 22, 14, 30, tzinfo=timezone.utc)
    zone = service.notebook_zone(config)

    # Elapsed same-day appointments (EN & ZH)
    assert day_plan.elapsed_appointment("Confirm 10:00 AM coffee today with Mara", moment, zone) is not None
    assert day_plan.elapsed_appointment("Confirm 2026-11-22 09:30 call", moment, zone) is not None
    assert day_plan.elapsed_appointment("确认今天上午10点会议", moment, zone) is not None
    assert day_plan.elapsed_appointment("确认 11月22日 11:00 见面", moment, zone) is not None
    assert day_plan.elapsed_appointment("Confirm meeting at 11:00", moment, zone, due="2026-11-22") is not None

    # Future appointments must NOT be flagged elapsed
    assert day_plan.elapsed_appointment("Confirm 16:00 meeting today", moment, zone) is None
    assert day_plan.elapsed_appointment("确认今天下午4点会议", moment, zone) is None
    assert day_plan.elapsed_appointment("Confirm 2026-11-23 09:00 call", moment, zone) is None

    # day_plan.build demotes elapsed appointment behind current actionable items and warns in text()
    elapsed_item = dict(
        key="elapsed", rank=0, record="people/mara.md", title="Mara",
        text="Confirm today at 10:00 coffee with Mara [1]", dir="mine",
        since="2026-11-22", due="2026-11-22", closed=False, quiet=False, reply={},
    )
    current_item = dict(
        key="current", rank=1, record="people/tomas.md", title="Tomas",
        text="Send updated pilot budget to Tomas [1]", dir="mine",
        since="2026-11-22", due="2026-11-23", closed=False, quiet=False, reply={},
    )
    saved = day_plan.build({"read": [{"name": "Calendar"}], "events": []}, [elapsed_item, current_item], config, moment)
    proposals = [row for row in saved["days"][0]["items"] if row["kind"] == "proposal"]
    assert proposals[0]["key"] == "current", proposals
    assert proposals[1]["key"] == "elapsed" and proposals[1].get("elapsed") is True, proposals
    rendered_text = day_plan.text(saved, "2026-11-22")
    assert "passed" in rendered_text.lower() or "elapsed" in rendered_text.lower(), rendered_text

    # owner_today surfaces elapsed prepared drafts so the night/agent does not treat them as ready to send
    import yaml
    root = tmp_path / "rem"
    prepare(root)
    cfg = default_config()
    cfg["schedule"]["timezone"] = "UTC"
    (root / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.setattr(service, "now", lambda: moment)
    drafts_dir = state_path(root, "drafts")
    drafts_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        drafts_dir / "elapsed-appt.json",
        {
            "id": "elapsed-appt",
            "status": "prepared",
            "record": "people/mara.md",
            "to": "mara@example.test",
            "subject": "Re: Coffee today at 10:00",
            "body": "Hi Mara, confirming our 10:00 AM coffee today!",
            "prepared_at": "2026-11-22T01:00:00+00:00",
        },
    )
    digest = owner_today.refresh(root)
    assert "elapsed" in digest.lower() and "mara@example.test" in digest, digest


def test_3479_write_full_screen_visible_on_today_reply_cards_all_skins_and_mobile(tmp_path):
    """#3479: Today reply cards show a visible localized 'Write full screen' / '全屏写' button beside Send/More."""
    root = tmp_path / "rem"
    _build_rc33_notebook(root)
    html_path = tmp_path / "reader.html"
    html_path.write_text(rem_reader.render(root, local=True), encoding="utf-8")

    pw, browser, page = _open_rendered(html_path, 1440, 900)
    try:
        page.evaluate(
            """() => {
              REM.live = true;
              const entry = todayGroups(threadEntries().filter(e => !isDone(e)))[0];
              const target = entry.entries[0];
              const srcIds = [...obligationEvidence(target).ids].filter(id => !id.startsWith('thread:'));
              const provider = 'outlook', thread = 'mail:fixture:3479';
              if (srcIds[0]) {
                REM.source_context[srcIds[0]] = { ...(REM.source_context[srcIds[0]] || {}), source: provider, thread };
              }
              REM.drafts = [{
                id: 'draft-3479',
                thread,
                provider,
                channel: 'mail',
                status: 'prepared',
                to: 'mara@fernhill.test',
                from: 'owner@example.test',
                subject: 'Re: Pilot notes',
                body: 'Hi Mara,\\n\\nLet us meet 【需要你：周三 / 周四】 to review the pilot.\\n\\nBest',
                gist: '确认周三或周四复盘。',
                why: '确认具体时间。'
              }];
              setInterfaceLanguage('en');
              location.hash = '#';
              render();
            }""",
            isolated_context=False,
        )
        page.locator("#main .qcard.focal .mail-write").wait_for()

        # Verify EN visible label directly next to Send / More, inline preview stays initial state
        en_info = page.evaluate(
            """() => {
              const btn = document.querySelector('#main .qcard.focal .mail-write');
              const rect = btn.getBoundingClientRect();
              const actions = btn.closest('.mail-actions');
              const inMore = !!btn.closest('.more-menu');
              const inlineBody = document.querySelector('#main .qcard.focal .mail-text');
              const writerOpen = !!document.querySelector('dialog.writer[open]');
              return {
                text: btn.innerText.trim(),
                aria: btn.getAttribute('aria-label'),
                key: btn.getAttribute('data-key'),
                w: rect.width,
                h: rect.height,
                inMore,
                hasSendSibling: !!actions?.querySelector('.btn-act, .btn-line'),
                inlineVisible: !!inlineBody && inlineBody.getBoundingClientRect().height > 10,
                writerOpen,
                tabIndex: btn.tabIndex
              };
            }""",
            isolated_context=False,
        )
        assert en_info["text"] == "Write full screen", en_info
        assert en_info["aria"] == "Write full screen", en_info
        assert en_info["key"] == "r", en_info
        assert en_info["w"] >= 90 and en_info["h"] >= 32, en_info
        assert not en_info["inMore"] and en_info["hasSendSibling"], en_info
        assert en_info["inlineVisible"] and not en_info["writerOpen"], en_info
        assert en_info["tabIndex"] >= 0, en_info

        # Fill inline slot choice, then click "Write full screen" and verify answer is preserved
        page.locator("#main .qcard.focal .owner-slot.choose button").first.click()
        page.locator("#main .qcard.focal .mail-write").click()
        page.locator("dialog.writer[open]").wait_for()
        writer_text = page.locator("dialog.writer[open]").inner_text()
        assert "周三" in writer_text, writer_text
        page.locator("dialog.writer[open] .writer-close, dialog.writer[open] button[aria-label='Close']").first.click()

        # Check all 4 skins in light & dark modes
        for skin in ("porcelain", "klein", "onion", "classic"):
            for theme in ("light", "dark"):
                box = page.evaluate(
                    """([skin, theme]) => {
                      setSkin(skin);
                      setTheme(theme);
                      const btn = document.querySelector('#main .qcard.focal .mail-write');
                      const r = btn.getBoundingClientRect();
                      const cs = getComputedStyle(btn);
                      return { text: btn.innerText.trim(), w: r.width, h: r.height, color: cs.color, bg: cs.backgroundColor };
                    }""",
                    [skin, theme],
                    isolated_context=False,
                )
                assert box["text"] == "Write full screen" and box["w"] >= 90 and box["h"] >= 32, (skin, theme, box)

        # Verify ZH localization ('全屏写') and mobile >= 44px touch target
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("() => { setInterfaceLanguage('zh'); render(); }", isolated_context=False)
        page.locator("#main .qcard.focal .mail-write").wait_for()
        zh_mobile = page.evaluate(
            """() => {
              const btn = document.querySelector('#main .qcard.focal .mail-write');
              const r = btn.getBoundingClientRect();
              return { text: btn.innerText.trim(), aria: btn.getAttribute('aria-label'), w: r.width, h: r.height };
            }""",
            isolated_context=False,
        )
        assert zh_mobile["text"] == "全屏写" and zh_mobile["aria"] == "全屏写", zh_mobile
        assert zh_mobile["h"] >= 44 and zh_mobile["w"] >= 44, zh_mobile
    finally:
        browser.close()
        pw.stop()


def test_3439_3438_3437_3364_browser_truthfulness_end_to_end(tmp_path):
    """End-to-end headless Chromium verification of #3439, #3438, #3437, and #3364."""
    root = tmp_path / "rem"
    _build_rc33_notebook(root)
    html_path = tmp_path / "reader.html"
    html_path.write_text(rem_reader.render(root, local=True), encoding="utf-8")

    pw, browser, page = _open_rendered(html_path, 1440, 900)
    try:
        # ---- 1. #3439: Elapsed same-day appointment draft is demoted below current item & marked needs-recheck ----
        result_3439 = page.evaluate(
            r"""() => {
              REM.live = true;
              const now = new Date();
              const pad = n => String(n).padStart(2, '0');
              const todayStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
              // Set local clock to 14:30 today so 10:00 today is guaranteed elapsed
              const fixedNow = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 14, 30, 0);
              REM.as_of = fixedNow.toISOString();
              window.clockNow = () => fixedNow.getTime();
              const groups = todayGroups(threadEntries().filter(e => !isDone(e)));
              const firstEntry = groups[0].entries[0];
              const secondEntry = groups[1].entries[0];
              const firstRow = REM.today_queue.find(r => (r.keys || [r.key]).includes(doneKey(firstEntry)));
              const secondRow = REM.today_queue.find(r => (r.keys || [r.key]).includes(doneKey(secondEntry)));
              const bindThread = (entry, provider, thread) => {
                const srcId = [...obligationEvidence(entry).ids].find(id => !id.startsWith('thread:'));
                if (srcId) REM.source_context[srcId] = { ...(REM.source_context[srcId] || {}), source: provider, thread };
                return { provider, thread };
              };
              const m1 = bindThread(firstEntry, 'outlook', 'mail:fixture:elapsed-1');
              const m2 = bindThread(secondEntry, 'gmail', 'mail:fixture:current-2');
              const firstCites = (firstEntry.t.text.match(/\[W?\d{1,3}\]/g) || ['[1]']).join(' ');
              firstEntry.t.text = `Confirm today at 10:00 coffee with ${groups[0].r.title} ${firstCites}`;
              firstEntry.t.originalText = firstEntry.t.text;
              firstEntry.t.due = todayStr;
              if (firstRow) firstRow.reply = { ...(firstRow.reply || {}), state: 'queued', provider: m1.provider, thread: m1.thread };
              if (secondRow) secondRow.reply = { ...(secondRow.reply || {}), state: 'queued', provider: m2.provider, thread: m2.thread };
              REM.drafts = [
                { id: 'd-elapsed', thread: m1.thread, provider: m1.provider, channel: 'mail', status: 'prepared',
                  to: 'first@example.test', from: 'owner@example.test', subject: 'Re: Coffee today at 10:00',
                  body: `Hi, confirming our ${todayStr} 10:00 meeting today.` },
                { id: 'd-current', thread: m2.thread, provider: m2.provider, channel: 'mail', status: 'prepared',
                  to: 'second@example.test', from: 'owner@example.test', subject: 'Re: Budget',
                  body: 'Hi, here is the updated pilot budget.' }
              ];
              todayLead = null;
              setInterfaceLanguage('en');
              location.hash = '#';
              render();
              const cards = [...document.querySelectorAll('#main .today-brief .qcard')];
              const elapsedCard = cards.find(c => c.dataset.path === groups[0].r.path);
              const sendBtn = elapsedCard?.querySelector('.mail-actions button:last-child');
              return {
                firstPath: groups[0].r.path,
                secondPath: groups[1].r.path,
                renderedOrder: cards.map(c => c.dataset.path),
                elapsedRecheckAttr: elapsedCard?.getAttribute('data-recheck'),
                elapsedStep: elapsedCard?.getAttribute('data-step'),
                bannerText: elapsedCard?.querySelector('.draft-recheck')?.textContent?.trim() || '',
                sendBtnClass: sendBtn?.className || ''
              };
            }""",
            isolated_context=False,
        )
        assert result_3439["renderedOrder"][0] == result_3439["secondPath"], result_3439
        assert result_3439["renderedOrder"].index(result_3439["firstPath"]) > 0, result_3439
        assert result_3439["elapsedRecheckAttr"] == "elapsed", result_3439
        assert result_3439["elapsedStep"] == "recheck", result_3439
        assert "10:00" in result_3439["bannerText"] and "recheck" in result_3439["bannerText"].lower(), result_3439
        assert "btn-act" not in result_3439["sendBtnClass"], result_3439

        # Non-bracket placeholder draft (TODO / {{...}}) is also demoted and marked
        placeholder_3439 = page.evaluate(
            """() => {
              REM.drafts[0].body = 'Hi, please meet at {{LOCATION}} — TODO: confirm room.';
              REM.drafts[0].subject = 'Re: Follow-up';
              const g0 = todayGroups(threadEntries().filter(e => !isDone(e)));
              for (const g of g0) for (const e of g.entries) {
                if (e.t.text.includes('10:00')) { e.t.text = 'Follow up on room booking'; e.t.originalText = e.t.text; }
              }
              todayLead = null;
              render();
              const cards = [...document.querySelectorAll('#main .today-brief .qcard')];
              const phCard = cards.find(c => c.getAttribute('data-recheck') === 'placeholder');
              return {
                leadPath: cards[0]?.dataset.path,
                phPath: phCard?.dataset.path,
                phBanner: phCard?.querySelector('.draft-recheck')?.textContent?.trim() || ''
              };
            }""",
            isolated_context=False,
        )
        assert placeholder_3439["phPath"] and placeholder_3439["leadPath"] != placeholder_3439["phPath"], placeholder_3439
        assert placeholder_3439["phBanner"], placeholder_3439

        # ---- 2. #3438: Memory changes local-time window + never conflicts with rewritten list or Today ----
        changes_scenarios = page.evaluate(
            r"""() => {
              const now = new Date(2026, 10, 22, 9, 0, 0);
              REM.as_of = now.toISOString();
              window.clockNow = () => now.getTime();
              const runIso = new Date(2026, 10, 22, 3, 0, 0).toISOString();
              // Ensure firstBuild() is false by setting an earlier first_run_at
              REM.first_run_at = new Date(2026, 10, 1, 3, 0, 0).toISOString();
              // Scenario A: run rewrote Mara, 0 claim diffs
              REM.logs = [{ started_at: runIso, finished_at: runIso, phase: 'daily-update', outcome: 'completed',
                            items: 2, changed: ['people/mara-ostrowski.md'], claim_changes: [] }];
              REM.brief_logs = REM.logs;
              REM.night_runs = REM.logs;
              location.hash = '#view=changes';
              render();
              const scenA = document.getElementById('main').innerText;

              // Scenario B: 0 run.changed, but a record has today's local stamp (metadata/date update only)
              const mara = byPath('people/mara-ostrowski.md');
              const origText = mara.text;
              mara.text = origText.replace(/Investigation:[^\n]*/m, 'Investigation: updated 2026-11-22');
              REM.logs = [{ started_at: runIso, finished_at: runIso, phase: 'sync', outcome: 'completed',
                            items: 1, changed: [], claim_changes: [] }];
              REM.brief_logs = REM.logs;
              REM.night_runs = REM.logs;
              render();
              const scenB = document.getElementById('main').innerText;
              mara.text = origText;

              // Scenario C: Pass was 3 days ago (> 36h) — must NOT claim "last night"
              const oldIso = new Date(2026, 10, 18, 3, 0, 0).toISOString();
              REM.logs = [{ started_at: oldIso, finished_at: oldIso, phase: 'daily-update', outcome: 'completed',
                            items: 1, changed: ['people/mara-ostrowski.md'], claim_changes: [] }];
              REM.brief_logs = REM.logs;
              REM.night_runs = REM.logs;
              render();
              const scenC = document.getElementById('main').innerText;
              const pagesSummaryC = pagesLine(lastPass());

              // Scenario D: Truly empty last night (0 claims, 0 run changes, 0 stamp changes)
              const emptyNow = new Date(2026, 10, 25, 9, 0, 0);
              const emptyRunIso = new Date(2026, 10, 25, 3, 0, 0).toISOString();
              REM.as_of = emptyNow.toISOString();
              window.clockNow = () => emptyNow.getTime();
              REM.logs = [{ started_at: emptyRunIso, finished_at: emptyRunIso, phase: 'sync', outcome: 'completed',
                            items: 1, changed: [], claim_changes: [] }];
              REM.brief_logs = REM.logs;
              REM.night_runs = REM.logs;
              render();
              const scenD = document.getElementById('main').innerText;

              return { scenA, scenB, scenC, pagesSummaryC, scenD };
            }""",
            isolated_context=False,
        )
        assert "No page content changed last night" not in changes_scenarios["scenA"], changes_scenarios["scenA"]
        assert "Pages rewritten" in changes_scenarios["scenA"] and "Mara Ostrowski" in changes_scenarios["scenA"], changes_scenarios["scenA"]
        assert "No page content changed last night" not in changes_scenarios["scenB"], changes_scenarios["scenB"]
        assert "Mara Ostrowski" in changes_scenarios["scenB"], changes_scenarios["scenB"]
        assert "last night" not in changes_scenarios["scenC"].lower(), changes_scenarios["scenC"]
        assert "last night" not in changes_scenarios["pagesSummaryC"].lower(), changes_scenarios["pagesSummaryC"]
        assert "No page content changed last night" in changes_scenarios["scenD"], changes_scenarios["scenD"]

        # ---- 3. #3437: Org overview count matches list & tree, strips stale prose, distinguishes direct vs descendant ----
        org_truth = page.evaluate(
            """() => {
              setInterfaceLanguage('en');
              location.hash = '#c=orgs';
              render();
              const listRow = orgRows().find(o => o.r.path === 'orgs/fernhill-labs.md');
              const listCount = listRow?.people?.length ?? -1;

              location.hash = '#r=' + encodeURIComponent('orgs/fernhill-labs.md');
              render();
              const openingEn = document.querySelector('#main .ov-opening')?.innerText || '';
              const treePeople = document.querySelectorAll('#main .ov-org-tree .ov-trow[data-kind="person"]').length;

              setInterfaceLanguage('zh');
              render();
              const openingZh = document.querySelector('#main .ov-opening')?.innerText || '';

              // Also test 0 direct + 2 descendants
              const lab = byPath('orgs/fernhill-labs.md');
              const origPeople = lab.people;
              lab.people = [];
              setInterfaceLanguage('en');
              render();
              const zeroDirectEn = document.querySelector('#main .ov-opening')?.innerText || '';
              lab.people = origPeople;
              return { listCount, treePeople, openingEn, openingZh, zeroDirectEn };
            }""",
            isolated_context=False,
        )
        assert org_truth["listCount"] == org_truth["treePeople"] >= 3, org_truth
        assert "0 people" not in org_truth["openingEn"] and "0 contacts" not in org_truth["openingEn"], org_truth
        assert str(org_truth["listCount"]) in org_truth["openingEn"], org_truth
        assert "direct" in org_truth["openingEn"].lower() and "subordinate" in org_truth["openingEn"].lower(), org_truth
        assert "暂无联系人" not in org_truth["openingZh"] and "下属单位" in org_truth["openingZh"], org_truth
        assert "0 direct" in org_truth["zeroDirectEn"].lower() and "subordinate" in org_truth["zeroDirectEn"].lower(), org_truth

        # ---- 4. #3364 Part A: Single authoritative translation count across all routes & Settings ----
        trans_truth = page.evaluate(
            """() => {
              setInterfaceLanguage('zh');
              // Inject service & needs_review written records that previously caused 219 vs 419 jump!
              REM.records.push(
                { path: 'people/noreply-bot.md', category: 'people', title: 'NoReply Bot', text: '# NoReply Bot\\n\\nAutomated notices.', written: true, written_in: 'en', service: true, translations: {} },
                { path: 'people/unreviewed-guest.md', category: 'people', title: 'Guest', text: '# Guest\\n\\nUnreviewed contact.', written: true, written_in: 'en', needs_review: true, translations: {} },
                { path: 'skills/catalog/parent.md', category: 'skills', title: 'Catalog Parent', text: '# Catalog Parent\\n\\nParent.', written: true, written_in: 'en', catalog_parent: true, translations: {} }
              );
              const expected = REM.untranslated_count;
              translateAllJob = null;
              detailReady = false;
              renderLangProgress();
              const preBadge = document.querySelector('#lang-progress .lb-long')?.textContent?.trim() || '';

              detailReady = true;
              const routes = ['#', '#c=knowledge', '#c=keys', '#c=people', '#r=' + encodeURIComponent('knowledge/caching-notes.md'), '#view=graph'];
              const seen = {};
              for (const h of routes) {
                location.hash = h;
                render();
                seen[h] = document.querySelector('#lang-progress .lb-long')?.textContent?.trim() || '';
              }
              // Settings translate-all button must also agree before and after Host job status arrives
              const settingsBefore = document.querySelector('#foot .ta-go')?.textContent?.trim() || '';
              translateAllJob = { state: 'idle', done: 10, total: 15 };
              for (const box of document.querySelectorAll('.translate-all')) drawTranslateAll(box);
              renderLangProgress();
              const badgeAfterJob = document.querySelector('#lang-progress .lb-long')?.textContent?.trim() || '';
              const settingsAfterJob = document.querySelector('#foot .ta-go')?.textContent?.trim() || '';
              translateAllJob = null;
              return { expected, preBadge, seen, settingsBefore, badgeAfterJob, settingsAfterJob };
            }""",
            isolated_context=False,
        )
        expected_str = f"{trans_truth['expected']} 页待翻译"
        assert trans_truth["preBadge"] == expected_str, trans_truth
        for route_hash, badge_text in trans_truth["seen"].items():
            assert badge_text == expected_str, (route_hash, trans_truth)
        assert f"({trans_truth['expected']}" in trans_truth["settingsBefore"] or str(trans_truth["expected"]) in trans_truth["settingsBefore"], trans_truth
        assert trans_truth["badgeAfterJob"] == "5 页待翻译", trans_truth
        assert "5" in trans_truth["settingsAfterJob"], trans_truth

        # ---- 5. #3364 Part B: Keys page shows loading placeholder row while /rem/keys/env is in flight ----
        keys_loading = page.evaluate(
            """async () => {
              REM.live = true;
              const origHostPost = window.hostPost;
              const resolvers = [];
              window.hostPost = (url, body) => {
                if (url === '/rem/keys/env') return new Promise(res => { resolvers.push(res); });
                return origHostPost(url, body);
              };
              // Remove any keychain keys to verify empty state stays hidden while loading
              const savedKeys = REM.records.filter(r => r.category === 'keys');
              REM.records = REM.records.filter(r => r.category !== 'keys');

              setInterfaceLanguage('en');
              location.hash = '#c=keys';
              await new Promise(r => setTimeout(r, 30));
              render();
              const loadingEn = document.querySelector('#main .keys-env-loading')?.textContent?.trim() || '';
              const busyDuring = document.querySelector('#main .keys-env')?.getAttribute('aria-busy');
              const emptyVisibleDuring = !document.querySelector('#main .empty')?.closest('[hidden]');

              setInterfaceLanguage('zh');
              render();
              const loadingZh = document.querySelector('#main .keys-env-loading')?.textContent?.trim() || '';

              // Now settle all pending /rem/keys/env fetches with 0 services -> placeholder disappears and empty state appears
              while (resolvers.length) resolvers.shift()({ ok: true, where: '~/.co/keys.env', services: [], settings: [] });
              await new Promise(r => setTimeout(r, 30));
              const loadingAfter = !!document.querySelector('#main .keys-env-loading');
              const emptyVisibleAfter = !!document.querySelector('#main .empty') && !document.querySelector('#main .empty').closest('[hidden]');

              REM.records.push(...savedKeys);
              window.hostPost = origHostPost;
              return { loadingEn, loadingZh, busyDuring, emptyVisibleDuring, loadingAfter, emptyVisibleAfter };
            }""",
            isolated_context=False,
        )
        assert "Loading co's own keys…" in keys_loading["loadingEn"], keys_loading
        assert "正在读取 co 自己用的密钥…" in keys_loading["loadingZh"], keys_loading
        assert keys_loading["busyDuring"] == "true", keys_loading
        assert not keys_loading["emptyVisibleDuring"], keys_loading
        assert not keys_loading["loadingAfter"] and keys_loading["emptyVisibleAfter"], keys_loading
    finally:
        browser.close()
        pw.stop()

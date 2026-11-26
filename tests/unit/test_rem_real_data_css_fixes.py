"""Red-first CSS, skin, contrast, layout & responsive regression tests for reader.html (#rem-evo-css).

Covers:
1. [P0 #4] Klein & Onion dark-mode surface overrides (no white-on-white 1.03:1).
2. [P1 #14] Dark/light .bau-bb-btn.primary, .bau-bb-btn.accent, .bau-bb-btn:disabled & .hyp .fc.sel text >= 4.5:1.
3. [P0 #5] :root.calm vs .calm global layout collapse.
4. [P0 #6] Command palette .palette .pl top border removal.
5. [P0 #2] Mobile (<=880px) #view=open multi-select checkboxes, 44px crush fix, .bau-dirbar & .bau-who.
6. [P0 #8 & P1 #20] Evidence drawer z-index, desktop .top & .ov-say width, action link gap, mobile sticky header height.
7. [P1 #12, #15, #28] .bau-row.done-inline:hover, .bau-strip-btn.on.late, dark-slab light-mode contrast,
   .sheet th .arrow, dark-mode mark highlight, .rem-activity spacing, .pd-card overflow/wrap, #approval-sheet mobile,
   openWriter mobile channel_defect Send dedupe, .ag-views centering, dvh/vh progressive fallbacks, 44px mobile targets,
   and :focus-visible rings on .tl-e.tl-open, .qcard.focal, .cal-scroll, .gx-search.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys

import pytest

from connectonion.rem import reader as rem_reader
from connectonion.rem.files import Notebook

REAL_PW_BROWSERS = Path.home() / ".cache" / "ms-playwright"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from rem_reader_notebook import build as build_fixture_notebook  # noqa: E402


def _build_css_fixture(root: Path) -> None:
    build_fixture_notebook(root, datetime(2026, 11, 22, tzinfo=timezone.utc))
    book = Notebook(root)
    # Add extra people to Fernhill Labs with structured units so org renders .ov-r6 with .ov-org-tree
    for slug, name, unit in [
        ("jonas-berg", "Jonas Berg", "Platform"),
        ("claire-wu", "Claire Wu", "Security"),
        ("tariq-amin", "Tariq Amin", "Platform"),
    ]:
        book.write(
            f"people/{slug}.md",
            f"# {name}\n\nEngineer at [Fernhill Labs](../orgs/fernhill-labs.md) ({unit}) [1].\n\n"
            f"## Profile\n- Organisation: [Fernhill Labs](../orgs/fernhill-labs.md)\n- Unit: {unit}\n- Role: Engineer\n\n"
            f"## Sources\n1. gmail:msg-{slug}\n",
        )


def _launch_browser():
    from patchright.sync_api import sync_playwright

    if REAL_PW_BROWSERS.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(REAL_PW_BROWSERS))
    pw = sync_playwright().start()
    launch_kwargs: dict[str, object] = {"headless": True}
    if Path("/opt/google/chrome/chrome").exists():
        launch_kwargs["channel"] = "chrome"
    browser = pw.chromium.launch(**launch_kwargs)
    return pw, browser


@pytest.fixture(scope="module")
def rendered_html(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("rem_css_fixes")
    root = tmp / "rem"
    _build_css_fixture(root)
    html_path = tmp / "reader.html"
    html_path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    return html_path


@pytest.fixture(scope="module")
def browser_ctx(rendered_html: Path):
    pw, browser = _launch_browser()
    try:
        yield browser, rendered_html
    finally:
        browser.close()
        pw.stop()


def _new_page(browser, html_path: Path, width: int = 1440, height: int = 900, color_scheme: str = "light"):
    ctx = browser.new_context(
        viewport={"width": width, "height": height},
        locale="en-US",
        color_scheme=color_scheme,
    )
    page = ctx.new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(html_path.as_uri())
    return ctx, page


JS_CONTRAST_HELPERS = """
window.__rgb = s => {
  const m = String(s).match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
  if (m) return [+m[1], +m[2], +m[3]];
  const c = String(s).match(/color\\(srgb\\s+([\\d.]+)\\s+([\\d.]+)\\s+([\\d.]+)/);
  if (c) return [Math.round(+c[1] * 255), Math.round(+c[2] * 255), Math.round(+c[3] * 255)];
  return [0, 0, 0];
};
window.__lum = ([r, g, b]) => {
  const lin = [r, g, b].map(v => {
    v /= 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
};
window.__cr = (c1, c2) => {
  const l1 = window.__lum(window.__rgb(c1));
  const l2 = window.__lum(window.__rgb(c2));
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
};
window.__probeColor = (prop, val) => {
  const d = document.createElement('div');
  d.style.setProperty(prop, val);
  document.body.appendChild(d);
  const out = getComputedStyle(d)[prop === 'background' ? 'backgroundColor' : 'color'];
  d.remove();
  return out;
};
"""


def test_p0_bug4_klein_and_onion_dark_mode_surfaces_and_contrast(browser_ctx):
    browser, html_path = browser_ctx
    for scheme in ("dark", "light"):
        ctx, page = _new_page(browser, html_path, 1280, 800, color_scheme=scheme)
        try:
            page.evaluate(JS_CONTRAST_HELPERS, isolated_context=False)
            findings = page.evaluate(
                """(scheme) => {
                  const issues = [];
                  const skins = ['', 'klein', 'onion', 'classic'];
                  const themes = scheme === 'dark' ? ['', 'dark'] : ['light', 'dark'];
                  for (const skin of skins) {
                    for (const theme of themes) {
                      const root = document.documentElement;
                      if (skin) root.setAttribute('data-skin', skin); else root.removeAttribute('data-skin');
                      if (theme) root.setAttribute('data-theme', theme); else root.removeAttribute('data-theme');
                      const isDark = theme === 'dark' || (theme === '' && scheme === 'dark');
                      const surfaces = ['--canvas', '--rail-bg', '--paper', '--raised', '--well', '--rule'];
                      for (const s of surfaces) {
                        const bg = window.__probeColor('background', `var(${s})`);
                        const bgLum = window.__lum(window.__rgb(bg));
                        if (isDark && bgLum > 0.08) {
                          issues.push(`${skin || 'porcelain'}/${theme || 'auto-dark'} ${s} too bright: lum=${bgLum.toFixed(3)}`);
                        }
                        const ink = window.__probeColor('color', 'var(--ink)');
                        const grey = window.__probeColor('color', 'var(--grey)');
                        if (window.__cr(bg, ink) < 7.0) {
                          issues.push(`${skin || 'porcelain'}/${theme || 'auto'} --ink on ${s} cr=${window.__cr(bg, ink).toFixed(2)}`);
                        }
                        if (window.__cr(bg, grey) < 4.5) {
                          issues.push(`${skin || 'porcelain'}/${theme || 'auto'} --grey on ${s} cr=${window.__cr(bg, grey).toFixed(2)}`);
                        }
                      }
                    }
                  }
                  return issues;
                }""",
                scheme,
                isolated_context=False,
            )
            assert not findings, "\n".join(findings)
        finally:
            ctx.close()


def test_p1_bug14_batch_buttons_and_hyp_sel_contrast_all_skins(browser_ctx):
    browser, html_path = browser_ctx
    ctx, page = _new_page(browser, html_path, 1280, 800)
    try:
        page.evaluate(JS_CONTRAST_HELPERS, isolated_context=False)
        findings = page.evaluate(
            """() => {
              const issues = [];
              const host = document.createElement('div');
              host.innerHTML = `
                <div class="bau-batchbar">
                  <button class="bau-bb-btn primary">Done</button>
                  <button class="bau-bb-btn accent">Process</button>
                  <button class="bau-bb-btn primary" disabled>Disabled</button>
                </div>
                <svg class="hyp"><g class="fc sel"><circle r="10"></circle><text>3</text></g></svg>
              `;
              document.body.appendChild(host);
              const pri = host.querySelector('.bau-bb-btn.primary:not(:disabled)');
              const acc = host.querySelector('.bau-bb-btn.accent');
              const dis = host.querySelector('.bau-bb-btn:disabled');
              const cir = host.querySelector('.hyp .fc.sel circle');
              const txt = host.querySelector('.hyp .fc.sel text');

              const disStyle = getComputedStyle(dis);
              if (parseFloat(disStyle.opacity) > 0.55 || disStyle.cursor !== 'not-allowed') {
                issues.push(`disabled style: opacity=${disStyle.opacity} cursor=${disStyle.cursor}`);
              }

              for (const skin of ['', 'klein', 'onion', 'classic']) {
                for (const theme of ['light', 'dark']) {
                  const root = document.documentElement;
                  if (skin) root.setAttribute('data-skin', skin); else root.removeAttribute('data-skin');
                  root.setAttribute('data-theme', theme);

                  const pCs = getComputedStyle(pri);
                  const pCr = window.__cr(pCs.backgroundColor, pCs.color);
                  if (pCr < 4.5) issues.push(`${skin || 'porcelain'}/${theme} .bau-bb-btn.primary cr=${pCr.toFixed(2)}`);

                  const aCs = getComputedStyle(acc);
                  const aCr = window.__cr(aCs.backgroundColor, aCs.color);
                  if (aCr < 4.5) issues.push(`${skin || 'porcelain'}/${theme} .bau-bb-btn.accent cr=${aCr.toFixed(2)}`);

                  const cFill = getComputedStyle(cir).fill;
                  const tFill = getComputedStyle(txt).fill;
                  const hCr = window.__cr(cFill, tFill);
                  if (hCr < 4.5) issues.push(`${skin || 'porcelain'}/${theme} .hyp .fc.sel text cr=${hCr.toFixed(2)}`);
                }
              }
              host.remove();
              return issues;
            }""",
            isolated_context=False,
        )
        assert not findings, "\n".join(findings)
    finally:
        ctx.close()


def test_p0_bug5_and_bug6_root_calm_and_palette_pl(browser_ctx):
    browser, html_path = browser_ctx
    ctx, page = _new_page(browser, html_path, 1280, 800)
    try:
        res = page.evaluate(
            """() => {
              document.documentElement.classList.add('calm');
              const rootCs = getComputedStyle(document.documentElement);
              const box = document.createElement('div');
              box.className = 'block-threads';
              box.innerHTML = '<div class="calm"><span class="dir">Clear</span></div>';
              document.getElementById('main').appendChild(box);
              const innerCalmDisplay = getComputedStyle(box.querySelector('.calm')).display;
              box.remove();

              openPalette();
              const pl = document.querySelector('dialog.palette .pl');
              const plBorderTop = pl ? getComputedStyle(pl).borderTopWidth : 'missing';
              document.querySelector('dialog.palette')?.close();
              document.documentElement.classList.remove('calm');
              return {
                rootDisplay: rootCs.display,
                rootPadTop: rootCs.paddingTop,
                rootBg: rootCs.backgroundColor,
                paperBg: getComputedStyle(document.body).backgroundColor,
                innerCalmDisplay,
                plBorderTop
              };
            }""",
            isolated_context=False,
        )
        assert res["rootDisplay"] == "block", res
        assert res["rootPadTop"] == "0px", res
        assert res["rootBg"] == res["paperBg"], res
        assert res["innerCalmDisplay"] == "flex", res
        assert res["plBorderTop"] == "0px", res
    finally:
        ctx.close()


def test_p0_bug2_mobile_open_view_multiselect_dirbar_and_who(browser_ctx):
    browser, html_path = browser_ctx
    ctx, page = _new_page(browser, html_path, 390, 844)
    try:
        page.evaluate("() => { location.hash = '#view=open'; render(); }", isolated_context=False)
        page.locator(".bau-open .bau-row").first.wait_for()
        normal = page.evaluate(
            """() => {
              const dirs = [...document.querySelectorAll('.bau-dirbar .bau-dir')];
              const dirBarRect = document.querySelector('.bau-dirs').getBoundingClientRect();
              const chopped = dirs.some(d => d.scrollWidth > d.clientWidth + 1);
              const thirdClipped = dirs.length >= 3 && dirs[2].getBoundingClientRect().right > dirBarRect.right + 2 && document.querySelector('.bau-dirs').scrollWidth <= document.querySelector('.bau-dirs').clientWidth;
              const who = document.querySelector('.bau-row .bau-who');
              const whoCs = getComputedStyle(who);
              return {
                dirCount: dirs.length,
                chopped,
                thirdClipped,
                dirsRight: dirBarRect.right,
                thirdRight: dirs[2]?.getBoundingClientRect().right || 0,
                dirsOverflowX: getComputedStyle(document.querySelector('.bau-dirs')).overflowX,
                whoDisplay: whoCs.display,
                whoW: who.getBoundingClientRect().width
              };
            }""",
            isolated_context=False,
        )
        assert not normal["chopped"], normal
        assert normal["dirsRight"] <= 390 and (normal["thirdRight"] <= normal["dirsRight"] + 1 or normal["dirsOverflowX"] in ("auto", "scroll")), normal
        assert normal["whoDisplay"] != "none" and normal["whoW"] > 30, normal

        page.locator(".bau-mode-btn").click()
        multi = page.evaluate(
            """() => {
              const row = document.querySelector('.bau-open.multi .bau-row');
              const sel = row.querySelector('.bau-selbox');
              const main = row.querySelector('.bau-main');
              const selCs = getComputedStyle(sel);
              const selRect = sel.getBoundingClientRect();
              const mainRect = main.getBoundingClientRect();
              return {
                selDisplay: selCs.display,
                selW: selRect.width,
                selH: selRect.height,
                mainW: mainRect.width,
                mainLeft: mainRect.left,
                selRight: selRect.right
              };
            }""",
            isolated_context=False,
        )
        assert multi["selDisplay"] in ("inline-flex", "flex", "grid"), multi
        assert multi["selW"] >= 44 and multi["selH"] >= 44, multi
        assert multi["mainW"] >= 200 and multi["mainLeft"] >= multi["selRight"] - 2, multi
    finally:
        ctx.close()


def test_p0_bug8_and_p1_bug20_evidence_drawer_zindex_desktop_layout_and_mobile_sticky(browser_ctx):
    browser, html_path = browser_ctx
    # 1. Desktop 1280x800 check on org page with org tree
    ctx, page = _new_page(browser, html_path, 1280, 800)
    try:
        page.evaluate("() => { location.hash = '#r=orgs%2Ffernhill-labs.md'; render(); }", isolated_context=False)
        page.locator("#main .ov-say").wait_for()
        desktop = page.evaluate(
            """() => {
              const r = REM.records.find(x => x.path === 'orgs/fernhill-labs.md');
              // Ensure source 1 maps to a session too so both action links appear
              const sid = 'gmail:msg-jonas-berg';
              REM.source_context = REM.source_context || {};
              REM.source_context[sid] = { source: 'gmail', sender: 'Jonas Berg <j@fernhill.example>', time: '2026-11-20T10:00:00Z', excerpt: 'Platform migration confirmed.' };
              REM.records.push({ path: 'sessions/s1.md', category: 'sessions', title: 'S1', session_messages: [{ id: 'm1', source: sid }] });
              const nl = String.fromCharCode(10); if (!r.text.includes(sid)) { r.text = r.text.replace('## Sources', '## Sources' + nl + '- [98] ' + sid); if (r.original) r.original = r.text; }
              FACTS.delete(r.path); sourceList._cache?.clear();
              CITES.from = r.path;
              document.querySelector('#sources')?.remove();
              const ds = document.createElement('div');
              ds.className = 'deep-sources';
              ds.reveal = () => {};
              ds.innerHTML = '<div id="sources"><div id="src-98"></div></div>';
              document.getElementById('main').appendChild(ds);
              openEvidence(r, '98', document.querySelector('#main .ov-say'));

              const backdropZ = parseInt(getComputedStyle(document.querySelector('.evidence-backdrop')).zIndex, 10);
              const panel = document.getElementById('evidence-panel');
              const panelZ = parseInt(getComputedStyle(panel).zIndex, 10);
              const railZ = parseInt(getComputedStyle(document.querySelector('.rail')).zIndex, 10);
              const topRect = document.querySelector('header.top').getBoundingClientRect();
              const panelRect = panel.getBoundingClientRect();
              const ovSayW = document.querySelector('#main .ov-say').getBoundingClientRect().width;
              const inSrc = panel.querySelector('.evidence-in-sources');
              const sessLink = panel.querySelector('.evidence-session-link');
              let linkGap = 0;
              if (inSrc && sessLink) {
                const a = inSrc.getBoundingClientRect(), b = sessLink.getBoundingClientRect();
                linkGap = Math.max(b.left - a.right, b.top - a.bottom);
              }
              return { backdropZ, panelZ, railZ, topRight: topRect.right, panelLeft: panelRect.left, ovSayW, linkGap };
            }""",
            isolated_context=False,
        )
        assert desktop["backdropZ"] > desktop["railZ"] and desktop["panelZ"] > desktop["backdropZ"], desktop
        assert desktop["panelZ"] < 40, desktop
        assert desktop["topRight"] <= desktop["panelLeft"] + 1, desktop
        assert desktop["ovSayW"] >= 500, desktop
        assert desktop["linkGap"] >= 8, desktop
    finally:
        ctx.close()

    # 2. Mobile 390x844 sticky header height inside .evidence-panel
    ctx_m, page_m = _new_page(browser, html_path, 390, 844)
    try:
        mobile = page_m.evaluate(
            """() => {
              const r = REM.records.find(x => x.path === 'people/mara-ostrowski.md');
              const sid = 'gmail:long-mail';
              REM.source_context = REM.source_context || {};
              REM.source_context[sid] = {
                source: 'gmail',
                sender: 'Mara Ostrowski <mara@fernhill.example>',
                subject: 'Partnership contract schedule',
                time: '2026-11-20T10:00:00Z',
                participants: { from: ['people/mara-ostrowski.md'], to: ['you@example.com'] },
                excerpt: ('Line of archived mail text.' + String.fromCharCode(10)).repeat(120)
              };
              const nl = String.fromCharCode(10); if (!r.text.includes(sid)) { r.text = r.text.replace('## Sources', '## Sources' + nl + '- [99] ' + sid); if (r.original) r.original = r.text; }
              FACTS.delete(r.path); sourceList._cache?.clear();
              openEvidence(r, '99', document.body);
              const panel = document.getElementById('evidence-panel');
              const topH = panel.querySelector('.evidence-top')?.offsetHeight || 0;
              const findH = panel.querySelector('.evidence-find')?.offsetHeight || 0;
              const envH = panel.querySelector('.msg-envelope')?.offsetHeight || 0;
              return { panelH: panel.clientHeight, stickyH: topH + findH + envH, topH, findH, envH };
            }""",
            isolated_context=False,
        )
        assert mobile["findH"] > 0 and mobile["envH"] > 0, mobile
        assert mobile["stickyH"] / mobile["panelH"] <= 0.36, mobile
    finally:
        ctx_m.close()


def test_p1_bug12_15_28_specificity_dark_slab_contrast_and_micro_polish(browser_ctx):
    browser, html_path = browser_ctx
    # Static CSS checks for progressive dvh/vh fallbacks
    css_text = rem_reader.TEMPLATE.read_text(encoding="utf-8").split("</head>", 1)[0]
    assert re.search(r"max-height:\s*75vh;\s*max-height:\s*75dvh", css_text), "Missing 75vh + 75dvh pair"
    assert re.search(r"max-height:\s*85vh;\s*max-height:\s*85dvh", css_text), "Missing 85vh + 85dvh pair"
    assert re.search(r"height:\s*100vh;\s*height:\s*100dvh", css_text), "Missing 100vh + 100dvh pair"

    # Desktop browser checks
    ctx, page = _new_page(browser, html_path, 1280, 800)
    try:
        page.evaluate(JS_CONTRAST_HELPERS, isolated_context=False)
        # Check #view=open .done-inline:hover specificity
        page.evaluate("() => { location.hash = '#view=open'; render(); }", isolated_context=False)
        page.locator(".bau-open .bau-row .bau-circle").first.click()
        done_row = page.locator(".bau-open .bau-row.done-inline").first
        done_row.wait_for()
        done_row.hover()
        hover_state = done_row.evaluate(
            """row => ({
              rest: getComputedStyle(row.querySelector('.bau-rest')).display,
              acts: getComputedStyle(row.querySelector('.bau-hover-acts')).display
            })"""
        )
        assert hover_state["rest"] in ("flex", "inline-flex") and hover_state["acts"] == "none", hover_state

        # Check .bau-strip-btn.on.late, dark-slab light-mode contrast, .sheet th .arrow, dark-mode mark,
        # .rem-activity + .rem-activity, .pd-card, .ag-views button, and :focus-visible rings
        checks = page.evaluate(
            """() => {
              document.documentElement.setAttribute('data-theme', 'light');
              document.documentElement.removeAttribute('data-skin');
              const box = document.createElement('div');
              box.innerHTML = `
                <div class="bau-strip">
                  <button class="bau-strip-btn on late"><div class="bau-strip-k"><span>01</span><span class="late">20 d</span></div></button>
                </div>
                <section class="night-card"><p class="schedule-failure">Cron failed</p></section>
                <section class="night"><div class="kicker">Last night</div><div class="stat"><div class="k">Runs</div></div></section>
                <div class="bau-batchbar">
                  <span class="later-ask">Bring it back:</span>
                  <button class="btn-quiet later-choice">Tonight</button>
                  <button class="btn-quiet later-cancel">Cancel</button>
                </div>
                <table class="sheet"><thead><tr><th><span class="arrow">↓</span></th></tr></thead></table>
                <a class="rem-activity" href="#1">A</a><a class="rem-activity" href="#2">B</a>
                <article class="pd-card"><div class="pd-card-foot"><span>x</span></div></article>
                <div class="agenda-bar"><div class="seg ag-views"><button type="button">Week</button></div></div>
              `;
              document.body.appendChild(box);

              const red = window.__probeColor('color', 'var(--red)');
              const stripKColor = getComputedStyle(box.querySelector('.bau-strip-btn.on.late .bau-strip-k')).color;
              const stripSpanColor = getComputedStyle(box.querySelector('.bau-strip-k .late')).color;

              const ncBg = getComputedStyle(box.querySelector('.night-card')).backgroundColor;
              const sfCr = window.__cr(ncBg, getComputedStyle(box.querySelector('.schedule-failure')).color);

              const nBg = getComputedStyle(box.querySelector('.night')).backgroundColor;
              const nkCr = window.__cr(nBg, getComputedStyle(box.querySelector('.night .kicker')).color);

              const bbBg = getComputedStyle(box.querySelector('.bau-batchbar')).backgroundColor;
              const laCr = window.__cr(bbBg, getComputedStyle(box.querySelector('.later-ask')).color);
              const lcCr = window.__cr(bbBg, getComputedStyle(box.querySelector('.later-choice')).color);
              const lxCr = window.__cr(bbBg, getComputedStyle(box.querySelector('.later-cancel')).color);

              const arrowCs = getComputedStyle(box.querySelector('.sheet th .arrow'));
              const arrowOpacity = arrowCs.opacity;
              const paperBg = window.__probeColor('background', 'var(--paper)');
              const arrowCr = window.__cr(paperBg, arrowCs.color);

              const acts = box.querySelectorAll('.rem-activity');
              const actGap = acts[1].getBoundingClientRect().left - acts[0].getBoundingClientRect().right;

              const pdOverflow = getComputedStyle(box.querySelector('.pd-card')).overflow;
              const pdWrap = getComputedStyle(box.querySelector('.pd-card-foot')).flexWrap;
              const agAlign = getComputedStyle(box.querySelector('.agenda-bar .ag-views button')).alignItems;

              // Dark mode mark check
              document.documentElement.setAttribute('data-theme', 'dark');
              const markHost = document.createElement('div');
              markHost.className = 'evidence-original session-page';
              markHost.innerHTML = '<mark class="span">highlighted</mark>';
              document.body.appendChild(markHost);
              const mEl = markHost.querySelector('mark');
              const mCs = getComputedStyle(mEl);
              const darkPaper = window.__probeColor('background', 'var(--paper)');
              const markBgCr = window.__cr(darkPaper, mCs.backgroundColor);
              const markFgCr = window.__cr(mCs.backgroundColor, mCs.color);
              markHost.remove();
              box.remove();
              document.documentElement.setAttribute('data-theme', 'light');

              return {
                red, stripKColor, stripSpanColor,
                sfCr, nkCr, laCr, lcCr, lxCr,
                arrowOpacity, arrowCr,
                actGap, pdOverflow, pdWrap, agAlign,
                markBgCr, markFgCr
              };
            }""",
            isolated_context=False,
        )
        assert checks["stripKColor"] == checks["red"] and checks["stripSpanColor"] == checks["red"], checks
        assert checks["sfCr"] >= 4.5 and checks["nkCr"] >= 4.5, checks
        assert checks["laCr"] >= 4.5 and checks["lcCr"] >= 4.5 and checks["lxCr"] >= 4.5, checks
        assert checks["arrowOpacity"] == "1" and checks["arrowCr"] >= 4.5, checks
        assert checks["actGap"] >= 12, checks
        assert checks["pdOverflow"] == "hidden" and checks["pdWrap"] == "wrap", checks
        assert checks["agAlign"] == "center", checks
        assert checks["markBgCr"] >= 1.6 and checks["markFgCr"] >= 4.5, checks

        # Focus-visible rings check via keyboard Tab
        focus_rings = page.evaluate(
            """() => {
              const host = document.createElement('div');
              host.innerHTML = `
                <div class="tl"><div class="tl-e tl-open" tabindex="0">item</div></div>
                <div class="today-brief"><div class="qcard focal" tabindex="0">card</div></div>
                <div class="cal-scroll" tabindex="0">cal</div>
                <input class="gx-search" type="search">
              `;
              document.body.prepend(host);
              return true;
            }""",
            isolated_context=False,
        )
        assert focus_rings
        page.keyboard.press("Tab")
        for sel in (".tl-e.tl-open", ".today-brief .qcard.focal", ".cal-scroll", ".gx-search"):
            el_loc = page.locator(sel).first
            el_loc.focus()
            page.keyboard.press("Shift")  # keep keyboard modality active
            ring = el_loc.evaluate(
                """el => {
                  const cs = getComputedStyle(el);
                  return { matches: el.matches(':focus-visible'), style: cs.outlineStyle, width: cs.outlineWidth, shadow: cs.boxShadow };
                }"""
            )
            assert ring["matches"], (sel, ring)
            assert (ring["style"] != "none" and parseFloat_ok(ring["width"])) or ring["shadow"] != "none" if False else (
                (ring["style"] != "none" and ring["width"] != "0px") or ring["shadow"] != "none"
            ), (sel, ring)
    finally:
        ctx.close()

    # Mobile 390x844 checks: #approval-sheet, openWriter channel_defect Send dedupe, and 44px touch targets
    ctx_m, page_m = _new_page(browser, html_path, 390, 844)
    try:
        mobile_ui = page_m.evaluate(
            """() => {
              // 1. openWriter with channel_defect: true
              const who = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
              openWriter({
                to: 'Mara Ostrowski <mara@fernhill.example>',
                from: 'you@example.com',
                provider: 'gmail',
                channel: 'whatsapp',
                channel_defect: 'not_on_whatsapp',
                subject: 'Test',
                body: 'Hello Mara'
              }, who, async () => null, () => {});
              const writer = document.querySelector('dialog.writer');
              const topSendVisible = getComputedStyle(writer.querySelector('.writer-send-top')).display !== 'none';
              const bottomSendVisible = getComputedStyle(writer.querySelector('.writer-actions button:first-child')).display !== 'none';
              writer.close();

              // 2. #approval-sheet mobile layout
              const sheet = document.createElement('dialog');
              sheet.id = 'approval-sheet';
              sheet.innerHTML = `
                <header><h2>Approve the 12 items REM prepared for review</h2><button type="button" class="btn-quiet">Close</button></header>
                <div class="approval-content"><strong>Mara</strong><span class="kind-badge">Reply</span></div>
              `;
              document.body.appendChild(sheet);
              sheet.showModal();
              const badgeW = sheet.querySelector('.kind-badge').getBoundingClientRect().width;
              const closeShrink = getComputedStyle(sheet.querySelector('header button')).flexShrink;
              sheet.close();
              sheet.remove();

              // 3. 44px touch targets on #rem-state, #display-menu, #settings .settings-close
              const remState = document.getElementById('rem-state').getBoundingClientRect();
              const dispMenu = document.getElementById('display-menu').getBoundingClientRect();
              const settingsDlg = document.getElementById('settings');
              settingsDlg.showModal();
              const setClose = settingsDlg.querySelector('.settings-close').getBoundingClientRect();
              settingsDlg.close();

              return {
                topSendVisible, bottomSendVisible,
                badgeW, closeShrink,
                remState: [remState.width, remState.height],
                dispMenu: [dispMenu.width, dispMenu.height],
                setClose: [setClose.width, setClose.height]
              };
            }""",
            isolated_context=False,
        )
        assert mobile_ui["topSendVisible"] is True and mobile_ui["bottomSendVisible"] is False, mobile_ui
        assert 20 <= mobile_ui["badgeW"] <= 140 and mobile_ui["closeShrink"] == "0", mobile_ui
        assert mobile_ui["remState"][0] >= 44 and mobile_ui["remState"][1] >= 44, mobile_ui
        assert mobile_ui["dispMenu"][0] >= 44 and mobile_ui["dispMenu"][1] >= 44, mobile_ui
        assert mobile_ui["setClose"][0] >= 44 and mobile_ui["setClose"][1] >= 44, mobile_ui
    finally:
        ctx_m.close()

"""Unanswered sections fold into one line (opt in with CO_REM_BROWSER_TEST=1); invented notebook.

A page's Full memory showed each unanswered section as its own heading over "未知 — 尚未调查" (rc48 hunt: a
skill page with 9 of 16 sections empty, in the Chinese reader). foldUnfilled folds them into one line naming
them; a section with anything else in it stays.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1", reason="opt in with CO_REM_BROWSER_TEST=1")


@pytest.mark.parametrize("unknown, names", [("未知 — 尚未调查", ["洞察", "什么时候用", "局限"]),
                                            ("Unknown — not investigated yet.", ["Insight", "When to use", "Limits"])])
def test_unanswered_sections_fold_into_one_line_and_filled_ones_stay(tmp_path, monkeypatch, unknown, names):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.config import prepare
    from connectonion.rem.reader import render
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    path = tmp_path / "reader.html"
    path.write_text(render(root, local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="en-US")
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        result = page.evaluate(r'''({unknown, names}) => {
          const note = document.createElement('div');
          note.innerHTML = '<h2>Kept</h2><p>Finds the leads a page has not followed.</p>'
            + names.map(n => '<h2>' + n + '</h2><p>' + unknown + '</p>').join('')
            + '<h2>Mixed</h2><p>' + unknown + '</p><p>Ran twice in October.</p>';
          const folded = foldUnfilled(note);
          return {folded, headings: [...note.querySelectorAll('h2')].map(h => h.textContent),
                  line: note.querySelector('.unfilled-sections')?.textContent || ''};
        }''', {"unknown": unknown, "names": names}, isolated_context=False)
        assert result["folded"] == names
        assert result["headings"] == ["Kept", "Mixed"]
        assert all(name in result["line"] for name in names)
        browser.close()

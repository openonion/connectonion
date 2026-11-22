"""A draft the page check refused says so in the owner's words (#2235 follow-up, 2026-11-23).

Live, a project's head showed "Candidate rejected, kept at candidate.md: Unused citation: 41": the runner's
words, a file name and a number. The head now says the draft did not pass and the page is unchanged; what
the check found sits behind a fold, worded plainly, with no path or file name. Same on a person, an
organisation and a project, on a desktop and a phone. The notebook is invented.
Opt in with CO_REM_BROWSER_TEST=1."""
import os
from urllib.parse import quote

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
INVESTIGATED = "\n\nInvestigation: mapped 2026-09-01 · investigated 2026-10-01 (gmail)\n"
PAGES = {
    "people/avery-lin.md": "# Avery Lin\n\nAvery runs the Lantern pilot. [1]\n\n## Facts\n- Email: avery@lantern.example [1]\n\n"
                           "## Sources\n- [1] gmail:avery0001 — 2026-01-10" + INVESTIGATED,
    "orgs/lantern-example.md": "# Lantern\n\nLantern builds reading lamps. [1]\n\n## Sources\n- [1] gmail:lant0001 — 2026-01-10"
                               + INVESTIGATED,
    "projects/lantern-pilot.md": "# Lantern pilot\n\nThe pilot runs until March. [1]\n\n## Sources\n- [1] gmail:pilot0001 — 2026-01-10"
                                 + INVESTIGATED,
}
REJECT = """(path) => {
  const r = byPath(path), at = new Date().toISOString();
  r.investigation = { label: 'update', last: '2026-10-01', run: { result: 'failed', reason_kind: 'rejected', started_at: at,
    finished_at: at, reason: 'The draft did not pass the page check, so nothing on the page changed.', detail: 'Unused citation: 41' } };
  KNOWN.clear(); render();
}"""


@pytest.fixture(params=[(1440, 900), (390, 844)], ids=["desktop", "phone"])
def tab(request, tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    monkeypatch.setenv("CONNECTONION_REM_CACHE", str(tmp_path / "cache"))
    root = tmp_path / "rem"
    prepare(root)
    book = Notebook(root)
    for path, text in PAGES.items():
        book.write(path, text)
    html = tmp_path / "reader.html"
    html.write_text(reader.render(root, live=False, local=True), encoding="utf-8")
    width, height = request.param
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": height}, locale="zh-CN")
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(html.as_uri())
        page.wait_for_function("() => typeof byPath === 'function' && byPath('people/avery-lin.md')")
        page.html_uri = html.as_uri()
        yield page
        browser.close()


@pytest.mark.parametrize("path", list(PAGES))
def test_a_refused_draft_says_the_page_is_unchanged_and_folds_what_the_check_found(tab, path):
    tab.goto(tab.html_uri + "#r=" + quote(path))
    tab.wait_for_function(f"() => byPath({path!r}) && document.querySelector('#main h1')")
    tab.evaluate(REJECT, path, isolated_context=False)
    line = tab.locator("#main .inv-line").first
    line.wait_for()
    said = line.inner_text()
    assert "这次调查的稿子没通过检查，页面保持原样" in said
    for leak in ("candidate", "Candidate", ".md", "/", "Unused citation"):
        assert leak not in said
    detail = tab.locator("#main .inv-detail").first
    assert detail.is_hidden()
    line.get_by_role("button", name="检查发现了什么").click()
    assert detail.is_visible()
    assert detail.inner_text() == "稿子列了第 41 条来源，正文却没有用到"
    assert line.get_by_role("button", name="检查发现了什么").get_attribute("aria-expanded") == "true"

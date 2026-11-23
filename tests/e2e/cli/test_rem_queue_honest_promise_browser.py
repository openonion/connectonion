"""A mapped page says where it really stands in the night's queue, on every page kind (#3420).

"此页已排入今晚队列" sat on 1,241 person pages while a night completed 3 to 10 investigations. A page inside the
measured nightly pace says 今晚; one beyond it says its place and an estimate, never 今晚. The notebook is the
invented one in tests/fixtures/rem_reader_notebook.py.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-queue-shots"))


@pytest.fixture
def page(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build

    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    build(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    from connectonion.rem.files import Notebook
    book = Notebook(tmp_path / "rem")
    book.stub_org("orgs/quillmoor-labs.md", "Quillmoor Labs", ["quillmoor.example"], [])
    book.stub_project("projects/tidewater-pilot.md", "Tidewater pilot", ["~/work/tidewater"])
    html = rem_reader.render(tmp_path / "rem", local=True)
    errors = []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            return route.fulfill(status=200, body="{}", content_type="application/json")
        return route.fulfill(body=html, content_type="text/html") if path in ("/", "/index.html") else route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        p = context.new_page()
        p.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        p.goto(BASE)
        p.locator(".night-card .count, #main h1").first.wait_for()
        yield p
        browser.close()
    assert not errors, errors


def _mapped(page, category):
    return page.evaluate("""([c]) => REM.records.find(r => r.category === c && known(r).status === "Mapped"
        && known(r).missing.length && !r.private_project)?.path""", [category], isolated_context=False)


def _lead(page, path, place, pace, language="zh", width=1440):
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate("""([path, place, pace, lang]) => { setInterfaceLanguage(lang);
        REM.status.worker = {enabled: true}; REM.night_throughput = pace; byPath(path).queue_place = place;
        location.hash = href(byPath(path)).slice(1); render(); }""", [path, place, pace, language], isolated_context=False)
    return page.locator(".missing.primary .lead").inner_text()


@pytest.mark.parametrize("category", ["people", "orgs", "projects"])
def test_tonight_only_inside_the_nightly_pace_on_every_page_kind(page, category):
    path = _mapped(page, category)
    assert path, f"the notebook has a mapped {category} page"
    assert _lead(page, path, 3, 5) == "此页已排入今晚队列"
    far = _lead(page, path, 40, 5)
    assert "今晚" not in far and far == "排队第 40 位 · 按最近每晚约 5 页，约 8 晚内写到"


@pytest.mark.parametrize("width", [1440, 390])
def test_the_queued_line_fits_and_reads_whole(page, width):
    path = _mapped(page, "people")
    assert _lead(page, path, 1241, 5, width=width) == "排队第 1,241 位 · 按最近每晚约 5 页，约 249 晚内写到"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if os.environ.get("REM_PR_SHOTS"):
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.locator(".missing.primary").scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"after-{width}.png"), full_page=False)

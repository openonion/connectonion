"""People's filter rows say what they filter, and their chips lead with names a person reads (#3157).

P大 on rc17: "筛选两排都叫『全部』，我刚点的是哪个全部？" and "筛选全是课程代码，给人看的吗？". Each chip row is labelled
(来源 / 标签); a course code or bare domain goes by its organisation's or tag page's own title when there is one and
otherwise waits under 更多; one company under a short and a full name is one chip; a nameless mailbox shows its address
once, in the name cell, with no organisation. The notebook is the invented one in tests/fixtures/rem_reader_notebook.py.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-people-filters-shots"))
TAGGED = {"people/mara-ostrowski.md": ["course", "uni", "fern", "client"],
          "people/tomas-reyes.md": ["course", "fern-labs", "client"],
          "people/ines-halvorsen.md": ["course", "uni"],
          "people/noor-bakhtiar.md": ["fern"]}
TAGS = {"course": {"label": "1234-T1A-PEAR", "kind": "topic", "aliases": []},       # a course code, no page of its own
        "uni": {"label": "example.edu", "kind": "org", "aliases": []},              # a university domain
        "fern": {"label": "Fernhill", "kind": "org", "aliases": []},                # one company, short name…
        "fern-labs": {"label": "Fernhill Labs", "kind": "org", "aliases": []},      # …and full name
        "client": {"label": "client", "kind": "topic", "aliases": []}}
UNI = "# Example University\n\n## Facts\n- Domains: example.edu\n\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n"


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem import tags
    from connectonion.rem.files import Notebook, state_path, write_json
    build(root, now)
    book = Notebook(root)
    for path, slugs in TAGGED.items():
        book.write(path, tags.with_tags(book.read(path), [{"tag": slug, "citation": ""} for slug in slugs]))
    book.write("orgs/example-edu-1a2b3c4d.md", UNI)
    # A person REM knows only by their mailbox: its title is the address.
    quinn = book.read("people/quinn-alder.md")
    address = "lee.c@example.org"
    lee = quinn.replace(quinn.splitlines()[0], "# " + address, 1).replace("Quinn Alder", address).replace("quinn", "lee.c")
    # Its organisation came from the mail domain, which is how the email ended up in People's org column (#3157).
    lee = re.sub(r"(?m)^- Company:.*$", "- Company: example.org (from email domain)", lee)
    if "- Company:" not in lee:
        lee = lee.replace("\n## Facts\n", "\n## Facts\n- Company: example.org (from email domain)\n", 1)
    book.write("people/lee-c-example-org.md", lee)
    write_json(state_path(root, "tags.json"), {"tags": TAGS})
    return root


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    html = rem_reader.render(_notebook(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc)), local=True)
    errors = []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            return route.fulfill(status=200, body="{}", content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE)
        page.locator(".night-card .count, #main h1").first.wait_for()

        def open_people(width=1440, wechat=False):
            page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
            page.evaluate("""([wechat]) => {
                setInterfaceLanguage("zh");
                if (wechat) { REM.chat_activity = { "people/noor-bakhtiar.md": { last: REM.as_of, n90: 12, mine: false } }; REM._resting = null; }
                location.hash = "c=people"; render(); }""", [wechat], isolated_context=False)
            page.locator("#main table").first.wait_for()
            return page

        yield open_people
        browser.close()
    assert not errors, errors


def _shot(page, name, width):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}-{width}.png"), full_page=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_each_chip_row_says_what_it_filters(reader, width):
    page = reader(width, wechat=True)
    tags = page.locator("#main .tag-bar")
    source = page.locator("#main .source-bar")
    assert tags.locator(".bar-label").inner_text() == "标签"
    assert source.locator(".bar-label").inner_text() == "来源"
    # One 全部 per row, each under its own label: never two unlabelled 全部.
    assert tags.locator("a.chip", has_text="全部").count() == 1
    assert source.locator("a.chip", has_text="全部").count() == 1
    _shot(page, "people-filters", width)


@pytest.mark.parametrize("width", [1440, 390])
def test_chips_lead_with_names_codes_wait_under_more_and_one_company_is_one_chip(reader, width):
    page = reader(width)
    bar = page.locator("#main .tag-bar")
    visible = bar.locator(":scope > a.chip").all_inner_texts()
    visible = [re.sub(r"\s+", " ", text).strip() for text in visible]
    names = [re.sub(r" \d+$", "", text) for text in visible[1:]]          # after 全部, without the count
    assert names, visible
    assert not any("1234-T1A-PEAR" in text for text in visible), visible  # the code doesn't head the row
    assert "example.edu" not in " ".join(visible) and any("Example University" in name for name in names), visible
    fern = [text for text in visible if "Fernhill" in text]
    assert len(fern) == 1, visible                                       # short and full name: one chip
    assert fern[0].endswith(" 3"), fern                                  # Mara, Tomás and Noor, counted once each
    more = bar.locator("details.chip-more")
    assert more.count() == 1
    more.locator("summary").click()
    assert "1234-T1A-PEAR" in more.inner_text()
    # The merged chip filters by either name.
    page.locator("#main .tag-bar a.chip", has_text="Fernhill").click()
    page.wait_for_function("() => location.hash.includes('tag=')")
    page.evaluate("render()", isolated_context=False)
    text = page.locator("#main table.people-table").inner_text()
    assert "Mara Ostrowski" in text and "Tomás Reyes" in text and "Noor Bakhtiar" in text and "Inès Halvorsen" not in text
    _shot(page, "people-chips-more", width)


def test_a_nameless_mailbox_shows_its_address_once_and_no_organisation(reader):
    page = reader(1440)
    row = page.locator("#main table.people-table tr", has=page.locator(".nm-unknown"))
    assert row.count() == 1
    assert row.inner_text().count("lee.c@example.org") == 1
    org = row.locator("td").nth(1)
    assert org.inner_text().strip() in ("", "—"), org.inner_text()

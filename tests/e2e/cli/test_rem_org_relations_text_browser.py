"""An org page's 关联 rows and 人物与组织结构 tree say what is true about THIS org (#3397).

The rc19 hunt (2026-11-23), on a client company's page:
- a 关联 row read 「ConnectOnion — Changed: 所提供的 Oct6 快照为 1.9.0a41…」: the other page's own version note, with an
  English field label, not a reason the two belong together;
- another row named an organisation with no reason at all;
- the owner's own co-founder was drawn inside the client's org tree, because the client's page named her.
The notebook is the invented one in tests/fixtures/rem_reader_notebook.py; every name below is invented.
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
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-org-relations-shots"))
CLIENT, OWN, FUND, MATE = "orgs/fernhill-labs.md", "orgs/quillmoor.md", "orgs/willowmere-fund.md", "people/kit-brennan.md"
TRAIL = "projects/lumen-trail.md"
SOURCES = "\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n"
VERSION_NOTE = "Changed: the shared snapshot was 2.1.0a4; a later 2.2rc1 needs opting in"


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    book.write(OWN, "# Quillmoor\n\n## Facts\n- Kind: own_company [1]\n- What they do: Agent tools [1]\n" + SOURCES)
    book.write(FUND, "# Willowmere Fund\n\n## Facts\n- Kind: investor [1]\n- What they do: Research grants [1]\n" + SOURCES)
    # A project whose own page names the client; the client page never mentions it back.
    book.write(TRAIL, "# Lumen Trail\n\n## Facts\n- Organisation: [Fernhill Labs](../orgs/fernhill-labs.md) [1]\n" + SOURCES)
    book.write(MATE, "# Kit Brennan\n\n## Facts\n- Company: [Quillmoor](../orgs/quillmoor.md) [1]\n"
                     "- Role: Co-founder [1]\n" + SOURCES)
    owner = book.read("people/avery-lin.md")
    book.write("people/avery-lin.md", owner.replace("- Company: Unknown", "- Company: [Quillmoor](../orgs/quillmoor.md) [1]", 1))
    harbour = book.read("projects/harbour.md")
    # The other page's own summary is a version note: it must never stand in as the reason on the client's page.
    book.write("projects/harbour.md", harbour.replace("\n\n", f"\n\n{VERSION_NOTE} [1].\n\n", 1))
    client = book.read(CLIENT)
    client = client.replace("## People here\n", "## People here\n- [Kit Brennan](../people/kit-brennan.md) — on the pilot thread [1]\n", 1)
    client = client.replace("## Open threads\n", "## Open threads\n"
                            f"- {VERSION_NOTE} for [Harbour](../projects/harbour.md) [1].\n"
                            "- Related: [Willowmere Fund](../orgs/willowmere-fund.md) [1]\n", 1)
    book.write(CLIENT, client)
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

        def go(where, width=1440):
            page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
            page.evaluate("""([where]) => { setInterfaceLanguage("zh"); location.hash = href(byPath(where)).slice(1); render(); }""",
                          [where], isolated_context=False)
            page.locator("#main h1").first.wait_for()
            return page

        yield go
        browser.close()
    assert not errors, errors


def _shot(page, name, width):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.locator("#main .ov-org-tree").scroll_into_view_if_needed()
    page.screenshot(path=str(SHOTS / f"{name}-{width}.png"), full_page=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_connections_never_show_a_version_note_and_a_reasonless_row_says_how_they_meet(reader, width):
    page = reader(CLIENT, width)
    rows = page.locator("#main .ov-connections p").all_inner_texts()
    assert rows, "the client page lists its connections"
    assert not [row for row in rows if "Changed" in row or "2.1.0a4" in row], rows
    # The review (#3400): no 链接, and the direction said in plain words, kind word first.
    assert "Willowmere Fund — 组织 · 这页里提到过" in rows, rows
    assert "Lumen Trail — 项目 · 它的页面提到这里" in rows, rows
    assert not [row for row in rows if "链接" in row], rows
    _shot(page, "org-connections", width)


def test_a_related_page_card_never_shows_a_version_note_as_its_reason(reader):
    page = reader(CLIENT)
    basis = page.evaluate("""() => (REM.records.find(r => r.path === "orgs/fernhill-labs.md").relations || [])
        .map(link => relationCard(link, "orgs/fernhill-labs.md").querySelector(".relation-basis")?.textContent || "")""",
                          isolated_context=False)
    assert not [text for text in basis if "2.1.0a4" in text or "Changed" in text], basis


@pytest.mark.parametrize("width", [1440, 390])
def test_the_owners_cofounder_is_your_side_not_inside_the_clients_tree(reader, width):
    page = reader(CLIENT, width)
    root = page.locator("#main .ov-org-tree [role=treeitem][aria-level='1']").first
    inside = root.locator("[role=treeitem]").all_inner_texts()
    assert not [text for text in inside if "Kit Brennan" in text], inside
    # Outside the company's tree, under a light heading with no fold: not one of its departments (#3400 review).
    assert page.locator("#main .ov-org-tree [role=tree] [aria-level='1']").count() == 1
    heading = page.locator("#main .ov-org-tree .ov-yours-h")
    assert heading.inner_text().strip() == "你这边对接的人"
    yours = page.locator("#main .ov-org-tree .ov-yours")
    assert yours.locator("[aria-expanded], .ov-twisty, [role=treeitem]").count() == 0
    assert yours.evaluate("node => !node.closest('[role=tree]')")
    assert any("Kit Brennan" in text for text in yours.locator("li").all_inner_texts())
    assert page.locator("#main .ov-opening").inner_text().count("Kit Brennan") == 0
    _shot(page, "org-tree-yours", width)

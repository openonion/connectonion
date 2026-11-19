"""People names a person's organisation as an organisation (rc35 hunt, #3157), in a real browser (opt in).

On the owner's notebook People's organisation column read like a log: a course group's code, two universities as
bare domains, and one company twice, once as its short name and once as its full one. A code is never an
organisation; a domain reads as the organisation's name (its page's, or the domain's own word); a short and a full
name of one company are one organisation. The open list's place chips use the same names. Every page here is
invented.
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

DOMAIN = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", re.I)
CODE = re.compile(r"^(?=\S*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+$")


def _person(title, email, company):
    return (f"# {title}\n\n{title} wrote about the pilot [1].\n\n## Contact\n- Email: {email} [1]\n"
            f"- Company: {company}\n- Role: Unknown\n\n## Sources\n- [1] gmail:a1b2c3d4e5f6 — invented\n")


PAGES = {
    "orgs/kiln-edu-au.md": "# kiln.edu.au\n\n## Domains\n- kiln.edu.au [1]\n\n## Facts\n- What they do: Unknown\n",
    "orgs/harbour-fine-wine.md": "# Harbour Fine Wine\n\n## Domains\n- Unknown\n\n## Facts\n- What they do: Wine merchant [1]\n",
    "orgs/wren.md": "# Wren\n\n## Domains\n- wren.example [1]\n\n## Facts\n- What they do: Startup programme [1]\n",
    # A university group's code where the company goes, as a page wrote it.
    "people/pia-grove.md": _person("Pia Grove", "pia@kiln.edu.au", "[kiln.edu.au](../orgs/kiln-edu-au.md) (from email domain) [1]"),
    "people/rob-ash.md": _person("Rob Ash", "rob@uni.example", "3900-F13A-PEAR [1]"),
    "people/sol-reed.md": _person("Sol Reed", "sol@harbourfinewine.com.au", "Harbour (project affiliation) [1]"),
    "people/tia-moss.md": _person("Tia Moss", "tia@harbourfinewine.com.au", "[Harbour Fine Wine](../orgs/harbour-fine-wine.md) [1]"),
    "people/uma-fell.md": _person("Uma Fell", "uma@wren.example", "[Wren Founders](../orgs/wren.md) [1]"),
    "people/vic-hale.md": _person("Vic Hale", "vic@wayfarer.io", "wayfarer.io (from email domain) [1]"),
}


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    root = build(tmp_path / "rem", frozen)
    for path, text in PAGES.items():
        (root / path).write_text(text, encoding="utf-8")
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        data = snapshot(root, local, today=today)
        data["as_of"] = frozen.isoformat()
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path = tmp_path / "reader.html"
    path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    return path.as_uri()


@pytest.fixture
def browser():
    from patchright.sync_api import sync_playwright
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        yield browser
        browser.close()


def _orgs(browser, uri, width):
    page = browser.new_page(viewport={"width": width, "height": 1000 if width > 500 else 844},
                            is_mobile=width < 500, has_touch=width < 500)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(uri + "#c=people")
    page.locator(".people-table tbody tr").first.wait_for()
    rows = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.people-table tbody tr[data-href]')]
      .map(row => [row.querySelector('td.c-name').textContent.trim(), row.querySelector('td.c-org')?.textContent.trim() || '']))""")
    return page, rows, errors


@pytest.mark.parametrize("width", [1440, 390])
def test_people_names_organisations_never_codes_domains_or_two_spellings(reader, browser, width):
    page, rows, errors = _orgs(browser, reader, width)
    assert errors == []
    named = {name: org for name, org in rows.items() if org and org != "—"}
    assert not [org for org in named.values() if DOMAIN.match(org) or CODE.match(org)], named
    assert rows["Rob Ash"] in ("", "—")  # a code is no organisation
    assert named["Pia Grove"] == "KILN"  # a university's domain reads as its short name
    assert named["Vic Hale"] == "Wayfarer"  # a domain with no page reads as its word
    # One company, one name: the short name is the full one when the mail domain is the company's.
    assert named["Sol Reed"] == named["Tia Moss"] == "Harbour Fine Wine"
    # A page linked under a unit's label goes by the organisation's own name.
    assert named["Uma Fell"] == "Wren"
    page.close()



def shows_host(host, text):
    """The domain appears as its own token in the tooltip, not inside a longer name."""
    return re.search(r"(?<![\w.-])" + re.escape(host) + r"(?![\w-])", text) is not None

def test_the_domain_and_the_page_words_stay_in_the_tooltip(reader, browser):
    page, _, _ = _orgs(browser, reader, 1440)
    tips = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.people-table tbody tr[data-href]')]
      .map(row => [row.querySelector('td.c-name').textContent.trim(), row.querySelector('td.c-org .clamp')?.title || '']))""")
    assert shows_host("kiln.edu.au", tips["Pia Grove"]) and shows_host("wayfarer.io", tips["Vic Hale"])
    assert "Harbour" in tips["Sol Reed"] and "Wren Founders" in tips["Uma Fell"]
    page.close()

"""Photograph v1.9.3rc61's Today, a person and an organisation with an entirely fictional notebook.

    python scripts/capture_193rc61_release_reader.py docs/releases/assets/v1.9.3rc61

Uses the fictional notebook the reader's browser tests build (Mara Ostrowski,
Fernhill Labs). No model, mailbox or live Host runs. Chrome failures propagate.
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from capture_193rc53_release_reader import save_png  # noqa: E402
from connectonion.rem.reader import render  # noqa: E402
from rem_reader_notebook import build  # noqa: E402

VERSION = "v1.9.3rc61"
VIEW = {"color_scheme": "light", "locale": "en-US", "timezone_id": "Australia/Sydney", "reduced_motion": "reduce"}
IMAGES = [
    ("rem-today.png", "Today: one statement, the most overdue person, and one card per person on hairlines",
     "The first screen says how many people wait on you and who is most overdue; each person's items share one card and only the first card's action is green.",
     "Open Today in the fictional notebook at 1440x1000."),
    ("rem-person-record.png", "A person's page as their record, with one quiet link to Today",
     "The head shows who Mara is, her organisation and role; what you owe her is done from Today, so the page has no reply button.",
     "Open people/mara-ostrowski.md."),
    ("rem-org-record.png", "An organisation's page as its record",
     "Identity, structure, people and roles, and contact history lead; to-dos stay in Today.",
     "Open orgs/fernhill-labs.md."),
    ("rem-today-phone.png", "Today on a 390px phone",
     "The statement and the first card fit the first screen and nothing scrolls sideways.",
     "Load Today at 390x844 @2x."),
]


def green_buttons(page) -> int:
    return page.evaluate("""() => [...document.querySelectorAll('button, a')].filter(node => {
      const box = node.getBoundingClientRect(), color = getComputedStyle(node).backgroundColor;
      return box.width && box.height && color === 'rgb(34, 210, 122)';
    }).length""")


def capture_desktop(page, page_file: Path, out: Path) -> None:
    page.goto(page_file.as_uri() + "#")
    expect(page.locator(".qcard").first).to_be_visible()
    assert green_buttons(page) <= 1, "one green action on Today"
    save_png(page, out, "rem-today.png")
    page.goto(page_file.as_uri() + "#r=people%2Fmara-ostrowski.md")
    expect(page.locator(".r4-person h1")).to_have_text("Mara Ostrowski")
    assert page.locator(".r4-head .r4-primary").count() == 0, "a person's page has no reply button"
    save_png(page, out, "rem-person-record.png")
    page.goto(page_file.as_uri() + "#r=orgs%2Ffernhill-labs.md")
    expect(page.locator("h1").first).to_be_visible()
    assert green_buttons(page) <= 1
    save_png(page, out, "rem-org-record.png")


def capture_phone(browser, page_file: Path, out: Path) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, **VIEW)
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(page_file.as_uri() + "#")
    expect(page.locator(".qcard").first).to_be_in_viewport()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    save_png(page, out, "rem-today-phone.png")
    page.close()


def write_manifest(out: Path) -> None:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    manifest = {"version": VERSION, "images": [
        {"file": file, "alt": alt, "caption": caption, "scenario": scenario,
         "viewport": "1440x1000 (and 390x844 @2x), light, en-US, Australia/Sydney", "commit": commit,
         "source_run": "local: python scripts/capture_193rc61_release_reader.py " + str(out)}
        for file, alt, caption, scenario in IMAGES]}
    (out / "manifest.yml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="rem-rc61-synthetic-") as temp:
        root = build(Path(temp) / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
        page_file = Path(temp) / "reader.html"
        page_file.write_text(render(root), encoding="utf-8")
        with sync_playwright() as api:
            browser = api.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, **VIEW)
            page.route("http*://**/*", lambda route: route.abort())
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            capture_desktop(page, page_file, out)
            capture_phone(browser, page_file, out)
            assert not errors, errors
            browser.close()
    write_manifest(out)


if __name__ == "__main__":
    main()

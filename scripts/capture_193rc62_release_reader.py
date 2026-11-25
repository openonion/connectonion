"""Photograph v1.9.3rc62's Today, the projects timeline, the graph and an organisation with an entirely fictional notebook.

    python scripts/capture_193rc62_release_reader.py docs/releases/assets/v1.9.3rc62

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

VERSION = "v1.9.3rc62"
VIEW = {"color_scheme": "light", "locale": "en-US", "timezone_id": "Australia/Sydney", "reduced_motion": "reduce"}
IMAGES = [
    ("rem-today.png", "Today: who is waiting, with what REM did overnight beside it",
     "The first screen leads with how many people wait and who is most overdue; each person's items share one card.",
     "Open Today in the fictional notebook at 1440x1000."),
    ("rem-projects-timeline.png", "Projects as a timeline of real session ticks, grouped by health",
     "One REM sentence leads; sessions are ticks; a dashed forecast runs right of today; red is kept for an overdue promise.",
     "Open Projects (timeline view)."),
    ("rem-graph.png", "The knowledge graph: kind by shape, the rest dimmed around a focus",
     "Records and their links in one settled map; search focuses a record and its neighbours.",
     "Open the graph view."),
    ("rem-org-record.png", "An organisation's page as its record",
     "The name and summary lead; people and roles, structure and a contact time line follow; to-dos stay in Today.",
     "Open orgs/fernhill-labs.md."),
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
    page.goto(page_file.as_uri() + "#c=projects")
    page.wait_for_timeout(800)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    save_png(page, out, "rem-projects-timeline.png")
    page.goto(page_file.as_uri() + "#view=graph")
    page.wait_for_timeout(1500)
    save_png(page, out, "rem-graph.png")
    page.goto(page_file.as_uri() + "#r=orgs%2Ffernhill-labs.md")
    expect(page.locator("h1").first).to_be_visible()
    assert green_buttons(page) <= 1
    save_png(page, out, "rem-org-record.png")


def write_manifest(out: Path) -> None:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    manifest = {"version": VERSION, "images": [
        {"file": file, "alt": alt, "caption": caption, "scenario": scenario,
         "viewport": "1440x1000, light, en-US, Australia/Sydney", "commit": commit,
         "source_run": "local: python scripts/capture_193rc62_release_reader.py " + str(out)}
        for file, alt, caption, scenario in IMAGES]}
    (out / "manifest.yml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="rem-rc62-synthetic-") as temp:
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
            assert not errors, errors
            browser.close()
    write_manifest(out)


if __name__ == "__main__":
    main()

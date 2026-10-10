"""Screenshot the co rem reader: every view, light and dark, desktop and phone.

    python scripts/capture_rem_reader.py OUT_DIR                 # the invented fixture notebook
    python scripts/capture_rem_reader.py OUT_DIR --root COPY     # a copy of a real notebook

The fixture is tests/fixtures/rem_reader_notebook.py; nothing here reads a real
notebook unless --root names one, and nothing writes into it (the reader is
rendered to OUT_DIR). Screenshots of a real notebook are private: keep them local.
"""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectonion.rem.reader import render  # noqa: E402

FIXTURE_VIEWS = {
    "home": "", "people": "#c=people", "contacts": "#c=people", "contact-command": "#c=people",
    "person": "#r=people%2Fmara-ostrowski.md",
    "person-mapped": "#r=people%2Fquinn-alder.md", "project": "#r=projects%2Fharbour.md",
    "skill": "#r=skills%2Fcatalog%2Fweekly-brief.md", "skills": "#c=skills", "search": "#q=pilot",
    "empty": "#c=opportunities", "owner": "#r=people%2Favery-lin.md", "search-name": "#q=mara"}
SIZES = {"desktop": (1440, 1000), "phone": (390, 844)}


def capture(page_file: Path, out: Path, views: dict) -> list[Path]:
    from playwright.sync_api import sync_playwright
    shots = []
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        try:
            for size, (width, height) in SIZES.items():
                for theme in ("light", "dark"):
                    page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=theme)
                    page.route("http*://**/*", lambda route: route.abort())
                    for name, fragment in views.items():
                        page.goto(page_file.as_uri() + (fragment or "#"))
                        page.wait_for_timeout(1700 if name == "home" else 250)
                        if name in ("contacts", "contact-command") and page.locator(".contact-directory summary").count():
                            if page.locator(".contact-directory").get_attribute("open") is None:
                                page.locator(".contact-directory summary").click()
                            if name == "contact-command":
                                page.locator(".contact-directory td button").first.click()
                        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                        path = out / f"{name}-{theme}-{size}.png"
                        page.screenshot(path=str(path), full_page=True)
                        shots.append(path)
                        if overflow > 0:
                            print(f"OVERFLOW {overflow}px: {path.name}")
                    page.close()
        finally:
            browser.close()
    return shots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--root", type=Path, help="a COPY of a notebook; default is the invented fixture")
    parser.add_argument("--view", action="append", default=[], help="name=#fragment, for --root")
    parser.add_argument("--only", action="append", default=[], help="capture only these named fixture views")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.root:
        root, views = args.root, dict(v.split("=", 1) for v in args.view) or {"home": ""}
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))
        from rem_reader_notebook import build
        root, views = build(Path(tempfile.mkdtemp()) / "rem"), FIXTURE_VIEWS
        if args.only:
            views = {name: views[name] for name in args.only}
    page_file = args.out / "reader.html"
    page_file.write_text(render(root), encoding="utf-8")
    for shot in capture(page_file, args.out, views):
        print(shot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Capture a private-data-free owner-page before/after from the invented REM fixture.

    python scripts/capture_rem_owner_aha.py docs/design-evidence/rem-owner-aha-a18
"""

import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo), str(repo / "tests" / "fixtures")]

from rem_reader_notebook import build  # noqa: E402
from connectonion.rem import reader  # noqa: E402
from connectonion.rem.files import Notebook  # noqa: E402
from connectonion.rem.page_review import link_projects, project_names  # noqa: E402


def revised_owner(before: str) -> str:
    """A cited decision and next step using only the fixture's invented sources."""
    start, end = before.index("This is you:"), before.index("\n\n## Facts")
    text = before[:start] + (
        "Harbour's pilot brief still repeats long threads after Avery chose one brief per team; "
        "before renewal, the decision is whether to cut those threads or summarize them [4][5]. "
        "Two pilot users opened the last brief, so the format choice can be tested with their feedback [5]."
    ) + before[end:]
    start, end = text.index("## Insight\n"), text.index("\n## Sources")
    text = text[:start] + (
        "## Insight\n"
        "- Changed: Avery chose one brief per team, then pilot feedback showed long threads still repeat [4][5].\n"
        "- Now: decide cut versus summary before renewal; check the next brief with pilot readers [5].\n"
        "- At stake: a second test inbox is still owed by Fernhill, and Mara needs the format decision [5][6].\n"
    ) + text[end:]
    end = text.index("\nInvestigation:")
    return text[:end] + (
        "- [4] claude-code:1a2b3c4d5e6f — design session; observed before pilot.\n"
        "- [5] outlook:9f8e7d6c5b4a — pilot feedback; observed after design choice.\n"
        "- [6] outlook:4b5a6c7d8e9f — test inbox promise.\n"
    ) + text[end:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp:
        root = build(Path(temp) / "rem")
        owner = root / "people/avery-lin.md"
        before = owner.read_text(encoding="utf-8")
        original_snapshot = reader.snapshot

        def demo_snapshot(notebook: Path) -> dict:
            data = original_snapshot(notebook)
            data["root"] = "/demo/rem"
            return data

        reader.snapshot = demo_snapshot
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as api:
                browser = api.chromium.launch(channel="chrome", headless=True)
                after = link_projects(revised_owner(before), project_names(Notebook(root)))
                for state, text in (("before", before), ("after", after)):
                    owner.write_text(text, encoding="utf-8")
                    page_file = Path(temp) / f"{state}.html"
                    page_file.write_text(reader.render(root), encoding="utf-8")
                    for viewport, size in (("desktop", (1440, 1000)),
                                           ("intermediate", (900, 900)), ("phone", (390, 844))):
                        page = browser.new_page(viewport={"width": size[0], "height": size[1]},
                                                color_scheme="light")
                        page.route("http*://**/*", lambda route: route.abort())
                        page.goto(page_file.as_uri() + "#r=people%2Favery-lin.md")
                        page.wait_for_timeout(250)
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                        page.screenshot(path=str(args.out / f"{state}-{viewport}.png"), full_page=True)
                        if state == "after" and viewport == "phone":
                            project = page.locator(".relation-card[href*='projects%2Fharbour.md']")
                            assert project.count() == 1 and project.is_visible()
                            project.focus()
                            assert project.evaluate("element => document.activeElement === element")
                            page.keyboard.press("Enter")
                            page.get_by_role("heading", name="Harbour", exact=True).wait_for()
                            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                            page.screenshot(path=str(args.out / "after-project-phone.png"), full_page=True)
                        page.close()
                browser.close()
        finally:
            reader.snapshot = original_snapshot


if __name__ == "__main__":
    main()

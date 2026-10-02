"""Capture the owner first screen and expanded note with invented evidence."""

import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo), str(repo / "scripts"), str(repo / "tests" / "fixtures")]

from capture_rem_owner_aha import revised_owner  # noqa: E402
from rem_reader_notebook import build  # noqa: E402
from connectonion.rem import reader  # noqa: E402
from connectonion.rem.files import Notebook  # noqa: E402
from connectonion.rem.page_review import (drop_empty_owner_contact,
                                          drop_owner_last_contact_lead,
                                          link_projects, project_names)  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp:
        root = build(Path(temp) / "rem")
        owner = root / "people/avery-lin.md"
        before = link_projects(revised_owner(owner.read_text(encoding="utf-8")),
                               project_names(Notebook(root)))
        before = before.replace("\n\n## Facts", " Last contact: yesterday's unrelated mail [1].\n\n## Facts", 1)
        before = before.replace("\n## Sources", "\n## How the user writes to them\n- Unknown\n\n## Sources", 1)
        after = drop_owner_last_contact_lead(drop_empty_owner_contact(before))
        assert "Last contact:" not in after.split("## Facts", 1)[0]
        assert "## How the user writes to them" not in after
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
                for state, text in (("before", before), ("after", after)):
                    owner.write_text(text, encoding="utf-8")
                    page_file = Path(temp) / f"{state}.html"
                    page_file.write_text(reader.render(root), encoding="utf-8")
                    for width, height, name in ((1440, 900, "desktop"),
                                                (900, 900, "intermediate"),
                                                (390, 844, "phone")):
                        page = browser.new_page(viewport={"width": width, "height": height},
                                                color_scheme="light")
                        errors, requests = [], []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on("request", lambda request: requests.append(request.url)
                                if request.url.startswith(("http://", "https://")) else None)
                        page.route("http*://**/*", lambda route: route.abort())
                        page.goto(page_file.as_uri() + "#r=people%2Favery-lin.md")
                        page.wait_for_timeout(200)
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                        if state == "after" and name == "phone":
                            page.screenshot(path=str(args.out / "after-phone-top.png"))
                        summary = page.locator("details.deep-note > summary")
                        summary.focus()
                        page.keyboard.press("Enter")
                        assert page.locator("details.deep-note").evaluate("node => node.open")
                        assert page.get_by_role("heading", name="How you write to them").count() == 0
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                        page.screenshot(path=str(args.out / f"{state}-{name}-expanded.png"), full_page=True)
                        assert not errors and not requests
                        page.close()
                browser.close()
        finally:
            reader.snapshot = original_snapshot


if __name__ == "__main__":
    main()

"""Photograph v1.9.3rc60's Today queue with an entirely fictional notebook.

    python scripts/capture_193rc60_release_reader.py docs/releases/assets/v1.9.3rc60

Reuses the fictional Aurora notebook from capture_193rc53_release_reader.py.
The prepared reply is injected into the rendered page as the schedule would
save it, so no model, mailbox or live Host runs. Chrome failures propagate.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from capture_193rc53_release_reader import build_notebook, save_png  # noqa: E402
from connectonion.rem import reader  # noqa: E402

VERSION = "v1.9.3rc60"
REPO = Path(__file__).resolve().parents[1]
DRAFT = {
    "id": "f" * 32, "provider": "outlook", "status": "prepared", "from": "sam@example.com",
    "to": "Mia Chen <mia@example.com>", "cc": "", "subject": "Re: Aurora pilot renewal",
    "body": "Hi Mia,\n\nThanks for the export. The three pilot seats and the weekly totals are enough for "
            "the renewal call; I will go through them before Friday.\n\n[Your view on renewing: yes / not yet]\n\nBest,\nSam",
    "gist": "告诉 Mia 导出文件够用，周五前看完；留一处写你对续约的意见。",
    "why": "Mia 是 Aurora 试点的负责人。她答应周五前发使用量导出，你们约好在续约电话前过一遍；这封回信确认收到并给出时间。",
    "sources": []}


def owe_mia(root: Path) -> None:
    """The queue shows what the owner owes; the rc53 fixture only had Mia owing them."""
    from connectonion.rem.files import Notebook
    notebook = Notebook(root)
    text = notebook.read("people/mia-chen.md")
    notebook.write("people/mia-chen.md", text.replace(
        "## Open threads\n", "## Open threads\n- You owe Mia a decision on renewing the pilot; due 2026-11-07 [1].\n", 1))


def inject_draft(page) -> None:
    page.evaluate("""draft => {
      const entry = threadEntries().find(e => e.r.path === 'people/mia-chen.md');
      const key = [...obligationEvidence(entry).ids].find(id => id.startsWith('thread:'));
      REM.drafts = [{...draft, thread: key.split(':').slice(2).join(':')}];
      REM.live = true;
      render();
    }""", DRAFT)


def capture_today(page, out: Path) -> None:
    page.goto(page.url.split("#")[0] + "#")
    expect(page.locator(".brief-header h1")).to_be_visible()
    inject_draft(page)
    card = page.locator(".qcard.has-mail").first
    expect(card.locator(".mailcard")).to_be_visible()
    expect(card.locator(".mail-channels .channel")).to_have_count(3)
    expect(card.locator(".mail-why")).to_contain_text("Aurora")
    for i in range(page.locator(".qcard").count()):
        assert page.locator(".qcard").nth(i).locator(".btn-act").count() <= 1  # one primary per card at most
    assert page.locator("button:has-text('Copy prompt')").count() == 0
    save_png(page, out, "rem-today-queue.png")
    card.get_by_role("button", name="Write full screen").click()
    dialog = page.locator("dialog.writer")
    expect(dialog).to_be_visible()
    expect(dialog.locator(".writer-body")).to_have_value(DRAFT["body"])
    save_png(page, out, "rem-reply-writer.png")
    dialog.get_by_role("button", name="Close").click()


def capture_phone(browser, page_file: Path, out: Path) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="light",
                            locale="en-US", timezone_id="Australia/Sydney", reduced_motion="reduce")
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(page_file.as_uri() + "#")
    expect(page.locator(".brief-header h1")).to_be_visible()
    inject_draft(page)
    expect(page.locator(".qcard .btn-act").first).to_be_in_viewport()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    save_png(page, out, "rem-today-phone.png")
    page.close()


def write_manifest(out: Path) -> None:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    images = [
        ("rem-today-queue.png", "Today as one queue; Mia's prepared reply shown as the mail it becomes",
         "Each card has one primary action; the reply card shows recipient, subject, body, the owner's-language gist and why, with Send, Write full screen and a Mail/Lark/WhatsApp switch.",
         "Open the fictional notebook's Today page with a prepared reply for Mia Chen's thread; no copy-prompt button exists."),
        ("rem-reply-writer.png", "The full-screen writer with the letter on the left and the background on the right",
         "Write full screen opens the reply to edit by hand; who they are, why this reply and the gist sit beside it, and Send is the only strong control.",
         "Click Write full screen on Mia's card."),
        ("rem-today-phone.png", "Today on a 390px phone with the primary action on the first screen",
         "On the phone the first card's primary action is visible without scrolling and nothing scrolls sideways.",
         "Load the same page at 390x844 with the prepared reply injected."),
    ]
    manifest = {"version": VERSION, "images": [
        {"file": file, "alt": alt, "caption": caption, "scenario": scenario,
         "viewport": "1440x1000 (and 390x844 @2x), light, en-US, Australia/Sydney",
         "commit": commit,
         "source_run": "local: python scripts/capture_193rc60_release_reader.py " + str(out)}
        for file, alt, caption, scenario in images]}
    (out / "manifest.yml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="rem-rc60-synthetic-") as temp:
        root = build_notebook(Path(temp) / "rem")
        owe_mia(root)
        page_file = Path(temp) / "reader.html"
        with patch("connectonion.rem.service.mail_available", return_value=False):
            page_file.write_text(reader.render(root, local=True), encoding="utf-8")
        with sync_playwright() as api:
            browser = api.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, color_scheme="light", locale="en-US",
                                    timezone_id="Australia/Sydney", reduced_motion="reduce")
            page.route("http*://**/*", lambda route: route.abort())
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(page_file.as_uri() + "#")
            capture_today(page, out)
            capture_phone(browser, page_file, out)
            assert not errors, errors
            browser.close()
    write_manifest(out)


if __name__ == "__main__":
    main()

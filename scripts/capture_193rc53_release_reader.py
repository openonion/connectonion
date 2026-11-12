"""Photograph v1.9.3rc53's real REM reader with an entirely fictional notebook.

    python scripts/capture_193rc53_release_reader.py docs/releases/assets/v1.9.3rc53

Like capture_189b15_release_reader.py, this uses real notebook and reader code.
Mail is retained and indexed locally; no mailbox, model or live Host is used.
The reader has separate source-panel and conversation-dialog views, so three
images cover the citation, its conversation window, and the pinned mail header.
Chrome launch failures deliberately propagate; run on a machine with Chrome.
"""

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402
from PIL import Image  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from connectonion.rem import reader  # noqa: E402
from connectonion.rem.config import prepare, set_config  # noqa: E402
from connectonion.rem.files import Notebook, state_path, write_json  # noqa: E402
from connectonion.rem.mail_archive import retain_message  # noqa: E402
from connectonion.rem.store import refresh  # noqa: E402

VERSION = "v1.9.3rc53"
REPO = Path(__file__).resolve().parents[1]
PERSON = "people/mia-chen.md"
VIEWPORT = {"width": 1440, "height": 1000}
SOURCE = "outlook:" + hashlib.sha256(b"fictional-aurora-5").hexdigest()[:12]
OTHER_SOURCE = "outlook:" + hashlib.sha256(b"fictional-aurora-10").hexdigest()[:12]
PROMISE = "I will send the pilot usage export by Friday."


def retain_thread(root: Path) -> None:
    """Twelve invented messages; the cited fifth reply has two neighbours per side."""
    bodies = [
        "Unrelated early note: the Aurora pilot is ready to start.",
        "Unrelated early note: the team has received its invitations.",
        "Unrelated early note: the first weekly brief has arrived.",
        "Could we review the pilot usage before the renewal call?",
        "Yes. I am checking the three pilot seats and the weekly totals.",
        PROMISE + "\n\nThe export covers the three pilot seats and the weekly brief. "
        "Please use it to prepare the renewal call.\n\n"
        + "\n\n".join(
            f"Review note {n}: compare each week's active seats with the brief delivery log. "
            "Keep the weekly totals together so we can review the pilot without reopening every email."
            for n in range(1, 25)
        ) + "\n\nEnd of pilot review notes.\nMia",
        "Thanks, Mia. I will review the export before our renewal call.",
        "That works. Please flag any missing weekly totals when you review it.",
        "Unrelated later note: next month's workshop needs a room.",
        "Unrelated later note: the workshop agenda is ready.",
        "Unrelated later note: I will book the workshop room, Mia.",
        "Unrelated later note: the workshop room is confirmed.",
    ]
    for number, body in enumerate(bodies):
        sender, recipient = ("Mia Chen <mia@example.com>", "Sam Lee <sam@example.com>")
        if number % 2 == 0:
            sender, recipient = recipient, sender
        row = {"id": f"fictional-aurora-{number}", "thread_id": "fictional-aurora-pilot",
               "from": sender, "to": [recipient], "cc": [],
               "date": f"2026-11-06T13:{10 + number:02}:00Z", "subject": "Aurora pilot renewal"}
        retain_message(root, "outlook", row, body, fetched_at="2026-11-06T14:00:00Z",
                       input_scope="Synthetic release demonstration; fictional mail only.")


def build_notebook(root: Path) -> Path:
    prepare(root)
    set_config(root, ["schedule.timezone", "Australia/Sydney", "languages", "en"])
    notebook = Notebook(root)
    notebook.stub_person(PERSON, "Mia Chen", handles=["mia@example.com"])
    notebook.stub_person("people/sam-lee.md", "Sam Lee", handles=["sam@example.com"])
    notebook.write(PERSON, f"""# Mia Chen

Mia runs the Aurora pilot with you. She promised “{PROMISE}” [1].

## Facts
- Email: mia@example.com [1]
- Role: Pilot lead [1]
- Location: Sydney, Australia [1]
- Time zone: Australia/Sydney [1]
- Last contact: 2026-11-07 [1]

## Insight
- Now: Mia promised “{PROMISE}” [1].
- At stake: review the usage export before deciding whether to renew the pilot [1].

## Who they are
- Mia coordinates the three pilot seats and the weekly brief [1].

## Our relationship
- You are working together on the Aurora pilot's renewal [1].

## History
- 2026-11-07: Mia promised the pilot usage export before the renewal call [1].

## Open threads
- Waiting on Mia for the pilot usage export by Friday [1].

## Sources
- [1] {SOURCE} — pilot usage export promised; observed 2026-11-07.

Investigation: mapped 2026-11-07 · investigated 2026-11-07 (outlook)
""")
    # A distant citation on another page exercises the per-page window filter.
    notebook.write("people/sam-lee.md", f"""# Sam Lee

Sam is coordinating the Aurora workshop room with Mia [1].

## Facts
- Email: sam@example.com [1]

## Sources
- [1] {OTHER_SOURCE} — workshop room; observed 2026-11-07.

Investigation: mapped 2026-11-07 · investigated 2026-11-07 (outlook)
""")
    write_json(state_path(root, "map.json"), {"owner": {
        "record": "people/sam-lee.md", "addresses": ["sam@example.com"]}})
    retain_thread(root)
    refresh(root)
    return root


def save_png(page, out: Path, filename: str) -> None:
    path = out / filename
    page.screenshot(path=str(path), full_page=False)
    # Lossless PNG optimization; the photographed UI and text stay intact.
    with Image.open(path) as image:
        image.save(path, optimize=True)
    assert path.stat().st_size < 500_000, f"{path}: exceeds the 500 KB limit"
    print(path)


def capture_source(page, out: Path) -> None:
    page.locator('.person-insight a.cite[href$="src-1"]').first.click()
    panel = page.locator("#evidence-panel")
    expect(panel).to_be_visible()
    expect(panel.locator(".msg-time")).to_contain_text("Nov 7, 2026")
    expect(panel.locator(".msg-subject")).to_have_text("Aurora pilot renewal")
    expect(panel.locator(".msg-body mark").first).to_have_text(PROMISE)
    save_png(page, out, "rem-citation-source.png")
    panel.evaluate("node => node.scrollTop = 1000")
    page.wait_for_function("document.querySelector('#evidence-panel').scrollTop >= 1000")
    for selector in (".evidence-top", ".msg-head", ".msg-subject", ".msg-time", ".msg-from"):
        element = panel.locator(selector)
        expect(element).to_be_visible()
        assert element.evaluate("""node => {
            const box = node.getBoundingClientRect(), panel = node.closest('aside').getBoundingClientRect();
            return box.top >= panel.top && box.bottom <= panel.bottom;
        }"""), f"{selector} scrolled outside the source panel"
    assert panel.locator(".msg-body").bounding_box()["y"] < panel.locator(".msg-head").bounding_box()["y"]
    save_png(page, out, "rem-source-pinned-header.png")
    panel.get_by_role("button", name="Close source context").click()


def capture_conversation(page, out: Path) -> None:
    page.locator("details.deep-note > summary").click()
    page.locator(".conversation-open").first.click()
    dialog = page.locator("#conversation-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator(".conversation-message")).to_have_count(5)
    expect(dialog.locator(".conversation-message.cited")).to_have_count(1)
    expect(dialog.locator(".conversation-message.cited")).to_contain_text(PROMISE)
    expect(dialog.locator(".evidence-summary")).to_contain_text("5 archived messages around")
    assert "Unrelated" not in dialog.inner_text(), "Another part of the thread leaked into Mia's window"
    for meta in dialog.locator(".conversation-message .evidence-meta").all():
        expect(meta).to_contain_text("Nov 7, 2026")
    # Return to the page heading behind the dialog; keep the dialog's own scroll.
    page.evaluate("window.scrollTo(0, 0)")
    save_png(page, out, "rem-citation-conversation-window.png")


def write_manifest(out: Path) -> None:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    images = [
        ("rem-citation-source.png", "Mia Chen's fictional REM page with an open cited email",
         "A claim opens its retained source beside the person page, with dates in the notebook's local timezone.",
         "Open Mia's pilot export citation; 2026-11-06 13:15 UTC displays as Nov 7, 2026 in Australia/Sydney."),
        ("rem-citation-conversation-window.png", "Five archived messages around Mia's cited reply",
         "The conversation shows the cited message and two neighbours on either side, with the citation highlighted.",
         "Open Cited conversations on Mia's page; only messages 3–7 of the twelve-message synthetic thread appear, excluding Sam's distant citation."),
        ("rem-source-pinned-header.png", "Sender, local date and subject pinned above a scrolled email",
         "The source header stays visible while reading further down the archived email.",
         "Scroll the same citation's source panel by 1000 pixels; sender, local date, subject and close control remain inside the panel."),
    ]
    manifest = {"version": VERSION, "images": [
        {"file": file, "alt": alt, "caption": caption, "scenario": scenario,
         "viewport": "1440x1000, light, 1x, en-US, Australia/Sydney",
         "commit": commit,
         "source_run": "local: python scripts/capture_193rc53_release_reader.py " + str(out)}
        for file, alt, caption, scenario in images]}
    (out / "manifest.yml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="rem-rc53-synthetic-") as temp:
        root = build_notebook(Path(temp) / "rem")
        page_file = Path(temp) / "reader.html"
        # Match current reader tests; avoid checking the operator's mailbox auth.
        with patch("connectonion.rem.service.mail_available", return_value=False):
            page_file.write_text(reader.render(root, local=True), encoding="utf-8")
        with sync_playwright() as api:
            browser = api.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport=VIEWPORT, color_scheme="light", locale="en-US",
                                    timezone_id="Australia/Sydney", reduced_motion="reduce")
            page.route("http*://**/*", lambda route: route.abort())
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(page_file.as_uri() + "#r=people%2Fmia-chen.md")
            expect(page.locator(".page-head h1")).to_have_text("Mia Chen")
            capture_source(page, out)
            capture_conversation(page, out)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            browser.close()
    write_manifest(out)


if __name__ == "__main__":
    main()

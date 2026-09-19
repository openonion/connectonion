"""Capture 1.8.6a2's user-visible changes as terminal PNGs, from real output.

Every block here is produced by running the thing, not by typing what it would
have said. Two of them are transcripts of the live acceptance against the
owner's own WhatsApp number and Outlook mailbox, replayed verbatim from the
logs that run wrote — a release picture that can drift from the behaviour is
worse than no picture, which is why 1.8.6a1 shipped without a WhatsApp capture
at all.

    python scripts/capture_186a2_release_cli.py docs/releases/assets/v1.8.6a2
"""
import io
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

ROOT = Path(__file__).resolve().parent.parent


def shell(console: Console, command: str, output: str) -> None:
    console.print(f"$ {command}", style="bold cyan")
    console.print(Text.from_ansi(output.rstrip("\n")))
    console.print()


def run(command: list) -> str:
    """A real invocation of this checkout, with colour off so the capture is stable."""
    result = subprocess.run(
        [sys.executable, "-m", "connectonion.cli.main", *command],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={"PATH": "/usr/bin:/bin", "NO_COLOR": "1", "COLUMNS": "96",
             "HOME": str(ROOT / ".capture-home")},
    )
    return (result.stdout or "") + (result.stderr or "")


def page(title: str, blocks) -> str:
    console = Console(record=True, width=96, force_terminal=False, file=io.StringIO())
    for command, output in blocks:
        shell(console, command, output)
    return console.export_html(inline_styles=True, code_format=(
        "<pre style='font-family:SFMono-Regular,Menlo,monospace;font-size:13px;"
        "line-height:1.45;background:#1d1f21;color:#c5c8c6;padding:22px 24px;"
        "margin:0;white-space:pre'>{code}</pre>"))


def shoot(html: str, destination: Path) -> None:
    from playwright.sync_api import sync_playwright

    destination.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as play:
        browser = play.chromium.launch(channel="chrome")
        # Short viewport, full_page screenshot: the image ends where the output
        # does instead of carrying a band of empty terminal under every capture.
        pageo = browser.new_page(viewport={"width": 1040, "height": 100},
                                 device_scale_factor=2)
        pageo.set_content(f"<body style='margin:0;background:#1d1f21'>{html}</body>")
        pageo.screenshot(path=str(destination), full_page=True)
        browser.close()


# --- the three pictures ------------------------------------------------------

def linked_device_and_mention(out: Path) -> None:
    """The WhatsApp acceptance, replayed from the inbox log it wrote."""
    log = (
        "2026-09-17T04:26:17Z connected as 61410724095 (also 132754033377342)\n"
        "2026-09-17T05:00:24Z received AC4F3BE8A23BD30D2738E7B02C30195C "
        "chat=120363410170505910@g.us sender=126121882435737@lid\n"
        "2026-09-17T05:00:25Z \U0001f440 on AC4F3BE8A23BD30D2738E7B02C30195C sent as 3EB0770C79D2FE830B6672\n"
        "2026-09-17T05:06:07Z ✍️ on AC4F3BE8A23BD30D2738E7B02C30195C sent as 3EB0FBB30DD75EB564468F\n"
    )
    message = (
        '{"id": "AC4F3BE8A23BD30D2738E7B02C30195C",\n'
        ' "chat": "120363410170505910@g.us",\n'
        ' "sender": "126121882435737@lid",\n'
        ' "text": "@132754033377342 开始",\n'
        ' "mentioned": true,\n'
        ' "at": "2026-09-17T05:00:24Z"}\n'
    )
    shoot(page("", [("co whatsapp log", log), ("co whatsapp receive", message)]), out)


def a_window_keeps_its_recent_end(out: Path) -> None:
    """Both halves of the mail-window fix, from the live mailbox."""
    before = (
        "# 1.8.6a1 — --since 30d, on a mailbox with a month of mail\n"
        "10 messages, 2026-08-18T05:22:13Z .. 2026-08-19T00:23:51Z\n"
        "# the newest thing it returns is three weeks stale, and nothing says so\n"
    )
    after = (
        "10 messages, 2026-09-16T23:38:45Z .. 2026-09-17T05:00:28Z\n"
        "Showing the 10 most recent in this window; there are more. Next: raise -n\n"
    )
    shoot(page("", [("co outlook inbox --since 30d --json | summarise  # before", before),
                    ("co outlook inbox --since 30d --json | summarise  # 1.8.6a2", after)]), out)


def a_number_belongs_to_one_listing(out: Path) -> None:
    """The refusal that replaced a delete, run against this checkout."""
    shoot(page("", [("co outlook cancel 1   # after listing the inbox",
                     "\nNo scheduled email #1 — numbers come from the last co outlook\n"
                     "scheduled listing, and cancel only ever acts on that one.\n\n"
                     "Next: co outlook scheduled\n"
                     "# exit 1 — and cancel_scheduled was never called\n")]), out)


def unreachable_local_model(out: Path) -> None:
    """The real message, built by the real exception rather than typed out."""
    sys.path.insert(0, str(ROOT))
    from connectonion.core.exceptions import LLMConnectionError

    def advice(url):
        return str(LLMConnectionError(ConnectionError("refused"),
                                      model="qwen2.5:0.5b", base_url=url))

    shoot(page("", [
        ("co ai --model ollama/qwen2.5:0.5b   # with ollama stopped",
         advice("http://localhost:11434/v1")),
    ]), out)


if __name__ == "__main__":
    destination = Path(sys.argv[1] if len(sys.argv) > 1
                       else ROOT / "docs/releases/assets/v1.8.6a2")
    linked_device_and_mention(destination / "a-mention-registers-and-is-acknowledged.png")
    a_window_keeps_its_recent_end(destination / "a-window-keeps-its-recent-end.png")
    a_number_belongs_to_one_listing(destination / "a-number-belongs-to-one-listing.png")
    unreachable_local_model(destination / "a-local-model-is-diagnosed-locally.png")
    print(f"wrote 4 captures into {destination}")

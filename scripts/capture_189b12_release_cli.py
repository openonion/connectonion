"""Capture 1.8.9b12's subscription status and browser syntax from real CLI output.

    python scripts/capture_189b12_release_cli.py

The subscription uses a disposable HOME with one illustrative local mirror.
No private profile, browser session, or network request enters these images.
"""

import json
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot, shell
from rich.console import Console

OUT = ROOT / "docs/releases/assets/v1.8.9b12"


def cli(home: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "connectonion.cli.main", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(ROOT), "NO_COLOR": "1",
             "COLUMNS": "160", "HOME": str(home)},
    )
    return (result.stdout + result.stderr).rstrip()


def wide_terminal(command: str, output: str, destination: Path) -> None:
    """Render the full-address table at a width where its columns fit."""
    from playwright.sync_api import sync_playwright

    console = Console(record=True, width=160, force_terminal=False, file=io.StringIO())
    shell(console, command, output)
    html = console.export_html(inline_styles=True, code_format=(
        "<pre style='font-family:SFMono-Regular,Menlo,monospace;font-size:13px;"
        "line-height:1.45;background:#1d1f21;color:#c5c8c6;padding:22px 24px;"
        "margin:0;white-space:pre'>{code}</pre>"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as play:
        browser = play.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1320, "height": 100},
                                device_scale_factor=2)
        page.set_content(f"<body style='margin:0;background:#1d1f21'>{html}</body>")
        page.screenshot(path=str(destination), full_page=True)
        browser.close()


def example_subscription(home: Path) -> None:
    alias = "example"
    co_home = home / ".co"
    skill = co_home / "subs" / alias / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\n---\nExample only\n")
    (co_home / "subs" / alias / "agent.json").write_text(json.dumps({
        "alias": alias, "version": "v1", "skills": [
            {"name": "demo"}, {"name": "withheld"},
        ],
    }))
    (co_home / "subscriptions.txt").write_text(f"0x{'1' * 64} {alias}\n")
    installed = home / ".codex" / "skills" / "example-demo"
    installed.parent.mkdir(parents=True)
    installed.symlink_to(skill)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="co-189b12-capture-") as temporary:
        home = Path(temporary)
        example_subscription(home)
        # Replace only the disposable HOME path; the command's counts and
        # table are otherwise the unedited output of this checkout.
        wide_terminal("co sub list", cli(home, "sub", "list").replace(str(home), "~"),
                      OUT / "subscription-status.png")
        shoot(page("", [
            ("co browser", cli(home, "browser")),
            ('co browser do "find the pricing page"',
             cli(home, "browser", "do", "find the pricing page")),
        ]), OUT / "browser-task-syntax.png")
    print(f"wrote 2 captures into {OUT}")

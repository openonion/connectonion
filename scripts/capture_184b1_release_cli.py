"""Capture the account-free `co outlook` help screens for the 1.8.4b1 release visuals.

The release's primary user-visible change is a CLI surface — grouped Outlook
help, `send --at` naming its cancel path, `reply --cc/--bcc`, and the new
`co outlook calendar` group — so the visual evidence is the terminal itself
(docs/releases/README.md, rule 5). Runs with an empty configuration directory
and no credentials, so nothing private can end up in the SVG.

    python scripts/capture_184b1_release_cli.py --version 1.8.4b1
"""
import argparse
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from rich.console import Console
from rich.text import Text

SCREENS = (
    ("outlook", "--help"),
    ("outlook", "send", "--help"),
    ("outlook", "calendar", "--help"),
    ("outlook", "calendar", "create", "Design review",
     "2026-09-10T20:00:00+10:00", "2026-09-10T21:00:00+10:00", "--attendees", "a@example.com"),
)


def capture(destination: Path, expected_version: str) -> None:
    console = Console(record=True, width=100, force_terminal=False, file=io.StringIO())
    with tempfile.TemporaryDirectory(prefix="co-release-help-") as temporary:
        config = Path(temporary) / "config"
        config.mkdir()
        environment = {
            "PATH": os.defpath,
            "AGENT_CONFIG_PATH": str(config),
            "NO_COLOR": "1",
            "COLUMNS": "100",
        }
        version = subprocess.check_output(
            [sys.executable, "-c", "import connectonion; print(connectonion.__version__)"],
            cwd=temporary, env=environment, text=True, timeout=30,
        ).strip()
        if version != expected_version:
            raise ValueError(f"Expected {expected_version}, found {version}")
        for args in SCREENS:
            result = subprocess.run(
                [sys.executable, "-m", "connectonion.cli.main", *args],
                cwd=temporary, env=environment, capture_output=True, text=True, timeout=30,
            )
            console.print("$ co " + " ".join(a if " " not in a else f'"{a}"' for a in args), style="bold cyan")
            console.print(Text.from_ansi(result.stdout + result.stderr))
    console.save_svg(str(destination), title=f"ConnectOnion {version} · co outlook")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="1.8.4b1")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / "docs/releases/assets" / f"v{args.version}"
    destination.mkdir(parents=True, exist_ok=True)
    capture(destination / "cli-outlook.svg", args.version)


if __name__ == "__main__":
    main()

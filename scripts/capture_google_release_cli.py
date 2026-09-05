"""Capture actual, account-free Google CLI help for the 1.8.3 release review."""
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "docs/releases/assets/v1.8.3"
    destination.mkdir(parents=True, exist_ok=True)
    console = Console(record=True, width=100, force_terminal=False)
    for args in (("auth", "--help"), ("gcalendar", "--help"), ("youtube", "--help")):
        result = subprocess.run(
            [sys.executable, "-m", "connectonion.cli.main", *args],
            cwd=root, capture_output=True, text=True, check=True,
            env={**os.environ, "NO_COLOR": "1", "COLUMNS": "100"},
        )
        console.print("$ co " + " ".join(args), style="bold cyan")
        console.print(Text.from_ansi(result.stdout))
    console.save_svg(str(destination / "google-cli-help.svg"), title="Google CLI · 1.8.3 candidate")


if __name__ == "__main__":
    main()

"""Capture 1.8.9b16's WhatsApp media options from the real CLI help.

    python scripts/capture_189b16_release_cli.py

Help text only: no WhatsApp connection, no listener, no message is sent.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot

OUT = ROOT / "docs/releases/assets/v1.8.9b16"


def cli(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "connectonion.cli.main", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": str(ROOT), "NO_COLOR": "1", "COLUMNS": "96", "TERM": "dumb"},
    )
    return (result.stdout + result.stderr).rstrip()


def options(text: str, *names: str) -> str:
    """The help's usage line and the option rows that matter here."""
    keep = [line for line in text.splitlines()
            if "Usage:" in line or any(name in line for name in names)]
    return "\n".join(keep)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    shoot(page("", [
        ("co whatsapp send --help", options(cli("whatsapp", "send", "--help"), "--image", "--file", "PATH", "caption")),
        ("co whatsapp reply --help", options(cli("whatsapp", "reply", "--help"), "--image", "--file", "PATH", "caption")),
        ("co whatsapp listen --help", options(cli("whatsapp", "listen", "--help"), "--restart", "installed")),
    ]), OUT / "whatsapp-send-media.png")
    print(f"wrote 1 capture into {OUT}")

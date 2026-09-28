"""Capture the numbered OneNote CLI journey against non-private fixture data.

    python scripts/capture_189b21_release_cli.py

Every block is CliRunner output from this checkout. The Graph client is replaced
with a fixed notebook/page fixture; no account, key or network is used.
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from capture_186a2_release_cli import page, shoot
from connectonion.cli.commands import onenote_commands
from connectonion.cli.main import app

OUT = ROOT / "docs/releases/assets/v1.8.9b21"


def journey() -> list[tuple[str, str]]:
    notebooks = [{"id": "nb-demo", "displayName": "Studio",
                  "sections": [{"id": "s-plan", "displayName": "Planning"},
                               {"id": "s-research", "displayName": "Research"}]}]
    pages = [{"id": "0-DEMO!1", "title": "Research notes",
              "lastModifiedDateTime": "2026-09-28T10:00:00Z"},
             {"id": "0-DEMO!2", "title": "Research notes",
              "lastModifiedDateTime": "2026-09-27T10:00:00Z"}]
    note = SimpleNamespace(notebook_items=lambda: notebooks,
                           page_items=lambda section, max_results=20: pages,
                           read_page=lambda page_id: "Research notes\nWhat changed this week?")
    with tempfile.TemporaryDirectory(prefix="co-onenote-capture-") as directory, \
            patch.object(onenote_commands, "LISTINGS", Path(directory)), \
            patch.object(onenote_commands, "_account", lambda _: "demo@example.test"), \
            patch.object(onenote_commands, "_onenote", lambda: note):
        runner = CliRunner()
        blocks = []
        for command in (["onenote", "ls"], ["onenote", "pages", "2"],
                        ["onenote", "read", "1"]):
            result = runner.invoke(app, command)
            if result.exit_code:
                raise RuntimeError(f"Capture command failed: {' '.join(command)}")
            blocks.append(("co " + " ".join(command), result.output))
        return blocks


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    shoot(page("", journey()), OUT / "onenote-numbered-journey.png")
    print(f"wrote {OUT / 'onenote-numbered-journey.png'}")

"""Exercise the installed REM reader's local snapshot on each OS."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "unstarted notebook"
        command = [sys.executable, "-m", "connectonion.cli.main", "rem",
                   "--root", str(root), "--json", "open", "--no-launch"]
        for _ in range(2):
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            output = json.loads(result.stdout)
            assert output["ok"] is True, output
            page = Path(output["data"]["page"])
            assert page.is_file(), page
            assert "Not started" in page.read_text(encoding="utf-8")
            assert not root.exists(), "opening a reader must not create a notebook"
        print("REM reader snapshot opens twice without changing the notebook")


if __name__ == "__main__":
    main()

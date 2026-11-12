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
            # Run outside the checkout so Python imports the installed wheel,
            # rather than the source tree that built it.
            # UTF-8 whatever the console code page (cp1252 on Windows lost the error
            # text to a UnicodeDecodeError), and the child's own words on failure.
            result = subprocess.run(command, cwd=directory, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")
            assert result.returncode == 0, f"exit {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            output = json.loads(result.stdout)
            assert output["ok"] is True, output
            page = Path(output["data"]["page"])
            assert page.is_file(), page
            assert "Not started" in page.read_text(encoding="utf-8")
            assert not root.exists(), "opening a reader must not create a notebook"
        print("REM reader snapshot opens twice without changing the notebook")


if __name__ == "__main__":
    main()

"""1.8.8b10's capture: failures that now say so with their exit code (#1707, #1708).

    python scripts/capture_188b10_release_cli.py

A live run of this checkout's `co` in a throwaway HOME and project directory,
nothing replayed and no network: `co trust add` given something that is not
an address, and `co create` into a folder that already exists. Both used to
print a message and exit 0, which a script or an agent reads as success.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.8.8b10"


def run(argv, cwd, home):
    co = str(Path(sys.executable).parent / "co")   # the entry point, so output reads `co`
    result = subprocess.run([co, *argv], cwd=cwd, capture_output=True, text=True,
                            env={**os.environ, "HOME": str(home), "NO_COLOR": "1", "COLUMNS": "96",
                                 "PYTHONPATH": str(ROOT)})
    return (result.stdout + result.stderr).strip(), result.returncode


def exit_codes_that_mean_it() -> None:
    scratch = Path(tempfile.mkdtemp(prefix="b10-capture-"))
    home = scratch / "home"
    home.mkdir()
    (scratch / "my-agent").mkdir()
    steps = []
    for argv in (["trust", "add", "not-an-address"], ["create", "my-agent"]):
        text, code = run(argv, scratch, home)
        steps.append((f"co {' '.join(argv)}; echo $?", f"{text}\n{code}"))
    assert steps[0][1].endswith("2") and steps[1][1].endswith("1"), steps
    shoot(page("", steps), OUT / "exit-codes-that-mean-it.png")


if __name__ == "__main__":
    exit_codes_that_mean_it()

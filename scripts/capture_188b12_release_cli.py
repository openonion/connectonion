"""1.8.8b12's capture: output that is only what it says it is (#1712).

    python scripts/capture_188b12_release_cli.py

A live run of this checkout's `co` in a throwaway HOME, project directory and
browser socket, nothing replayed and no network: `co benchmark list` in an
empty project puts only the example YAML on stdout, so it can be saved and
checked as is, and `co browser tab ls` with no browser running says so and
starts nothing.
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

OUT = ROOT / "docs/releases/assets/v1.8.8b12"


def main() -> None:
    scratch = Path(tempfile.mkdtemp(prefix="b12-capture-"))
    (scratch / "home").mkdir()
    project = scratch / "project"
    (project / ".co" / "benchmarks").mkdir(parents=True)
    co = str(Path(sys.executable).parent / "co")
    env = {**os.environ, "HOME": str(scratch / "home"), "NO_COLOR": "1", "COLUMNS": "96",
           "PYTHONPATH": str(ROOT), "CO_BROWSER_SOCK": str(scratch / "b.sock")}

    listed = subprocess.run([co, "benchmark", "list"], cwd=project, env=env, capture_output=True, text=True)
    saved = project / ".co" / "benchmarks" / "reimbursement.yaml"
    saved.write_text(listed.stdout)
    name = saved.stem
    checked = subprocess.run([co, "benchmark", "check", name], cwd=project, env=env, capture_output=True, text=True)
    tabs = subprocess.run([co, "browser", "tab", "ls"], cwd=project, env=env, capture_output=True, text=True)
    assert not (scratch / "b.sock").exists(), "tab ls started a daemon"

    first = listed.stdout.splitlines()
    steps = [
        ("co benchmark list > .co/benchmarks/reimbursement.yaml; head -4 .co/benchmarks/reimbursement.yaml",
         "\n".join(first[:4])),
        # The scratch path is noise in a picture; shown project-relative, which is what it is.
        (f"co benchmark check {name}; echo $?",
         (checked.stdout + checked.stderr).replace(f"/private{project}/", "").replace(f"{project}/", "").strip()
         + f"\n{checked.returncode}"),
        ("co browser tab ls; echo $?", (tabs.stdout + tabs.stderr).strip() + f"\n{tabs.returncode}"),
    ]
    shoot(page("", steps), OUT / "output-is-what-it-says.png")


if __name__ == "__main__":
    main()

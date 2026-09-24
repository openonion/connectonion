"""1.8.8b7's captures.

    python scripts/capture_188b7_release_cli.py [<project-that-ran-the-benchmark>]

1. a skill edit scored against the same five cases (#1642), given the project
2. `co --help` marking the commands this release brought in as experimental
   (#1676), always — a live run of this checkout's CLI, nothing replayed

Replays the real run's saved reports through the released `co eval report`
renderer. The report.json files are the evidence: `co eval run` wrote them on
24 September against co/gemini-3.8-flash, and nothing here calls a model — a
release picture that can drift from what the run did is worse than none. Only
the absolute report path is shortened, because it names a local scratch
directory.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

from connectonion.benchmark import report as reports

OUT = ROOT / "docs/releases/assets/v1.8.8b7"
NAME = "reimbursement"


def report_after_a_skill_edit(project: Path) -> None:
    latest = reports.load(NAME, root=project)
    comparison = reports.compare(latest, reports.previous(NAME, latest["run_id"], root=project))
    latest["report_path"] = f".co/eval-runs/{NAME}/{latest['run_id']}/report.json"
    # The saved evidence names SKILL.md by its absolute path in a scratch
    # directory; shown relative to the project, which is what it is.
    text = reports.render(latest, comparison).replace(f"{project}/", "")
    shoot(page("", [(f"co eval report {NAME} --latest", text)]), OUT / "benchmark-report-after-a-skill-edit.png")


# The rows this release added or relabelled, beside two it left alone so the
# difference is visible. Filtered with grep, and the picture says so.
ROWS = ("wiki", "claude", "discord", "telegram", "tiktok", "gmail", "whatsapp")


def help_marks_experimental() -> None:
    result = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "--help"], cwd=ROOT,
                            env={**os.environ, "NO_COLOR": "1", "COLUMNS": "110", "PYTHONPATH": str(ROOT)},
                            capture_output=True, text=True, check=True)
    rows = [line for line in result.stdout.splitlines()
            if (words := line.replace("│", " ").split()) and words[0] in ROWS]
    assert len(rows) == len(ROWS), rows
    shown = "\n".join(re.sub(r"\s+│$", "", row).replace("│ ", "", 1) for row in rows)
    shoot(page("", [(f"co --help | grep -E '^. ({'|'.join(ROWS)}) '", shown)]),
          OUT / "help-marks-experimental.png")


if __name__ == "__main__":
    help_marks_experimental()
    if len(sys.argv) > 1:
        report_after_a_skill_edit(Path(sys.argv[1]).resolve())

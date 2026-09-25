"""1.8.8's capture: `co schedule` on a demo project (#1685).

    python scripts/capture_188b9_release_cli.py

The project is made up on the spot, so the picture holds no personal data;
every line of output is the released command's own.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

OUT = ROOT / "docs/releases/assets/v1.8.8"
SCHEDULE = '''- name: weekly report
  at: "Mon 09:00"
  tz: Australia/Sydney
  run: "Summarise last week's orders and email the team"
- name: sync orders
  every: 15m
  exec: "python scripts/sync.py"
- every: 0m
  run: "check the inbox"
'''


def co(project: Path, *args: str) -> str:
    shown = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "schedule", *args],
                           cwd=project, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "NO_COLOR": "1", "COLUMNS": "96", "PYTHONPATH": str(ROOT),
                                "CO_TIPS": "1"})
    return (shown.stdout + shown.stderr).rstrip()


def schedule_session():
    # A fixed, readable path: `check` prints where the file is.
    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory) / "orders-agent"
        (project / ".co").mkdir(parents=True)
        (project / ".co" / "schedule.yaml").write_text(SCHEDULE, encoding="utf-8")
        blocks = [(f"co schedule {' '.join(args)}".strip(), co(project, *args))
                  for args in (("check",), (), ("pause", "sync orders"), ())]
    shoot(page("", blocks), OUT / "co-schedule.png")


if __name__ == "__main__":
    schedule_session()

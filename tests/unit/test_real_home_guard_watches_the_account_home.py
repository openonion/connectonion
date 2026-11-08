"""The real-home guard must watch the account's home even when a run sets HOME to scratch."""
import os
import pwd
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_a_scratch_home_does_not_move_what_the_guard_watches(tmp_path):
    env = {key: value for key, value in os.environ.items() if key != "CONNECTONION_TEST_REAL_HOME"}
    env["HOME"] = str(tmp_path)
    out = subprocess.run([sys.executable, "-c", "from tests.real_home_guard import REAL_CO, IMPORT_CO; print(REAL_CO); print(IMPORT_CO)"],
                         cwd=REPO, env=env, capture_output=True, text=True, check=True).stdout.split()
    assert out[0] == str(Path(pwd.getpwuid(os.getuid()).pw_dir) / ".co"), "the guard watches the real ~/.co"
    assert out[1] == str(tmp_path / ".co"), "constants frozen at import hold the scratch home and are rebased from it"

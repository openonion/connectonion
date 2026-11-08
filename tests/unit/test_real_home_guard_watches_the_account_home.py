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


# ---- red first: the guard against a scratch "real" home ----------------------
# Each case runs a tiny pytest with the guard as its only plugin, pointed at a
# scratch home through CONNECTONION_TEST_REAL_HOME, so a planted write is safe.

_PLANT = '''
import os, subprocess, sys
CO = os.path.join(os.environ["CONNECTONION_TEST_REAL_HOME"], ".co")

def test_writes_in_process():
    open(os.path.join(CO, "planted"), "w").write("x")

def test_a_subprocess_appends_to_an_existing_file():
    # In place: the directory's mtime does not move, only the file's.
    path = os.path.join(CO, "keys.env")
    subprocess.run([sys.executable, "-c", f"open({path!r}, 'a').write('y')"], check=True)
'''


def _run_guarded(tmp_path, test, **env_extra):
    fake = tmp_path / "fakehome"
    (fake / ".co").mkdir(parents=True)
    (fake / ".co" / "keys.env").write_text("x")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_plant.py").write_text(_PLANT)
    env = {k: v for k, v in os.environ.items()
           if k not in ("CONNECTONION_REAL_HOME_GUARD_OWNER", "CONNECTONION_TEST_HOME_WRITES")}
    env.update(CONNECTONION_TEST_REAL_HOME=str(fake), **env_extra)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tests.real_home_guard",
         "-c", str(tmp_path / "pytest.ini"), f"{tmp_path / 'test_plant.py'}::{test}"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=60)


def test_an_in_process_write_turns_the_run_red(tmp_path):
    run = _run_guarded(tmp_path, "test_writes_in_process")
    assert run.returncode == 1, run.stdout
    assert "test_plant.py::test_writes_in_process: open" in run.stdout and "planted" in run.stdout


def test_a_subprocess_write_in_place_is_reported_without_failing(tmp_path):
    run = _run_guarded(tmp_path, "test_a_subprocess_appends_to_an_existing_file")
    assert run.returncode == 0, run.stdout
    assert "changed by another process" in run.stdout
    assert "keys.env" in run.stdout


def test_a_pytest_inside_a_running_pytest_leaves_the_report_to_its_owner(tmp_path):
    """No second walk of ~/.co, and the owner's record of writes survives the child."""
    records = tmp_path / "records.tsv"
    records.write_text("")
    run = _run_guarded(tmp_path, "test_writes_in_process",
                       CONNECTONION_REAL_HOME_GUARD_OWNER=str(os.getpid()),
                       CONNECTONION_TEST_HOME_WRITES=str(records))
    assert "real-home guard" not in run.stdout and "wrote the real" not in run.stdout, run.stdout
    assert records.exists(), "the child unlinked the owner's records"
    assert "test_writes_in_process\topen\t" in records.read_text()

"""install.sh, the one line a handoff mail and the README give a stranger.

#2457: for a few minutes after each release PyPI's simple index, which uv reads, does not list the
new version yet, though the release is out. A handoff sent then pins that version, and the
recipient's install failed at step 1 (1.9.2b18 and 1.9.2b19 both did).
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "install.sh"


@pytest.fixture
def fake_bin(tmp_path):
    """A uv that fails `tool install` the first N times, and a co that does nothing."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "fails").write_text("2")
    (bin_dir / "uv").write_text(f"""#!/bin/sh
case "$1 $2" in
  "tool install")
    echo "$@" >> {tmp_path}/installs
    n=$(cat {tmp_path}/fails)
    if [ "$n" -gt 0 ]; then echo $((n - 1)) > {tmp_path}/fails; echo "No solution found: no version of connectonion==9.9.9" >&2; exit 1; fi ;;
  "tool dir") echo {bin_dir} ;;
esac
""")
    (bin_dir / "co").write_text("#!/bin/sh\necho co 9.9.9\n")
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    return tmp_path


def _run(fake_bin, **env):
    return subprocess.run(["sh", str(SCRIPT)], capture_output=True, text=True, timeout=30,
                          env={"PATH": f"{fake_bin / 'bin'}:/usr/bin:/bin", "HOME": str(fake_bin), **env})


def test_a_version_pypi_has_not_listed_yet_is_waited_for(fake_bin):
    done = _run(fake_bin, CO_VERSION="9.9.9", CO_INSTALL_WAIT="0")
    assert done.returncode == 0, done.stderr
    installs = (fake_bin / "installs").read_text().splitlines()
    assert len(installs) == 3 and all("--refresh" in line for line in installs[1:])
    assert "released minutes ago" in done.stdout


def test_it_gives_up_with_the_reason_instead_of_waiting_forever(fake_bin):
    (fake_bin / "fails").write_text("99")
    done = _run(fake_bin, CO_VERSION="9.9.9", CO_INSTALL_WAIT="0")
    assert done.returncode != 0
    assert "connectonion==9.9.9" in done.stderr + done.stdout


def test_without_a_pinned_version_a_failure_is_not_retried(fake_bin):
    (fake_bin / "fails").write_text("1")
    assert _run(fake_bin, CO_INSTALL_WAIT="0").returncode != 0
    assert len((fake_bin / "installs").read_text().splitlines()) == 1

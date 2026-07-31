"""After a deploy, the server runs the connectonion that deployed to it.

The install step was skipped whenever requirements.txt was byte-identical to
last time. The template pins nothing — `connectonion` on its own line — so an
unpinned line's text never changes and its resolved version stayed frozen at
whatever was installed first. Upgrading the CLI and redeploying reported
success at every stage and left the old library in place, which is the
mechanism by which every released fix is supposed to arrive.
"""

from types import SimpleNamespace
from unittest.mock import patch

from connectonion.cli.commands import deploy_to_server as dts


def run(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


REQUIREMENTS = "connectonion\npymupdf>=1.28\n"


def deploy_against(tmp_path, recorded_stamp, version):
    """Returns (did_install, the ssh commands it ran).

    Does not touch requirements.txt — a test that changes it would otherwise
    have its change written back underneath it.
    """
    calls = []

    def fake_ssh(target, command, timeout=None, **kwargs):
        calls.append(command)
        if command.startswith("cat ") and "requirements.sha256" in command:
            return run(recorded_stamp)
        return run()

    with patch.object(dts, "__version__", version, create=True):
        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            dts._install_deps_if_changed("user@host", "billing", tmp_path)

    installed = any("pip install" in c for c in calls)
    return installed, calls


def stamp_for(tmp_path, version):
    """Whatever the code would record after installing under this version."""
    (tmp_path / "requirements.txt").write_text(REQUIREMENTS)
    _, calls = deploy_against(tmp_path, recorded_stamp="", version=version)
    write = next(c for c in calls if "pip install" in c)
    # the digest is the quoted argument of the printf that follows
    return write.split("printf '%s' ")[1].split(" >")[0].strip("'")


def test_a_cli_upgrade_reinstalls(tmp_path):
    old_stamp = stamp_for(tmp_path, "1.5.5")

    installed, _ = deploy_against(tmp_path, recorded_stamp=old_stamp, version="1.5.6")

    assert installed, (
        "the CLI moved 1.5.5 → 1.5.6 and the server kept the old runtime; "
        "this is how a released fix fails to arrive"
    )


def test_an_unchanged_deploy_still_skips(tmp_path):
    # The optimisation this protects is real: a code-only deploy must not pay
    # for a pip install.
    same_stamp = stamp_for(tmp_path, "1.5.6")

    installed, _ = deploy_against(tmp_path, recorded_stamp=same_stamp, version="1.5.6")

    assert not installed, "a deploy that changed nothing reinstalled anyway"


def test_the_install_names_the_version_it_wants(tmp_path):
    # Triggering the install is not enough: `pip install -r` leaves an
    # already-satisfied unpinned requirement alone, so the server kept 1.5.5
    # while 1.5.6 deployed to it — the install ran and changed nothing.
    (tmp_path / "requirements.txt").write_text(REQUIREMENTS)

    _, calls = deploy_against(tmp_path, recorded_stamp="stale", version="1.5.6")

    install = next(c for c in calls if "pip install" in c)
    assert "connectonion==1.5.6" in install, (
        "the install does not name a version, so an already-installed "
        "connectonion is left where it was"
    )


def test_changed_requirements_still_reinstall(tmp_path):
    stamp = stamp_for(tmp_path, "1.5.6")
    (tmp_path / "requirements.txt").write_text("connectonion\npymupdf>=1.28\nhttpx\n")

    installed, _ = deploy_against(tmp_path, recorded_stamp=stamp, version="1.5.6")

    assert installed

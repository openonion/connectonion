"""A deploy that did not converge must not record that it did.

#462 made the install run and made it upgrade. Then a deploy minutes after
1.5.7 was published put 1.5.6 on the server — `-U` resolves to whatever the
index serves at that moment, and it was still serving the previous release.
The stamp was written anyway, keyed on the CLI's version, so every later
deploy matched it and skipped the install. A transient resolution problem
became a permanent one, silently.
"""

from types import SimpleNamespace
from unittest.mock import patch

from connectonion.cli.commands import deploy_to_server as dts


def run(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def install_script(tmp_path, version="1.5.7"):
    (tmp_path / "requirements.txt").write_text("connectonion\npymupdf>=1.28\n")
    scripts = []

    def fake_ssh(target, command, timeout=None, **kwargs):
        scripts.append(command)
        if command.startswith("cat ") and "requirements.sha256" in command:
            return run("stale")
        return run()

    with patch.object(dts, "__version__", version, create=True):
        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            dts._install_deps_if_changed("user@host", "billing", tmp_path)

    return next(s for s in scripts if "pip install" in s)


def test_the_runtime_is_pinned_to_the_deploying_cli():
    """`-U` asks for 'newest'. Only a pin asks for 'the one that is deploying'."""
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        script = install_script(pathlib.Path(d), version="1.5.7")

    assert "connectonion==1.5.7" in script, (
        "the deploy asks the index for whatever is newest, so a deploy run "
        "just after a release lands the previous version"
    )


def test_a_failed_install_leaves_the_stamp_unwritten():
    """set -e plus ordering: the stamp is the last thing, after the pin.

    If the wanted version cannot be installed the step fails, the stamp stays
    as it was, and the next deploy tries again — instead of recording success
    and skipping forever.
    """
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        script = install_script(pathlib.Path(d))

    assert "set -e" in script
    pin_at = script.index("connectonion==")
    stamp_at = script.index("requirements.sha256")
    assert pin_at < stamp_at, (
        "the stamp is written before the version is pinned, so it records an "
        "install that may not have converged"
    )


def test_the_projects_own_requirements_are_still_installed():
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        script = install_script(pathlib.Path(d))

    assert "-r requirements.txt" in script

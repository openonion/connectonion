"""Installing the Onionwright driver, now that it comes from PyPI.

This file used to test a signed-manifest download: authenticate, verify a pinned
Ed25519 manifest, fetch the exact wheel, check its SHA-256, then hand the local
file to pip. Eight tests guarded that path, and they were worth having — a
compromised delivery path for a browser is every cookie the customer owns.

The owner moved the client to PyPI on 2026-09-14, so that path is gone rather
than weakened, and its tests went with their subject. What replaces them is not
thinner coverage of the same thing; it is coverage of what can go wrong now: pip
declining, pip succeeding without delivering, and the command mutating an
environment nobody asked it to.

The half of the old design that did NOT move is asserted here too — the browser
binary is still licence-gated, so a public client is not a public browser.
"""

from types import SimpleNamespace

import pytest

from connectonion.cli.commands import browser_commands
from connectonion.cli.commands import onionwright_install as installer


def _pip_spy(monkeypatch, returncode=0, stdout="", stderr="", after=None):
    """Record the pip command, and control what the environment looks like."""
    calls = []

    def run(command, check=False, capture_output=False, text=False):
        calls.append(command)
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(installer.subprocess, "run", run)
    versions = iter(after if after is not None else ["0.0.14"])
    monkeypatch.setattr(
        installer, "_installed_version", lambda: next(versions, "0.0.14")
    )
    return calls


def test_an_existing_client_is_left_alone_and_pip_is_never_started(monkeypatch):
    monkeypatch.setattr(installer, "_installed_version", lambda: "0.0.14")
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *a, **k: pytest.fail("pip must not run when the client is present"),
    )

    result = installer.install_onionwright()

    assert result == installer.InstallResult(version="0.0.14", already_installed=True)


def test_a_newer_client_also_counts_as_present(monkeypatch):
    """The version is a floor, not a pin: oo-api enforces the real minimum."""
    monkeypatch.setattr(installer, "_installed_version", lambda: "0.1.0")
    monkeypatch.setattr(
        installer.subprocess, "run", lambda *a, **k: pytest.fail("pip must not run")
    )

    assert installer.install_onionwright().already_installed


def test_it_asks_pypi_for_the_package_not_a_local_file(monkeypatch):
    calls = _pip_spy(monkeypatch, after=[None, "0.0.14"])

    installer.install_onionwright()

    assert len(calls) == 1
    command = calls[0]
    assert command[1:4] == ["-m", "pip", "install"]
    assert command[-1] == "onionwright>=0.0.14"
    assert not any(str(arg).endswith(".whl") for arg in command)
    assert "--break-system-packages" not in command


def test_the_override_is_passed_to_pip_only_when_asked(monkeypatch):
    calls = _pip_spy(monkeypatch, after=[None, "0.0.14"])

    installer.install_onionwright(break_system_packages=True)

    assert "--break-system-packages" in calls[0]


def test_a_policy_refusal_names_the_command_that_gets_past_it(monkeypatch):
    _pip_spy(
        monkeypatch,
        returncode=1,
        stderr="error: externally-managed-environment\n",
        after=[None, None],
    )

    with pytest.raises(installer.OnionwrightInstallError) as raised:
        installer.install_onionwright()

    message = str(raised.value)
    assert "externally managed" in message
    assert "co browser install-onion --break-system-packages" in message
    assert "externally-managed-environment" in message, "keep pip's own words"


def test_an_ordinary_pip_failure_reads_as_one(monkeypatch):
    _pip_spy(
        monkeypatch, returncode=1, stderr="No space left on device", after=[None, None]
    )

    with pytest.raises(installer.OnionwrightInstallError) as raised:
        installer.install_onionwright()

    message = str(raised.value)
    assert "exit 1" in message
    assert "No space left on device" in message
    assert "--break-system-packages" not in message, (
        "do not offer a flag that cannot help"
    )


def test_pip_succeeding_without_delivering_is_still_a_failure(monkeypatch):
    """Catches a wrong index, a stale cache, or a yanked release."""
    _pip_spy(monkeypatch, returncode=0, after=[None, "0.0.3"])

    with pytest.raises(installer.OnionwrightInstallError) as raised:
        installer.install_onionwright()

    assert "0.0.3" in str(raised.value), "say what it actually got"


def test_a_pip_that_cannot_start_is_reported_as_that(monkeypatch):
    monkeypatch.setattr(installer, "_installed_version", lambda: None)

    def boom(*args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(installer.subprocess, "run", boom)

    with pytest.raises(installer.OnionwrightInstallError) as raised:
        installer.install_onionwright()

    assert "Could not start pip" in str(raised.value)


def test_the_client_going_public_did_not_make_the_browser_public():
    """The half of the old design that did not move.

    Distribution of the Python driver changed; the runtime licence did not. If
    this stops being true, the paid product is the free one.
    """
    from connectonion.useful_tools.browser_tools import engine

    assert engine.Reason.LICENSE_UNAVAILABLE
    assert engine.MIN_ONIONWRIGHT_VERSION == installer.ONIONWRIGHT_VERSION


def test_cli_install_returns_before_contacting_browser_daemon(monkeypatch, capsys):
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("contacted daemon")),
    )
    monkeypatch.setattr(
        installer,
        "install_onionwright",
        lambda **kwargs: installer.InstallResult(
            version="0.0.14", already_installed=False
        ),
    )

    assert browser_commands.handle_browser(["install-onion"]) == 0
    output = capsys.readouterr()
    assert "Installed Onionwright 0.0.14 from PyPI" in output.out
    # stderr carries only the next-step tip — no daemon error, no traceback.
    assert output.err.strip() == "Use it:  co browser --engine wtf <function> [args]"


def test_cli_reports_a_failed_install_without_contacting_the_daemon(monkeypatch, capsys):
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("contacted daemon")),
    )
    monkeypatch.setattr(
        installer,
        "install_onionwright",
        lambda **kwargs: (_ for _ in ()).throw(
            installer.OnionwrightInstallError("this Python is externally managed")
        ),
    )

    assert browser_commands.handle_browser(["install-onion"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "externally managed" in output.err


def test_cli_install_rejects_extra_arguments_without_daemon(monkeypatch, capsys):
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("contacted daemon")),
    )

    assert browser_commands.handle_browser(["install-onion", "--yolo"]) == 2
    assert "--break-system-packages" in capsys.readouterr().err

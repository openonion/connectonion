"""Install the Onionwright client, the driver the paid browser runs on.

It comes from PyPI. Until 2026-09-14 it did not: PyPI held a name-reservation
placeholder and the real wheel travelled a licence-gated endpoint, authenticated,
with a pinned Ed25519 manifest and a SHA-256 check — openonion/onionwright#9
chose one distribution mechanism rather than two. The owner reversed that, so
this module is now a thin, honest wrapper around pip.

What did NOT move: the browser binary is still licence-gated, and the runtime
licence is still checked at launch. Installing this package gets you the driver,
not a browser nobody paid for.

The command stays explicit about *when* it runs. Importing ConnectOnion, or
selecting the system browser, must never mutate a Python environment; only an
explicit `co browser install-onion` or a typed `--engine wtf` reaches here.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from dataclasses import dataclass

from packaging.version import InvalidVersion, Version

from ..._version import __version__

# The floor, not a pin. A newer client is expected to keep working against the
# catalogue: oo-api records `minimum_client_version` per artifact and refuses a
# client below it, which is the check that actually protects a paid download.
ONIONWRIGHT_VERSION = "0.0.14"
ONIONWRIGHT_REQUIREMENT = f"onionwright>={ONIONWRIGHT_VERSION}"


class OnionwrightInstallError(RuntimeError):
    """The client could not be installed."""


@dataclass(frozen=True)
class InstallResult:
    version: str
    already_installed: bool


def _installed_version() -> str | None:
    try:
        return importlib.metadata.version("onionwright")
    except importlib.metadata.PackageNotFoundError:
        return None


def _is_compatible(version: str | None) -> bool:
    if version is None:
        return False
    try:
        return Version(version) >= Version(ONIONWRIGHT_VERSION)
    except InvalidVersion:
        return False


def paid_client_is_ready() -> bool:
    """Whether this interpreter already has a client the paid engine can use.

    Cheap enough to ask before every paid command: one metadata lookup, no
    network. That is what lets asking for the paid engine fetch its client
    instead of returning an instruction to run a second command.
    """
    return _is_compatible(_installed_version())


def _install_failure_advice(completed, break_system_packages: bool) -> str:
    """Say why pip refused, and name the command that gets past it.

    An exit code on its own sent a reader looking for a broken download when
    the actual answer was a policy the OS applies to its own interpreter, and
    every Homebrew and system Python answers that way. Print what pip said, then
    the one command that works here — not a suggestion to fix pip.
    """
    output = f"{completed.stdout or ''}{completed.stderr or ''}".strip()
    tail = f"\n\npip said:\n{output}" if output else ""
    if "externally-managed-environment" in output and not break_system_packages:
        return (
            "this Python is externally managed, so pip will not write to it.\n\n"
            f"  This interpreter:  {sys.executable}\n\n"
            "Install into it anyway — the right answer when `co` itself lives "
            "there, because\nOnionwright has to be importable by this same "
            "interpreter:\n"
            "  co browser install-onion --break-system-packages\n\n"
            "Or put both in a virtualenv, where nothing needs the flag:\n"
            "  python3 -m venv ~/.co/venv\n"
            # The exact version running now, not `--pre`: `--pre` lets pip take
            # pre-release dependencies too (httpx 1.0.dev6 crashed 1.8.8b7).
            f"  ~/.co/venv/bin/pip install 'connectonion=={__version__}'"
            f"{tail}"
        )
    return f"pip could not install Onionwright (exit {completed.returncode}).{tail}"


def install_onionwright(*, break_system_packages: bool = False) -> InstallResult:
    """Install the current client into this exact Python environment."""
    current = _installed_version()
    if _is_compatible(current):
        return InstallResult(version=current or ONIONWRIGHT_VERSION, already_installed=True)

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--disable-pip-version-check",
        *(["--break-system-packages"] if break_system_packages else []),
        ONIONWRIGHT_REQUIREMENT,
    ]
    try:
        # Captured rather than streamed: the exit code alone cannot tell a
        # refusal-by-policy from a genuine failure. The output is printed back
        # on failure, so nothing is hidden.
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True
        )
    except OSError as exc:
        raise OnionwrightInstallError(
            "Could not start pip in the current Python environment."
        ) from exc
    if completed.returncode != 0:
        raise OnionwrightInstallError(
            _install_failure_advice(completed, break_system_packages)
        )

    installed = _installed_version()
    if not _is_compatible(installed):
        raise OnionwrightInstallError(
            f"pip completed but Onionwright {ONIONWRIGHT_VERSION} or newer is not "
            f"installed. PyPI has {installed or 'nothing'} for this interpreter."
        )
    return InstallResult(version=installed or ONIONWRIGHT_VERSION, already_installed=False)

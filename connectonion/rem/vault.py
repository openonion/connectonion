"""The secret behind a Keys page lives in the operating system's vault, never in the notebook (#3137).

The notebook is Markdown that the night's models read and the phone can open over the relay, so a password
or API key written there would leak with everything else. A ``keys/`` page says what a secret is (service,
account, purpose, who has it, where it is used, when it rotates); its value is a generic password in the
macOS Keychain under the service name ``co-rem:<page slug>``. Reading it back goes through the Keychain's own
prompt (Touch ID or the login password), so REM never holds a master key of its own.

``RUN`` is the one place a process starts, so tests replace it and never touch the real Keychain.
"""

from __future__ import annotations

import re
import subprocess
import sys

from .files import RemError

SERVICE_PREFIX = "co-rem:"
NOT_FOUND = 44  # `security` exits 44 when no such item exists


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)


RUN = _run


def service_name(slug: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,120}", slug):
        raise RemError("A key's name is lowercase letters, digits and dashes")
    return SERVICE_PREFIX + slug


def _supported() -> None:
    if sys.platform != "darwin":
        raise RemError("Keys keep their secret in the macOS Keychain; this system's vault is not supported yet")


def put(slug: str, account: str, secret: str) -> None:
    """Store (or replace) the secret.

    `security` takes the value as an argument (its no-value `-w` prompts on a terminal, which a Host has not),
    so for the moment of the call it is visible in this Mac's process list; it is never written to a file, a log
    or the notebook. A local process that polls `ps` at that instant could see it; nothing remote can.""" 
    _supported()
    if not secret:
        raise RemError("Nothing to store: the secret is empty")
    done = RUN(["security", "add-generic-password", "-U", "-s", service_name(slug), "-a", account or slug,
                "-l", f"co rem · {slug}", "-w", secret])
    if done.returncode != 0:
        raise RemError(f"The Keychain refused to store it: {(done.stderr or '').strip() or done.returncode}")


def get(slug: str) -> str:
    """The secret, after the Keychain's own prompt; RemError when there is none or the owner declined."""
    _supported()
    done = RUN(["security", "find-generic-password", "-s", service_name(slug), "-w"])
    if done.returncode == NOT_FOUND:
        raise RemError("No secret is stored for this key on this Mac")
    if done.returncode != 0:
        raise RemError("The Keychain did not give the secret (declined or locked)")
    return done.stdout.rstrip("\n")


def has(slug: str) -> bool:
    """Whether a secret is stored, without reading it (no prompt)."""
    _supported()
    return RUN(["security", "find-generic-password", "-s", service_name(slug)]).returncode == 0


def delete(slug: str) -> bool:
    _supported()
    done = RUN(["security", "delete-generic-password", "-s", service_name(slug)])
    if done.returncode not in (0, NOT_FOUND):
        raise RemError(f"The Keychain refused to delete it: {(done.stderr or '').strip() or done.returncode}")
    return done.returncode == 0

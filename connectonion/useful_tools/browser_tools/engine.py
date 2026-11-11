"""Resolve the 1.8 browser engine once, before a browser session can charge.

On macOS a WTF launch also brings /Applications/WTF Browser.app to the build it
started (#2932): see refresh_applications_app.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from packaging.version import InvalidVersion, Version

AUTO = "auto"
SYSTEM = "system"
# `wtf` is the product's name. `onion` is what the wire between client and
# daemon still calls it, because that value is also what remote_egress checks
# to decide whether a paid session may carry traffic — renaming it needs both
# sides moving together, which is 1.9 work and invisible from the CLI.
WTF = "wtf"
ONION = "onion"
MODES = (AUTO, SYSTEM, ONION)
# What a person or an agent may type. `onion` is kept and answered.
ACCEPTED_MODES = (AUTO, SYSTEM, WTF, ONION)
ENGINE_SETTING = "CO_BROWSER_ENGINE"
# 154 carries the headless identity fix (openonion/browser#139): a headless
# session sends the same UA, Client Hints and headers as a headed one. Artifact
# keys are immutable per revision, so the fix could only ship by moving the pin.
# Every platform listed here must be in oo-api's catalogue at this revision
# before this ships: a client asks for exactly this revision and nothing else.
# macOS moved to .100 for the renewal fix (openonion/browser#145): before it,
# every macOS renewal reused one Idempotency-Key and paid sessions ended after
# 15 minutes. Linux renews through Onionwright, never had that bug, and stays.
BROWSER_REVISION = "154.0.8037.100" if sys.platform == "darwin" else "154.0.8037.58"
MIN_ONIONWRIGHT_VERSION = "0.0.14"
# The copy of the browser a person double-clicks. Onionwright downloads and runs
# its own under ~/.onionwright and never looks here, so until #2932 this one
# stayed at whatever revision someone once dragged in, and the server refused it.
APPLICATIONS = Path("/Applications")
APP_NAME = "WTF Browser.app"
BUNDLE_ID = "ai.openonion.browser"


class Reason:
    SYSTEM_REQUESTED = "system_requested"
    # Told apart on purpose: when a charge is unexpected, the first question
    # is which invocations were a standing choice rather than a request.
    WTF_CONFIGURED = "wtf_configured"
    WTF_READY = "wtf_ready"
    SYSTEM_DEFAULT = "system_default"
    ONION_READY = "onion_ready"
    INVALID_MODE = "invalid_engine_mode"
    ONIONWRIGHT_MISSING = "onionwright_missing"
    ONIONWRIGHT_INCOMPATIBLE = "onionwright_incompatible"
    LICENSE_UNAVAILABLE = "license_unavailable"
    PREFLIGHT_FAILED = "preflight_failed"


def normalize_mode(mode: str) -> str:
    """The internal name for what someone typed. Raises on anything else."""
    cleaned = str(mode).strip().lower()
    if cleaned == ONION:
        return WTF
    if cleaned in (AUTO, SYSTEM, WTF):
        return cleaned
    raise ValueError(f"engine must be one of: {', '.join(ACCEPTED_MODES)}")


def configured_mode() -> str | None:
    """The default from the selected env file, or None if there is not one.

    A typo returns None rather than raising: a bad value in a config file must
    not make every browser command fail, and `co browser config` is where a
    wrong one is diagnosed.
    """
    import os

    raw = os.environ.get(ENGINE_SETTING)
    if not raw:
        return None
    try:
        return normalize_mode(raw)
    except ValueError:
        return None


def effective_mode(requested: str | None) -> str:
    """What to run: the flag if given, else the configured default, else auto.

    A flag wins in both directions, so `--engine system` is always a way to
    not spend money and needs no file edited.
    """
    if requested is not None:
        return normalize_mode(requested)
    return configured_mode() or AUTO


class BrowserEngineError(RuntimeError):
    """An explicit Onion request could not start; it never becomes system."""

    def __init__(self, reason: str, next_action: str):
        self.reason = reason
        self.next_action = next_action
        super().__init__(f"{reason}: {next_action}")


@dataclass(frozen=True)
class Resolution:
    requested: str
    resolved: str
    reason: str
    next_action: str
    browser_revision: str = BROWSER_REVISION
    client: Any | None = None
    prepared: Any | None = None

    @property
    def fallback(self) -> bool:
        """Whether a paid engine was attempted and could not be used.

        The plain default is not a fallback: since paying became opt-in,
        `auto` resolves to system Chrome without attempting anything, and
        calling that a fallback would report a failure that never happened.
        """
        return (
            self.requested == AUTO
            and self.resolved == SYSTEM
            and self.reason != Reason.SYSTEM_DEFAULT
        )

    @property
    def artifact_id(self) -> str | None:
        capability = getattr(self.prepared, "capability", None)
        artifact = getattr(capability, "artifact", None)
        return getattr(artifact, "artifact_id", None)

    @property
    def executable(self) -> str | None:
        """The browser this resolution will actually run.

        Not the driver's default install: a paid resolution runs the downloaded
        artifact, and reporting the default instead tells an operator the
        system browser is in use while a different binary serves every page.
        """
        path = getattr(self.prepared, "executable", None)
        return str(path) if path else None

    @property
    def interval_usd(self) -> float | None:
        """What one billing interval costs, when the server said.

        Surfaced so a paid session can say what it costs. Only an explicit
        `onion` request reaches a paid session now (#1327), and it still has to
        say what that session costs.
        """
        capability = getattr(self.prepared, "capability", None)
        price = getattr(capability, "interval_usd", None)
        return price if isinstance(price, (int, float)) else None

    @property
    def onionwright_version(self) -> str | None:
        capability = getattr(self.prepared, "capability", None)
        version = getattr(capability, "client_version", None)
        if version is None:
            version = getattr(self.client, "client_version", None)
        return version if isinstance(version, str) else None

    def public_status(self) -> dict[str, Any]:
        """Safe status/audit fields; never includes tokens, licence bytes, or paths."""
        return {
            "requested_engine": self.requested,
            "resolved_engine": self.resolved,
            "fallback": self.fallback,
            "reason": self.reason,
            "next_action": self.next_action,
            "browser_revision": self.browser_revision,
            "onionwright_version": self.onionwright_version,
            "artifact_id": self.artifact_id,
            "interval_usd": self.interval_usd,
            "executable": self.executable,
        }


def _default_token() -> str:
    # Imported only after the explicit system return below. This may read the
    # normal ConnectOnion credential sources; system mode must touch none of it.
    from connectonion.credentials import require_ambient_api_key

    return require_ambient_api_key()


def _default_client(token: str, home: Path):
    # Onionwright remains optional. Presence of the paid package is not a
    # requirement for the free/system product.
    import onionwright

    if not callable(getattr(onionwright, "launch_paid_async", None)):
        raise AttributeError("installed Onionwright has no async paid launcher")
    return onionwright.PaidSessionClient(token=token, home=home)


def _system(requested: str, reason: str, next_action: str) -> Resolution:
    return Resolution(
        requested=requested,
        resolved=SYSTEM,
        reason=reason,
        next_action=next_action,
    )


def _unavailable(requested: str, reason: str, next_action: str) -> Resolution:
    """Report a paid engine that could not be prepared.

    Only an explicit `onion` request reaches this now, and an explicit request
    never becomes system silently. The `auto` branch is kept because the
    fallback shape is what makes an added mode safe by default rather than
    billable by accident.
    """
    if requested == ONION:
        raise BrowserEngineError(reason, next_action)
    return _system(requested, reason, next_action)


def resolve(
    requested: str = AUTO,
    *,
    browser_revision: str = BROWSER_REVISION,
    token_loader: Callable[[], str] = _default_token,
    client_factory: Callable[[str, Path], Any] = _default_client,
    home: Path | None = None,
) -> Resolution:
    """Resolve one immutable engine choice without starting a paid session.

    `system` and `auto` return before importing Onionwright, loading a token,
    calling the server, or touching the paid cache: the default engine is the
    installed system Chrome, and money is never spent unless the caller asks
    for it by name. `onion` runs Onionwright's complete non-billing `prepare`:
    exact signed manifest, compatibility, download, checksum, extraction, and
    executable readiness, and fails with a typed error rather than falling back.
    Only the later `launch()` call is allowed to create and charge a session.
    """
    if requested not in MODES:
        raise BrowserEngineError(
            Reason.INVALID_MODE,
            f"choose one of: {', '.join(MODES)}",
        )
    if requested == SYSTEM:
        return _system(
            SYSTEM,
            Reason.SYSTEM_REQUESTED,
            "Start Patchright with the installed system Chrome.",
        )
    if requested == AUTO:
        # Paying is opt-in. `auto` used to resolve to the paid engine whenever
        # preparation succeeded, which meant an ordinary `co browser go_to`
        # could open a billable session on a machine that merely had
        # Onionwright installed (#1327 named the problem and left the default
        # to be settled). It is settled here: nothing charges unless the caller
        # names `onion`. `auto` stays a valid mode because the CLI, the client
        # and the daemon all use it as the wire value for "not chosen", so a
        # warm paid daemon still serves later verbs that name no engine.
        return _system(
            AUTO,
            Reason.SYSTEM_DEFAULT,
            "Start Patchright with the installed system Chrome; "
            "use --engine onion to start a paid WTF Browser session.",
        )

    paid_home = home or Path.home() / ".onionwright"
    try:
        token = token_loader()
    except Exception:
        return _unavailable(
            requested,
            Reason.LICENSE_UNAVAILABLE,
            "Run `co auth`, or request the system browser.",
        )
    try:
        client = client_factory(token, paid_home)
    except ModuleNotFoundError:
        return _unavailable(
            requested,
            Reason.ONIONWRIGHT_MISSING,
            "Run `co browser install-onion`, or request the system browser.",
        )
    except (ImportError, AttributeError, TypeError):
        return _unavailable(
            requested,
            Reason.ONIONWRIGHT_INCOMPATIBLE,
            "Run `co browser install-onion` to upgrade Onionwright.",
        )

    client_version = getattr(client, "client_version", None)
    try:
        compatible = (
            isinstance(client_version, str)
            and Version(client_version) >= Version(MIN_ONIONWRIGHT_VERSION)
        )
    except InvalidVersion:
        compatible = False
    if not compatible:
        return _unavailable(
            requested,
            Reason.ONIONWRIGHT_INCOMPATIBLE,
            f"Run `co browser install-onion` for Onionwright {MIN_ONIONWRIGHT_VERSION} or newer.",
        )

    try:
        prepared = client.prepare(browser_revision)
    except Exception as exc:
        reason = getattr(exc, "code", Reason.PREFLIGHT_FAILED)
        message = getattr(exc, "message", None) or (
            "Paid browser preflight failed before session creation; use system Chrome."
        )
        return _unavailable(requested, reason, message)

    if not getattr(prepared, "ready", False):
        capability = getattr(prepared, "capability", None)
        reason = getattr(capability, "reason", Reason.PREFLIGHT_FAILED)
        next_action = getattr(capability, "next_action", None) or (
            "Use system Chrome; no paid browser session was created."
        )
        return _unavailable(requested, reason, next_action)

    return Resolution(
        requested=requested,
        resolved=ONION,
        reason=Reason.ONION_READY,
        next_action="Start the exact prepared Onion Browser session.",
        browser_revision=browser_revision,
        client=client,
        prepared=prepared,
    )


def _our_build(app: Path) -> tuple[str, str] | None:
    """(revision, channel) when the bundle at `app` is OpenOnion's browser, else None."""
    plist = app / "Contents" / "Info.plist"
    if not plist.is_file():
        return None
    info = plistlib.loads(plist.read_bytes())
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        return None
    channel = app / "Contents" / "Resources" / "openonion-release-channel"
    return (
        info.get("CFBundleShortVersionString", ""),
        channel.read_text().strip() if channel.is_file() else "",
    )


def _app_is_running(app: Path) -> bool:
    """Whether any process was started from inside this bundle: the app or a helper."""
    programs = subprocess.run(
        ["/bin/ps", "-axo", "comm="], capture_output=True, text=True, errors="replace", check=True
    ).stdout
    return any(line.startswith(f"{app}/Contents/") for line in programs.splitlines())


def _ditto(source: Path, destination: Path) -> None:
    """Copy a signed bundle the way that keeps its signature and notarization valid."""
    subprocess.run(["/usr/bin/ditto", str(source), str(destination)], check=True)


def _why_not_now(app: Path) -> str | None:
    """Why `co` must not put a build at `app` right now, in a person's words; None when it may."""
    if not os.access(app.parent, os.W_OK):
        return f"co cannot write to {app.parent}"
    if app.exists() and _app_is_running(app):
        return "it is open"
    return None


def _newer(found: tuple[str, str], wanted: tuple[str, str]) -> bool:
    """Whether `found` is a later revision on the channel of `wanted`.

    Several `co` installs with different pins share one Mac. The one with the
    older pin must not put back the build the server refuses, and the two must
    not trade the app back and forth. Revisions compare as numbers, because as
    text 154.0.8037.58 sorts after 154.0.8037.100.
    """
    theirs, ours = (tuple(map(int, build[0].split("."))) for build in (found, wanted))
    return found[1] == wanted[1] and theirs > ours


def _install_or_replace(runtime_app: Path, app: Path, trash: Path) -> str | None:
    """Put the build at `runtime_app` at `app`; the caller knows it is ours.

    The new copy is staged beside the app and renamed into place, so a copy that
    is interrupted never leaves a half bundle that reads as the current build.
    """
    wanted, found = _our_build(runtime_app), _our_build(app)
    if found == wanted:
        return None
    if app.exists() and found is None:
        return f"{app} is not OpenOnion's build, so co left it alone"
    if found and _newer(found, wanted):
        return f"{app.parent} has {found[0]}, newer than the {wanted[0]} co runs, so co left it"
    staged = app.with_name(f".{app.name}.installing")
    shutil.rmtree(staged, ignore_errors=True)       # left by a copy that was interrupted
    blocked = _why_not_now(app)
    if blocked is None:
        _ditto(runtime_app, staged)
        blocked = _why_not_now(app)                 # a person can open the old app during the copy
    if blocked:
        shutil.rmtree(staged, ignore_errors=True)
        return f"{app} stays {'at ' + found[0] if found else 'absent'}: {blocked}"
    said = f"co put WTF Browser {wanted[0]} in {app.parent}"
    if found:
        trash.mkdir(exist_ok=True)
        kept = trash / f"WTF Browser {found[0]} {datetime.now():%Y-%m-%d %H.%M.%S}.app"
        shutil.move(app, kept)
        said += f"; the {found[0]} that was there is in the Trash as {kept.name!r}"
    staged.rename(app)
    return said


def refresh_applications_app(executable: str, applications: Path, trash: Path) -> str | None:
    """Make the WTF Browser in `applications` the build `executable` belongs to (#2932).

    A later revision on the same channel is left where it is: see _newer.
    Returns what a person should be told, or None when nothing needed doing:
    the app is already that build, or `executable` is not inside our bundle.
    """
    runtime_app = Path(executable).parent.parent.parent
    if _our_build(runtime_app) is None:
        return None
    import fcntl  # POSIX only, and only a macOS launch gets here

    with open(runtime_app / "Contents" / "Info.plist", "rb") as turn:
        # Two daemons started together would share one staging copy; they take turns.
        fcntl.flock(turn, fcntl.LOCK_EX)
        return _install_or_replace(runtime_app, applications / APP_NAME, trash)


def _refresh_applications_app_and_say(executable: str, applications: Path, trash: Path) -> None:
    said = refresh_applications_app(executable, applications, trash)
    if said:
        print(f"WTF Browser app: {said}", file=sys.stderr)


def _refresh_applications_app_beside_the_launch(resolution: Resolution) -> None:
    """After a WTF launch on macOS, bring /Applications to the build just started.

    On its own thread: the copy is about 350 MB, and nothing it does or fails
    at may slow the browser that is already up or take its paid session down.
    Not a daemon thread, so a short script still finishes the copy before exit.
    """
    if sys.platform != "darwin" or not resolution.executable:
        return
    threading.Thread(
        target=_refresh_applications_app_and_say,
        args=(resolution.executable, APPLICATIONS, Path.home() / ".Trash"),
        name="wtf-browser-app",
    ).start()


def applications_app_line(executable: str | None, applications: Path) -> str | None:
    """What `co browser status` says about the WTF Browser a person can click.

    `executable` is the paid runtime this daemon runs. Without one, the pinned
    revision stands in for it and the channel is taken as matching.
    """
    if sys.platform != "darwin":
        return None
    app = applications / APP_NAME
    found = _our_build(app)
    if app.exists() and found is None:
        return f"WTF Browser app: {app} is not OpenOnion's build, so co leaves it alone"
    wanted = executable and _our_build(Path(executable).parent.parent.parent)
    wanted = wanted or (BROWSER_REVISION, found[1] if found else "")
    if found == wanted:
        return f"WTF Browser app: {applications} has {found[0]}, the build co runs"
    if found and _newer(found, wanted):
        return f"WTF Browser app: {applications} has {found[0]}, newer than the {wanted[0]} co runs, so co leaves it"
    have = f"none in {applications}"
    if found:
        told = slice(None) if found[1] != wanted[1] else slice(1)  # the channel only when it differs
        have = f"{applications} has {' '.join(found[told]).strip()}, co runs {' '.join(wanted[told]).strip()}"
    blocked = _why_not_now(app)
    then = f"{blocked}, so co leaves it" if blocked else (
        "co installs the build it runs the next time it starts the WTF browser"
    )
    return f"WTF Browser app: {have} — {then}"


def launch(
    resolution: Resolution,
    playwright,
    idempotency_key: str,
    **launch_kwargs,
):
    """Cross the billing boundary for a previously prepared Onion resolution."""
    if resolution.resolved != ONION or resolution.client is None or resolution.prepared is None:
        raise BrowserEngineError(
            Reason.PREFLIGHT_FAILED,
            "Only a ready Onion resolution can start a paid session.",
        )
    try:
        from onionwright import launch_paid
    except (ImportError, AttributeError) as exc:
        raise BrowserEngineError(
            Reason.ONIONWRIGHT_INCOMPATIBLE,
            "Upgrade Onionwright to the ConnectOnion 1.8 compatible release.",
        ) from exc
    run = launch_paid(
        playwright,
        resolution.client,
        resolution.browser_revision,
        idempotency_key,
        prepared=resolution.prepared,
        **launch_kwargs,
    )
    _refresh_applications_app_beside_the_launch(resolution)
    return run


async def launch_async(
    resolution: Resolution,
    playwright,
    idempotency_key: str,
    **launch_kwargs,
):
    """Cross the billing boundary through Onionwright's async driver contract."""
    if resolution.resolved != ONION or resolution.client is None or resolution.prepared is None:
        raise BrowserEngineError(
            Reason.PREFLIGHT_FAILED,
            "Only a ready Onion resolution can start a paid session.",
        )
    try:
        from onionwright import launch_paid_async
    except (ImportError, AttributeError) as exc:
        raise BrowserEngineError(
            Reason.ONIONWRIGHT_INCOMPATIBLE,
            "Upgrade Onionwright to the ConnectOnion 1.8 compatible release.",
        ) from exc
    run = await launch_paid_async(
        playwright,
        resolution.client,
        resolution.browser_revision,
        idempotency_key,
        prepared=resolution.prepared,
        **launch_kwargs,
    )
    _refresh_applications_app_beside_the_launch(resolution)
    return run

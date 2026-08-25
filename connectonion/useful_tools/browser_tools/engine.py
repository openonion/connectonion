"""Resolve the 1.8 browser engine once, before a browser session can charge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from packaging.version import InvalidVersion, Version


AUTO = "auto"
SYSTEM = "system"
ONION = "onion"
MODES = (AUTO, SYSTEM, ONION)
BROWSER_REVISION = "150.0.7871.187"
MIN_ONIONWRIGHT_VERSION = "0.0.11"


class Reason:
    SYSTEM_REQUESTED = "system_requested"
    ONION_READY = "onion_ready"
    INVALID_MODE = "invalid_engine_mode"
    ONIONWRIGHT_MISSING = "onionwright_missing"
    ONIONWRIGHT_INCOMPATIBLE = "onionwright_incompatible"
    LICENSE_UNAVAILABLE = "license_unavailable"
    PREFLIGHT_FAILED = "preflight_failed"


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
        return self.requested == AUTO and self.resolved == SYSTEM

    @property
    def artifact_id(self) -> str | None:
        capability = getattr(self.prepared, "capability", None)
        artifact = getattr(capability, "artifact", None)
        return getattr(artifact, "artifact_id", None)

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

    return onionwright.PaidSessionClient(token=token, home=home)


def _system(requested: str, reason: str, next_action: str) -> Resolution:
    return Resolution(
        requested=requested,
        resolved=SYSTEM,
        reason=reason,
        next_action=next_action,
    )


def _unavailable(requested: str, reason: str, next_action: str) -> Resolution:
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

    `system` returns before importing Onionwright, loading a token, calling the
    server, or touching the paid cache. `auto` and `onion` run Onionwright's
    complete non-billing `prepare`: exact signed manifest, compatibility,
    download, checksum, extraction, and executable readiness. Only the later
    `launch()` call is allowed to create and charge a session.
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
            "Install the compatible Onionwright package, or request the system browser.",
        )
    except (ImportError, AttributeError, TypeError):
        return _unavailable(
            requested,
            Reason.ONIONWRIGHT_INCOMPATIBLE,
            "Upgrade Onionwright to the ConnectOnion 1.8 compatible release.",
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
            f"Install Onionwright {MIN_ONIONWRIGHT_VERSION} or newer.",
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
    return launch_paid(
        playwright,
        resolution.client,
        resolution.browser_revision,
        idempotency_key,
        prepared=resolution.prepared,
        **launch_kwargs,
    )

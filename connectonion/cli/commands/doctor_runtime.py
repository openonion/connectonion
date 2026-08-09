"""Deterministic browser/runtime checks and narrowly-scoped repairs for doctor."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import platform
import subprocess
import sys
from typing import Callable, Iterable


PATCHRIGHT_VERSION = "1.61.2"
SUPPORTED_SYSTEMS = {"Darwin", "Linux", "Windows"}


@dataclass(frozen=True)
class RuntimeCheck:
    id: str
    label: str
    status: str
    detail: str
    repair: tuple[str, ...] | None = None


@dataclass(frozen=True)
class RepairOutcome:
    id: str
    label: str
    outcome: str
    detail: str


def _linux_prerequisites(browser_path: str | None) -> RuntimeCheck:
    if platform.system() != "Linux":
        return RuntimeCheck("os-prerequisites", "OS prerequisites", "ok", "managed by the platform")
    if not browser_path:
        return RuntimeCheck(
            "os-prerequisites",
            "OS prerequisites",
            "pending",
            "checked after a browser is installed",
        )
    try:
        result = subprocess.run(
            ["ldd", browser_path], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return RuntimeCheck(
            "os-prerequisites",
            "OS prerequisites",
            "blocked",
            "could not inspect browser libraries; run: python -m patchright install --with-deps chromium",
        )
    missing = sorted(
        line.split("=>", 1)[0].strip()
        for line in result.stdout.splitlines()
        if "=> not found" in line
    )
    if missing:
        return RuntimeCheck(
            "os-prerequisites",
            "OS prerequisites",
            "blocked",
            "missing libraries: " + ", ".join(missing)
            + "; run: python -m patchright install --with-deps chromium",
        )
    if result.returncode:
        return RuntimeCheck(
            "os-prerequisites", "OS prerequisites", "blocked", "ldd could not inspect the browser"
        )
    return RuntimeCheck("os-prerequisites", "OS prerequisites", "ok", "browser libraries resolved")


def runtime_checks() -> list[RuntimeCheck]:
    """Inspect supported Python, package, platform, daemon, driver, and browser state."""
    from ... import __version__
    from ..browser_agent.daemon import _owner_alive, default_sock_path
    from ...useful_tools.browser_tools.browser import (
        driver_stealth_status,
        installed_browser_path,
    )

    checks: list[RuntimeCheck] = []
    python_ok = sys.version_info >= (3, 10)
    checks.append(
        RuntimeCheck(
            "python",
            "Python",
            "ok" if python_ok else "unsupported",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            + ("" if python_ok else "; ConnectOnion requires Python >=3.10"),
        )
    )
    checks.append(RuntimeCheck("package", "ConnectOnion package", "ok", __version__))

    system = platform.system() or "unknown"
    system_supported = system in SUPPORTED_SYSTEMS
    checks.append(
        RuntimeCheck(
            "platform",
            "Operating system",
            "ok" if system_supported else "unsupported",
            system if system_supported else f"{system}; supported: Darwin, Linux, Windows",
        )
    )
    safe_to_repair = python_ok and system_supported

    driver_status, version, detail = driver_stealth_status()
    if driver_status == "ok":
        checks.append(RuntimeCheck("patchright", "Patchright", "ok", f"{version} · {detail}"))
    else:
        pip_command = [sys.executable, "-m", "pip", "install"]
        if driver_status == "broken":
            pip_command.extend(["--force-reinstall", "--no-cache-dir"])
        pip_command.append(f"patchright=={PATCHRIGHT_VERSION}")
        repair = tuple(pip_command) if safe_to_repair else None
        checks.append(RuntimeCheck("patchright", "Patchright", driver_status, detail, repair))

    browser_path = installed_browser_path() if driver_status != "missing" else None
    checks.append(
        RuntimeCheck("browser", "Browser binary", "ok", browser_path)
        if browser_path
        else RuntimeCheck(
            "browser",
            "Browser binary",
            "missing",
            "none installed for this user",
            (sys.executable, "-m", "patchright", "install", "chromium")
            if safe_to_repair
            else None,
        )
    )

    daemon_running = _owner_alive(default_sock_path())
    checks.append(
        RuntimeCheck(
            "browser-daemon",
            "Browser daemon",
            "ok" if daemon_running else "idle",
            "running" if daemon_running else "stopped; starts on demand",
        )
    )
    checks.append(_linux_prerequisites(browser_path))
    return checks


def repair_runtime(
    checks: Iterable[RuntimeCheck],
    *,
    approve: Callable[[RuntimeCheck], bool],
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    recheck: Callable[[], list[RuntimeCheck]] = runtime_checks,
) -> list[RepairOutcome]:
    """Apply approved known repairs, then classify every unhealthy item."""
    checks = list(checks)
    attempted: dict[str, str | None] = {}
    declined: set[str] = set()

    for check in checks:
        if check.status in {"ok", "idle"}:
            continue
        if not check.repair:
            continue
        if not approve(check):
            declined.add(check.id)
            continue
        try:
            result = run(list(check.repair), check=False)
            attempted[check.id] = None if result.returncode == 0 else f"command exited {result.returncode}"
        except PermissionError:
            attempted[check.id] = "permission denied"
        except OSError as exc:
            attempted[check.id] = f"could not start repair: {exc.strerror or type(exc).__name__}"

    if attempted:
        importlib.invalidate_caches()
        try:
            from ...useful_tools.browser_tools.browser import forget_browser_path

            forget_browser_path()
        except ImportError:
            pass

    after = {check.id: check for check in recheck()} if attempted else {check.id: check for check in checks}
    outcomes: list[RepairOutcome] = []
    for check in checks:
        if check.status in {"ok", "idle"}:
            continue
        current = after.get(check.id)
        if check.id in declined:
            outcomes.append(RepairOutcome(check.id, check.label, "skipped", "not approved"))
            continue
        if check.id not in attempted:
            if current and current.status in {"ok", "idle"}:
                outcomes.append(RepairOutcome(check.id, check.label, "repaired", current.detail))
            else:
                outcomes.append(RepairOutcome(check.id, check.label, "skipped", check.detail))
            continue
        error = attempted[check.id]
        if not error and current and current.status in {"ok", "idle"}:
            outcomes.append(RepairOutcome(check.id, check.label, "repaired", current.detail))
        else:
            detail = error or (current.detail if current else "check did not return a result")
            outcomes.append(RepairOutcome(check.id, check.label, "still-blocked", detail))
    return outcomes


def repairable_checks(checks: Iterable[RuntimeCheck]) -> list[RuntimeCheck]:
    return [check for check in checks if check.repair]


def _check_json(check: RuntimeCheck) -> dict:
    return {
        "id": check.id,
        "label": check.label,
        "status": check.status,
        "detail": check.detail,
    }


def runtime_json_report(
    *,
    fix: bool,
    approved: bool,
    probe: Callable[[], list[RuntimeCheck]] | None = None,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> tuple[dict, int]:
    """Return schema-v1 runtime diagnostics with no timestamps or secret values."""
    probe = runtime_checks if probe is None else probe
    run = subprocess.run if run is None else run
    initial = probe()
    plan = [
        {
            "check_id": check.id,
            "label": check.label,
            "command": list(check.repair),
            "requires_approval": True,
        }
        for check in initial
        if check.status not in {"ok", "idle"} and check.repair
    ]
    final = initial

    def capture_recheck():
        nonlocal final
        final = probe()
        return final

    outcomes: list[RepairOutcome] = []
    if fix:
        outcomes = repair_runtime(
            initial,
            approve=lambda _check: approved,
            run=run,
            recheck=capture_recheck,
        )

    approval_required = bool(fix and plan and not approved)
    blocked = [
        check.id
        for check in final
        if check.status not in {"ok", "idle", "pending"}
    ]
    code = 1 if blocked or approval_required else 0
    report = {
        "schema_version": 1,
        "command": "co doctor",
        "fix_requested": fix,
        "approved_noninteractive": approved,
        "approval_required": approval_required,
        "checks": [_check_json(check) for check in final],
        "plan": plan,
        "outcomes": [
            {
                "check_id": outcome.id,
                "label": outcome.label,
                "outcome": outcome.outcome,
                "detail": outcome.detail,
            }
            for outcome in outcomes
        ],
        "summary": {
            "status": "blocked" if code else "healthy",
            "exit_code": code,
            "blocked_check_ids": blocked,
        },
    }
    return report, code

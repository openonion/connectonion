"""`co doctor --fix` only applies approved, deterministic runtime repairs."""

import subprocess

from connectonion.cli.commands.doctor_runtime import (
    PATCHRIGHT_VERSION,
    RuntimeCheck,
    repair_runtime,
)


def _completed(_command, **_kwargs):
    return subprocess.CompletedProcess([], 0)


def test_a_fresh_runtime_is_repaired_in_one_invocation():
    missing = [
        RuntimeCheck(
            "patchright",
            "Patchright",
            "missing",
            "not installed",
            ("python", "-m", "pip", "install", f"patchright=={PATCHRIGHT_VERSION}"),
        ),
        RuntimeCheck(
            "browser",
            "Browser binary",
            "missing",
            "not installed",
            ("python", "-m", "patchright", "install", "chromium"),
        ),
    ]
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return _completed(command, **kwargs)

    healthy = lambda: [
        RuntimeCheck("patchright", "Patchright", "ok", PATCHRIGHT_VERSION),
        RuntimeCheck("browser", "Browser binary", "ok", "/user/chromium"),
    ]
    outcomes = repair_runtime(missing, approve=lambda _check: True, run=run, recheck=healthy)

    assert calls == [list(check.repair) for check in missing]
    assert [outcome.outcome for outcome in outcomes] == ["repaired", "repaired"]


def test_repeated_runs_are_idempotent():
    calls = []
    checks = [RuntimeCheck("browser", "Browser binary", "ok", "/user/chromium")]

    outcomes = repair_runtime(
        checks,
        approve=lambda _check: True,
        run=lambda *args, **kwargs: calls.append((args, kwargs)),
        recheck=lambda: checks,
    )

    assert calls == []
    assert outcomes == []


def test_unsupported_items_are_skipped_without_a_command():
    calls = []
    check = RuntimeCheck("platform", "Operating system", "unsupported", "Plan 9")

    outcomes = repair_runtime(
        [check],
        approve=lambda _check: True,
        run=lambda *args, **kwargs: calls.append((args, kwargs)),
        recheck=lambda: [check],
    )

    assert calls == []
    assert outcomes[0].outcome == "skipped"
    assert "Plan 9" in outcomes[0].detail


def test_permission_denied_is_still_blocked_without_a_traceback():
    check = RuntimeCheck(
        "browser",
        "Browser binary",
        "missing",
        "not installed",
        ("python", "-m", "patchright", "install", "chromium"),
    )

    def denied(*_args, **_kwargs):
        raise PermissionError("secret local path must not be rendered")

    outcomes = repair_runtime(
        [check], approve=lambda _check: True, run=denied, recheck=lambda: [check]
    )

    assert outcomes[0].outcome == "still-blocked"
    assert outcomes[0].detail == "permission denied"
    assert "secret local path" not in outcomes[0].detail


def test_declined_repairs_are_skipped():
    check = RuntimeCheck(
        "browser",
        "Browser binary",
        "missing",
        "not installed",
        ("python", "-m", "patchright", "install", "chromium"),
    )

    outcomes = repair_runtime(
        [check], approve=lambda _check: False, run=_completed, recheck=lambda: [check]
    )

    assert outcomes[0].outcome == "skipped"
    assert outcomes[0].detail == "not approved"


def test_a_dependent_check_is_reclassified_after_repair():
    browser = RuntimeCheck(
        "browser",
        "Browser binary",
        "missing",
        "not installed",
        ("python", "-m", "patchright", "install", "chromium"),
    )
    prerequisites = RuntimeCheck(
        "os-prerequisites", "OS prerequisites", "pending", "checked after install"
    )
    after = [
        RuntimeCheck("browser", "Browser binary", "ok", "/user/chromium"),
        RuntimeCheck("os-prerequisites", "OS prerequisites", "ok", "libraries resolved"),
    ]

    outcomes = repair_runtime(
        [browser, prerequisites],
        approve=lambda _check: True,
        run=_completed,
        recheck=lambda: after,
    )

    assert [outcome.outcome for outcome in outcomes] == ["repaired", "repaired"]

"""Codex's own weekly meter, and the investigation budget read against it (#1843).

The notebook used to budget in calls and characters and could not say what
share of the owner's Codex plan it spent; the percentage limits in the docs
stayed "not implemented" for want of a meter. Codex has one: `codex app-server`
answers `account/rateLimits/read` without starting a model turn, so a reading
costs nothing. It reports whole percents, so every figure here is good to
about one point.
"""

import os
from datetime import datetime
from pathlib import Path

# Runs whose points count against the investigation budget. Maintenance is the
# incremental daily pass and is bounded by the call cap instead.
INVESTIGATION_PHASES = ("daily-investigation", "investigate", "investigate me")


def _codex_auth() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"


def _app_server_request(method: str, params: dict) -> dict:
    from ..useful_tools.codex import CodexAppServer, _base_command
    command = _base_command()
    if not command:
        raise RuntimeError("codex is not on PATH")
    client = CodexAppServer(command)
    client.start()
    try:
        client.initialize(timeout=30)
        return client.request(method, params, timeout=30)
    finally:
        client.close()


def read(config: dict, request=None) -> dict:
    """The weekly window as Codex reports it, or {"unknown": why}.

    Never raises: a meter that cannot be read must not fail the run it is
    recording. It says why instead, and the run log keeps that reason.
    """
    runner = config.get("runner")
    if runner != "codex":
        return {"unknown": f"the {runner} runner has no quota meter"}
    # Checked before starting anything: a signed-out Codex (and every test's
    # isolated HOME) would otherwise spawn an app-server only to be refused.
    if not _codex_auth().is_file():
        return {"unknown": "Codex is not signed in"}
    try:
        payload = (request or _app_server_request)("account/rateLimits/read", {})
        limits = payload["rateLimits"]
        primary = limits["primary"]
        return {"used_percent": int(primary["usedPercent"]),
                "window_minutes": int(primary["windowDurationMins"]),
                "resets_at": int(primary["resetsAt"]),
                "plan": limits.get("planType") or "unknown"}
    except Exception as error:  # an older Codex, a changed payload, a timeout: all "unknown", with the reason
        return {"unknown": f"Codex did not report its quota ({type(error).__name__}: {error})"}


def points_spent(logs: list[dict], now: dict) -> int:
    """Points this window's investigation runs moved the meter, summed per run.

    Summed per run, not "now minus the first reading", because the owner's own
    coding moves the same meter between runs. A run that straddles a reset
    reads lower after than before; it counts as zero, never as a refund.
    """
    if "unknown" in now:
        return 0
    window_start = now["resets_at"] - now["window_minutes"] * 60
    spent = 0
    for run in logs:
        if run.get("phase") not in INVESTIGATION_PHASES:
            continue
        before, after = (run.get("quota") or {}).get("before", {}), (run.get("quota") or {}).get("after", {})
        if "used_percent" not in before or "used_percent" not in after:
            continue
        if datetime.fromisoformat(run["started_at"]).timestamp() < window_start:
            continue
        spent += max(0, after["used_percent"] - before["used_percent"])
    return spent


def blocks(reading: dict, spent: int, limits: dict) -> str:
    """Why no new investigation page may start now, or '' when one may."""
    if "unknown" in reading:
        return ""  # no meter: the daily call cap is the only bound, as before #1843
    floor = limits["quota_floor_percent"]
    if reading["used_percent"] >= floor:
        return (f"the Codex week is at {reading['used_percent']}%, at or past the {floor}% "
                "floor kept for your own work")
    budget = limits["investigation_quota_points"]
    if spent >= budget:
        return f"investigation has used {spent} of its {budget}-point weekly budget"
    return ""

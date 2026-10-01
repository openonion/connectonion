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
INVESTIGATION_PHASES = ("daily-investigation", "daily-update", "investigate", "investigate me", "projects write")


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


# What one point is taken to cost when the meter cannot see a run (#1990):
# tokens the model read fresh or wrote. Cached input is left out; Codex
# charges it at a small fraction. On the 1.9.0a7 acceptance notebook 3.4M
# input tokens, mostly cached, left the whole-percent week at 29% before and
# after; a million fresh tokens a point keeps that pass under one point, as
# the meter measured it.
TOKENS_PER_POINT = 1_000_000


def _token_points(usage) -> float:
    usage = usage if isinstance(usage, dict) else {}

    def number(key):
        value = usage.get(key)
        return value if isinstance(value, (int, float)) else 0
    fresh = max(0, number("input_tokens") - number("cached_input_tokens")) + number("output_tokens")
    return fresh / TOKENS_PER_POINT


def run_points(run: dict) -> float:
    """What one run cost in points: the meter when it moved, its tokens when it did not.

    Codex reports whole percents. Every run of the 1.9.0a7 acceptance pass read
    29% before and after, so "after minus before" was 0 for each and the budget
    never moved (#1990). A reading that moved is measured and wins. A reset
    mid-run reads lower after than before; that run counts its tokens, never a refund.
    """
    quota = run.get("quota") or {}
    before, after = quota.get("before") or {}, quota.get("after") or {}
    if "used_percent" in before and "used_percent" in after and after["used_percent"] > before["used_percent"]:
        return after["used_percent"] - before["used_percent"]
    return _token_points(run.get("usage"))


def points_spent(logs: list[dict], now: dict) -> float:
    """Points this window's investigation runs cost, summed per run, to one decimal.

    Summed per run, not "now minus the first reading", because the owner's own
    coding moves the same meter between runs.
    """
    if "unknown" in now:
        return 0
    window_start = now["resets_at"] - now["window_minutes"] * 60
    spent = 0.0
    for run in logs:
        if run.get("phase") not in INVESTIGATION_PHASES:
            continue
        if datetime.fromisoformat(run["started_at"]).timestamp() < window_start:
            continue
        spent += run_points(run)
    spent = round(spent, 1)
    return int(spent) if spent == int(spent) else spent


def run_spent(start: dict, now: dict, logs: list[dict], began: str) -> float:
    """What one CATEGORY or first run has spent: the meter's move, or its runs' points if more.

    `began` is when the run started (ISO). The meter alone stayed flat over a
    whole acceptance pass (#1990), so a `--budget 10` never stopped anything.
    """
    moved = now["used_percent"] - start["used_percent"] if "used_percent" in now and "used_percent" in start else 0
    counted = sum(run_points(run) for run in logs if run.get("phase") in INVESTIGATION_PHASES
                  and datetime.fromisoformat(run["started_at"]) >= datetime.fromisoformat(began))
    spent = round(max(moved, counted), 1)
    return int(spent) if spent == int(spent) else spent


def blocks(reading: dict, spent: int, limits: dict) -> str:
    """Why no new investigation page may start now, or '' when one may."""
    floor_reason = floor_block(reading, limits)
    if floor_reason:
        return floor_reason
    if "unknown" in reading:
        return ""  # no meter: the daily call cap is the only bound, as before #1843
    budget = limits["investigation_quota_points"]
    if spent >= budget:
        return f"investigation has used {spent} of its {budget}-point weekly budget"
    return ""


def floor_block(reading: dict, limits: dict) -> str:
    """The weekly safety floor shared by daily and first-run investigations."""
    if "unknown" in reading:
        return ""
    floor = limits["quota_floor_percent"]
    if reading["used_percent"] >= floor:
        return (f"the Codex week is at {reading['used_percent']}%, at or past the {floor}% "
                "floor kept for your own work")
    return ""

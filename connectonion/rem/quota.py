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

from .files import read_json, state_path, write_json

# Runs whose points count against the investigation budget. Maintenance is the
# incremental daily pass and is bounded by the call cap instead. A round's Abstract
# task carries the round's phase (stages.py tells it by its stage) and is not one of
# them: `co rem abstract` never was, and a budget that only holds investigation must
# not be spent by a stage that runs while it is held.
INVESTIGATION_PHASES = ("daily-investigation", "daily-update", "investigate", "investigate me", "projects write",
                        "same-person")
DEPTH_PHASES = ("enrich", "muse")


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


def meter(root, config: dict, request=None) -> dict:
    """The live reading, else the last one a run recorded in this week's window.

    104 of 166 scheduled runs could not read the meter (sandboxed app-server), and an
    unknown reading let every guard through. The week only moves up inside its
    window, so the last recorded value is a floor on where it is now.
    """
    live = read(config) if request is None else read(config, request)
    if "unknown" not in live:
        return live
    from . import service
    moment = service.now().timestamp()
    last = next((reading for run in service.run_logs(root) for key in ("after", "before")
                 if "used_percent" in (reading := (run.get("quota") or {}).get(key) or {})
                 and reading.get("resets_at", 0) > moment), None)
    return {**last, "last_recorded": live["unknown"]} if last else live


# Fresh tokens (input minus cached input, plus output) per point of the Codex week, on the
# standard tier, by reasoning effort. Fast (priority) bills twice: FAST_COST.
# Measured (#3083 audits, #3099):
# - medium: the rc20 night, 2026-11-17, every turn at medium on the fast tier: 7.45M fresh
#   tokens (6.28M REM, 1.17M other Codex in the window) moved the meter 9 points, 0.83M a
#   point at fast, so 1.66M at standard.
# - max: the night before, one deepen group with nothing else running, Astra at max on the
#   fast tier: 1.40M fresh for 20 points, 70K a point at fast, so 140K at standard.
# - high and xhigh are not measured: geometric steps between medium and max.
# - low and minimal are not measured: medium's figure, so they are never charged less than medium.
# - LEGACY: runs recorded before their effort was (2026-11-17): seven Codex pro batches
#   (gpt-6-luna, 2026-10-08..11) measured 11.6M-13.6M fresh tokens a point at standard.
TOKENS_PER_POINT = {"minimal": 1_660_000, "low": 1_660_000, "medium": 1_660_000, "high": 730_000,
                    "xhigh": 320_000, "max": 140_000}
LEGACY_TOKENS_PER_POINT = 12_000_000
FAST_COST = 2


def _token_points(usage, speed, effort="") -> float:
    usage = usage if isinstance(usage, dict) else {}

    def number(key):
        value = usage.get(key)
        return value if isinstance(value, (int, float)) else 0
    fresh = max(0, number("input_tokens") - number("cached_input_tokens")) + number("output_tokens")
    per_point = TOKENS_PER_POINT.get(effort or "", LEGACY_TOKENS_PER_POINT)
    return fresh * (FAST_COST if speed == "fast" else 1) / per_point


def _tokens_known(run: dict) -> bool:
    usage = run.get("usage")
    return isinstance(usage, dict) and any(isinstance(value, (int, float)) and value > 0 for value in usage.values())


def group_points(runs: list[dict]) -> float:
    """What overlapping runs cost: their own tokens when known, the meter's movement as the cap.

    The meter is one week for all of Codex: charged whole, a group paid for the owner's own
    coding beside it ("Deepening has used 37 of 30" for well under a point by tokens, #3083).
    Runs with no tokens are counted from the meter alone. Flat or missing readings, or a
    weekly reset, leave tokens as the measure. Reset timestamps jitter, so readings within
    an hour belong to one week.
    """
    tokens = sum(_token_points(run.get("usage"), run.get("speed") or "standard", run.get("effort")) for run in runs)
    quotas = [run.get("quota") or {} for run in runs]
    before = [quota["before"] for quota in quotas if "used_percent" in (quota.get("before") or {})]
    after = [quota["after"] for quota in quotas if "used_percent" in (quota.get("after") or {})]
    resets = [reading.get("resets_at") for reading in before + after]
    if before and after and None not in resets and max(resets) - min(resets) <= 3600:
        moved = max(reading["used_percent"] for reading in after) - min(reading["used_percent"] for reading in before)
        if moved > 0:
            return min(moved, tokens) if any(_tokens_known(run) for run in runs) else moved
    return tokens


def _measured(run: dict) -> bool:
    quota = run.get("quota") or {}
    return any("used_percent" in (quota.get(key) or {}) for key in ("before", "after"))


def _groups(runs: list[dict]):
    """Join overlapping intervals so parallel investigations cannot multiply spend.

    Only a run with a reading of its own joins or extends a group; one without is
    counted alone, from its tokens. A native round's own record has no reading and
    lasts for hours: on 2026-11-16 those records joined every investigation task of
    the day into one group, whose highest reading minus its lowest (44 - 6) was the
    whole day's Codex week, and investigation was held at "38 of 35" for under a point.
    """
    group, end = [], None
    for run in sorted(runs, key=lambda run: datetime.fromisoformat(run["started_at"])):
        if not _measured(run):
            yield [run]
            continue
        start = datetime.fromisoformat(run["started_at"])
        finish = datetime.fromisoformat(run.get("finished_at") or run["started_at"])
        if group and start > end:
            yield group
            group = []
        end = max(end, finish) if group else finish
        group.append(run)
    if group:
        yield group


def points_spent(logs: list[dict], now: dict, phases=INVESTIGATION_PHASES) -> float:
    """Points this window's investigation runs cost, grouped by overlap, to one decimal.

    Gaps between groups do not count: the owner's own coding moves the same meter.
    """
    if "unknown" in now or "resets_at" not in now:
        return 0
    window_start = now["resets_at"] - now["window_minutes"] * 60
    runs = [run for run in logs if run.get("phase") in phases
            and (run.get("stage") or "").removesuffix(" (repair)") != "abstract"
            and datetime.fromisoformat(run["started_at"]).timestamp() >= window_start]
    spent = round(sum(group_points(group) for group in _groups(runs)), 1)
    return int(spent) if spent == int(spent) else spent


def depth_points(logs: list[dict], now: dict) -> float:
    """Deepening keeps its own weekly bound even without a readable meter."""
    if "resets_at" not in now:
        from . import service
        now = {"resets_at": service.now().timestamp(), "window_minutes": 7 * 24 * 60}
    return points_spent(logs, now, phases=DEPTH_PHASES)


def run_spent(start: dict, now: dict, logs: list[dict], began: str) -> float:
    """What one CATEGORY or first run has spent: the meter's move, or its runs' points if more.

    `began` is when the run started (ISO). The meter alone stayed flat over a
    whole acceptance pass (#1990), so a `--budget 10` never stopped anything.
    """
    moved = now["used_percent"] - start["used_percent"] if "used_percent" in now and "used_percent" in start else 0
    runs = [run for run in logs if run.get("phase") in INVESTIGATION_PHASES
            and datetime.fromisoformat(run["started_at"]) >= datetime.fromisoformat(began)]
    counted = sum(group_points(group) for group in _groups(runs))
    # Tokens are the run's own spend (#3099); the meter, which the owner's coding also moves,
    # stands in only while none of its runs has reported tokens.
    spent = round(counted if any(_tokens_known(run) for run in runs) else max(moved, counted), 1)
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


def investigation_hold(reading: dict, spent: float, limits: dict) -> dict | None:
    """The weekly investigation budget is spent: why in words and until when, else None.

    Not the floor, which holds every stage and is asked on its own. 2026-11-16: this
    budget was a round's stop reason, so a night ended before Abstract, Translate and
    Deepen with the Codex week at 37%. It holds investigation; the round goes on."""
    budget = limits["investigation_quota_points"]
    if "unknown" in reading or spent < budget:
        return None
    resets = reading.get("resets_at")
    when = f"; the Codex week resets {datetime.fromtimestamp(resets).astimezone():%a %d %b %H:%M}" if resets else ""
    return {"reason": f"investigation is waiting for its weekly budget ({spent} of {budget} points used{when})",
            "until": resets}


def floor_block(reading: dict, limits: dict) -> str:
    """The weekly safety floor shared by daily and first-run investigations."""
    if "unknown" in reading:
        return ""
    floor = limits["quota_floor_percent"]
    if reading["used_percent"] >= floor:
        resets = datetime.fromtimestamp(reading["resets_at"]).astimezone() if reading.get("resets_at") else None
        return (f"the Codex week is at {reading['used_percent']}%, at or past the {floor}% "
                "floor kept for your own work" + (f"; investigation resumes when it resets {resets:%a %d %b %H:%M}"
                                                  if resets else ""))
    return ""


PAUSE = "quota-paused.json"


def record_pause(root, reading: dict, limits: dict) -> None:
    """Since when the floor has held REM's work, kept across turns until it lifts (#2938).

    Two nights of turns stopped at the floor and every place the owner looks read
    "quiet". The first stop is the date status and the morning note give.
    """
    from . import service
    path, moment = state_path(root, PAUSE), service.now().isoformat()
    saved = read_json(path, {})
    open_since = saved.get("since") if saved and not saved.get("ended_at") else None
    if floor_block(reading, limits):
        write_json(path, {"since": open_since or moment, "used_percent": reading["used_percent"],
                          "floor": limits["quota_floor_percent"], "resets_at": reading.get("resets_at")})
    elif open_since:
        write_json(path, {**saved, "ended_at": moment})


def paused(root) -> dict | None:
    """The pause holding REM now, or None: ended, or its week has reset since."""
    from . import service
    saved = read_json(state_path(root, PAUSE), {})
    if not saved or saved.get("ended_at"):
        return None
    if saved.get("resets_at") and saved["resets_at"] <= service.now().timestamp():
        return None
    return {"reason": "quota", **saved}


def paused_between(root, start, end) -> bool:
    """Whether the floor held REM at any time in [start, end), for the night's record."""
    from . import service
    saved = read_json(state_path(root, PAUSE), {})
    if not saved:
        return False
    began = datetime.fromisoformat(saved["since"])
    stops = [service.now()]
    if saved.get("ended_at"):
        stops.append(datetime.fromisoformat(saved["ended_at"]))
    if saved.get("resets_at"):
        stops.append(datetime.fromtimestamp(saved["resets_at"]).astimezone())
    return began < end and min(stops) > start

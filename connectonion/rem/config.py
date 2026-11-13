"""Start-first defaults. Read-only inspection never initializes the notebook."""

import copy
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .files import WRITE_WAIT_SECONDS, CATEGORIES, RemError, atomic_write, maintenance_lock, read_json, safe_path, state_path, write_json


def local_timezone() -> str:
    candidate = os.environ.get("TZ", "").removeprefix(":")
    if not candidate:
        # macOS resolves further into zoneinfo.default, so inspect the public
        # localtime link before canonicalizing its target.
        local = Path("/etc/localtime")
        target = os.readlink(local) if local.is_symlink() else str(local.resolve())
        candidate = target.split("/zoneinfo/")[-1] if "/zoneinfo/" in target else ""
    try:
        ZoneInfo(candidate)
    except (ValueError, ZoneInfoNotFoundError):
        return ""  # Do not invent UTC for a user whose timezone is unknown.
    return candidate


# Every stage runs through co ai. "default" lets the selected harness choose its model.
RUNNERS = ("codex", "coai", "claude-code")


def schedule_runner() -> str:
    """Prefer persistent exec sessions when the installed CLI can run."""
    from .runner import ready
    from .codex_schedule import app_installed
    return 'codex-app' if ready({'runner': 'codex'})[0] and app_installed() else 'codex-exec'


# The cheapest model that does each kind of call well, measured on the owner's
# runs 2026-10-10..11-09 (sprint-12/model-levels.md). Level 1 is the weakest.
LEVEL_MODELS = {"level1": "gpt-6-luna", "level2": "gpt-6.1-terra",
                "level3": "gpt-6.1-sol", "level4": "gpt-6-astra"}
STAGE_LEVELS = {
    # 1: short, structured, checked by code afterwards.
    "sessions-summary": 1, "topic": 1,
    # 2: faithful transformation or a narrow judgement over small input.
    "translate": 2, "extract": 2, "same-person": 2, "plan": 2,
    # 3: writing pages and drafts the owner reads, from cited evidence.
    "maintain": 3, "abstract": 3, "init": 3, "investigate": 3, "render": 3,
    "projects": 3, "reply-draft": 3, "native": 3,
    # 4: deep rounds, independent audits, and owed work done for the owner.
    "enrich": 4, "muse": 4, "claim-audit": 4, "insight-critic": 4, "synthesize": 4, "task": 4,
}


# Names before 1.9.3, still accepted by `config set`.
OLD_NAMES = {"model": "models.level3", "models.summary": "models.level1"}


def level_model(config: dict, stage: str) -> str:
    return config["models"][f"level{STAGE_LEVELS[stage]}"]


def describe_levels(config: dict) -> list[str]:
    """One line per level for status and config: its model, then the stages on it."""
    return [f"level {n} {config['models'][f'level{n}']} · "
            + ", ".join(stage for stage, level in STAGE_LEVELS.items() if level == n) for n in range(1, 5)]


def default_config() -> dict:
    # models: owner decision 2026-11-09, one model per level; STAGE_LEVELS says
    # which level each model call runs on. `model` is never saved: it is level3's
    # model, kept beside the levels for code that runs the work level.
    # language: what a page's prose is written in, a BCP 47 tag (en, zh, zh-TW, ja).
    # Headings, Facts labels and markers stay English: code reads them.
    # languages: the languages the owner reads, first in the reader's "Read in"
    # menu and translated in the background. Empty means the languages he writes,
    # detected from his own mail and sessions (D-103), not "translate nothing".
    # tasks.auto: owed work starts after the night's drafts, with full access and Undo
    # (owner, D-100, 2026-11-09). An owner's own `config set tasks.auto false` wins.
    return {"version": 1, "notify": {"channel": "none", "target": ""}, "tasks": {"auto": True}, "runner": "codex", "model": LEVEL_MODELS["level3"], "models": dict(LEVEL_MODELS), "speed": "fast", "effort": "medium", "language": "en", "languages": [],
            # Each slot is followed by 15-minute turns for up to three hours. The old six
            # slots left 22:00-03:00 with nothing running; the weekly Codex budget, not the
            # number of slots, bounds what the night spends.
            "schedule": {"times": ["00:00", "01:00", "02:00", "03:00", "04:00", "05:00", "06:00",
                                   "17:00", "18:00", "19:00", "22:00", "23:00"],
                         "timezone": local_timezone(), "runner": "codex-exec", "profile": "default"},
            # input_chars_per_batch bounds the source messages plus every notebook page
            # the runner reads back. At 60k the reads ran out five times in six real
            # batches (2026-09-07); 200k is ~50k tokens, small for the runner models.
            # items_per_batch is the most the maintainer reads raw. A sync gathers up
            # to extract_items_per_batch; a batch larger than items_per_batch is first
            # digested by the rem-extract pass and the maintainer reads that.
            # 40, not 150: one turn digesting 79 mails came back as 18 bullets, and a
            # person's page is only as full as the notes handed to the maintainer.
            # runner_calls_per_day was 6 when one maintenance call read the whole
            # notebook (0.7-1.4M input tokens a call). A page per call costs about
            # 120k, so 6 left one batch a night against a backlog of hundreds of
            # sessions; 30 is less total spend than the old three batches.
            # Native page rounds and their final audits share 200 calls/day.
            # timeout_seconds is one model turn. Codex reads a large material file
            # piece by piece; at 600 two real turns timed out on 2026-09-23/24
            # (a 300k digest chunk, then a project's material).
            # extract_chars_per_batch stays under input_chars_per_batch: a digest
            # chunk is read through the same 600-second turn, and at 300k a Codex
            # turn reading it piece by piece timed out on 2026-09-23 (Briar, 39
            # mails with attachments) while every 200k investigate turn finished.
            "limits": {"runner_calls_per_day": 200, "items_per_batch": 20,
                       "input_chars_per_batch": 200000, "timeout_seconds": 1200,
                       "extract_items_per_batch": 40, "extract_chars_per_batch": 150000,
                       # Pages at once for init's first run and investigate CATEGORY;
                       # --workers overrides one run. Measured 2026-10-20 (Codex, fast):
                       # 4/8/12/16 workers wrote ~30/38/61/63 pages an hour with no
                       # failures and no 429s; a model round slowed only 430s -> 530s.
                       # 48 (2026-10-09) slowed each turn 2.5x for no more pages than 16.
                       "workers": 16,
                       # Points of the Codex weekly window (#1843): investigation's
                       # budget, and the level past which it starts nothing so the
                       # owner's own coding keeps the rest of the week.
                       "investigation_quota_points": 35, "quota_floor_percent": 90,
                       # Deepening's share of the Codex week, separate from investigation's
                       # 35; the owner agreed 30% on #2533.
                       "depth_quota_points": 30,
                       # 2026-10-20: large-page rounds take 35–97 minutes, mostly
                       # waiting on model turns. Three pages fill the slot's workers
                       # while keeping each enrich + muse round whole.
                       "depth_workers": 3, "depth_pages_per_slot": 3,
                       # 2026-10-20: stop starting pages after an hour;
                       # running rounds finish even when they exceed the slot.
                       "depth_slot_minutes": 60,
                       # A page whose evidence is more than one turn can hold is read in
                       # rounds, each part whole, then one synthesis turn (#2314).
                       "investigation_rounds": 8}}


LANGUAGE = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
# D-104: schedules are compared night against night (.state/night-stats.jsonl). dense is a
# slot every 30 minutes from 22:00 to 07:00, each with its 15-minute follow-ups.
# Times set with `config set schedule.times` win over any profile.
PROFILES = {"default": default_config()["schedule"]["times"],
            "dense": sorted(f"{hour:02d}:{minute:02d}" for hour in (*range(22, 24), *range(0, 8))
                            for minute in (0, 30) if (hour, minute) != (7, 30))}


def validate(config: dict) -> dict:
    defaults = default_config()
    if not isinstance(config, dict) or set(config) - {"model"} != set(defaults) - {"model"} or config["version"] != 1:
        raise RemError("Invalid co rem config keys or version")
    if config["runner"] not in RUNNERS:
        raise RemError(f"runner must be one of {', '.join(RUNNERS)}")
    if not isinstance(config["tasks"], dict) or set(config["tasks"]) != {"auto"} or type(config["tasks"]["auto"]) is not bool:
        raise RemError("tasks.auto must be true or false")
    notify = config["notify"]
    if (not isinstance(notify, dict) or set(notify) != {"channel", "target"}
            or notify["channel"] not in ("none", "outlook", "telegram", "lark", "whatsapp", "email")
            or not isinstance(notify["target"], str)):
        raise RemError("notify.channel must be none, outlook, telegram, lark, whatsapp or email; notify.target must be text")
    models = config["models"]
    if (not isinstance(models, dict) or set(models) != set(LEVEL_MODELS)
            or any(not isinstance(name, str) or not name.strip() for name in models.values())):
        raise RemError("models.level1 to models.level4 must each be a model name or default")
    if config["effort"] not in ("minimal", "low", "medium", "high", "xhigh"):
        raise RemError("effort must be minimal, low, medium, high or xhigh")
    if config["speed"] not in ("fast", "standard"):
        raise RemError("speed must be fast or standard")
    if not isinstance(config["language"], str) or not LANGUAGE.fullmatch(config["language"]):
        raise RemError("language must be a language tag such as en, zh, zh-TW or ja")
    if (not isinstance(config["languages"], list)
            or any(not isinstance(tag, str) or not LANGUAGE.fullmatch(tag) for tag in config["languages"])):
        raise RemError("languages must be language tags separated by commas, such as zh,en")
    schedule, limits = config["schedule"], config["limits"]
    if not isinstance(schedule, dict) or set(schedule) != {"times", "timezone", "runner", "profile"}:
        raise RemError("Schedule requires times and timezone")
    if schedule["profile"] not in PROFILES:
        raise RemError(f"schedule.profile must be {' or '.join(PROFILES)}")
    if schedule["runner"] not in ("codex-exec", "codex-app"):
        raise RemError("schedule.runner must be codex-exec or codex-app")
    times = schedule["times"]
    if (not isinstance(times, list) or not times or len(times) != len(set(map(str, times)))
            or any(not isinstance(t, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in times)):
        raise RemError("schedule.times must contain unique HH:MM times")
    try:
        ZoneInfo(schedule["timezone"])
    except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise RemError("Set schedule.timezone to a valid IANA timezone") from error
    if not isinstance(limits, dict) or set(limits) != set(defaults["limits"]):
        raise RemError("Invalid limit keys")
    if any(type(value) is not int or value < 1 for value in limits.values()):
        raise RemError("Limits must be positive integers")
    if limits["workers"] > 32:
        raise RemError("workers must be 1 to 32")
    if any(limits[key] > 100 for key in ("quota_floor_percent", "investigation_quota_points", "depth_quota_points")):
        raise RemError("quota_floor_percent, investigation_quota_points and depth_quota_points are percents: 1 to 100")
    return config


# Defaults this package once shipped and has since replaced. `init` wrote every
# default into config.yaml and a saved value always wins, so a notebook kept
# the defaults of the day it was made: one from 2026-09-20 ran the refused
# gpt-5.3-codex-spark for four nights (#1714). A saved value equal to one of
# these is read as unset, unless the owner chose it with `config set`.
SUPERSEDED = {"model": {"gpt-5.3-codex-spark", "gpt-6-luna"},
              "limits.timeout_seconds": {600},
              "limits.extract_chars_per_batch": {300000},
              "limits.runner_calls_per_day": {6, 30, 50},
              "limits.investigation_quota_points": {20},
              "limits.quota_floor_percent": {70},
              # init wrote the rc61 default into every config.yaml; it was never his choice.
              "tasks.auto": {False},
              "schedule.times": {("03:00", "04:00", "06:00", "17:00", "18:00", "19:00")}}
EXPLICIT = "config-explicit.json"
# Count caps the owner retired on 2026-11-09 (D-104, "启动的时候，数量可以不用受限制"):
# none of them stops night work any more. A saved value is dropped when read.
RETIRED = ("tasks_per_night", "drafts_per_night", "jobs_per_round", "translations_per_day")
RETIRED_NOTE = ("was retired (D-104): count caps no longer stop the night; only the Codex week floor "
                "(limits.quota_floor_percent) does")


OLD_TIMES = ["03:00", "04:00", "06:00", "17:00", "18:00", "19:00"]
# Written once the pin migration ran, and by any later `config set schedule.times`:
# from then on a pin equal to the old default is the owner's choice.
PIN_CHECKED = "config-pin-checked.json"


def _explicit(root: Path, config: dict) -> set:
    """Keys the owner set. A schedule.times pin equal to the old default, saved before the
    pin check, came from a session restore rather than from him, and does not count."""
    explicit = set(read_json(state_path(root, EXPLICIT), []))
    schedule = config.get("schedule") if isinstance(config.get("schedule"), dict) else {}
    if ("schedule.times" in explicit and schedule.get("times") == OLD_TIMES
            and not state_path(root, PIN_CHECKED).is_file()):
        explicit.discard("schedule.times")
    return explicit


def migrate_schedule_pin(root: Path) -> None:
    """Once: unpin a schedule equal to the old default and log it. Caller holds the lock (start)."""
    if state_path(root, PIN_CHECKED).is_file() or not safe_path(root, "config.yaml").is_file():
        return
    saved = yaml.safe_load(safe_path(root, "config.yaml").read_text(encoding="utf-8")) or {}
    explicit = read_json(state_path(root, EXPLICIT), [])
    if "schedule.times" in explicit and "schedule.times" not in _explicit(root, saved):
        write_json(state_path(root, EXPLICIT), [key for key in explicit if key != "schedule.times"])
        entry = {"at": _now(), "key": "schedule.times", "from": OLD_TIMES, "to": read_config(root)["schedule"]["times"],
                 "why": "the pinned value was exactly the old default (a session restore, not a choice); "
                        "co rem config set schedule.times pins times again"}
        with state_path(root, "config-migrations.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")
    write_json(state_path(root, PIN_CHECKED), {"at": _now()})


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _drop_superseded(root: Path, config: dict) -> None:
    explicit = _explicit(root, config)
    defaults = default_config()
    for key, old in SUPERSEDED.items():
        section, _, name = key.rpartition(".")
        saved = config.get(section) if section else config
        current = defaults[section] if section else {"model": LEVEL_MODELS["level3"]}
        value = saved.get(name) if isinstance(saved, dict) else None
        if key not in explicit and isinstance(saved, dict) and (tuple(value) if isinstance(value, list) else value) in old:
            saved[name] = current[name]


def read_config(root: Path, *, validated: bool = True) -> dict:
    path = safe_path(root, "config.yaml")
    if not path.exists():
        return default_config()
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeError) as error:
        raise RemError("Invalid config.yaml; preserve it for diagnosis") from error
    if not isinstance(config, dict):
        raise RemError("config.yaml must contain a mapping")
    # A limit added after this file was written takes its default; the file is
    # not rewritten until the user changes something.
    if isinstance(config.get("limits"), dict):
        saved = {key: value for key, value in config["limits"].items() if key not in RETIRED}
        config["limits"] = {**default_config()["limits"], **saved}
    config.setdefault("notify", {"channel": "none", "target": ""})
    config.setdefault("tasks", {"auto": True})
    config.setdefault("language", "en")
    config.setdefault("languages", [])
    config.setdefault("speed", "fast")
    config.setdefault("effort", "medium")
    if isinstance(config.get("schedule"), dict) and 'runner' not in config['schedule']:
        config['schedule']['runner'] = default_config()['schedule']['runner']
    if isinstance(config.get("schedule"), dict):
        config["schedule"].setdefault("profile", "default")
    _drop_superseded(root, config)
    explicit = _explicit(root, config)
    if ("schedule.profile" in explicit and "schedule.times" not in explicit
            and config["schedule"].get("profile") in PROFILES):
        config["schedule"]["times"] = PROFILES[config["schedule"]["profile"]]
    _migrate_models(config)
    return validate(config) if validated else config


def _migrate_models(config: dict) -> None:
    """Before 1.9.3 `model` was the work model (now level3) and models.summary
    the summary model (now level1). A non-Codex notebook keeps its one model on
    every level its harness can run; a saved level always wins."""
    work = config.pop("model", None)
    saved = config.get("models") if isinstance(config.get("models"), dict) else {}
    levels = dict(LEVEL_MODELS) if config.get("runner") == "codex" else dict.fromkeys(LEVEL_MODELS, work or "default")
    levels.update({"level3": work} if work else {})
    levels.update({"level1": saved["summary"]} if "summary" in saved else {})
    levels.update({key: value for key, value in saved.items() if key in LEVEL_MODELS})
    config["models"] = levels
    config["model"] = levels["level3"]


def _move_generated_notes(root: Path) -> None:
    """Before 1.9.1 the maps and skill run reports went to notes/, and in every
    real notebook they were all notes/ held. They are run logs now; the skill
    pages that link a report follow it."""
    notes = root / "notes"
    moved = [*notes.glob("skill-runs-*.md"), *(notes / f"{c}-map.md" for c in ("people", "projects", "orgs"))]
    moved = [path for path in moved if path.is_file()]
    for path in moved:
        path.replace(root / "logs" / path.name)
    if not moved:
        return
    for page in (root / "skills/catalog").glob("*.md"):
        text = page.read_text(encoding="utf-8")
        if "../../notes/skill-runs-" in text:
            atomic_write(page, text.replace("../../notes/skill-runs-", "../../logs/skill-runs-"))


def prepare(root: Path) -> None:
    """Prepare only missing paths; caller holds the root lock when concurrent."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path(root, "maintenance.lock").parent.mkdir(exist_ok=True, mode=0o700)
    for name in (*CATEGORIES, "skills/catalog", "skills/candidates", "skills/approved"):
        safe_path(root, name).mkdir(parents=True, exist_ok=True, mode=0o700)
    _move_generated_notes(root)
    path = safe_path(root, "config.yaml")
    if not path.exists():
        atomic_write(path, yaml.safe_dump(saved(first_runner(default_config())), sort_keys=False))
    migrate_schedule_pin(root)


def saved(config: dict) -> dict:
    """What config.yaml holds: the levels, not the `model` derived from them."""
    return {key: value for key, value in config.items() if key != "model"}


def first_runner(config: dict) -> dict:
    """Codex when it can run; otherwise Claude Code, if that can."""
    from .runner import ready
    config['schedule']['runner'] = schedule_runner()
    if not ready(config)[0]:
        return config
    fallback = {**config, "runner": "claude-code", "model": "claude-sonnet-5-5",
                "models": dict.fromkeys(LEVEL_MODELS, "claude-sonnet-5-5")}
    return fallback if not ready(fallback)[0] else config


def set_config(root: Path, pairs: list[str]) -> dict:
    if not pairs or len(pairs) % 2:
        raise RemError("config set needs KEY VALUE pairs")
    with maintenance_lock(root):
        return _set_config(root, pairs)


def request_language(root: Path, language: str) -> dict:
    """Persist the owner's reader choice without replacing other languages."""
    if not isinstance(language, str) or not LANGUAGE.fullmatch(language):
        raise RemError("language must be a language tag such as en, zh, zh-TW or ja")
    with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
        config = read_config(root)
        if language in config["languages"]:
            return config
        return _set_config(root, ["languages", ",".join([*config["languages"], language])])


def _set_config(root: Path, pairs: list[str]) -> dict:
    migrate_schedule_pin(root)
    config = copy.deepcopy(read_config(root, validated=False))
    previous_runner = config["runner"]
    pairs = [OLD_NAMES.get(part, part) if index % 2 == 0 else part for index, part in enumerate(pairs)]
    for key, raw in zip(pairs[::2], pairs[1::2]):
        parts = key.split(".")
        target = config
        if len(parts) == 2 and parts[0] in ("schedule", "limits", "models", "tasks", "notify"):
            target = config.get(parts[0])
            if not isinstance(target, dict):
                raise RemError("Invalid nested configuration; preserve config.yaml for diagnosis")
        elif len(parts) != 1 or key not in ("runner", "speed", "effort", "language", "languages"):
            raise RemError(f"{key}: " "not a setting; the keys are runner, speed, effort, language, languages, models.level1 to models.level4, schedule.runner, schedule.times, schedule.timezone, schedule.profile, limits.<name> and route.<stage> (see `co rem config`)")
        if parts[0] == "limits" and parts[-1] in RETIRED:
            raise RemError(f"{key} {RETIRED_NOTE}")
        if parts[-1] not in target:
            raise RemError(f"{key}: " "not a setting; the keys are runner, speed, effort, language, languages, models.level1 to models.level4, schedule.runner, schedule.times, schedule.timezone, schedule.profile, limits.<name> and route.<stage> (see `co rem config`)")
        if key == "tasks.auto":
            if raw not in ("true", "false"):
                raise RemError("tasks.auto must be true or false")
            value = raw == "true"
        elif key == "schedule.times":
            value = sorted(raw.split(","))
        elif key == "languages":
            value = [tag.strip() for tag in raw.split(",") if tag.strip()]
        elif parts[0] == "limits":
            try:
                value = int(raw)
            except ValueError as error:
                raise RemError("Limits must be positive integers") from error
        else:
            value = raw
        target[parts[-1]] = value
    if config["runner"] != previous_runner:
        # Another harness cannot run these model names; levels this command names stay.
        config["models"].update({level: LEVEL_MODELS[level] if config["runner"] == "codex" else "default"
                                 for level in LEVEL_MODELS if f"models.{level}" not in pairs[::2]})
    explicit = set(read_json(state_path(root, EXPLICIT), [])) | set(pairs[::2])
    config["model"] = config["models"]["level3"]
    validate(config)
    atomic_write(safe_path(root, "config.yaml"), yaml.safe_dump(saved(config), sort_keys=False))
    write_json(state_path(root, EXPLICIT), sorted(explicit))
    if "schedule.times" in pairs[::2]:
        write_json(state_path(root, PIN_CHECKED), {"at": _now()})
    return config

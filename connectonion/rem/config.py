"""Start-first defaults. Read-only inspection never initializes the notebook."""

import copy
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .files import CATEGORIES, RemError, atomic_write, maintenance_lock, read_json, safe_path, state_path, write_json


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

def default_config() -> dict:
    # Spark was the default until Codex 0.155 refused it for ChatGPT logins
    # ("not supported when using Codex with a ChatGPT account"), which made every
    # new user's first investigation fail in eleven seconds. gpt-6-luna runs on
    # a ChatGPT subscription (checked with Codex 0.155.1 on 2026-09-23). It is a
    # starting name, not a rule: what a model can do -- drive tools, or only
    # reply with a page -- is measured when the model changes and recorded in
    # .state/tier.json (tier.py, #1847), never read off its name or generation.
    return {"version": 1, "runner": "codex", "model": "gpt-6-luna",
            "schedule": {"times": ["03:00", "04:00", "06:00", "17:00", "18:00", "19:00"],
                         "timezone": local_timezone()},
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
            # timeout_seconds is one model turn. Codex reads a large material file
            # piece by piece; at 600 two real turns timed out on 2026-09-23/24
            # (a 300k digest chunk, then a project's material).
            # extract_chars_per_batch stays under input_chars_per_batch: a digest
            # chunk is read through the same 600-second turn, and at 300k a Codex
            # turn reading it piece by piece timed out on 2026-09-23 (Dora, 39
            # mails with attachments) while every 200k investigate turn finished.
            "limits": {"runner_calls_per_day": 30, "items_per_batch": 20,
                       "input_chars_per_batch": 200000, "timeout_seconds": 1200,
                       "extract_items_per_batch": 40, "extract_chars_per_batch": 150000,
                       # Points of the Codex weekly window (#1843): investigation's
                       # budget, and the level past which it starts nothing so the
                       # owner's own coding keeps the rest of the week.
                       "investigation_quota_points": 10, "quota_floor_percent": 70}}


def validate(config: dict) -> dict:
    defaults = default_config()
    if not isinstance(config, dict) or set(config) != set(defaults) or config["version"] != 1:
        raise RemError("Invalid co rem config keys or version")
    if config["runner"] not in RUNNERS or not isinstance(config["model"], str) or not config["model"].strip():
        raise RemError(f"runner must be one of {', '.join(RUNNERS)}, with a model name or default")
    schedule, limits = config["schedule"], config["limits"]
    if not isinstance(schedule, dict) or set(schedule) != {"times", "timezone"}:
        raise RemError("Schedule requires times and timezone")
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
    if limits["quota_floor_percent"] > 100 or limits["investigation_quota_points"] > 100:
        raise RemError("quota_floor_percent and investigation_quota_points are percents: 1 to 100")
    return config


# Defaults this package once shipped and has since replaced. `init` wrote every
# default into config.yaml and a saved value always wins, so a notebook kept
# the defaults of the day it was made: one from 2026-09-20 ran the refused
# gpt-5.3-codex-spark for four nights (#1714). A saved value equal to one of
# these is read as unset, unless the owner chose it with `config set`.
SUPERSEDED = {"model": {"gpt-5.3-codex-spark"},
              "limits.timeout_seconds": {600},
              "limits.extract_chars_per_batch": {300000},
              "limits.runner_calls_per_day": {6}}
EXPLICIT = "config-explicit.json"


def _drop_superseded(root: Path, config: dict) -> None:
    explicit = set(read_json(state_path(root, EXPLICIT), []))
    defaults = default_config()
    for key, old in SUPERSEDED.items():
        section, _, name = key.rpartition(".")
        saved = config.get(section) if section else config
        current = defaults[section] if section else defaults
        if key not in explicit and isinstance(saved, dict) and saved.get(name) in old:
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
        config["limits"] = {**default_config()["limits"], **config["limits"]}
    _drop_superseded(root, config)
    # Older coai notebooks retained the Codex default even though it was never
    # forwarded. Preserve their effective behavior when all stages start using COAI.
    if config.get("runner") == "coai" and config.get("model") == default_config()["model"]:
        config["model"] = "default"
    return validate(config) if validated else config


def prepare(root: Path) -> None:
    """Prepare only missing paths; caller holds the root lock when concurrent."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path(root, "maintenance.lock").parent.mkdir(exist_ok=True, mode=0o700)
    for name in (*CATEGORIES, "skills/catalog", "skills/candidates", "skills/approved"):
        safe_path(root, name).mkdir(parents=True, exist_ok=True, mode=0o700)
    path = safe_path(root, "config.yaml")
    if not path.exists():
        atomic_write(path, yaml.safe_dump(default_config(), sort_keys=False))


def set_config(root: Path, pairs: list[str]) -> dict:
    if not pairs or len(pairs) % 2:
        raise RemError("config set needs KEY VALUE pairs")
    with maintenance_lock(root):
        config = copy.deepcopy(read_config(root, validated=False))
        previous_runner = config["runner"]
        for key, raw in zip(pairs[::2], pairs[1::2]):
            parts = key.split(".")
            target = config
            if len(parts) == 2 and parts[0] in ("schedule", "limits"):
                target = config.get(parts[0])
                if not isinstance(target, dict):
                    raise RemError("Invalid nested configuration; preserve config.yaml for diagnosis")
            elif len(parts) != 1 or key not in ("model", "runner"):
                raise RemError(f"{key}: " "not a setting; the keys are model, runner, schedule.times, schedule.timezone, limits.<name> and route.<stage> (see `co rem config`)")
            if parts[-1] not in target:
                raise RemError(f"{key}: " "not a setting; the keys are model, runner, schedule.times, schedule.timezone, limits.<name> and route.<stage> (see `co rem config`)")
            if key == "schedule.times":
                value = sorted(raw.split(","))
            elif parts[0] == "limits":
                try:
                    value = int(raw)
                except ValueError as error:
                    raise RemError("Limits must be positive integers") from error
            else:
                value = raw
            target[parts[-1]] = value
        if config["runner"] != previous_runner and "model" not in pairs[::2]:
            config["model"] = "default"
        validate(config)
        atomic_write(safe_path(root, "config.yaml"), yaml.safe_dump(config, sort_keys=False))
        explicit = set(read_json(state_path(root, EXPLICIT), [])) | set(pairs[::2])
        write_json(state_path(root, EXPLICIT), sorted(explicit))
        return config

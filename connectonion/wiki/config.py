"""Start-first defaults. Read-only inspection never initializes the notebook."""

import copy
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .files import CATEGORIES, WikiError, atomic_write, maintenance_lock, safe_path, state_path


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


def default_config() -> dict:
    return {"version": 1, "runner": "codex", "model": "gpt-5.3-codex-spark",
            "schedule": {"times": ["03:00", "04:00", "06:00", "17:00", "18:00", "19:00"],
                         "timezone": local_timezone()},
            # input_chars_per_batch bounds the source messages plus every notebook page
            # the runner reads back. At 60k the reads ran out five times in six real
            # batches (2026-09-07); 200k is ~50k tokens, small for the runner models.
            # items_per_batch is the most the maintainer reads raw. A sync gathers up
            # to extract_items_per_batch; a batch larger than items_per_batch is first
            # digested by the tool-less wiki-extract pass and the maintainer reads that.
            # 40, not 150: one turn digesting 79 mails came back as 18 bullets, and a
            # person's page is only as full as the notes handed to the maintainer.
            "limits": {"runner_calls_per_day": 6, "items_per_batch": 20,
                       "input_chars_per_batch": 200000, "timeout_seconds": 600,
                       "extract_items_per_batch": 40, "extract_chars_per_batch": 300000}}


def validate(config: dict) -> dict:
    defaults = default_config()
    if not isinstance(config, dict) or set(config) != set(defaults) or config["version"] != 1:
        raise WikiError("Invalid Wiki config keys or version")
    if config["runner"] != "codex" or not isinstance(config["model"], str) or not config["model"].strip():
        raise WikiError("This milestone requires runner codex and an explicit model")
    schedule, limits = config["schedule"], config["limits"]
    if not isinstance(schedule, dict) or set(schedule) != {"times", "timezone"}:
        raise WikiError("Schedule requires times and timezone")
    times = schedule["times"]
    if (not isinstance(times, list) or not times or len(times) != len(set(map(str, times)))
            or any(not isinstance(t, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in times)):
        raise WikiError("schedule.times must contain unique HH:MM times")
    try:
        ZoneInfo(schedule["timezone"])
    except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise WikiError("Set schedule.timezone to a valid IANA timezone") from error
    if not isinstance(limits, dict) or set(limits) != set(defaults["limits"]):
        raise WikiError("Invalid limit keys")
    if any(type(value) is not int or value < 1 for value in limits.values()):
        raise WikiError("Limits must be positive integers")
    return config


def read_config(root: Path, *, validated: bool = True) -> dict:
    path = safe_path(root, "config.yaml")
    if not path.exists():
        return default_config()
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeError) as error:
        raise WikiError("Invalid config.yaml; preserve it for diagnosis") from error
    if not isinstance(config, dict):
        raise WikiError("config.yaml must contain a mapping")
    # A limit added after this file was written takes its default; the file is
    # not rewritten until the user changes something.
    if isinstance(config.get("limits"), dict):
        config["limits"] = {**default_config()["limits"], **config["limits"]}
    return validate(config) if validated else config


def prepare(root: Path) -> None:
    """Prepare only missing paths; caller holds the root lock when concurrent."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path(root, "maintenance.lock").parent.mkdir(exist_ok=True, mode=0o700)
    for name in (*CATEGORIES, "skills/candidates", "skills/approved"):
        safe_path(root, name).mkdir(parents=True, exist_ok=True, mode=0o700)
    path = safe_path(root, "config.yaml")
    if not path.exists():
        atomic_write(path, yaml.safe_dump(default_config(), sort_keys=False))


def set_config(root: Path, pairs: list[str]) -> dict:
    if not pairs or len(pairs) % 2:
        raise WikiError("config set needs KEY VALUE pairs")
    with maintenance_lock(root):
        config = copy.deepcopy(read_config(root, validated=False))
        for key, raw in zip(pairs[::2], pairs[1::2]):
            parts = key.split(".")
            target = config
            if len(parts) == 2 and parts[0] in ("schedule", "limits"):
                target = config.get(parts[0])
                if not isinstance(target, dict):
                    raise WikiError("Invalid nested configuration; preserve config.yaml for diagnosis")
            elif len(parts) != 1 or key not in ("model", "runner"):
                raise WikiError("Unknown or immutable configuration key")
            if parts[-1] not in target:
                raise WikiError("Unknown configuration key")
            if key == "schedule.times":
                value = sorted(raw.split(","))
            elif parts[0] == "limits":
                try:
                    value = int(raw)
                except ValueError as error:
                    raise WikiError("Limits must be positive integers") from error
            else:
                value = raw
            target[parts[-1]] = value
        validate(config)
        atomic_write(safe_path(root, "config.yaml"), yaml.safe_dump(config, sort_keys=False))
        return config

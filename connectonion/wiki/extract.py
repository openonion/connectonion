"""Digest a batch through the same COAI CLI used by every Wiki stage."""

import hashlib
import json
import tempfile
from pathlib import Path

from .files import read_json, state_path, write_json
from .runner import RunFailed, instructions, run_task, task_prompt

NOTHING = "Nothing worth keeping."


def extraction_instructions(kind: str = "") -> str:
    """This stage's Skill, composed with the source the batch came from."""
    return instructions("extract", kind)


def extraction_item(notes: str, items: list[dict]) -> dict:
    """The one maintain item that stands for a whole extracted batch."""
    projects = [item.get("project", "") for item in items if item.get("project")]
    project = max(set(projects), key=projects.count) if projects else ""
    sources = sorted({item["source"].rsplit(":", 1)[0] for item in items})
    return {"role": "extract", "text": notes, "timestamp": items[-1]["timestamp"],
            "source": sources[0] if len(sources) == 1 else f"{sources[0]} +{len(sources) - 1}",
            "reference": "; ".join(sources[:5]), "project": project, "messages": len(items),
            # Every message the digest read, by its own id. The writer cites
            # these, not the digest: without them a page about anyone with
            # enough mail to need a digest could not cite a single message.
            "sources": sorted({item["source"] for item in items if item.get("source")})}


def _batch_key(items: list[dict], kind: str) -> str:
    return hashlib.sha256(json.dumps([kind, [item["source"] for item in items]]).encode()).hexdigest()


def finished_digest(root: Path, items: list[dict], kind: str) -> str | None:
    """Notes an earlier run already paid to extract from exactly this batch.

    A batch whose maintainer failed keeps its cursor, so the next run gathers the
    same material. Extraction is the expensive pass and its notes are already on
    disk; reading the batch through it again bought the same notes twice.
    """
    saved = read_json(state_path(root, "extracts/unmaintained.json"), {})
    if saved.get("key") != _batch_key(items, kind):
        return None
    notes = state_path(root, saved.get("notes", ""))
    return notes.read_text(encoding="utf-8").strip() if notes.is_file() else None


def remember_digest(root: Path, items: list[dict], kind: str, notes: str) -> None:
    """Called once the notes are on disk; `forget_digest` once a maintainer has used them."""
    write_json(state_path(root, "extracts/unmaintained.json"), {"key": _batch_key(items, kind), "notes": notes})


def forget_digest(root: Path) -> None:
    state_path(root, "extracts/unmaintained.json").unlink(missing_ok=True)


def run_extract(items: list[dict], config: dict, kind: str = "", *, root: Path) -> dict:
    """Read the extraction artifact, not the agent's status message."""
    tasks = state_path(root, "tasks")
    tasks.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="extract-", dir=tasks) as temporary:
        directory = Path(temporary)
        prompt = task_prompt(directory, items, "extract", kind)
        output = directory / "notes.md"
        prompt += (f"Write the complete extraction notes to {output}; this file is your output. "
                   "If nothing is worth keeping, write exactly 'Nothing worth keeping.' "
                   "Do not edit notebook pages, read other sources, or start nested Wiki jobs.")
        result = run_task(tasks, prompt, config, "extract")
        notes = output.read_text(encoding="utf-8").strip() if output.is_file() else ""
        if not notes:
            raise RunFailed("co ai extraction returned no notes file", result.get("usage"))
        return {"notes": notes, "usage": result.get("usage")}

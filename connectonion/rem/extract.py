"""Digest a batch through the same COAI CLI used by every co rem stage."""

import hashlib
import json
import re
import tempfile
from pathlib import Path

from .files import read_json, state_path, write_json
from .runner import RunFailed, instructions, run_task, task_prompt
from .tier import current

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
        task = prepare(items, config, kind, root=root, directory=directory)
        from .inquiry import stage_config
        return check(task, run_task(tasks, task["prompt"], stage_config(root, config, "extract"), "extract"))


def prepare(items, config, kind="", *, root, directory, native=False):
    prompt = task_prompt(directory, items, "extract", kind, native=native)
    output = directory / "notes.md"
    # A summary-tier model has no tool to write a file with (#1847): its notes are its reply.
    summary = not native and current(root, config) == "summary"
    prompt += ("Reply with ONLY the complete extraction notes; do not call tools or write files. "
               if summary else f"Write the complete extraction notes to {output}; this file is your output. ")
    prompt += ("If nothing is worth keeping, write exactly 'Nothing worth keeping.' "
               "Do not edit notebook pages, read other sources, or start nested co rem jobs.")
    return {"directory": str(directory), "candidate": str(output), "prompt": prompt, "summary": summary,
            "root": str(root)}


def check(task, result):
    directory, output = Path(task["directory"]), Path(task["candidate"])
    summary = task["summary"]
    if summary:
        output.write_text(str(result.get("result") or ""), encoding="utf-8")
    notes = output.read_text(encoding="utf-8").strip() if output.is_file() else ""
    if not notes:
        raise RunFailed("co ai extraction returned no notes file", result.get("usage"))
    topics = re.search(r'^## Topics\s*\n.*?(?=^## |\Z)', notes, re.M | re.S)
    if topics and task.get('root'):
        digest = hashlib.sha256(topics[0].encode()).hexdigest()
        write_json(state_path(Path(task['root']), f'extracts/topics/{digest}.json'), {'notes': topics[0]})
    return {"notes": notes, "usage": result.get("usage"),
            "instructions_chars": len((directory / "instructions.md").read_text(encoding="utf-8"))}

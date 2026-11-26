"""Only completed or abandoned turn scratch is disposable; receipts and active work remain."""

import os

from connectonion.rem.config import prepare
from connectonion.rem.files import state_path, write_json
from connectonion.rem.tidy import tidy


def _old(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Disposable fictional material")
    os.utime(path, (1, 1))
    return path


def test_tidy_prunes_turn_logs_and_stale_scratch_preserving_receipts_and_evidence(tmp_path):
    prepare(tmp_path)
    directory = state_path(tmp_path, "turns")
    finished = "20400101T000000.000000Z"
    running = "20400102T000000.000000Z"
    for name, result in ((finished, "completed"), (running, "running")):
        receipt = {"turn_id": name, "result": result, "started_at": "2040-01-01T00:00:00+00:00"}
        if result == "completed":
            receipt["finished_at"] = "2040-01-01T01:00:00+00:00"
        write_json(directory / f"{name}.json", receipt)
        for suffix in (".jsonl", ".last.md", ".preparation.jsonl"):
            _old(directory / f"{name}{suffix}")
    orphan = _old(directory / "abandoned/material.md")
    os.utime(orphan.parent, (1, 1))
    recent = directory / "preparing.jsonl"
    recent.write_text("A new turn is starting")
    research = _old(state_path(tmp_path, "research/cited/capture.json"))
    attachment = _old(state_path(tmp_path, "attachments/gmail/123456789abc/terms.txt"))
    from connectonion.rem.files import Notebook
    Notebook(tmp_path).write("knowledge/terms.md", "# Terms\n\n## Sources\n- [1] gmail:123456789abc:terms.txt\n")
    run = state_path(tmp_path, "runs/run_fixture.json")
    write_json(run, {"started_at": "2040-01-01T00:00:00+00:00", "outcome": "completed"})

    done = tidy(tmp_path)

    assert done["pruned turn scratch"] == sorted([
        f".state/turns/{finished}.jsonl", f".state/turns/{finished}.last.md",
        f".state/turns/{finished}.preparation.jsonl", ".state/turns/abandoned"])
    assert (directory / f"{finished}.json").is_file()
    assert (directory / f"{running}.jsonl").is_file()
    assert (directory / f"{running}.last.md").is_file()
    assert (directory / f"{running}.preparation.jsonl").is_file()
    assert recent.is_file() and research.is_file() and attachment.is_file() and run.is_file()
    assert tidy(tmp_path) == {}


def test_tidy_preserves_active_task_scratch_and_never_follows_links(tmp_path):
    prepare(tmp_path)
    scratch = _old(state_path(tmp_path, "turns/task-active.jsonl"))
    write_json(state_path(tmp_path, "tasks/active/task.json"), {"status": "running", "turn_id": "task-active"})
    write_json(state_path(tmp_path, "tasks/other/receipt.json"), {"result": "running",
               "log": str(state_path(tmp_path, "turns/other.jsonl"))})
    other = _old(state_path(tmp_path, "turns/other.jsonl"))
    outside = _old(tmp_path / "outside.txt")
    link = state_path(tmp_path, "turns/linked.jsonl")
    link.symlink_to(outside)
    folder = state_path(tmp_path, "turns/linked-folder")
    folder.mkdir()
    (folder / "linked.txt").symlink_to(outside)
    os.utime(folder, (1, 1))

    tidy(tmp_path)

    assert scratch.is_file() and other.is_file()
    assert link.is_symlink() and folder.is_dir() and outside.is_file()


def test_tidy_keeps_scratch_directories_containing_running_task_files(tmp_path):
    prepare(tmp_path)
    nested = _old(state_path(tmp_path, "turns/nested/active.jsonl"))
    os.utime(nested.parent, (1, 1))
    identified = _old(state_path(tmp_path, "turns/task-active/material.md"))
    os.utime(identified.parent, (1, 1))
    write_json(state_path(tmp_path, "tasks/active/receipt.json"),
               {"result": "running", "log": str(nested)})
    write_json(state_path(tmp_path, "tasks/identified/task.json"),
               {"status": "running", "turn_id": "task-active"})

    tidy(tmp_path)

    assert nested.is_file() and identified.is_file()

"""The post-run audit catches what reading 1.9.2b3's logs by hand caught."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _audit():
    spec = importlib.util.spec_from_file_location("rem_trial_audit", ROOT / "scripts" / "rem_trial_audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(root, name, **fields):
    runs = root / ".state" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{name}.json").write_text(json.dumps({"id": name, "phase": "investigate", "started_at":
                                                   "2026-10-10T01:00:00+00:00", "finished_at":
                                                   "2026-10-10T01:05:00+00:00", **fields}))


def _rollout(sessions, session, cwd, calls, originator="connectonion"):
    day = sessions / "2026" / "10" / "10"
    day.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "session_meta", "payload": {"id": session, "cwd": str(cwd), "originator": originator}}]
    rows += [{"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                                   "arguments": json.dumps({"cmd": call})}} for call in calls]
    (day / f"rollout-2026-10-10T01-00-00-{session}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))


def _notebook(tmp_path):
    root, home = tmp_path / "home" / ".co" / "rem", tmp_path / "home"
    (root / "people").mkdir(parents=True)
    tasks = root / ".state" / "tasks" / "investigate-abc"
    tasks.mkdir(parents=True)
    return root, home, tasks


def test_a_clean_run_passes(tmp_path):
    root, home, tasks = _notebook(tmp_path)
    (root / "people" / "mia.md").write_text("# Mia Chen\n\nMia leads research [1].\n\n## Facts\n"
                                            "- Also known as: Mimi\n\n## Sources\n- [1] gmail:aa11 — 2026-10-09\n")
    _run(root, "run_1", record="people/mia.md", outcome="completed")
    _rollout(home / ".codex" / "sessions", "s-clean", tasks, [f"cat {tasks}/material.md"])
    report = _audit().audit(root, home / ".codex" / "sessions", home)
    assert report["severe"] == [], report["severe"]


def test_the_problems_found_in_the_b3_logs_are_each_severe(tmp_path):
    root, home, tasks = _notebook(tmp_path)
    sessions = home / ".codex" / "sessions"
    # REM read a transcript of the user's and another notebook (row 2 of the audit).
    _rollout(sessions, "s-wander", tasks, [f"rg Larry {home}/.claude/projects/x.jsonl",
                                           f"cat {home}/.co/rem-trials/iter13/people/v.md"])
    # A page cites REM's own task session as the user's words (row 3).
    _rollout(sessions, "01a12360-47f8-7513-aff3-eb033d92fb14", root / ".state" / "tasks" / "model-access", [])
    (root / "people" / "aaron.md").write_text("# Aaron\n\nAsked for a Wiki-only task [1].\n\n"
                                              "## Sources\n- [1] codex:01a12360-47f8-7513-aff3-eb033d92fb14:136643 — 2026-10-10\n")
    # A page refused last, missing from the refusal ledger (row 6).
    _run(root, "run_2", record="skills/catalog/x.md", outcome="refused", error="Section must occur once: Limitations")
    report = _audit().audit(root, sessions, home)
    kinds = {finding["check"] for finding in report["severe"]}
    assert {"read outside the material", "cites REM's own session", "refusal missing from ledger"} <= kinds
    wander = next(f for f in report["severe"] if f["check"] == "read outside the material")
    assert ".claude/projects" in wander["example"] and wander["count"] == 2


def test_page_checks_name_the_page(tmp_path):
    root, home, _ = _notebook(tmp_path)
    (root / "orgs").mkdir()
    (root / "orgs" / "x.md").write_text("# morganpost.net\n\nA newsroom [1][3].\n\n## Sources\n- [1] gmail:a\n- [3] gmail:b\n")
    (root / "people" / "bo.md").write_text("# Bo\n\nBo [1].\n\n## Facts\n- Also known as: bo@x.example\n\n"
                                           "## Sources\n- [1] gmail:c\n")
    report = _audit().audit(root, home / ".codex" / "sessions", home)
    found = {(f["check"], f["page"]) for f in report["pages"]}
    assert ("sources numbered with gaps", "orgs/x.md") in found
    assert ("organisation titled by its domain", "orgs/x.md") in found
    assert ("also known as is only addresses", "people/bo.md") in found


def test_main_exits_nonzero_when_anything_is_severe(tmp_path, capsys):
    root, home, tasks = _notebook(tmp_path)
    _run(root, "run_2", record="people/a.md", outcome="refused", error="x")
    code = _audit().main([str(root), "--sessions", str(home / ".codex" / "sessions"), "--home", str(home)])
    assert code == 1
    assert "refusal missing from ledger" in capsys.readouterr().out


def test_a_repository_the_task_names_is_that_turns_material(tmp_path):
    root, home, tasks = _notebook(tmp_path)
    sessions = home / ".codex" / "sessions"
    _rollout(sessions, "01a12399-0000-7000-8000-000000000001", tasks,
             [f"git -C {home}/code/harbour log -5", f"cat {home}/.claude/projects/x.jsonl"])
    rollout = next(sessions.rglob("*.jsonl"))
    rows = rollout.read_text().split("\n")
    rows.insert(1, json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": f"/rem-investigate <co_rem_task> The project repository is {home}/code/harbour"}]}}))
    rollout.write_text("\n".join(rows))
    wander = next(f for f in _audit().audit(root, sessions, home)["severe"] if f["check"] == "read outside the material")
    assert wander["count"] == 1 and ".claude/projects" in wander["example"]

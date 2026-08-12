"""Behavioral contract for resumable, machine-readable ``co ai`` runs."""

import json
import os

import pytest
import typer

import connectonion.cli.commands.ai_commands as ai_commands
from connectonion.cli.co_ai.agent import create_agent
from connectonion.cli.co_ai.one_shot_sessions import (
    SessionSnapshotError,
    load_snapshot,
    new_session_id,
    save_snapshot,
    session_lock,
)
from connectonion.core.tool_factory import extract_methods_from_instance
from connectonion.useful_tools.todo_list import TodoList
from tests.utils.mock_helpers import MockLLM


def _todo(content):
    return {
        "content": content,
        "status": "pending",
        "active_form": f"Working on {content}",
        "priority": "medium",
    }


def _plan(*contents):
    return [
        {"content": content, "priority": "medium", "status": "pending"}
        for content in contents
    ]


class _ToolRegistry:
    def __init__(self, todo=None):
        self.todo = todo
        self.removed = []

    def get_instance(self, name, default=None):
        return self.todo if name == "todolist" else default

    def remove(self, name):
        self.removed.append(name)
        return True


class _Todo:
    def __init__(self):
        self.state = []

    def _dump_state(self):
        return list(self.state)

    def _load_state(self, state):
        self.state = list(state)


class _Agent:
    system_prompt = "system"

    def __init__(self, noise="progress"):
        self.noise = noise
        self.current_session = None
        self.received_session = None
        self.tools = _ToolRegistry(_Todo())

    def input(self, prompt, session=None):
        print(self.noise)
        self.received_session = session
        base = dict(session or {})
        messages = list(base.get("messages", []))
        messages.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "done"},
        ])
        self.current_session = {
            **base,
            "messages": messages,
            "trace": list(base.get("trace", [])),
            "turn": base.get("turn", 0) + 1,
            "mode": ":danger-full-access",
        }
        self.tools.todo.state.append(_todo(prompt))
        self.current_session["plan"] = [
            {
                "content": item["content"],
                "priority": item["priority"],
                "status": item["status"],
            }
            for item in self.tools.todo.state
        ]
        return "done"


def test_snapshot_round_trip_preserves_full_session_and_tool_state(tmp_path):
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [{"role": "system", "content": "s"}],
        "trace": [],
        "turn": 2,
        "mode": ":danger-full-access",
        "permissions": {"Bash(git *)": {"allowed": True}},
        "plan": _plan("ship"),
    }

    save_snapshot(tmp_path, session, {"todolist": [_todo("ship")]})
    loaded_session, tool_state = load_snapshot(tmp_path, session_id)

    assert loaded_session == session
    assert tool_state == {"todolist": [_todo("ship")]}
    if os.name != "nt":
        assert oct((tmp_path / "ai" / "sessions").stat().st_mode & 0o777) == "0o700"
        snapshot = tmp_path / "ai" / "sessions" / f"{session_id}.json"
        assert oct(snapshot.stat().st_mode & 0o777) == "0o600"


def test_v1_todo_snapshot_migrates_priority_and_canonical_plan(tmp_path):
    session_id = new_session_id()
    session_dir = tmp_path / "ai" / "sessions"
    session_dir.mkdir(parents=True)
    old_todo = {
        "content": "Old task",
        "status": "pending",
        "active_form": "Doing old task",
    }
    (session_dir / f"{session_id}.json").write_text(json.dumps({
        "version": 1,
        "cwd": str(tmp_path.resolve()),
        "session": {
            "session_id": session_id,
            "messages": [],
            "trace": [],
            "turn": 1,
        },
        "tools": {"todolist": [old_todo]},
    }), encoding="utf-8")

    session, tools = load_snapshot(tmp_path, session_id, cwd=tmp_path)

    assert tools == {"todolist": [{**old_todo, "priority": "medium"}]}
    assert session["plan"] == [{
        "content": "Old task",
        "priority": "medium",
        "status": "pending",
    }]


def test_v1_empty_todo_gets_stable_content_and_rebuilds_unowned_plan(tmp_path):
    session_id = new_session_id()
    session_dir = tmp_path / "ai" / "sessions"
    session_dir.mkdir(parents=True)
    (session_dir / f"{session_id}.json").write_text(json.dumps({
        "version": 1,
        "cwd": str(tmp_path.resolve()),
        "session": {
            "session_id": session_id,
            "messages": [],
            "trace": [],
            "turn": 1,
            "plan": [
                {"content": "stale", "priority": "high", "status": "completed"},
            ],
        },
        "tools": {"todolist": [{
            "content": "",
            "status": "pending",
            "active_form": "",
        }]},
    }), encoding="utf-8")

    session, tools = load_snapshot(tmp_path, session_id, cwd=tmp_path)

    assert tools == {"todolist": [{
        "content": "Untitled legacy task 1",
        "status": "pending",
        "active_form": "",
        "priority": "medium",
    }]}
    assert session["plan"] == _plan("Untitled legacy task 1")


@pytest.mark.parametrize("plan", [None, [], _plan("different")])
def test_v2_snapshot_rejects_missing_or_mismatched_canonical_plan(
    tmp_path,
    plan,
):
    session_id = new_session_id()
    session_dir = tmp_path / "ai" / "sessions"
    session_dir.mkdir(parents=True)
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 1,
    }
    if plan is not None:
        session["plan"] = plan
    (session_dir / f"{session_id}.json").write_text(json.dumps({
        "version": 2,
        "cwd": str(tmp_path.resolve()),
        "session": session,
        "tools": {"todolist": [_todo("canonical")]},
    }), encoding="utf-8")

    with pytest.raises(SessionSnapshotError, match="inconsistent plan"):
        load_snapshot(tmp_path, session_id, cwd=tmp_path)


def test_save_rejects_mismatched_canonical_plan(tmp_path):
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 1,
        "plan": _plan("session"),
    }

    with pytest.raises(SessionSnapshotError, match="inconsistent plan"):
        save_snapshot(
            tmp_path,
            session,
            {"todolist": [_todo("tool")]},
            cwd=tmp_path,
        )


def test_new_snapshot_round_trips_high_and_low_priorities(tmp_path):
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 1,
        "plan": [
            {"content": "Urgent", "priority": "high", "status": "in_progress"},
            {"content": "Later", "priority": "low", "status": "pending"},
        ],
    }
    tools = {"todolist": [
        {
            "content": "Urgent",
            "status": "in_progress",
            "active_form": "Doing urgent",
            "priority": "high",
        },
        {
            "content": "Later",
            "status": "pending",
            "active_form": "Doing later",
            "priority": "low",
        },
    ]}

    save_snapshot(tmp_path, session, tools, cwd=tmp_path)

    assert load_snapshot(tmp_path, session_id, cwd=tmp_path) == (session, tools)


def test_real_todo_list_state_round_trips_without_becoming_an_llm_tool():
    todo = TodoList()
    todo.add("Ship it", "Shipping it", priority="high")
    todo.start("Ship it")
    restored = TodoList()

    restored._load_state(todo._dump_state())

    assert restored.current_task == "Shipping it"
    assert restored._todos[0].priority == "high"
    tool_names = [tool.name for tool in extract_methods_from_instance(restored)]
    assert "_dump_state" not in tool_names
    assert "_load_state" not in tool_names


def test_resumable_agent_omits_process_local_background_tools(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "connectonion.core.agent.create_llm", lambda **_: MockLLM()
    )

    agent = create_agent(co_dir=tmp_path / ".co", background_tools=False)

    assert "run_background" not in agent.tools.names()
    assert "task_output" not in agent.tools.names()
    assert "kill_task" not in agent.tools.names()
    assert "bash" in agent.tools.names()


@pytest.mark.parametrize("session_id", ["../escape", "not-a-uuid", ""])
def test_snapshot_ids_must_be_canonical_uuids(tmp_path, session_id):
    with pytest.raises(SessionSnapshotError, match="valid session ID"):
        load_snapshot(tmp_path, session_id)


def test_snapshot_rejects_unknown_schema_version(tmp_path):
    session_id = new_session_id()
    session_dir = tmp_path / "ai" / "sessions"
    session_dir.mkdir(parents=True)
    (session_dir / f"{session_id}.json").write_text(
        json.dumps({"version": 99, "session": {}, "tools": {}}),
        encoding="utf-8",
    )

    with pytest.raises(SessionSnapshotError, match="version 99"):
        load_snapshot(tmp_path, session_id)


def test_snapshot_rejects_resume_from_another_working_directory(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    other = tmp_path / "other"
    co_dir = tmp_path / "state"
    project.mkdir()
    other.mkdir()
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 1,
    }

    monkeypatch.chdir(project)
    save_snapshot(co_dir, session)
    monkeypatch.chdir(other)

    with pytest.raises(SessionSnapshotError, match="belongs to"):
        load_snapshot(co_dir, session_id)


def test_session_lock_rejects_a_concurrent_writer(tmp_path):
    session_id = new_session_id()

    with session_lock(tmp_path, session_id):
        with pytest.raises(SessionSnapshotError, match="already running"):
            with session_lock(tmp_path, session_id):
                pass


def test_failed_atomic_replace_leaves_the_previous_snapshot(tmp_path, monkeypatch):
    session_id = new_session_id()
    original = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 1,
    }
    save_snapshot(tmp_path, original)

    def fail_replace(source, target):
        raise OSError("disk stopped")

    monkeypatch.setattr("connectonion.cli.co_ai.one_shot_sessions.os.replace", fail_replace)
    with pytest.raises(OSError, match="disk stopped"):
        save_snapshot(tmp_path, {**original, "turn": 2})

    loaded, _ = load_snapshot(tmp_path, session_id)
    assert loaded["turn"] == 1
    assert not list((tmp_path / "ai" / "sessions").glob(f".{session_id}.*"))


def test_atomic_replace_is_the_last_fallible_commit_step(tmp_path, monkeypatch):
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 1,
    }
    real_chmod = os.chmod

    def reject_post_commit_chmod(path, mode):
        if os.fspath(path).endswith(".json"):
            raise AssertionError("committed snapshot must not be chmodded")
        return real_chmod(path, mode)

    monkeypatch.setattr(
        "connectonion.cli.co_ai.one_shot_sessions.os.chmod",
        reject_post_commit_chmod,
    )

    save_snapshot(tmp_path, session)

    stored, _ = load_snapshot(tmp_path, session_id)
    assert stored == session
    if os.name != "nt":
        snapshot = tmp_path / "ai" / "sessions" / f"{session_id}.json"
        assert oct(snapshot.stat().st_mode & 0o777) == "0o600"


def test_json_mode_emits_one_stdout_object_and_saves_resume_state(
    tmp_path, monkeypatch, capsys
):
    agent = _Agent()
    created = {}

    def create_agent(**kwargs):
        created.update(kwargs)
        return agent

    monkeypatch.setattr("connectonion.cli.co_ai.agent.GLOBAL_CO_DIR", tmp_path)
    monkeypatch.setattr("connectonion.cli.co_ai.agent.create_agent", create_agent)

    ai_commands.handle_ai(
        prompt="first", json_output=True, yolo=True, yolo_turns=7
    )

    captured = capsys.readouterr()
    envelope = json.loads(captured.out)
    assert envelope == {
        "session_id": envelope["session_id"],
        "result": "done",
        "error": None,
    }
    assert captured.out.count("\n") == 1
    assert "progress" in captured.err
    assert created["yolo_turns"] == 7
    assert created["background_tools"] is False

    stored, tools = load_snapshot(tmp_path, envelope["session_id"])
    assert stored["mode"] == ":danger-full-access"
    assert stored["turn"] == 1
    assert tools == {"todolist": [_todo("first")]}


def test_resume_restores_messages_plugin_state_and_todos(tmp_path, monkeypatch, capsys):
    session_id = new_session_id()
    save_snapshot(
        tmp_path,
        {
            "session_id": session_id,
            "messages": [{"role": "system", "content": "old"}],
            "trace": [{"type": "old"}],
            "turn": 4,
            "mode": ":workspace",
            "plan": _plan("old todo"),
        },
        {"todolist": [_todo("old todo")]},
    )
    agent = _Agent()
    monkeypatch.setattr("connectonion.cli.co_ai.agent.GLOBAL_CO_DIR", tmp_path)
    monkeypatch.setattr("connectonion.cli.co_ai.agent.create_agent", lambda **_: agent)

    ai_commands.handle_ai(prompt="next", resume=session_id, json_output=True)

    envelope = json.loads(capsys.readouterr().out)
    assert envelope["session_id"] == session_id
    assert agent.received_session["mode"] == ":workspace"
    assert agent.received_session["turn"] == 4
    assert agent.tools.todo.state == [_todo("old todo"), _todo("next")]


def test_failed_resume_preserves_the_last_atomic_snapshot(
    tmp_path, monkeypatch, capsys
):
    session_id = new_session_id()
    original = {
        "session_id": session_id,
        "messages": [{"role": "system", "content": "old"}],
        "trace": [{"type": "old"}],
        "turn": 4,
        "mode": ":workspace",
        "plan": _plan("old todo"),
    }
    save_snapshot(tmp_path, original, {"todolist": [_todo("old todo")]})

    class BrokenResumeAgent(_Agent):
        def input(self, prompt, session=None):
            session["turn"] = 99
            session["messages"].append({"role": "user", "content": prompt})
            self.tools.todo.state.append(_todo("uncommitted todo"))
            raise RuntimeError("follow-up failed")

    monkeypatch.setattr("connectonion.cli.co_ai.agent.GLOBAL_CO_DIR", tmp_path)
    monkeypatch.setattr(
        "connectonion.cli.co_ai.agent.create_agent",
        lambda **_: BrokenResumeAgent(),
    )

    with pytest.raises(typer.Exit) as caught:
        ai_commands.handle_ai(
            prompt="next", resume=session_id, json_output=True
        )

    assert caught.value.exit_code == 1
    envelope = json.loads(capsys.readouterr().out)
    assert envelope == {
        "session_id": session_id,
        "result": None,
        "error": "follow-up failed",
    }
    stored, tools = load_snapshot(tmp_path, session_id)
    assert stored == original
    assert tools == {"todolist": [_todo("old todo")]}


def test_json_failure_is_structured_and_nonzero(tmp_path, monkeypatch, capsys):
    class BrokenAgent(_Agent):
        def input(self, prompt, session=None):
            print("before failure")
            raise TypeError("our bug")

    monkeypatch.setattr("connectonion.cli.co_ai.agent.GLOBAL_CO_DIR", tmp_path)
    monkeypatch.setattr(
        "connectonion.cli.co_ai.agent.create_agent", lambda **_: BrokenAgent()
    )

    with pytest.raises(typer.Exit) as caught:
        ai_commands.handle_ai(prompt="task", json_output=True)

    captured = capsys.readouterr()
    assert caught.value.exit_code == 1
    assert json.loads(captured.out) == {
        "session_id": None,
        "result": None,
        "error": "our bug",
    }
    assert "before failure" in captured.err


def test_transient_one_shot_rejects_resume_without_echoing_the_session_id(capsys):
    with pytest.raises(typer.Exit) as caught:
        ai_commands._handle_json_one_shot(
            "task",
            "co/test",
            4,
            True,
            1,
            new_session_id(),
            persist_session=False,
        )

    assert caught.value.exit_code == 1
    assert json.loads(capsys.readouterr().out) == {
        "session_id": None,
        "result": None,
        "error": "A transient one-shot run cannot resume a session.",
    }


def test_missing_resume_is_an_error_not_a_new_conversation(tmp_path, monkeypatch, capsys):
    missing = new_session_id()
    monkeypatch.setattr("connectonion.cli.co_ai.agent.GLOBAL_CO_DIR", tmp_path)

    with pytest.raises(typer.Exit) as caught:
        ai_commands.handle_ai(prompt="task", resume=missing, json_output=True)

    assert caught.value.exit_code == 1
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["session_id"] == missing
    assert envelope["result"] is None
    assert "not found" in envelope["error"]


def test_json_and_resume_require_a_one_shot_prompt(capsys):
    with pytest.raises(typer.Exit) as caught:
        ai_commands.handle_ai(json_output=True)

    assert caught.value.exit_code == 2
    assert json.loads(capsys.readouterr().out)["error"] == (
        "--json and --resume require a one-shot prompt"
    )


def test_resume_requires_the_machine_readable_contract(capsys):
    with pytest.raises(typer.Exit) as caught:
        ai_commands.handle_ai(prompt="task", resume=new_session_id())

    assert caught.value.exit_code == 2
    assert "--resume requires --json" in capsys.readouterr().out


def test_virtual_session_cwd_is_opaque_protocol_data(tmp_path):
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
        "mode": ":read-only",
        "plan": [],
    }

    save_snapshot(tmp_path, session, {}, virtual_cwd="/")
    payload = json.loads(
        (tmp_path / "ai" / "sessions" / f"{session_id}.json").read_text(
            encoding="utf-8"
        )
    )
    restored, tools = load_snapshot(tmp_path, session_id, virtual_cwd="/")

    assert payload["cwd"] == "/"
    assert restored == session
    assert tools == {}
    with pytest.raises(SessionSnapshotError, match="Invalid virtual"):
        save_snapshot(tmp_path, session, {}, cwd=tmp_path, virtual_cwd="/")

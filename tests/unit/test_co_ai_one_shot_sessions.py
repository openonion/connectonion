"""Behavioral contract for resumable, machine-readable ``co ai`` runs."""

import json
import os
from contextlib import contextmanager

import pytest
import typer

import connectonion.cli.co_ai.one_shot_sessions as session_storage
import connectonion.cli.commands.ai_commands as ai_commands
from connectonion.cli.co_ai.agent import create_agent
from connectonion.cli.co_ai.one_shot_sessions import (
    SessionLease,
    SessionSnapshotError,
    SnapshotStorageLimits,
    acquire_bounded_new_session_lease,
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


def _snapshot_limits(*, sessions=2, total=4096, single=2048):
    return SnapshotStorageLimits(
        max_sessions=sessions,
        max_total_bytes=total,
        max_snapshot_bytes=single,
    )


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


def test_bounded_snapshot_replacement_charges_only_the_new_exact_bytes(tmp_path):
    session_id = new_session_id()
    limits = _snapshot_limits(sessions=1, total=900, single=900)
    original = {
        "session_id": session_id,
        "messages": [{"role": "user", "content": "short"}],
        "trace": [],
        "turn": 1,
    }
    replacement = {
        **original,
        "messages": [{"role": "user", "content": "x" * 400}],
        "turn": 2,
    }

    save_snapshot(tmp_path, original, storage_limits=limits)
    save_snapshot(tmp_path, replacement, storage_limits=limits)

    assert load_snapshot(tmp_path, session_id, storage_limits=limits)[0] == replacement


def test_bounded_snapshot_count_rejection_preserves_every_committed_file(tmp_path):
    limits = _snapshot_limits(sessions=1)
    first_id = new_session_id()
    second_id = new_session_id()
    first = {
        "session_id": first_id,
        "messages": [],
        "trace": [],
        "turn": 0,
    }
    second = {**first, "session_id": second_id}
    save_snapshot(tmp_path, first, storage_limits=limits)
    directory = tmp_path / "ai" / "sessions"
    before = (directory / f"{first_id}.json").read_bytes()

    with pytest.raises(SessionSnapshotError, match="quota exceeded"):
        save_snapshot(tmp_path, second, storage_limits=limits)

    assert (directory / f"{first_id}.json").read_bytes() == before
    assert not (directory / f"{second_id}.json").exists()


def test_bounded_snapshot_count_includes_orphan_lease_ids(tmp_path):
    first_id = new_session_id()
    second_id = new_session_id()
    directory = tmp_path / "ai" / "sessions"
    directory.mkdir(parents=True)
    (directory / f"{first_id}.lock").write_bytes(b"")
    session = {
        "session_id": second_id,
        "messages": [],
        "trace": [],
        "turn": 0,
    }

    with pytest.raises(SessionSnapshotError, match="quota exceeded"):
        save_snapshot(
            tmp_path,
            session,
            storage_limits=_snapshot_limits(sessions=1),
        )

    assert not (directory / f"{second_id}.json").exists()


def test_oversized_snapshot_rejection_preserves_last_good_bytes(tmp_path):
    session_id = new_session_id()
    original = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 1,
    }
    wide_limits = _snapshot_limits(single=4096)
    narrow_limits = _snapshot_limits(single=400)
    save_snapshot(tmp_path, original, storage_limits=wide_limits)
    path = tmp_path / "ai" / "sessions" / f"{session_id}.json"
    before = path.read_bytes()

    with pytest.raises(SessionSnapshotError, match="exceeds the storage limit"):
        save_snapshot(
            tmp_path,
            {
                **original,
                "messages": [{"role": "user", "content": "x" * 1000}],
                "turn": 2,
            },
            storage_limits=narrow_limits,
        )

    assert path.read_bytes() == before


def test_bounded_snapshot_total_rejection_preserves_last_good_bytes(tmp_path):
    first_id = new_session_id()
    second_id = new_session_id()
    first = {
        "session_id": first_id,
        "messages": [{"role": "user", "content": "x" * 300}],
        "trace": [],
        "turn": 1,
    }
    second = {
        **first,
        "session_id": second_id,
        "messages": [{"role": "user", "content": "y" * 300}],
    }
    save_snapshot(tmp_path, first, storage_limits=_snapshot_limits())
    path = tmp_path / "ai" / "sessions" / f"{first_id}.json"
    before = path.read_bytes()

    with pytest.raises(SessionSnapshotError, match="quota exceeded"):
        save_snapshot(
            tmp_path,
            second,
            storage_limits=_snapshot_limits(
                total=len(before) + 10,
                single=len(before) + 10,
            ),
        )

    assert path.read_bytes() == before
    assert not (path.parent / f"{second_id}.json").exists()


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="no O_NOFOLLOW")
def test_bounded_snapshot_load_rejects_symlink_without_reading_target(tmp_path):
    session_id = new_session_id()
    target = tmp_path / "private"
    target.write_text("secret", encoding="utf-8")
    directory = tmp_path / "ai" / "sessions"
    directory.mkdir(parents=True)
    (directory / f"{session_id}.json").symlink_to(target)

    with pytest.raises(SessionSnapshotError, match="storage is unavailable"):
        load_snapshot(tmp_path, session_id, storage_limits=_snapshot_limits())

    assert target.read_text(encoding="utf-8") == "secret"


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="no O_NOFOLLOW")
def test_bounded_snapshot_store_rejects_symlinked_control_directory(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    (state / "ai").symlink_to(target, target_is_directory=True)
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
    }

    with pytest.raises(SessionSnapshotError, match="storage is unavailable"):
        save_snapshot(state, session, storage_limits=_snapshot_limits())

    assert list(target.iterdir()) == []


def test_unpublished_cleanup_releases_lease_when_storage_lock_cannot_open(
    tmp_path,
    monkeypatch,
):
    session_id = new_session_id()
    lease = SessionLease(session_id, open(tmp_path / "lease", "a+", encoding="utf-8"))

    @contextmanager
    def fail_before_enter(_co_dir):
        raise SessionSnapshotError("Session storage is unavailable.")
        yield

    monkeypatch.setattr(session_storage, "_snapshot_storage_lock", fail_before_enter)

    with pytest.raises(SessionSnapshotError, match="storage is unavailable"):
        session_storage.discard_unpublished_session(tmp_path, session_id, lease)

    assert lease.closed is True


def test_bounded_snapshot_read_rejects_zero_file_identity(tmp_path, monkeypatch):
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
    }
    limits = _snapshot_limits()
    save_snapshot(tmp_path, session, storage_limits=limits)
    real_fstat = session_storage.os.fstat

    class ZeroIdentity:
        def __init__(self, source):
            self.st_mode = source.st_mode
            self.st_size = source.st_size
            self.st_dev = 0
            self.st_ino = 0

    monkeypatch.setattr(
        session_storage.os,
        "fstat",
        lambda descriptor: ZeroIdentity(real_fstat(descriptor)),
    )

    path = tmp_path / "ai" / "sessions" / f"{session_id}.json"
    with pytest.raises(SessionSnapshotError, match="is unreadable"):
        session_storage._read_snapshot(
            path,
            session_id,
            max_bytes=limits.max_snapshot_bytes,
            require_stable_identity=True,
        )


def test_bounded_scan_stops_at_legacy_orphan_lock_limit(tmp_path, monkeypatch):
    directory = tmp_path / "ai" / "sessions"
    directory.mkdir(parents=True)
    for _ in range(4):
        (directory / f"{new_session_id()}.lock").write_bytes(b"")
    real_scandir = session_storage.os.scandir

    class GuardedScan:
        def __init__(self, path):
            self._entries = real_scandir(path)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            self._entries.close()

        def __iter__(self):
            for index, entry in enumerate(self._entries, start=1):
                if index > 3:
                    raise AssertionError("scan continued beyond the quota boundary")
                yield entry

    monkeypatch.setattr(session_storage.os, "scandir", GuardedScan)
    session = {
        "session_id": new_session_id(),
        "messages": [],
        "trace": [],
        "turn": 0,
    }

    with pytest.raises(SessionSnapshotError, match="quota exceeded"):
        save_snapshot(
            tmp_path,
            session,
            storage_limits=_snapshot_limits(sessions=2),
        )


@pytest.mark.skipif(os.name == "nt", reason="POSIX flock failure injection")
def test_failed_bounded_admission_does_not_consume_a_session_slot(
    tmp_path,
    monkeypatch,
):
    import fcntl

    failed_id = new_session_id()
    real_flock = fcntl.flock

    def fail_session_lease(handle, operation):
        if operation & fcntl.LOCK_NB:
            raise OSError("injected lease failure")
        return real_flock(handle, operation)

    with monkeypatch.context() as failure:
        failure.setattr(fcntl, "flock", fail_session_lease)
        with pytest.raises(SessionSnapshotError, match="lock is unavailable"):
            acquire_bounded_new_session_lease(
                tmp_path,
                failed_id,
                _snapshot_limits(sessions=1),
            )

    directory = tmp_path / "ai" / "sessions"
    assert list(directory.glob("*.lock")) == []
    replacement_id = new_session_id()
    lease = acquire_bounded_new_session_lease(
        tmp_path,
        replacement_id,
        _snapshot_limits(sessions=1),
    )
    try:
        assert lease.session_id == replacement_id
    finally:
        session_storage.discard_unpublished_session(
            tmp_path,
            replacement_id,
            lease,
        )


@pytest.mark.parametrize("failure", ["fstat", "fdopen"])
def test_bounded_admission_failure_never_unlinks_a_replacement(
    tmp_path,
    monkeypatch,
    failure,
):
    session_id = new_session_id()
    directory = tmp_path / "ai" / "sessions"
    replacement = b"replacement owned by another actor"
    real_fstat = session_storage.os.fstat
    real_fdopen = session_storage.os.fdopen
    fstat_calls = 0
    fdopen_calls = 0

    def replace_path():
        path = directory / f"{session_id}.lock"
        path.unlink()
        path.write_bytes(replacement)

    def fail_second_fstat(descriptor):
        nonlocal fstat_calls
        fstat_calls += 1
        if fstat_calls == 2:
            replace_path()
            raise OSError("injected fstat failure")
        return real_fstat(descriptor)

    def fail_second_fdopen(*args, **kwargs):
        nonlocal fdopen_calls
        fdopen_calls += 1
        if fdopen_calls == 2:
            replace_path()
            raise OSError("injected fdopen failure")
        return real_fdopen(*args, **kwargs)

    monkeypatch.setattr(
        session_storage.os,
        "fstat",
        fail_second_fstat if failure == "fstat" else real_fstat,
    )
    monkeypatch.setattr(
        session_storage.os,
        "fdopen",
        fail_second_fdopen if failure == "fdopen" else real_fdopen,
    )

    with pytest.raises(SessionSnapshotError, match="lock is unavailable"):
        acquire_bounded_new_session_lease(
            tmp_path,
            session_id,
            _snapshot_limits(sessions=1),
        )

    assert (directory / f"{session_id}.lock").read_bytes() == replacement


def test_bounded_admission_rejects_zero_file_identity_without_unlink(
    tmp_path,
    monkeypatch,
):
    session_id = new_session_id()
    real_fstat = session_storage.os.fstat
    fstat_calls = 0

    class ZeroIdentity:
        def __init__(self, source):
            self.st_mode = source.st_mode
            self.st_dev = 0
            self.st_ino = 0

    def zero_second_identity(descriptor):
        nonlocal fstat_calls
        fstat_calls += 1
        source = real_fstat(descriptor)
        return ZeroIdentity(source) if fstat_calls == 2 else source

    monkeypatch.setattr(session_storage.os, "fstat", zero_second_identity)

    with pytest.raises(SessionSnapshotError, match="lock is unavailable"):
        acquire_bounded_new_session_lease(
            tmp_path,
            session_id,
            _snapshot_limits(sessions=1),
        )

    assert (
        tmp_path / "ai" / "sessions" / f"{session_id}.lock"
    ).is_file()


def test_bounded_snapshot_scan_removes_only_canonical_stale_temporary(tmp_path):
    session_id = new_session_id()
    directory = tmp_path / "ai" / "sessions"
    directory.mkdir(parents=True)
    stale = directory / f".{session_id}.stale"
    stale.write_bytes(b"partial")
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
    }

    save_snapshot(tmp_path, session, storage_limits=_snapshot_limits())

    assert not stale.exists()
    assert load_snapshot(tmp_path, session_id, storage_limits=_snapshot_limits())[0] == session


@pytest.mark.parametrize("name", ["unknown", "not-a-uuid.json", "not-a-uuid.lock"])
def test_bounded_snapshot_scan_fails_closed_on_unexpected_entries(tmp_path, name):
    session_id = new_session_id()
    directory = tmp_path / "ai" / "sessions"
    directory.mkdir(parents=True)
    (directory / name).write_bytes(b"unexpected")
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
    }

    with pytest.raises(SessionSnapshotError, match="storage is unavailable"):
        save_snapshot(tmp_path, session, storage_limits=_snapshot_limits())

    assert not (directory / f"{session_id}.json").exists()


def test_unbounded_stdio_snapshot_behavior_remains_explicit(tmp_path):
    session_id = new_session_id()
    session = {
        "session_id": session_id,
        "messages": [{"role": "user", "content": "x" * 4096}],
        "trace": [],
        "turn": 1,
    }

    save_snapshot(tmp_path, session)

    assert load_snapshot(tmp_path, session_id)[0] == session


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

"""Persistent ACP session ownership and transactional resume behavior."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
import time
from typing import Any
from uuid import UUID

import pytest
from acp import RequestError, text_block
from acp.schema import CloseSessionResponse, ResumeSessionResponse

from connectonion.cli.co_ai import acp_server
from connectonion.cli.co_ai.acp_server import (
    ConnectOnionACPAgent,
    capture_network_workspace,
)
from connectonion.cli.co_ai.one_shot_sessions import (
    SessionSnapshotError,
    acquire_session_lease,
    load_snapshot,
    save_snapshot,
    session_lock,
)


def _todo(content: str) -> dict[str, str]:
    return {
        "content": content,
        "status": "pending",
        "active_form": f"Working on {content}",
        "priority": "medium",
    }


def _plan(*contents: str) -> list[dict[str, str]]:
    return [
        {"content": content, "priority": "medium", "status": "pending"}
        for content in contents
    ]


class _Todo:
    def __init__(self) -> None:
        self.state: list[dict[str, str]] = []

    def _dump_state(self) -> list[dict[str, str]]:
        return copy.deepcopy(self.state)

    def _load_state(self, state: list[dict[str, str]]) -> None:
        self.state = copy.deepcopy(state)


class _Tools:
    def __init__(self) -> None:
        self.todo = _Todo()

    def get_instance(self, name: str, default: Any = None) -> Any:
        return self.todo if name == "todolist" else default


class _Client:
    def __init__(self, *, fail_updates: bool = False) -> None:
        self.fail_updates = fail_updates
        self.updates: list[tuple[str, Any]] = []

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **_kwargs: Any,
    ) -> None:
        if self.fail_updates:
            raise RuntimeError("private update transport failure")
        self.updates.append((session_id, update))


class _PersistentFakeAgent:
    system_prompt = "system"

    def __init__(self, actions: list[str] | None = None) -> None:
        self.actions = list(actions or ["natural"])
        self.current_session: dict[str, Any] | None = None
        self.io: Any = None
        self.tools = _Tools()
        self.received_sessions: list[dict[str, Any] | None] = []
        self.started = threading.Event()

    def input(self, prompt: str, session: dict[str, Any] | None = None) -> str:
        self.received_sessions.append(copy.deepcopy(session))
        if session is not None:
            self.current_session = copy.deepcopy(session)
        if self.current_session is None:
            self.current_session = {
                "messages": [{"role": "system", "content": self.system_prompt}],
                "trace": [],
                "turn": 0,
            }

        action = self.actions.pop(0) if self.actions else "natural"
        self.current_session["turn"] += 1
        self.current_session["messages"].append({"role": "user", "content": prompt})
        self.tools.todo.state.append(_todo(prompt))
        self.current_session["plan"] = [
            {
                "content": item["content"],
                "priority": item["priority"],
                "status": item["status"],
            }
            for item in self.tools.todo.state
        ]
        self.started.set()
        if action == "block":
            while not self.io.receive_all("INTERRUPT"):
                time.sleep(0.01)
            action = "interrupted"

        result = f"answer: {prompt}"
        if action in {"natural", "max_iterations"}:
            self.current_session["messages"].append({
                "role": "assistant",
                "content": result,
            })
        terminal = {
            "type": "turn_result",
            "turn": self.current_session["turn"],
            "reason": action,
            "usage": None,
        }
        self.current_session["trace"].append(terminal)
        self.io.send(terminal)
        if action == "error":
            raise RuntimeError("private agent failure")
        return result


class _GateAgent(_PersistentFakeAgent):
    """Keep a worker alive until a test explicitly permits it to finish."""

    def __init__(self, actions: list[str] | None = None) -> None:
        super().__init__(actions)
        self.release = threading.Event()

    def input(self, prompt: str, session: dict[str, Any] | None = None) -> str:
        self.started.set()
        self.release.wait()
        return super().input(prompt, session=session)


def _server(
    state_dir,
    factory,
) -> ConnectOnionACPAgent:
    return ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        session_co_dir=state_dir,
    )


def _network_server(state_dir, project, factory, **limits):
    workspace = capture_network_workspace(project)
    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        session_co_dir=state_dir,
        network_workspace=workspace,
        input_limits=limits,
    )
    return server, workspace


def _project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


@pytest.fixture(autouse=True)
def _isolate_project_lookup(tmp_path, monkeypatch):
    """Keep project discovery independent from a developer's parent .co dir."""
    monkeypatch.chdir(tmp_path)


def test_explicit_session_lease_is_idempotently_closeable(tmp_path):
    session_id = "6c1fd90a-e0bf-4363-bcc2-c1ae32643f39"
    lease = acquire_session_lease(tmp_path, session_id)

    with pytest.raises(SessionSnapshotError, match="already running"):
        with session_lock(tmp_path, session_id):
            pass

    lease.close()
    lease.close()
    with session_lock(tmp_path, session_id):
        pass


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="no O_NOFOLLOW")
def test_session_lease_rejects_a_symlink_lock_without_touching_target(tmp_path):
    session_id = "1f7aed9b-b25a-4472-9fbf-9625763ec743"
    target = tmp_path / "target"
    target.write_text("private", encoding="utf-8")
    target.chmod(0o644)
    lock_dir = tmp_path / "ai" / "sessions"
    lock_dir.mkdir(parents=True)
    (lock_dir / f"{session_id}.lock").symlink_to(target)

    with pytest.raises(SessionSnapshotError, match="lock is unavailable"):
        acquire_session_lease(tmp_path, session_id)

    assert target.read_text(encoding="utf-8") == "private"
    assert target.stat().st_mode & 0o777 == 0o644


@pytest.mark.asyncio
async def test_initialize_advertises_resume_and_close_but_not_load(tmp_path):
    server = _server(tmp_path / "state", lambda **_: _PersistentFakeAgent())

    initialized = await server.initialize(protocol_version=1)

    capabilities = initialized.agent_capabilities
    assert capabilities.load_session is False
    assert capabilities.session_capabilities.resume is not None
    assert capabilities.session_capabilities.close is not None


@pytest.mark.asyncio
async def test_new_session_persists_canonical_snapshot_and_holds_lease(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = _server(state_dir, lambda **_: _PersistentFakeAgent())

    created = await server.new_session(str(project), mcp_servers=[])

    assert str(UUID(created.session_id)) == created.session_id
    session, tools = load_snapshot(state_dir, created.session_id)
    assert session == {
        "session_id": created.session_id,
        "messages": [{"role": "system", "content": "system"}],
        "trace": [],
        "turn": 0,
        "mode": ":read-only",
        "plan": [],
    }
    assert tools == {"todolist": []}
    with pytest.raises(SessionSnapshotError, match="already running"):
        with session_lock(state_dir, created.session_id):
            pass

    closed = await server.close_session(created.session_id)
    assert isinstance(closed, CloseSessionResponse)
    with session_lock(state_dir, created.session_id):
        pass


@pytest.mark.asyncio
async def test_resume_restores_session_and_tool_state_without_replay(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    session_id = "8bb6aebe-4a92-4e1c-8bb0-f3c7743470db"
    saved = {
        "session_id": session_id,
        "messages": [{"role": "system", "content": "old"}],
        "trace": [{"type": "old"}],
        "turn": 4,
        "mode": ":workspace",
        "plan": _plan("old todo"),
    }
    save_snapshot(state_dir, saved, {"todolist": [_todo("old todo")]})
    agent = _PersistentFakeAgent()
    created_with: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> _PersistentFakeAgent:
        created_with.append(kwargs)
        return agent

    server = _server(state_dir, factory)
    client = _Client()
    server.on_connect(client)

    resumed = await server.resume_session(session_id, str(project), mcp_servers=[])
    assert isinstance(resumed, ResumeSessionResponse)
    assert client.updates == []
    assert created_with[0]["resumable"] is True

    response = await server.prompt(session_id, [text_block("next")])

    assert response.stop_reason == "end_turn"
    assert agent.received_sessions[0]["turn"] == 4
    assert agent.received_sessions[0]["mode"] == ":workspace"
    stored, tools = load_snapshot(state_dir, session_id)
    assert stored["turn"] == 5
    assert stored["plan"] == [
        {"content": "old todo", "priority": "medium", "status": "pending"},
        {"content": "next", "priority": "medium", "status": "pending"},
    ]
    assert tools == {"todolist": [_todo("old todo"), _todo("next")]}
    await server.close_session(session_id)


@pytest.mark.asyncio
async def test_runtime_lease_blocks_a_second_server_until_close(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    owner = _server(state_dir, lambda **_: _PersistentFakeAgent())
    contender = _server(state_dir, lambda **_: _PersistentFakeAgent())
    session = await owner.new_session(str(project), mcp_servers=[])

    with pytest.raises(RequestError, match="Unable to resume session"):
        await contender.resume_session(
            session.session_id,
            str(project),
            mcp_servers=[],
        )

    await owner.close_session(session.session_id)
    await contender.resume_session(session.session_id, str(project), mcp_servers=[])
    await contender.close_session(session.session_id)


@pytest.mark.asyncio
async def test_network_session_count_quota_is_shared_across_connections(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "principal"
    first, first_workspace = _network_server(
        state_dir,
        project,
        lambda **_: _PersistentFakeAgent(),
        max_acp_sessions=1,
    )
    second, second_workspace = _network_server(
        state_dir,
        project,
        lambda **_: _PersistentFakeAgent(),
        max_acp_sessions=1,
    )
    try:
        created = await first.new_session("/", mcp_servers=[])

        with pytest.raises(RequestError, match="Unable to create"):
            await second.new_session("/", mcp_servers=[])

        snapshots = list((state_dir / "ai" / "sessions").glob("*.json"))
        assert [path.stem for path in snapshots] == [created.session_id]
        locks = list((state_dir / "ai" / "sessions").glob("*.lock"))
        assert [path.stem for path in locks] == [created.session_id]
        await first.close_session(created.session_id)
    finally:
        first_workspace.close()
        second_workspace.close()


@pytest.mark.asyncio
async def test_concurrent_network_admission_fills_last_slot_once(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "principal"
    first, first_workspace = _network_server(
        state_dir,
        project,
        lambda **_: _PersistentFakeAgent(),
        max_acp_sessions=1,
    )
    second, second_workspace = _network_server(
        state_dir,
        project,
        lambda **_: _PersistentFakeAgent(),
        max_acp_sessions=1,
    )
    try:
        results = await asyncio.gather(
            first.new_session("/", mcp_servers=[]),
            second.new_session("/", mcp_servers=[]),
            return_exceptions=True,
        )

        created = [result for result in results if not isinstance(result, BaseException)]
        rejected = [result for result in results if isinstance(result, RequestError)]
        assert len(created) == 1
        assert len(rejected) == 1
        assert len(list((state_dir / "ai" / "sessions").glob("*.json"))) == 1
        await (first if results[0] is created[0] else second).close_session(
            created[0].session_id
        )
    finally:
        first_workspace.close()
        second_workspace.close()


@pytest.mark.asyncio
async def test_cancelled_network_admission_removes_provisional_lease(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "principal"
    server, workspace = _network_server(
        state_dir,
        project,
        lambda **_: _PersistentFakeAgent(),
        max_acp_sessions=1,
    )
    reserved = threading.Event()
    release_admission = threading.Event()
    real_load = server._load_owned_session

    def pause_after_reservation(*args, **kwargs):
        ownership = real_load(*args, **kwargs)
        reserved.set()
        assert release_admission.wait(timeout=1)
        return ownership

    monkeypatch.setattr(server, "_load_owned_session", pause_after_reservation)
    try:
        request = asyncio.create_task(server.new_session("/", mcp_servers=[]))
        assert await asyncio.to_thread(reserved.wait, 1)
        request.cancel()
        release_admission.set()

        with pytest.raises(asyncio.CancelledError):
            await request
        directory = state_dir / "ai" / "sessions"
        assert list(directory.glob("*.json")) == []
        assert list(directory.glob("*.lock")) == []
    finally:
        release_admission.set()
        workspace.close()


@pytest.mark.asyncio
async def test_network_prompt_snapshot_quota_rolls_back_disk_and_runtime(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "principal"
    agent = _PersistentFakeAgent()
    server, workspace = _network_server(
        state_dir,
        project,
        lambda **_: agent,
        max_acp_snapshot_size=1 / 1024,
        max_acp_session_storage=1,
    )
    server.on_connect(_Client())
    try:
        created = await server.new_session("/", mcp_servers=[])
        path = state_dir / "ai" / "sessions" / f"{created.session_id}.json"
        before = path.read_bytes()

        with pytest.raises(RequestError, match="co ai prompt failed"):
            await server.prompt(created.session_id, [text_block("x" * 2000)])

        assert path.read_bytes() == before
        stored, _ = load_snapshot(
            state_dir,
            created.session_id,
            virtual_cwd="/",
        )
        assert stored["turn"] == 0
        assert agent.current_session["turn"] == 0
        await server.close_session(created.session_id)
    finally:
        workspace.close()


@pytest.mark.asyncio
async def test_network_unknown_resume_does_not_create_a_durable_lock_file(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "principal"
    server, workspace = _network_server(
        state_dir,
        project,
        lambda **_: _PersistentFakeAgent(),
    )
    unknown = "cfb44753-f6da-47b3-9281-a0e9f664dd3c"
    try:
        with pytest.raises(RequestError, match="Unable to resume"):
            await server.resume_session(unknown, "/", mcp_servers=[])

        assert list((state_dir / "ai" / "sessions").glob("*.lock")) == []
    finally:
        workspace.close()


@pytest.mark.asyncio
async def test_cancelled_network_new_session_removes_unpublished_snapshot_and_lease(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "principal"
    server, workspace = _network_server(
        state_dir,
        project,
        lambda **_: _PersistentFakeAgent(),
    )
    committed = threading.Event()
    release_constructor = threading.Event()
    cleanup_threads = []
    real_open = server._open_session_runtime
    real_discard = acp_server.discard_unpublished_session

    def pause_after_initial_commit(*args, **kwargs):
        runtime = real_open(*args, **kwargs)
        committed.set()
        assert release_constructor.wait(timeout=1)
        return runtime

    def track_discard(*args, **kwargs):
        cleanup_threads.append(threading.get_ident())
        return real_discard(*args, **kwargs)

    monkeypatch.setattr(server, "_open_session_runtime", pause_after_initial_commit)
    monkeypatch.setattr(acp_server, "discard_unpublished_session", track_discard)
    try:
        request = asyncio.create_task(server.new_session("/", mcp_servers=[]))
        assert await asyncio.to_thread(committed.wait, 1)
        request.cancel()
        release_constructor.set()
        with pytest.raises(asyncio.CancelledError):
            await request

        directory = state_dir / "ai" / "sessions"
        assert list(directory.glob("*.json")) == []
        assert list(directory.glob("*.lock")) == []
        assert cleanup_threads
        assert cleanup_threads != [threading.get_ident()]
    finally:
        release_constructor.set()
        workspace.close()


@pytest.mark.asyncio
async def test_resume_rejects_wrong_cwd_before_agent_construction(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    other = tmp_path / "other"
    other.mkdir()
    state_dir = tmp_path / "state"
    session_id = "7f02ea66-c266-4991-82bb-dc07ca461301"
    save_snapshot(state_dir, {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
    })
    constructed = []
    server = _server(
        state_dir,
        lambda **_: constructed.append(True) or _PersistentFakeAgent(),
    )

    with pytest.raises(RequestError):
        await server.resume_session(session_id, str(other), mcp_servers=[])

    assert constructed == []
    with session_lock(state_dir, session_id):
        pass
    monkeypatch.chdir(project)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "snapshot",
    ["missing", "corrupt", "old-version", "malformed-tool"],
)
async def test_resume_rejects_unusable_snapshots_before_agent_construction(
    tmp_path,
    monkeypatch,
    snapshot,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    session_id = "731948c4-1194-442b-b678-9b5d5a3871c4"
    if snapshot != "missing":
        session_dir = state_dir / "ai" / "sessions"
        session_dir.mkdir(parents=True)
        payload = "not json"
        if snapshot == "old-version":
            payload = json.dumps({"version": 0, "session": {}, "tools": {}})
        elif snapshot == "malformed-tool":
            payload = json.dumps({
                "version": 1,
                "cwd": str(project.resolve()),
                "session": {
                    "session_id": session_id,
                    "messages": [],
                    "trace": [],
                    "turn": 0,
                },
                "tools": {"todolist": [{"content": "missing fields"}]},
            })
        (session_dir / f"{session_id}.json").write_text(
            payload,
            encoding="utf-8",
        )
    constructed = []
    server = _server(
        state_dir,
        lambda **_: constructed.append(True) or _PersistentFakeAgent(),
    )

    with pytest.raises(RequestError, match="Unable to resume session"):
        await server.resume_session(session_id, str(project), mcp_servers=[])

    assert constructed == []
    with session_lock(state_dir, session_id):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["new", "resume"])
async def test_cancelled_runtime_construction_settles_and_releases_lease(
    tmp_path,
    monkeypatch,
    operation,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    session_id = "70d27939-748d-4f6a-8cc7-236e4029813f"
    if operation == "resume":
        save_snapshot(state_dir, {
            "session_id": session_id,
            "messages": [],
            "trace": [],
            "turn": 0,
        })
    server = _server(state_dir, lambda **_: _PersistentFakeAgent())
    real_open = server._open_session_runtime
    started = threading.Event()
    release = threading.Event()

    def blocked_open(*args: Any) -> Any:
        started.set()
        release.wait()
        return real_open(*args)

    monkeypatch.setattr(server, "_open_session_runtime", blocked_open)
    if operation == "new":
        opening = asyncio.create_task(server.new_session(str(project), mcp_servers=[]))
    else:
        opening = asyncio.create_task(
            server.resume_session(session_id, str(project), mcp_servers=[])
        )
    await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1)

    opening.cancel()
    await asyncio.sleep(0)
    opening.cancel()
    assert not opening.done()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(opening, timeout=1)
    assert server._sessions == {}
    if operation == "new":
        snapshots = list((state_dir / "ai" / "sessions").glob("*.json"))
        assert len(snapshots) == 1
        session_id = snapshots[0].stem
    with session_lock(state_dir, session_id):
        pass


@pytest.mark.asyncio
async def test_successful_turns_commit_in_order(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _PersistentFakeAgent(["natural", "max_iterations"])
    server = _server(state_dir, lambda **_: agent)
    server.on_connect(_Client())
    session = await server.new_session(str(project), mcp_servers=[])

    first = await server.prompt(session.session_id, [text_block("one")])
    second = await server.prompt(session.session_id, [text_block("two")])

    stored, tools = load_snapshot(state_dir, session.session_id)
    assert first.stop_reason == "end_turn"
    assert second.stop_reason == "max_turn_requests"
    assert stored["turn"] == 2
    assert stored["plan"] == [
        {"content": "one", "priority": "medium", "status": "pending"},
        {"content": "two", "priority": "medium", "status": "pending"},
    ]
    assert [message["content"] for message in stored["messages"][-4:]] == [
        "one",
        "answer: one",
        "two",
        "answer: two",
    ]
    assert tools == {"todolist": [_todo("one"), _todo("two")]}
    await server.close_session(session.session_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["interrupted", "error", "update"])
async def test_unsuccessful_turn_rolls_back_disk_and_runtime(
    tmp_path,
    monkeypatch,
    failure,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    action = "natural" if failure == "update" else failure
    agent = _PersistentFakeAgent([action, "natural"])
    server = _server(state_dir, lambda **_: agent)
    client = _Client(fail_updates=failure == "update")
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])
    before, before_tools = load_snapshot(state_dir, session.session_id)

    if failure == "error" or failure == "update":
        with pytest.raises(RequestError):
            await server.prompt(session.session_id, [text_block("bad")])
    else:
        response = await server.prompt(session.session_id, [text_block("bad")])
        assert response.stop_reason == "cancelled"

    stored, tools = load_snapshot(state_dir, session.session_id)
    assert stored == before
    assert tools == before_tools
    assert agent.current_session == before
    assert agent.tools.todo.state == []

    client.fail_updates = False
    recovered = await server.prompt(session.session_id, [text_block("good")])
    assert recovered.stop_reason == "end_turn"
    stored, tools = load_snapshot(state_dir, session.session_id)
    assert stored["turn"] == 1
    assert stored["plan"] == [
        {"content": "good", "priority": "medium", "status": "pending"},
    ]
    assert tools == {"todolist": [_todo("good")]}
    await server.close_session(session.session_id)


@pytest.mark.asyncio
async def test_persistence_failure_restores_last_good_state(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _PersistentFakeAgent(["natural"])
    server = _server(state_dir, lambda **_: agent)
    server.on_connect(_Client())
    session = await server.new_session(str(project), mcp_servers=[])
    before, _ = load_snapshot(state_dir, session.session_id)

    def fail_save(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(acp_server, "save_snapshot", fail_save)
    with pytest.raises(RequestError):
        await server.prompt(session.session_id, [text_block("bad")])

    stored, stored_tools = load_snapshot(state_dir, session.session_id)
    assert stored == before
    assert stored_tools == {"todolist": []}
    assert agent.current_session == before
    assert agent.tools.todo.state == []
    await server.close_session(session.session_id)


@pytest.mark.asyncio
async def test_atomic_replace_is_the_last_fallible_commit_step(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _PersistentFakeAgent(["natural"])
    server = _server(state_dir, lambda **_: agent)
    server.on_connect(_Client())
    session = await server.new_session(str(project), mcp_servers=[])
    real_save = acp_server.save_snapshot
    real_deepcopy = acp_server.copy.deepcopy
    committed = False

    def tracked_save(*args: Any, **kwargs: Any) -> None:
        nonlocal committed
        real_save(*args, **kwargs)
        committed = True

    def reject_post_commit_copy(value: Any) -> Any:
        if committed:
            raise AssertionError("nothing fallible may run after atomic replace")
        return real_deepcopy(value)

    monkeypatch.setattr(acp_server, "save_snapshot", tracked_save)
    monkeypatch.setattr(acp_server.copy, "deepcopy", reject_post_commit_copy)

    response = await server.prompt(session.session_id, [text_block("durable")])

    assert response.stop_reason == "end_turn"
    stored, tools = load_snapshot(state_dir, session.session_id)
    runtime = server._sessions[session.session_id]
    assert stored == runtime.last_good_session == agent.current_session
    assert tools == runtime.last_good_tools == {"todolist": [_todo("durable")]}
    await server.close_session(session.session_id)


@pytest.mark.asyncio
async def test_commit_uses_explicit_cwd_without_a_fallible_context_exit(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _PersistentFakeAgent()
    server = _server(state_dir, lambda **_: agent)
    session = await server.new_session(str(project), mcp_servers=[])
    runtime = server._sessions[session.session_id]
    runtime.agent.current_session = copy.deepcopy(runtime.last_good_session)
    runtime.agent.current_session["turn"] = 1
    runtime.agent.current_session["messages"].append({
        "role": "user",
        "content": "explicit cwd",
    })
    runtime.agent.tools.todo.state.append(_todo("explicit cwd"))
    runtime.agent.current_session["plan"] = _plan("explicit cwd")

    def reject_process_context(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("snapshot commit must not change process cwd")

    monkeypatch.setattr(server, "_process_context", reject_process_context)
    monkeypatch.chdir(tmp_path)

    server._commit_runtime(runtime)

    stored, tools = load_snapshot(
        state_dir,
        session.session_id,
        cwd=project,
    )
    assert stored == runtime.last_good_session == runtime.agent.current_session
    assert tools == runtime.last_good_tools == {
        "todolist": [_todo("explicit cwd")]
    }
    await server.close_session(session.session_id)


@pytest.mark.asyncio
async def test_failed_rollback_quarantines_runtime_and_releases_lease(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = _server(state_dir, lambda **_: _PersistentFakeAgent(["natural"]))
    server.on_connect(_Client())
    session = await server.new_session(str(project), mcp_servers=[])

    def fail_save(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    def fail_restore(_runtime: Any) -> None:
        raise RuntimeError("restore failed")

    monkeypatch.setattr(acp_server, "save_snapshot", fail_save)
    monkeypatch.setattr(server, "_restore_runtime", fail_restore)
    with pytest.raises(RequestError):
        await server.prompt(session.session_id, [text_block("bad")])

    with pytest.raises(RequestError, match="Session not found"):
        await server.prompt(session.session_id, [text_block("late")])
    with session_lock(state_dir, session.session_id):
        pass


@pytest.mark.asyncio
async def test_close_interrupts_active_prompt_then_releases_ownership(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _PersistentFakeAgent(["block"])
    server = _server(state_dir, lambda **_: agent)
    server.on_connect(_Client())
    session = await server.new_session(str(project), mcp_servers=[])
    prompt = asyncio.create_task(
        server.prompt(session.session_id, [text_block("wait")])
    )
    await asyncio.wait_for(asyncio.to_thread(agent.started.wait), timeout=1)

    closed = await asyncio.wait_for(server.close_session(session.session_id), timeout=1)

    assert isinstance(closed, CloseSessionResponse)
    assert (await prompt).stop_reason == "cancelled"
    with session_lock(state_dir, session.session_id):
        pass
    with pytest.raises(RequestError, match="Session not found"):
        await server.prompt(session.session_id, [text_block("late")])


@pytest.mark.asyncio
async def test_repeated_prompt_cancellation_cannot_release_a_live_worker(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _GateAgent(["natural"])
    server = _server(state_dir, lambda **_: agent)
    server.on_connect(_Client())
    session = await server.new_session(str(project), mcp_servers=[])
    before, _ = load_snapshot(state_dir, session.session_id)
    prompting = asyncio.create_task(
        server.prompt(session.session_id, [text_block("wait")])
    )
    await asyncio.wait_for(asyncio.to_thread(agent.started.wait), timeout=1)

    prompting.cancel()
    await asyncio.sleep(0)
    prompting.cancel()
    closing = asyncio.create_task(server.close_session(session.session_id))
    await asyncio.sleep(0)

    assert not prompting.done()
    assert not closing.done()
    with pytest.raises(SessionSnapshotError, match="already running"):
        with session_lock(state_dir, session.session_id):
            pass

    agent.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(prompting, timeout=1)
    assert isinstance(await asyncio.wait_for(closing, timeout=1), CloseSessionResponse)
    stored, _ = load_snapshot(state_dir, session.session_id)
    assert stored == before
    with session_lock(state_dir, session.session_id):
        pass


@pytest.mark.asyncio
async def test_cancelled_close_still_finishes_before_releasing_ownership(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _GateAgent(["block"])
    server = _server(state_dir, lambda **_: agent)
    server.on_connect(_Client())
    session = await server.new_session(str(project), mcp_servers=[])
    prompting = asyncio.create_task(
        server.prompt(session.session_id, [text_block("wait")])
    )
    await asyncio.wait_for(asyncio.to_thread(agent.started.wait), timeout=1)
    closing = asyncio.create_task(server.close_session(session.session_id))
    await asyncio.sleep(0)

    closing.cancel()
    await asyncio.sleep(0)
    closing.cancel()
    assert not closing.done()
    with pytest.raises(SessionSnapshotError, match="already running"):
        with session_lock(state_dir, session.session_id):
            pass

    agent.release.set()
    assert (await asyncio.wait_for(prompting, timeout=1)).stop_reason == "cancelled"
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(closing, timeout=1)
    with session_lock(state_dir, session.session_id):
        pass


@pytest.mark.asyncio
async def test_cancelled_commit_and_eof_wait_for_the_atomic_writer(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = _server(state_dir, lambda **_: _PersistentFakeAgent(["natural"]))
    contender = _server(state_dir, lambda **_: _PersistentFakeAgent())
    server.on_connect(_Client())
    session = await server.new_session(str(project), mcp_servers=[])
    real_save = acp_server.save_snapshot
    save_started = threading.Event()
    allow_save = threading.Event()

    def blocked_save(*args: Any, **kwargs: Any) -> None:
        save_started.set()
        allow_save.wait()
        real_save(*args, **kwargs)

    monkeypatch.setattr(acp_server, "save_snapshot", blocked_save)
    prompting = asyncio.create_task(
        server.prompt(session.session_id, [text_block("committed")])
    )
    await asyncio.wait_for(asyncio.to_thread(save_started.wait), timeout=1)

    prompting.cancel()
    await asyncio.sleep(0)
    prompting.cancel()
    eof_cleanup = asyncio.create_task(server.close_all())
    await asyncio.sleep(0)

    assert not prompting.done()
    assert not eof_cleanup.done()
    with pytest.raises(RequestError, match="Unable to resume session"):
        await contender.resume_session(
            session.session_id,
            str(project),
            mcp_servers=[],
        )

    allow_save.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(prompting, timeout=1)
    await asyncio.wait_for(eof_cleanup, timeout=1)
    stored, tools = load_snapshot(state_dir, session.session_id)
    assert stored["turn"] == 1
    assert tools == {"todolist": [_todo("committed")]}

    await contender.resume_session(session.session_id, str(project), mcp_servers=[])
    await contender.close_session(session.session_id)

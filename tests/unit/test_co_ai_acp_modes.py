"""ACP session modes stay transactional and below launch authority."""

from __future__ import annotations

import asyncio
import copy
import threading
import time
from typing import Any

import pytest
from acp import PROTOCOL_VERSION, RequestError, text_block
from acp.schema import CurrentModeUpdate, SetSessionModeResponse

from connectonion import Agent
from connectonion.cli.co_ai import acp_server
from connectonion.cli.co_ai.acp_server import ConnectOnionACPAgent
from connectonion.cli.co_ai.one_shot_sessions import (
    load_snapshot,
    save_snapshot,
    session_lock,
)
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.useful_plugins import enable_yolo, tool_approval, yolo
from tests.utils.mock_helpers import MockLLM


class _Client:
    def __init__(self, *, fail_mode_update: bool = False) -> None:
        self.updates: list[tuple[str, Any]] = []
        self.permission_requests: list[dict[str, Any]] = []
        self.fail_mode_update = fail_mode_update

    async def request_permission(self, **kwargs: Any) -> dict[str, Any]:
        self.permission_requests.append(kwargs)
        return {
            "outcome": {
                "outcome": "selected",
                "optionId": "reject_once",
            }
        }

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **_kwargs: Any,
    ) -> None:
        if self.fail_mode_update and isinstance(update, CurrentModeUpdate):
            raise RuntimeError("private mode transport marker")
        self.updates.append((session_id, update))


class _BlockingModeClient(_Client):
    def __init__(self) -> None:
        super().__init__()
        self.mode_update_started = asyncio.Event()

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        if isinstance(update, CurrentModeUpdate):
            self.mode_update_started.set()
            await asyncio.Future()
        await super().session_update(session_id, update, **kwargs)


class _ModeAgent:
    system_prompt = "system"

    def __init__(
        self,
        *,
        block: bool = False,
        internal_mode: str | None = None,
    ) -> None:
        self.current_session: dict[str, Any] | None = None
        self.io: Any = None
        self.block = block
        self.internal_mode = internal_mode
        self.started = threading.Event()

    def input(
        self,
        prompt: str,
        session: dict[str, Any] | None = None,
    ) -> str:
        if session is not None:
            self.current_session = copy.deepcopy(session)
        assert self.current_session is not None
        self.current_session["turn"] += 1
        self.started.set()
        if self.block:
            while not self.io.receive_all("INTERRUPT"):
                time.sleep(0.01)
        if self.internal_mode is not None:
            self.current_session["mode"] = self.internal_mode
            self.io.send({
                "type": "mode_changed",
                "mode": self.internal_mode,
                "triggered_by": "agent",
            })
        reason = "interrupted" if self.block else "natural"
        terminal = {
            "type": "turn_result",
            "turn": self.current_session["turn"],
            "reason": reason,
            "usage": None,
        }
        self.current_session["trace"].append(terminal)
        self.io.send(terminal)
        return prompt


async def _initialized_server(
    state_dir,
    factory,
    *,
    yolo: bool = False,
    yolo_turns: int = 7,
) -> ConnectOnionACPAgent:
    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=yolo,
        yolo_turns=yolo_turns,
        agent_factory=factory,
        session_co_dir=state_dir,
    )
    await server.initialize(protocol_version=PROTOCOL_VERSION)
    return server


def _project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


@pytest.fixture(autouse=True)
def _isolate_project_lookup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.mark.asyncio
async def test_new_default_session_returns_exact_modes_and_persists_default(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = await _initialized_server(state_dir, lambda **_: _ModeAgent())

    created = await server.new_session(str(project), mcp_servers=[])

    assert _dump(created.modes) == {
        "currentModeId": ":read-only",
        "availableModes": [
            {
                "id": ":read-only",
                "name": "Read only",
                "description": "Read freely; ask before edits, commands, or broader access.",
            },
            {
                "id": ":workspace",
                "name": "Auto",
                "description": (
                    "Edit the workspace automatically; broader actions still ask."
                ),
            },
        ],
    }
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":read-only"
    assert not {"skip_tool_approval", "full_access_turns", "full_access_turns_used"} & stored.keys()
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_yolo_launch_advertises_and_persists_bounded_full_access(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = await _initialized_server(
        state_dir,
        lambda **_: _ModeAgent(),
        yolo=True,
        yolo_turns=7,
    )

    created = await server.new_session(str(project), mcp_servers=[])

    assert created.modes.current_mode_id == ":danger-full-access"
    assert [mode.id for mode in created.modes.available_modes] == [
        ":read-only",
        ":workspace",
        ":danger-full-access",
    ]
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":danger-full-access"
    assert stored["full_access_turns"] == 7
    assert stored["full_access_turns_used"] == 0
    assert stored["skip_tool_approval"] is True
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_idle_auto_change_commits_memory_disk_and_resume(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    first = await _initialized_server(state_dir, lambda **_: _ModeAgent())
    created = await first.new_session(str(project), mcp_servers=[])

    changed = await first.set_session_mode(created.session_id, ":workspace")

    assert isinstance(changed, SetSessionModeResponse)
    runtime = first._sessions[created.session_id]
    assert runtime.last_good_session["mode"] == ":workspace"
    assert runtime.session_for_next_prompt["mode"] == ":workspace"
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":workspace"
    await first.close_session(created.session_id)

    resumed_server = await _initialized_server(state_dir, lambda **_: _ModeAgent())
    resumed = await resumed_server.resume_session(
        created.session_id,
        str(project),
        mcp_servers=[],
    )
    assert resumed.modes.current_mode_id == ":workspace"
    await resumed_server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_unknown_and_unauthorized_full_access_do_not_mutate_session(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = await _initialized_server(state_dir, lambda **_: _ModeAgent())
    created = await server.new_session(str(project), mcp_servers=[])

    for mode in ("future", ":danger-full-access"):
        with pytest.raises(RequestError, match="Invalid params"):
            await server.set_session_mode(created.session_id, mode)

    runtime = server._sessions[created.session_id]
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert runtime.last_good_session["mode"] == ":read-only"
    assert stored["mode"] == ":read-only"
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_authorized_full_access_upgrade_and_downgrade_clean_bypass_state(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = await _initialized_server(
        state_dir,
        lambda **_: _ModeAgent(),
        yolo=True,
        yolo_turns=9,
    )
    created = await server.new_session(str(project), mcp_servers=[])

    await server.set_session_mode(created.session_id, ":read-only")
    safe, _ = load_snapshot(state_dir, created.session_id)
    assert safe["mode"] == ":read-only"
    assert not {"skip_tool_approval", "full_access_turns", "full_access_turns_used"} & safe.keys()

    await server.set_session_mode(created.session_id, ":danger-full-access")
    full_access, _ = load_snapshot(state_dir, created.session_id)
    assert full_access["mode"] == ":danger-full-access"
    assert full_access["full_access_turns"] == 9
    assert full_access["full_access_turns_used"] == 0
    assert full_access["skip_tool_approval"] is True
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_auto_mode_drives_the_existing_tool_approval_policy(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    executed: list[str] = []

    def write(content: str) -> str:
        """Record a deterministic file-edit-like effect."""

        executed.append(content)
        return content

    def factory(**_kwargs: Any) -> Agent:
        return Agent(
            name="acp-mode",
            tools=[write],
            plugins=[tool_approval],
            llm=MockLLM(responses=[
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name="write",
                        arguments={"content": "value"},
                        id="call-auto",
                    )],
                    raw_response={},
                ),
                LLMResponse(
                    content="done",
                    tool_calls=[],
                    raw_response={},
                ),
            ]),
            max_iterations=2,
            log=False,
            quiet=True,
            co_dir=project / ".co",
        )

    server = await _initialized_server(state_dir, factory)
    server.on_connect(_Client())
    created = await server.new_session(str(project), mcp_servers=[])
    await server.set_session_mode(created.session_id, ":workspace")

    response = await server.prompt(created.session_id, [text_block("write")])

    assert response.stop_reason == "end_turn"
    assert executed == ["value"]
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":workspace"
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_default_downgrade_disarms_real_agent_full_access_activation(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    executed: list[str] = []

    def write(content: str) -> str:
        """Record a side effect that Default mode must not auto-approve."""

        executed.append(content)
        return content

    def factory(**_kwargs: Any) -> Agent:
        agent = Agent(
            name="acp-yolo-downgrade",
            tools=[write],
            plugins=[tool_approval, yolo],
            llm=MockLLM(responses=[LLMResponse(
                content="",
                tool_calls=[ToolCall(
                    name="write",
                    arguments={"content": "must ask"},
                    id="call-safe",
                )],
                raw_response={},
            )]),
            max_iterations=2,
            log=False,
            quiet=True,
            co_dir=project / ".co",
        )
        enable_yolo(agent, turns=7)
        return agent

    client = _Client()
    server = await _initialized_server(state_dir, factory, yolo=True, yolo_turns=7)
    server.on_connect(client)
    created = await server.new_session(str(project), mcp_servers=[])
    runtime = server._sessions[created.session_id]
    assert runtime.agent._yolo_turns is None
    await server.set_session_mode(created.session_id, ":read-only")

    response = await server.prompt(created.session_id, [text_block("write")])

    assert response.stop_reason == "refusal"
    assert executed == []
    assert len(client.permission_requests) == 1
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":read-only"
    assert "skip_tool_approval" not in stored
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_busy_prompt_rejects_mode_change_without_policy_race(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    agent = _ModeAgent(block=True)
    server = await _initialized_server(tmp_path / "state", lambda **_: agent)
    server.on_connect(_Client())
    created = await server.new_session(str(project), mcp_servers=[])
    prompting = asyncio.create_task(
        server.prompt(created.session_id, [text_block("block")])
    )
    await asyncio.wait_for(asyncio.to_thread(agent.started.wait), timeout=1)

    with pytest.raises(RequestError, match="Session is busy"):
        await server.set_session_mode(created.session_id, ":workspace")

    await server.cancel(created.session_id)
    response = await asyncio.wait_for(prompting, timeout=1)
    assert response.stop_reason == "cancelled"
    stored, _ = load_snapshot(tmp_path / "state", created.session_id)
    assert stored["mode"] == ":read-only"
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_persistence_failure_leaves_mode_unchanged_without_private_details(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = await _initialized_server(state_dir, lambda **_: _ModeAgent())
    created = await server.new_session(str(project), mcp_servers=[])

    def fail_save(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("private mode persistence marker")

    monkeypatch.setattr(acp_server, "save_snapshot", fail_save)
    with pytest.raises(RequestError) as exc_info:
        await server.set_session_mode(created.session_id, ":workspace")

    assert "private mode persistence marker" not in str(exc_info.value)
    runtime = server._sessions[created.session_id]
    assert runtime.last_good_session["mode"] == ":read-only"
    assert runtime.session_for_next_prompt["mode"] == ":read-only"
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":read-only"
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_internal_mode_update_is_published_only_after_commit(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _ModeAgent(internal_mode=":workspace")
    client = _Client()
    server = await _initialized_server(state_dir, lambda **_: agent)
    server.on_connect(client)
    created = await server.new_session(str(project), mcp_servers=[])

    response = await server.prompt(created.session_id, [text_block("change")])

    assert response.stop_reason == "end_turn"
    mode_updates = [
        update for _, update in client.updates
        if isinstance(update, CurrentModeUpdate)
    ]
    assert [update.current_mode_id for update in mode_updates] == [":workspace"]
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":workspace"
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_failed_prompt_commit_does_not_publish_internal_mode(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _ModeAgent(internal_mode=":workspace")
    client = _Client()
    server = await _initialized_server(state_dir, lambda **_: agent)
    server.on_connect(client)
    created = await server.new_session(str(project), mcp_servers=[])

    def fail_save(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("private prompt commit marker")

    monkeypatch.setattr(acp_server, "save_snapshot", fail_save)
    with pytest.raises(RequestError):
        await server.prompt(created.session_id, [text_block("change then fail")])

    assert not any(
        isinstance(update, CurrentModeUpdate) for _, update in client.updates
    )
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":read-only"
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_mode_notification_failure_cannot_roll_back_durable_commit(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _ModeAgent(internal_mode=":workspace")
    server = await _initialized_server(state_dir, lambda **_: agent)
    server.on_connect(_Client(fail_mode_update=True))
    created = await server.new_session(str(project), mcp_servers=[])
    runtime = server._sessions[created.session_id]

    response = await server.prompt(created.session_id, [text_block("change")])

    assert response.stop_reason == "end_turn"
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":workspace"
    assert runtime.last_good_session["mode"] == ":workspace"
    assert created.session_id not in server._sessions
    with session_lock(state_dir, created.session_id):
        pass

    with pytest.raises(RequestError, match="Session not found"):
        await server.prompt(created.session_id, [text_block("must reconnect")])


@pytest.mark.asyncio
async def test_cancelled_mode_notification_quarantines_committed_runtime(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    agent = _ModeAgent(internal_mode=":workspace")
    client = _BlockingModeClient()
    server = await _initialized_server(state_dir, lambda **_: agent)
    server.on_connect(client)
    created = await server.new_session(str(project), mcp_servers=[])
    prompting = asyncio.create_task(
        server.prompt(created.session_id, [text_block("change")])
    )
    await asyncio.wait_for(client.mode_update_started.wait(), timeout=1)

    prompting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await prompting

    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":workspace"
    assert created.session_id not in server._sessions
    with session_lock(state_dir, created.session_id):
        pass
    with pytest.raises(RequestError, match="Session not found"):
        await server.prompt(created.session_id, [text_block("must reconnect")])


@pytest.mark.asyncio
async def test_cancelled_mode_request_settles_atomic_commit(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = await _initialized_server(state_dir, lambda **_: _ModeAgent())
    created = await server.new_session(str(project), mcp_servers=[])
    real_save = acp_server.save_snapshot
    started = threading.Event()
    release = threading.Event()

    def blocking_save(*args: Any, **kwargs: Any) -> None:
        started.set()
        release.wait()
        real_save(*args, **kwargs)

    monkeypatch.setattr(acp_server, "save_snapshot", blocking_save)
    changing = asyncio.create_task(
        server.set_session_mode(created.session_id, ":workspace")
    )
    await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1)
    changing.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await changing
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":workspace"
    assert server._sessions[created.session_id].last_good_session["mode"] == ":workspace"
    await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_close_waits_for_mode_commit_then_releases_lease(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    server = await _initialized_server(state_dir, lambda **_: _ModeAgent())
    created = await server.new_session(str(project), mcp_servers=[])
    real_save = acp_server.save_snapshot
    started = threading.Event()
    release = threading.Event()

    def blocking_save(*args: Any, **kwargs: Any) -> None:
        started.set()
        release.wait()
        real_save(*args, **kwargs)

    monkeypatch.setattr(acp_server, "save_snapshot", blocking_save)
    changing = asyncio.create_task(
        server.set_session_mode(created.session_id, ":workspace")
    )
    await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1)
    closing = asyncio.create_task(server.close_session(created.session_id))
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()

    await asyncio.wait_for(changing, timeout=1)
    await asyncio.wait_for(closing, timeout=1)
    stored, _ = load_snapshot(state_dir, created.session_id)
    assert stored["mode"] == ":workspace"
    with session_lock(state_dir, created.session_id):
        pass


@pytest.mark.asyncio
async def test_resume_preserves_committed_full_access_budget_without_reset(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    session_id = "7840827a-480b-43f7-b773-266071f71b72"
    saved = {
        "session_id": session_id,
        "messages": [{"role": "system", "content": "system"}],
        "trace": [],
        "turn": 2,
        "mode": ":danger-full-access",
        "full_access_turns": 8,
        "full_access_turns_used": 3,
        "skip_tool_approval": True,
    }
    save_snapshot(state_dir, saved, {}, cwd=project)
    server = await _initialized_server(
        state_dir,
        lambda **_: _ModeAgent(),
        yolo=True,
        yolo_turns=99,
    )

    resumed = await server.resume_session(session_id, str(project), mcp_servers=[])

    assert resumed.modes.current_mode_id == ":danger-full-access"
    runtime = server._sessions[session_id]
    assert runtime.last_good_session["full_access_turns"] == 8
    assert runtime.last_good_session["full_access_turns_used"] == 3
    await server.close_session(session_id)


@pytest.mark.asyncio
async def test_resume_rejects_full_access_budget_above_current_launch_ceiling(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    session_id = "f80d832e-58d5-40a7-af89-46686efcc62b"
    saved = {
        "session_id": session_id,
        "messages": [{"role": "system", "content": "system"}],
        "trace": [],
        "turn": 2,
        "mode": ":danger-full-access",
        "full_access_turns": 8,
        "full_access_turns_used": 3,
        "skip_tool_approval": True,
    }
    save_snapshot(state_dir, saved, {}, cwd=project)
    server = await _initialized_server(
        state_dir,
        lambda **_: _ModeAgent(),
        yolo=True,
        yolo_turns=4,
    )

    with pytest.raises(RequestError, match="Unable to resume session"):
        await server.resume_session(session_id, str(project), mcp_servers=[])

    with session_lock(state_dir, session_id):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode_state", "yolo"),
    [
        ({"mode": "future"}, False),
        ({
            "mode": ":danger-full-access",
            "full_access_turns": 8,
            "full_access_turns_used": 3,
            "skip_tool_approval": True,
        }, False),
        ({"mode": ":read-only", "skip_tool_approval": True}, False),
        ({
            "mode": ":danger-full-access",
            "full_access_turns": 8,
            "full_access_turns_used": 8,
            "skip_tool_approval": True,
        }, True),
    ],
)
async def test_resume_rejects_unknown_or_over_authorized_mode_state(
    tmp_path,
    monkeypatch,
    mode_state,
    yolo,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    session_id = "88eb833d-a7cc-4483-9833-ec6bda4b7602"
    saved = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
        **mode_state,
    }
    save_snapshot(state_dir, saved, {}, cwd=project)
    server = await _initialized_server(
        state_dir,
        lambda **_: _ModeAgent(),
        yolo=yolo,
    )

    with pytest.raises(RequestError, match="Unable to resume session"):
        await server.resume_session(session_id, str(project), mcp_servers=[])

    with session_lock(state_dir, session_id):
        pass

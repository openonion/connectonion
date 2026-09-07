"""Trust state belongs to the hosted project, not the process' current cwd.

An agent tool may change into a temporary directory and remove it.  Calling
``Path.cwd()`` after that raises ``FileNotFoundError: [Errno 2] No such file or
directory``.  The host used to do exactly that on the next authorization check,
which surfaced to O Chat as ``Agent error: misconfigured``.
"""

import os
from unittest.mock import MagicMock

from connectonion.network.trust import TrustAgent


def test_authorization_uses_the_project_bound_when_the_host_started(tmp_path,
                                                                   monkeypatch):
    project = tmp_path / "agent"
    (project / ".co").mkdir(parents=True)
    monkeypatch.chdir(project)

    trust = TrustAgent("open")

    abandoned = tmp_path / "tool-work"
    abandoned.mkdir()
    original_cwd = os.open(".", os.O_RDONLY)
    try:
        os.chdir(abandoned)
        abandoned.rmdir()

        decision = trust.should_allow("0x" + "a" * 64, {"prompt": "hello"})
    finally:
        os.fchdir(original_cwd)
        os.close(original_cwd)

    assert decision.allow


def test_authorization_does_not_follow_a_tool_into_another_project(tmp_path,
                                                                   monkeypatch):
    hosted = tmp_path / "hosted"
    (hosted / ".co").mkdir(parents=True)
    blocked = "0x" + "b" * 64
    (hosted / ".co" / "blocklist.txt").write_text(blocked + "\n")
    monkeypatch.chdir(hosted)
    trust = TrustAgent("open")

    unrelated = tmp_path / "unrelated"
    (unrelated / ".co").mkdir(parents=True)
    monkeypatch.chdir(unrelated)

    decision = trust.should_allow(blocked, {"prompt": "hello"})

    assert not decision.allow
    assert decision.reason == "Denied by fast rules"


def test_explicit_host_directory_wins_over_the_startup_working_directory(
        tmp_path, monkeypatch):
    hosted = tmp_path / "hosted"
    hosted_co_dir = hosted / ".co"
    hosted_co_dir.mkdir(parents=True)
    blocked = "0x" + "c" * 64
    (hosted_co_dir / "blocklist.txt").write_text(blocked + "\n")

    launcher = tmp_path / "launcher"
    launcher.mkdir()
    monkeypatch.chdir(launcher)
    trust = TrustAgent("open", co_dir=hosted_co_dir)

    decision = trust.should_allow(blocked, {"prompt": "hello"})

    assert not decision.allow
    assert decision.reason == "Denied by fast rules"


def test_create_app_binds_trust_beside_custom_storage(tmp_path, monkeypatch):
    """External ASGI hosting keeps trust and replay state in one project."""
    from connectonion.network.host import server
    from connectonion.network.host.session.storage import SessionStorage

    launcher = tmp_path / "launcher"
    launcher.mkdir()
    hosted_co_dir = tmp_path / "hosted" / ".co"
    hosted_co_dir.mkdir(parents=True)
    monkeypatch.chdir(launcher)

    captured = {}
    real_trust_agent = server.TrustAgent

    class CapturingTrustAgent(real_trust_agent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured["co_dir"] = self._co_dir

    monkeypatch.setattr(server, "TrustAgent", CapturingTrustAgent)

    def create_agent():
        agent = MagicMock()
        agent.name = "test-agent"
        agent.tools.names.return_value = []
        return agent

    storage = SessionStorage(hosted_co_dir / "session_results.jsonl")
    server.create_app(create_agent, storage=storage, trust="open")

    assert captured["co_dir"] == hosted_co_dir.resolve()

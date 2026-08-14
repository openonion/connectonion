"""Trust state belongs to the hosted project, not the process' current cwd.

An agent tool may change into a temporary directory and remove it.  Calling
``Path.cwd()`` after that raises ``FileNotFoundError: [Errno 2] No such file or
directory``.  The host used to do exactly that on the next authorization check,
which surfaced to O Chat as ``Agent error: misconfigured``.
"""

import os

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

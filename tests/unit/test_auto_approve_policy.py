"""Default Auto Approve is deterministic, scoped, versioned, and fail closed."""

from types import SimpleNamespace

import pytest

from connectonion.useful_plugins.tool_approval import check_approval, tool_approval
from connectonion.useful_plugins.tool_approval.policy import (
    DEFAULT_PROFILE,
    POLICY_ID,
    SAFE_PROFILE,
    advertised_profile_state,
    apply_auto_approve_policy,
    ensure_approval_profile,
    evaluate_auto_approve,
    set_approval_profile,
)
from connectonion.useful_plugins.ulw import handle_yolo_mode_change


def test_new_session_advertises_versioned_default_without_trusting_client_state():
    state = advertised_profile_state(
        {"approval_profile": {"id": "full_access", "version": 1}},
        new_session=True,
        allow_full_access=False,
    )
    assert state["schemaVersion"] == 1
    assert state["currentModeId"] == "default"
    assert state["policy"] == {
        "id": "connectonion.auto-approve",
        "version": 1,
    }
    assert [mode["id"] for mode in state["availableModes"]] == ["safe", "default"]


def test_unversioned_default_advertises_safe_and_admin_alone_sees_full_access():
    safe = advertised_profile_state(
        {"mode": "default"}, new_session=False, allow_full_access=False
    )
    admin = advertised_profile_state(
        {"mode": "accept_edits"}, new_session=False, allow_full_access=True
    )
    assert safe["currentModeId"] == "safe"
    assert admin["currentModeId"] == "default"
    assert [mode["id"] for mode in admin["availableModes"]] == [
        "safe", "default", "full_access",
    ]


class IO:
    def __init__(self, response=None):
        self.sent = []
        self.response = response or {"approved": True, "scope": "once"}

    def send(self, message):
        self.sent.append(message)

    def receive(self):
        return self.response


@pytest.fixture(autouse=True)
def _workspace_is_the_test_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def agent(tmp_path, *, io=True, profile=DEFAULT_PROFILE, requester=None):
    session = {
        "messages": [],
        "trace": [],
        "permissions": {},
        "approval_profile": {"id": profile, "version": 1, "source": "test"},
        "mode": profile,
    }
    if requester:
        session["requester"] = requester
    return SimpleNamespace(
        current_session=session,
        io=IO() if io else None,
        storage=None,
        logger=None,
    )


def call(agent, name, arguments):
    agent.current_session["pending_tool"] = {"name": name, "arguments": arguments}
    apply_auto_approve_policy(agent)
    check_approval(agent)
    return agent.current_session["pending_tool"]["approval_policy"]


def test_every_decision_has_stable_audit_fields(tmp_path):
    result = evaluate_auto_approve("read_file", {"path": str(tmp_path / "README.md")}, tmp_path)
    assert result == {
        "decision": "allow",
        "policy_id": POLICY_ID,
        "policy_version": 1,
        "source": "built-in",
        "reason": "read-only workspace operation",
        "effect_class": "read",
        "scope": "workspace",
        "requires_human": False,
    }


def test_policy_plugin_runs_immediately_before_human_approval():
    assert tool_approval[-2:] == [apply_auto_approve_policy, check_approval]


def test_decision_is_written_to_existing_trace_and_approval_message(tmp_path):
    instance = agent(tmp_path)
    instance.current_session["trace"] = [{"type": "tool_call", "id": "call-1", "name": "send_email"}]
    instance.current_session["pending_tool"] = {
        "id": "call-1",
        "name": "send_email",
        "arguments": {"to": "person@example.com"},
    }
    apply_auto_approve_policy(instance)
    check_approval(instance)
    result = instance.current_session["pending_tool"]["approval_policy"]
    assert instance.current_session["trace"][0]["approval_policy"] == result
    assert instance.io.sent[0]["policy"] == result


@pytest.mark.parametrize("name", ["read", "read_file", "glob", "grep", "search"])
def test_workspace_reads_are_auto_approved(tmp_path, name):
    instance = agent(tmp_path)
    result = call(instance, name, {"path": str(tmp_path / "file.txt")})
    assert result["decision"] == "allow"
    assert instance.io.sent == []


@pytest.mark.parametrize("name", ["write", "edit", "multi_edit"])
def test_workspace_edits_are_auto_approved(tmp_path, name):
    instance = agent(tmp_path)
    result = call(instance, name, {"path": str(tmp_path / "src.py")})
    assert result["decision"] == "allow"
    assert instance.io.sent == []


@pytest.mark.parametrize(
    "command",
    [
        "pytest -q tests/unit/test_one.py",
        "python -m pytest tests/unit/test_one.py",
        "uv run pytest -q tests/unit/test_one.py",
        "npm run lint",
        "cargo test --lib",
        "pytest -q && ruff check src",
    ],
)
def test_focused_verification_commands_are_auto_approved(tmp_path, command):
    instance = agent(tmp_path)
    result = call(instance, "bash", {"command": command})
    assert result["decision"] == "allow"
    assert instance.io.sent == []


@pytest.mark.parametrize(
    ("name", "arguments", "effect"),
    [
        ("delete", {"path": "src.py"}, "deletion"),
        ("write", {"path": "../outside.txt"}, "write_outside_workspace"),
        ("bash", {"command": "rm -rf build"}, "deletion"),
        ("bash", {"command": "cat .env"}, "credentials"),
    ],
)
def test_hard_denies_never_open_the_human_prompt(tmp_path, monkeypatch, name, arguments, effect):
    monkeypatch.chdir(tmp_path)
    instance = agent(tmp_path)
    with pytest.raises(ValueError, match="denied by"):
        call(instance, name, arguments)
    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "deny"
    assert result["effect_class"] == effect
    assert instance.io.sent == []


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("new_plugin_tool", {}),
        ("send_email", {"to": "person@example.com"}),
        ("bash", {"command": "git push origin main"}),
        ("bash", {"command": "co deploy"}),
        ("read_file", {"path": "/etc/hosts"}),
    ],
)
def test_ambiguous_or_external_calls_reuse_the_human_approval_path(tmp_path, name, arguments):
    instance = agent(tmp_path)
    result = call(instance, name, arguments)
    assert result["decision"] == "ask"
    assert instance.io.sent[0]["type"] == "approval_needed"


def test_broad_config_cannot_silently_turn_co_deploy_into_a_safe_command(tmp_path):
    instance = agent(tmp_path)
    instance.current_session["permissions"] = {
        "Bash(co *)": {
            "allowed": True,
            "source": "config",
            "reason": "legacy broad CLI permission",
            "when": {"command": "co *"},
        }
    }
    result = call(instance, "bash", {"command": "co deploy"})
    assert result["decision"] == "ask"
    assert result["requires_human"] is True
    assert instance.io.sent[0]["type"] == "approval_needed"


def test_human_session_grant_is_still_the_single_reusable_approval_store(tmp_path):
    instance = agent(tmp_path)
    instance.io.response = {"approved": True, "scope": "session"}
    call(instance, "send_email", {"to": "person@example.com"})
    assert instance.current_session["permissions"]["send_email"]["source"] == "user"

    instance.io.sent.clear()
    call(instance, "send_email", {"to": "second@example.com"})
    assert instance.io.sent == []


def test_unknown_tool_fails_closed_when_unattended(tmp_path):
    instance = agent(tmp_path, io=False)
    instance.current_session["pending_tool"] = {"name": "new_plugin_tool", "arguments": {}}
    apply_auto_approve_policy(instance)
    with pytest.raises(ValueError, match="denied by"):
        check_approval(instance)


def test_policy_exception_asks_interactively_and_denies_unattended(tmp_path, monkeypatch):
    import importlib

    policy = importlib.import_module("connectonion.useful_plugins.tool_approval.policy")

    def broken(*args, **kwargs):
        raise RuntimeError("details must not become authority")

    monkeypatch.setattr(policy, "evaluate_auto_approve", broken)
    interactive = agent(tmp_path)
    result = call(interactive, "read", {})
    assert result["decision"] == "ask"
    assert result["effect_class"] == "policy_failure"

    unattended = agent(tmp_path, io=False)
    unattended.current_session["pending_tool"] = {"name": "read", "arguments": {}}
    apply_auto_approve_policy(unattended)
    with pytest.raises(ValueError, match="denied by"):
        check_approval(unattended)


def test_new_session_gets_versioned_default_but_legacy_default_migrates_safe(tmp_path):
    new = SimpleNamespace(current_session={"_new_session": True}, io=None)
    old = SimpleNamespace(current_session={"mode": "default"}, io=None)
    assert ensure_approval_profile(new) == DEFAULT_PROFILE
    assert new.current_session["approval_profile"]["version"] == 1
    assert ensure_approval_profile(old) == SAFE_PROFILE
    assert old.current_session["approval_profile"]["source"] == "legacy-session-migration"


@pytest.mark.parametrize(
    ("alias", "expected"),
    [("safe", "safe"), ("accept_edits", "default"), ("ulw", "full_access"),
     ("full-access", "full_access"), ("auto", "default")],
)
def test_mode_aliases_persist_a_versioned_profile(tmp_path, alias, expected):
    instance = agent(tmp_path, profile="safe")
    assert set_approval_profile(instance, alias) == expected
    assert instance.current_session["approval_profile"]["id"] == expected


def test_contact_cannot_restore_full_access(tmp_path):
    requester = {"address": "0x" + "a" * 64, "level": "contact"}
    instance = agent(tmp_path, profile="full_access", requester=requester)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": "pytest -q"}}
    apply_auto_approve_policy(instance)
    assert instance.current_session["approval_profile"]["id"] == "safe"
    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "ask"


def test_full_access_is_still_bounded_by_control_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".co").mkdir()
    instance = agent(tmp_path, profile="full_access")
    with pytest.raises(ValueError, match="decides what this agent may do"):
        call(instance, "write", {"path": str(tmp_path / ".co" / "host.yaml")})


def test_bounded_yolo_updates_the_versioned_policy_before_its_first_tool(tmp_path):
    instance = agent(tmp_path, io=False, profile="safe")
    handle_yolo_mode_change(instance, turns=30)

    result = call(instance, "add", {"content": "compile", "active_form": "compiling"})

    assert instance.current_session["approval_profile"]["id"] == "full_access"
    assert result["decision"] == "allow"
    assert result["reason"] == "Full access was explicitly selected"

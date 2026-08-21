"""OIP Auto profile is deterministic, narrow, and fail closed."""

from types import SimpleNamespace

import pytest

from connectonion.useful_plugins.tool_approval import check_approval, tool_approval
from connectonion.useful_plugins.tool_approval.policy import (
    POLICY_ID,
    apply_auto_approve_policy,
    evaluate_auto_approve,
)


class IO:
    def __init__(self, response=None):
        self.sent = []
        self.response = response or {"approved": True, "scope": "once"}

    def send(self, message):
        self.sent.append(message)

    def receive(self):
        return self.response


def agent(*, mode="auto", permissions=None, requester=None, io=True):
    session = {
        "messages": [],
        "trace": [],
        "permissions": permissions or {},
        "mode": mode,
    }
    if requester:
        session["requester"] = requester
    return SimpleNamespace(
        current_session=session,
        io=IO() if io else None,
        storage=None,
        logger=None,
    )


def call(instance, name, arguments):
    instance.current_session["pending_tool"] = {"name": name, "arguments": arguments}
    apply_auto_approve_policy(instance)
    check_approval(instance)
    return instance.current_session["pending_tool"].get("approval_policy")


def test_policy_plugin_precedes_the_human_approval_hook():
    assert tool_approval[-2:] == [apply_auto_approve_policy, check_approval]


def test_every_auto_decision_has_stable_ui_safe_audit_fields(tmp_path):
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


@pytest.mark.parametrize("name", ["read", "read_file", "glob", "grep", "search"])
def test_auto_profile_allows_workspace_reads_without_a_dialog(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    instance = agent()

    result = call(instance, name, {"path": str(tmp_path / "file.txt")})

    assert result["decision"] == "allow"
    assert instance.io.sent == []


@pytest.mark.parametrize("name", ["write", "edit", "multi_edit"])
def test_auto_profile_allows_reversible_workspace_edits(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    instance = agent()

    result = call(instance, name, {"path": str(tmp_path / "src.py")})

    assert result["decision"] == "allow"
    assert instance.io.sent == []


@pytest.mark.parametrize(
    "command",
    [
        "pytest -q tests/unit/test_one.py",
        "python -m pytest tests/unit/test_one.py",
        "npm run lint",
        "cargo test --lib",
    ],
)
def test_auto_profile_allows_focused_verification(tmp_path, monkeypatch, command):
    monkeypatch.chdir(tmp_path)
    instance = agent()

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
def test_auto_profile_hard_denies_never_open_a_dialog(tmp_path, monkeypatch, name, arguments, effect):
    monkeypatch.chdir(tmp_path)
    instance = agent()

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
def test_auto_profile_keeps_ambiguous_or_external_calls_human_reviewable(tmp_path, monkeypatch, name, arguments):
    monkeypatch.chdir(tmp_path)
    instance = agent()

    result = call(instance, name, arguments)

    assert result["decision"] == "ask"
    assert instance.io.sent[0]["type"] == "approval_needed"
    assert instance.io.sent[0]["policy"] == result


def test_broad_config_cannot_silently_turn_deploy_into_auto(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    instance = agent(permissions={
        "Bash(co *)": {
            "allowed": True,
            "source": "config",
            "reason": "legacy broad CLI permission",
            "when": {"command": "co *"},
        }
    })

    result = call(instance, "bash", {"command": "co deploy"})

    assert result["decision"] == "ask"
    assert instance.io.sent[0]["type"] == "approval_needed"


def test_read_only_mode_keeps_the_manual_approval_contract():
    instance = agent(mode="read-only")

    result = call(instance, "write", {"path": "owned.txt"})

    assert result is None
    assert instance.io.sent[0]["type"] == "approval_needed"


def test_contact_uses_the_same_auto_contract_as_every_participant():
    instance = agent(requester={"address": "0x" + "a" * 64, "level": "contact"})

    result = call(instance, "write", {"path": "owned.txt"})

    assert result["decision"] == "allow"
    assert instance.io.sent == []


@pytest.mark.parametrize(
    ("name", "arguments", "effect"),
    [
        ("write", {"path": "../outside.txt"}, "write_outside_workspace"),
        ("read_file", {"path": "../outside.txt"}, "read_outside_workspace"),
        ("new_plugin_tool", {}, "unknown"),
    ],
)
def test_headless_auto_fails_closed_without_an_approval_channel(
    tmp_path, monkeypatch, name, arguments, effect
):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {
        "name": name,
        "arguments": arguments,
    }

    apply_auto_approve_policy(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "deny"
    assert result["effect_class"] == effect
    with pytest.raises(ValueError, match="denied by connectonion.auto"):
        check_approval(instance)


def test_headless_auto_still_allows_a_reversible_workspace_edit(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {
        "name": "write",
        "arguments": {"path": str(tmp_path / "inside.txt")},
    }

    apply_auto_approve_policy(instance)
    check_approval(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "allow"


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("write", {"path": "/outside.txt", "content": "verified"}),
        ("add", {"content": "verify", "active_form": "verifying"}),
        ("start", {"content": "verify"}),
        ("complete", {"content": "verify"}),
    ],
)
def test_headless_full_access_keeps_the_explicit_bounded_bypass(name, arguments):
    instance = agent(mode="full-access", io=False)
    instance.current_session["turns_left"] = 2
    instance.current_session["pending_tool"] = {
        "name": name,
        "arguments": arguments,
    }

    apply_auto_approve_policy(instance)
    check_approval(instance)

    assert "approval_policy" not in instance.current_session["pending_tool"]

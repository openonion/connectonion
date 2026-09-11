"""OIP Auto profile is deterministic, narrow, and fail closed."""

from types import SimpleNamespace

import pytest

from connectonion.cli.co_ai.agent import grant_managed_delegation_permissions
from connectonion.useful_plugins.tool_approval import check_approval, tool_approval
from connectonion.useful_plugins.tool_approval.approval import load_permission_patterns
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


@pytest.mark.parametrize("provider_tool", ["codex", "claude_code"])
def test_auto_honors_only_the_exact_co_ai_managed_delegation_grant(
    tmp_path, monkeypatch, provider_tool
):
    monkeypatch.chdir(tmp_path)
    instance = agent()
    grant_managed_delegation_permissions(instance)

    result = call(instance, provider_tool, {
        "prompt": "Create and test the requested project",
        "cwd": ".",
    })

    assert result["decision"] == "allow"
    assert result["effect_class"] == "managed_delegation"
    assert instance.io.sent == []


@pytest.mark.parametrize(
    "permission",
    [
        {
            "allowed": True,
            "source": "config",
            "reason": "managed delegation owns inner approval",
            "expires": {"type": "never"},
        },
        {
            "allowed": True,
            "source": "safe",
            "reason": "arbitrary safe grant",
            "expires": {"type": "never"},
        },
        {
            "allowed": True,
            "source": "safe",
            "reason": "managed delegation owns inner approval",
        },
    ],
)
def test_auto_does_not_treat_near_match_claude_grants_as_managed_delegation(
    tmp_path, monkeypatch, permission
):
    monkeypatch.chdir(tmp_path)
    instance = agent(permissions={"claude_code": permission})

    result = call(instance, "claude_code", {"prompt": "inspect", "cwd": "."})

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
    with pytest.raises(ValueError, match=f"denied by {POLICY_ID}"):
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
    "command",
    ["co browser status", "co browser status && co status"],
)
def test_headless_auto_honors_the_operator_command_allowlist(
    tmp_path, monkeypatch, command
):
    """Regression for #1270: cron has no dialog, but does have standing grants."""
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions={
        "Bash(co *)": {
            "allowed": True,
            "source": "config",
            "reason": "operator standing grant",
            "when": {"command": "co *"},
        }
    })
    instance.current_session["pending_tool"] = {
        "name": "bash",
        "arguments": {"command": command},
    }

    apply_auto_approve_policy(instance)
    check_approval(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow"
    assert result["effect_class"] == "configured_command"
    assert result["reason"] == "operator-configured command allowlist"


def test_packaged_permissions_keep_headless_co_browser_status_working(
    tmp_path, monkeypatch
):
    """Exercise the same shipped permission source used by a fresh 1.7 install."""
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=load_permission_patterns(tmp_path / ".co"))
    instance.current_session["pending_tool"] = {
        "name": "bash",
        "arguments": {"command": "co browser status"},
    }

    apply_auto_approve_policy(instance)
    check_approval(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "allow"


@pytest.mark.parametrize(
    ("command", "effect"),
    [
        ("co deploy", "publication"),
        ("co publish", "publication"),
        ("co email send --to a@example.com hi", "command"),
    ],
)
def test_headless_broad_co_grant_cannot_authorize_stronger_effects(
    tmp_path, monkeypatch, command, effect
):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions={
        "Bash(co *)": {
            "allowed": True,
            "source": "config",
            "reason": "legacy broad CLI permission",
            "when": {"command": "co *"},
        }
    })
    instance.current_session["pending_tool"] = {
        "name": "bash",
        "arguments": {"command": command},
    }

    apply_auto_approve_policy(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "deny"
    assert result["effect_class"] == effect
    with pytest.raises(ValueError, match=f"denied by {POLICY_ID}"):
        check_approval(instance)


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


# ---------------------------------------------------------------------------
# #1481: read-only commands run unattended, and a read-only pipe segment does
# not poison a command an operator has already granted.
#
# Before this, only eleven test/build tools auto-approved; `head`, `grep`,
# `wc`, `ls` fell through to "ask", and unattended "ask" is "deny". A 7×/day
# LinkedIn round died on `co browser ... get_text | head -40` after sixteen
# clean iterations, posted nothing, and wrote no report.
# ---------------------------------------------------------------------------

READ_ONLY_COMMANDS = [
    "head -40 notes.txt",
    "tail -n 5 log.txt",
    "cat README.md",
    "grep -i foo notes.txt",
    "rg --count foo",
    "wc -l notes.txt",
    "ls -la",
    "sed -n 1,10p notes.txt",
    "awk '{print $1}' notes.txt",
    "sort notes.txt | uniq -c | cut -d' ' -f1",
    "basename /tmp/x.txt",
    "jq .name package.json",
    "echo ok",
    "pwd",
    "cd src && ls",
]


@pytest.mark.parametrize("command", READ_ONLY_COMMANDS)
def test_headless_auto_allows_read_only_commands(tmp_path, monkeypatch, command):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow", result
    assert result["effect_class"] == "read"


@pytest.mark.parametrize(
    "command",
    [
        "sed -i s/a/b/ notes.txt",            # in-place edit writes the file
        "sed --in-place s/a/b/ notes.txt",
        "echo secret >> ~/.bashrc",           # a redirect outside the workspace
        "echo x > ../outside.txt",
        "echo 'Bash(*)' > .co/host.yaml",     # a redirect into a control file
        "cat notes.txt > $HOME/notes.txt",    # a redirect nobody can resolve
        "tee out.txt",                        # writes its input
        "find . -name '*.log' -delete",       # deletes
        "xargs rm",                           # runs whatever it is given
        "cat .env",                           # credentials: still denied
    ],
)
def test_read_only_names_do_not_cover_writes_or_credentials(tmp_path, monkeypatch, command):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "deny", result   # headless: nothing to ask
    # The control-file case is refused one step earlier, by name, before the
    # policy verdict is even read; either refusal is the right answer.
    with pytest.raises(ValueError, match=f"denied by {POLICY_ID}|names a file that decides"):
        check_approval(instance)


@pytest.mark.parametrize(
    "command",
    [
        "CO_WHO=x co browser -t t get_text | head -40",
        "CO_WHO=x co browser -t t get_text | grep -i foo",
        "co browser -t t run_page_script a.js && echo ok",
        "co browser status 2>&1 | tail -3",
    ],
)
def test_a_read_only_segment_does_not_poison_a_granted_command(tmp_path, monkeypatch, command):
    """The shipped Bash(co *) grant covered the browser command; the pipe into
    head is what killed the unattended run (#1481)."""
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=load_permission_patterns(tmp_path / ".co"))
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow", result
    assert result["effect_class"] == "configured_command"


def test_a_granted_command_still_cannot_smuggle_an_ungranted_one(tmp_path, monkeypatch):
    """Only read-only segments ride along. `co browser ... && co email send` is
    still an email send."""
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=load_permission_patterns(tmp_path / ".co"))
    instance.current_session["pending_tool"] = {
        "name": "bash",
        "arguments": {"command": "co browser status && co email send --to a@example.com hi"},
    }

    apply_auto_approve_policy(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "echo hi > notes.txt",
        "head -1 notes.txt > out.txt",
        "printf '%s\\n' a b >> list.txt",
        "cargo test --quiet > test-output.txt 2>&1",
        "sort notes.txt | uniq > uniq.txt",
    ],
)
def test_a_redirect_into_the_workspace_is_a_reversible_edit(tmp_path, monkeypatch, command):
    """`echo x > file` is what a model reaches for instead of the write tool, and
    it is held to the write tool's rule: inside the workspace it is allowed."""
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow", result
    assert result["effect_class"] in {"workspace_edit", "verification"}, result


HEREDOC_WRITE = "cat << 'EOF' > greeter/src/main.rs\nfn main() {\n    println!(\"hi\");\n}\nEOF"


def test_a_heredoc_into_a_workspace_file_is_a_reversible_edit(tmp_path, monkeypatch):
    """A real model's first move, unattended, was `cat << 'EOF' > src/main.rs`.
    bashlex cannot parse a here-document, so it was refused as unparseable.
    The body is data; the first line is what runs."""
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": HEREDOC_WRITE}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow", result
    assert result["effect_class"] == "workspace_edit"


@pytest.mark.parametrize(
    "command",
    [
        "cat << 'EOF' > ../outside.rs\nfn main() {}\nEOF",     # outside the workspace
        "cat << 'EOF' > .co/host.yaml\npermissions: {}\nEOF",  # a control file
        "bash << 'EOF'\nrm -rf /\nEOF",                        # the body executes
        "python3 << 'EOF'\nprint(1)\nEOF",
    ],
)
def test_a_heredoc_body_that_executes_or_lands_outside_is_not_an_edit(tmp_path, monkeypatch, command):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "cat .ssh/id_rsa",                     # a private key inside the workspace
        "head -5 .ssh/id_ed25519",
        "cat .co/keys/agent.key",              # the agent's OWN signing key
        "grep -r . .co/keys/",
        "cat server.pem",
        "cat deploy.key",
        "cat .ssh/authorized_keys",            # who may log in
        "cat .npmrc",                          # carries an auth token
        "cat .git-credentials",
        "wc -c id_rsa",
    ],
)
def test_key_material_is_never_read_silently_wherever_it_lives(tmp_path, monkeypatch, command):
    """A private key read is a credential read, workspace or not.

    The outside-workspace rule caught `head ~/.ssh/id_rsa` only because `~`
    is usually not the project. Where the workspace *is* the home directory —
    or where a key was committed, or the agent's own `.co/keys/` is under the
    project root — the read was allowed, because the credential check only
    looked for `.env`, `secret` and `credential` in the words. Found by
    verifying #1481 against the shipped permissions rather than by a test.
    """
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "deny", result
    assert result["effect_class"] == "credentials", result


@pytest.mark.parametrize(
    "command",
    [
        "cat keys.md",                 # documentation about keys is not a key
        "grep -n 'key' notes.txt",
        "head -3 keyboard.md",
        "cat monkey.txt",
        "ls .co/skills",
    ],
)
def test_the_key_rule_does_not_swallow_ordinary_files(tmp_path, monkeypatch, command):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "allow"

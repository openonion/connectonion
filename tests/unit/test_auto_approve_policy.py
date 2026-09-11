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


def test_an_operators_own_grant_for_a_delegate_is_not_managed_delegation():
    """An explicit host.yaml grant runs the tool, but by its own authority.

    The distinction matters for the audit line: managed delegation means
    "co ai injected this and the inner agent owns approval", while a config
    grant means "the operator wrote this down". Both allow; they are not the
    same statement, and only the exact runtime grant may claim the first.
    """
    instance = agent(permissions={"claude_code": {
        "allowed": True,
        "source": "config",
        "reason": "managed delegation owns inner approval",   # near-match wording
        "expires": {"type": "never"},
    }})

    result = call(instance, "claude_code", {"prompt": "inspect", "cwd": "."})

    assert result["decision"] == "allow"
    assert result["effect_class"] == "configured_tool"
    assert instance.io.sent == []


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
        # `co` is a multiplexer, so its strong verbs classify by verb now:
        # that, not a hardcoded exception, is what keeps `Bash(co *)` off them.
        ("co email send --to a@example.com hi", "external_effect"),
        ("co transfer 0xabc 5", "payment"),
        ("co server destroy prod", "external_effect"),
        ("co keys --reveal", "credentials"),
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
        "sed -n 1,10p notes.txt",             # sed takes a program: not read-only
        "sed -i s/a/b/ notes.txt",
        "awk '{print $1}' notes.txt",         # nor is awk
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


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("read_file", "server.pem"),
        ("read", ".ssh/id_rsa"),
        ("read_file", ".ssh/id_ed25519"),
        ("read_file", "deploy.key"),
        ("read_file", ".netrc"),
        ("read_file", ".git-credentials"),
        ("glob", ".ssh/*"),
        ("write", ".ssh/authorized_keys"),
        ("edit", "server.pem"),
        ("multi_edit", ".aws/credentials"),
    ],
)
def test_the_read_and_write_tools_hold_the_same_line_on_key_material(tmp_path, monkeypatch, name, path):
    """`cat server.pem` was denied while `read_file("server.pem")` was allowed.

    Found by running the fixed code through the real `co ai`: asked for
    `cat server.pem | head -2`, the model reached for `read_file` instead, and
    the console printed "policy read-only workspace operation". The shell rule
    and the tool rule have to agree, or the gate is a detour.
    """
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": name, "arguments": {"path": path}}

    apply_auto_approve_policy(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "deny", result
    assert result["effect_class"] == "credentials", result


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("read_file", "keys.md"),
        ("read_file", "notes.txt"),
        ("write", "src/main.rs"),
        ("edit", "monkey.py"),
        ("glob", "src/*.rs"),
    ],
)
def test_ordinary_files_still_reach_the_read_and_write_tools(tmp_path, monkeypatch, name, path):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": name, "arguments": {"path": path}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "allow"


def test_the_read_only_list_is_not_a_way_to_run_arbitrary_code(tmp_path, monkeypatch):
    """Nothing that takes a program text is read-only.

    `awk 'BEGIN{system("rm -rf /")}'` reads like an inspection and is
    arbitrary execution; GNU `sed`'s `e` flag is the same. Keeping them while
    excluding their execution constructs would need a parser in a security
    path, so both ask — including their innocent shapes, whose job `head`,
    `cut` and `read_file(limit=, offset=)` already do.
    """
    monkeypatch.chdir(tmp_path)
    for command in [
        "awk 'BEGIN{system(\"rm -rf /\")}'",   # arbitrary execution
        "awk -f script.awk data.txt",          # runs a program file
        "awk '{print $1}' notes.txt",           # the innocent shape, same rule
        "sed 's/a/b/e' notes.txt",             # GNU sed's e flag executes
        "sed -n 1,10p notes.txt",              # the innocent shape, same rule
        "find . -exec rm {} +",
        "xargs -I{} rm {}",
        "env sh -c 'rm -rf /'",
    ]:
        instance = agent(io=False)
        instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}
        apply_auto_approve_policy(instance)
        result = instance.current_session["pending_tool"]["approval_policy"]
        assert result["decision"] == "deny", (command, result)


@pytest.mark.parametrize(
    "command",
    [
        "head $(echo /etc/shadow)",      # the path arrives from a substitution
        "cat `echo /etc/passwd`",
        "head $HOME/.ssh/id_rsa",        # and from the environment
        "cat ${SECRET_PATH}",
        "cat $(cat which_file.txt)",
    ],
)
def test_a_path_the_policy_cannot_resolve_is_not_a_workspace_path(tmp_path, monkeypatch, command):
    """A read-only command whose target comes from a substitution or a variable
    is not a read the policy has checked.

    `cat $(cat which_file.txt)` reads whatever that file names. Two of these
    were refused before the rule existed, but by luck: one word happened to
    split across the substitution and another happened to contain "secret".
    """
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "grep 'foo$' notes.txt",       # a bare $ is end-of-line, not a variable
        "grep -c '$' notes.txt",
        "echo $HOME",                  # echo reads no file
        "head -3 notes.txt",
    ],
)
def test_a_bare_dollar_is_not_a_variable(tmp_path, monkeypatch, command):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "allow"


@pytest.mark.parametrize(
    "command",
    ["make test", "make check", "make lint", "make build", "make coverage"],
)
def test_make_still_runs_a_named_verification_target(tmp_path, monkeypatch, command):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow", result
    assert result["effect_class"] == "verification"


@pytest.mark.parametrize(
    "command",
    [
        "make install",              # not verification; writes outside by convention
        "make",                      # the default target is whatever the file says
        "make -C /etc all",          # make, pointed somewhere else
        "make -f /tmp/evil.mk test", # make, given another program
        "make test install",         # one verification target does not carry the rest
    ],
)
def test_make_is_not_a_way_to_run_anything(tmp_path, monkeypatch, command):
    """1.8.4 allowed all of these under "focused test, lint, or build command".

    `cargo`, `go` and the package runners were already narrowed to their
    verification subcommands; `make` was the one left open. Found by an
    adversarial sweep of the shipped policy before publishing 1.8.5a1, not by
    a test.
    """
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False)
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "deny"


# ---------------------------------------------------------------------------
# An explicit grant is an approval already given.
#
# Measured on 1.8.4: nine grants written by hand into the operator's own
# host.yaml, eight of them ignored. `Bash(curl *)` was denied unattended and
# asked *every single time* with a person present. A skill's declared `tools:`
# bought nothing at all — the same `Bash(mkdir *)` ran as `source: config` and
# was refused as `source: skill`.
# ---------------------------------------------------------------------------

def _granted(pattern, source="config", command=None):
    return {pattern: {
        "allowed": True,
        "source": source,
        "reason": f"written by the {source}",
        **({"when": {"command": pattern[5:-1]}} if pattern.startswith("Bash(") else {}),
        "expires": {"type": "turn_end" if source == "skill" else "never"},
    }}


@pytest.mark.parametrize("source", ["config", "skill"])
@pytest.mark.parametrize(
    ("pattern", "command"),
    [
        ("Bash(curl *)", "curl https://example.com"),        # external network
        ("Bash(rm -rf build)", "rm -rf build"),              # destructive
        ("Bash(git push *)", "git push origin main"),        # publication
        ("Bash(co deploy)", "co deploy"),                    # publication
        ("Bash(cat .env)", "cat .env"),                      # credentials
        ("Bash(sed -i *)", "sed -i s/a/b/ notes.txt"),       # takes a program
        ("Bash(awk *)", "awk '{print $1}' notes.txt"),
        ("Bash(mkdir *)", "mkdir -p build"),                 # ordinary
        ("Bash(co email send *)", "co email send --to a@b.c hi"),
    ],
)
def test_an_explicit_grant_runs_unattended_whatever_the_effect(
    tmp_path, monkeypatch, source, pattern, command
):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=_granted(pattern, source))
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow", (pattern, command, result)
    assert result["effect_class"] == "configured_command"


@pytest.mark.parametrize("source", ["config", "skill"])
def test_an_explicit_grant_does_not_ask_again_with_a_person_present(tmp_path, monkeypatch, source):
    """You wrote the grant. Being asked every time is the bug (#1481)."""
    monkeypatch.chdir(tmp_path)
    instance = agent(permissions=_granted("Bash(curl *)", source))

    result = call(instance, "bash", {"command": "curl https://example.com"})

    assert result["decision"] == "allow", result
    assert instance.io.sent == [], "a dialog was shown for a call the operator had already allowed"


@pytest.mark.parametrize("source", ["config", "skill"])
def test_an_explicit_grant_covers_a_non_bash_tool_too(tmp_path, monkeypatch, source):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=_granted("send_email", source))
    instance.current_session["pending_tool"] = {"name": "send_email", "arguments": {"to": "a@b.c"}}

    apply_auto_approve_policy(instance)
    check_approval(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow", result
    assert result["effect_class"] == "configured_tool"


@pytest.mark.parametrize(
    ("pattern", "command"),
    [
        ("Bash(git *)", "git push origin main"),      # git is ordinary, push publishes
        ("Bash(co *)", "co deploy"),
        ("Bash(co *)", "co email send --to a@b.c hi"),
        ("Bash(co *)", "co keys --reveal"),
        ("Bash(ls *)", "rm -rf build"),               # does not match at all
    ],
)
def test_a_wildcard_cannot_reach_a_stronger_effect_than_it_names(tmp_path, monkeypatch, pattern, command):
    """`Bash(curl *)` plainly means network. `Bash(git *)` does not plainly
    mean "push", and `Bash(co *)` does not mean "send mail as me" — `co` is a
    multiplexer whose verbs have nothing like the same power. A wildcard is
    honoured for the effect its own text classifies to, and no further; the
    operator who wants more names it, as `Bash(git push *)` does above."""
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=_granted(pattern))
    instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}

    apply_auto_approve_policy(instance)

    assert instance.current_session["pending_tool"]["approval_policy"]["decision"] == "deny"


def test_the_shipped_defaults_are_not_an_operators_grant(tmp_path, monkeypatch):
    """78 entries ship in the template declaring `source: config`, which made
    them indistinguishable from something the operator wrote — the reason the
    broad `Bash(co *)` needed a hardcoded exception. They load as `template`
    now and still buy exactly what they did: `co status`, `co browser ...`."""
    monkeypatch.chdir(tmp_path)
    shipped = load_permission_patterns(tmp_path / ".co")
    assert shipped["Bash(co *)"]["source"] == "template"

    for command, expected in [
        ("co status", "allow"),
        ("co browser status", "allow"),
        ("co deploy", "deny"),
        ("co email send --to a@b.c hi", "deny"),
        ("co keys --reveal", "deny"),
    ]:
        instance = agent(io=False, permissions=dict(shipped))
        instance.current_session["pending_tool"] = {"name": "bash", "arguments": {"command": command}}
        apply_auto_approve_policy(instance)
        got = instance.current_session["pending_tool"]["approval_policy"]["decision"]
        assert got == expected, (command, got)


def test_a_quoted_program_does_not_read_as_ungranted(tmp_path, monkeypatch):
    """The grant check must not re-parse a segment's text.

    `_extract_subcommands` returns segments with quotes removed, so feeding
    `awk BEGIN{system("x")}` back to bashlex raises — and the first version of
    this code swallowed that into "no grant". It happened to deny something
    dangerous, which is how a swallowed error hides: the same path denies a
    grant the operator did write, for a command whose text simply does not
    re-parse.
    """
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=_granted("Bash(awk *)"))
    instance.current_session["pending_tool"] = {
        "name": "bash",
        "arguments": {"command": 'awk \'BEGIN{system("echo hi")}\''},
    }

    apply_auto_approve_policy(instance)

    result = instance.current_session["pending_tool"]["approval_policy"]
    assert result["decision"] == "allow", result


# ---------------------------------------------------------------------------
# A refusal says how to fix it.
#
# "command is outside the focused verification allowlist" tells an operator
# nothing about what to write, where. The daily digest stopped sending on the
# 1.7.0 upgrade and nobody learned why for days, because the refusal named a
# policy instead of a remedy.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("co email send --to a@b.c hi", "Bash(co email send *)"),   # not Bash(co *)
        ("curl https://example.com", "Bash(curl *)"),
        ("git push origin main", "Bash(git push origin *)"),
        ("CO_WHO=x co browser get_text", "Bash(co browser get_text *)"),
        ("sed -i s/a/b/ notes.txt", "Bash(sed *)"),
        ("ping -c 1 8.8.8.8", "Bash(ping *)"),
    ],
)
def test_the_suggested_grant_names_the_verb_not_the_binary(command, expected):
    from connectonion.useful_plugins.tool_approval.policy import suggested_grant_pattern

    assert suggested_grant_pattern("bash", {"command": command}) == expected


@pytest.mark.parametrize(
    ("command", "effect", "expected"),
    [
        ("rm -rf build", "deletion", "Bash(rm -rf build)"),
        ("cat .env", "credentials", "Bash(cat .env)"),
        ("co transfer 0xabc 5", "payment", "Bash(co transfer 0xabc 5)"),
        ("curl https://example.com", "external_network", "Bash(curl *)"),
    ],
)
def test_a_dangerous_effect_is_suggested_exactly_not_as_a_wildcard(command, effect, expected):
    """The remedy is a nudge toward whatever it prints, and an operator in a
    hurry pastes it. `Bash(rm *)` would also cover `rm -rf /`, so a deletion,
    a credential or a payment gets named exactly."""
    from connectonion.useful_plugins.tool_approval.policy import suggested_grant_pattern

    assert suggested_grant_pattern("bash", {"command": command}, effect) == expected


def test_a_non_bash_tool_is_suggested_by_its_name():
    from connectonion.useful_plugins.tool_approval.policy import suggested_grant_pattern

    assert suggested_grant_pattern("send_email", {"to": "a@b.c"}) == "send_email"


def test_an_unattended_refusal_names_the_line_to_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=load_permission_patterns(tmp_path / ".co"))
    instance.current_session["pending_tool"] = {
        "name": "bash",
        "arguments": {"command": "co email send --to aaron@example.com digest"},
    }

    apply_auto_approve_policy(instance)

    policy = instance.current_session["pending_tool"]["approval_policy"]
    assert policy["decision"] == "deny"
    remedy = policy["remedy"]
    assert "Bash(co email send *)" in remedy
    assert ".co/host.yaml" in remedy
    assert "SKILL.md frontmatter" in remedy

    # And the model reads it, because it is in the error it gets back.
    with pytest.raises(ValueError) as refusal:
        check_approval(instance)
    assert "Bash(co email send *)" in str(refusal.value)
    assert "tools:" in str(refusal.value)


def test_a_granted_call_carries_no_remedy(tmp_path, monkeypatch):
    """Nothing to fix, nothing to say."""
    monkeypatch.chdir(tmp_path)
    instance = agent(io=False, permissions=_granted("Bash(co email send *)"))
    instance.current_session["pending_tool"] = {
        "name": "bash",
        "arguments": {"command": "co email send --to a@b.c hi"},
    }

    apply_auto_approve_policy(instance)

    policy = instance.current_session["pending_tool"]["approval_policy"]
    assert policy["decision"] == "allow"
    assert "remedy" not in policy

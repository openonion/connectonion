"""Deterministic, fail-closed policy for canonical Auto mode.

The Host owns the selected permission profile.  This module never persists a
client-supplied mode or grants Full access; it only classifies one pending
tool call after the Host has selected ``auto``.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.events import before_each_tool
from ...core.mode import AUTO, FULL_ACCESS, READ_ONLY, mode_id, mode_of, set_mode
from ...project import project_root
from .approval import matches_permission_pattern
from .bash_parser import _extract_subcommands, check_bash_chain_permitted, segment_permitted

if TYPE_CHECKING:
    from ...core.agent import Agent


POLICY_ID = "connectonion.auto"
POLICY_VERSION = 1
MANAGED_DELEGATION_TOOLS = frozenset({"codex", "claude_code"})
MANAGED_DELEGATION_REASON = "managed delegation owns inner approval"

READ_TOOLS = {
    "read", "read_file", "glob", "grep", "search", "list", "ls",
    "list_files", "get_file_info", "task_output", "get_emails", "get_events",
    "screenshot", "load_guide",
}
WORKFLOW_TOOLS = {"task", "ask_user", "skill", "todo_list"}
WORKSPACE_EDIT_TOOLS = {"write", "edit", "multi_edit"}
DELETE_TOOLS = {"delete", "remove", "unlink", "rmdir", "delete_file"}
EXTERNAL_EFFECT_TOOLS = {
    "send_email", "post", "publish", "deploy", "transfer", "pay",
    "create_payment", "delete_event", "send_message",
}

_FOCUSED_COMMANDS = {
    "pytest", "ruff", "mypy", "pyright", "eslint", "tsc", "vitest",
    "jest", "cargo", "go", "make",
}
# This category is an execution surface by design: an agent that may write a
# test and run it may run anything the test runs. What the narrowing below is
# for is the commands in it that are not verification at all — `make install`
# writes outside the workspace by convention, and 1.8.4 allowed it, along with
# bare `make` and `make -C /etc all`. `cargo`, `go` and the package runners
# were already narrowed this way; `make` was the one left open.
_MAKE_VERIFICATION_TARGETS = {
    "test", "tests", "check", "checks", "lint", "typecheck", "fmt", "format",
    "build", "coverage", "cov", "ci", "verify", "audit",
}
_PACKAGE_RUNNERS = {"npm", "pnpm", "yarn", "bun"}
_DESTRUCTIVE_COMMANDS = {"rm", "rmdir", "shred", "truncate", "del", "erase", "format"}
_EXTERNAL_COMMANDS = {"curl", "wget", "ssh", "scp", "rsync", "mail", "sendmail"}
_SENSITIVE_COMMANDS = {
    "env", "printenv", "security", "keychain", "gcloud", "aws", "az",
}
# Our own CLI is a multiplexer: `co status` and `co email send` are the same
# binary and nothing like the same power. Classifying the second by its verb
# is what stops a wildcard over `co` from reaching it — and it is the reason
# `Bash(co *)` needed a hardcoded exception before. The keys are the first two
# words; a one-word key covers every subcommand of it.
_CO_SUBCOMMAND_EFFECTS = {
    "email": ("external_effect", "ask", "sending mail requires human approval"),
    "transfer": ("payment", "ask", "moving credit requires human approval"),
    "server": ("external_effect", "ask", "creating or destroying a server requires human approval"),
    "keys": ("credentials", "deny", "credential access is never auto-approved"),
    "auth": ("credentials", "ask", "changing an account login requires human approval"),
    "reset": ("deletion", "ask", "resetting a project requires human approval"),
}
# Commands that read, filter or print and do nothing else. They run unattended
# in Auto, on workspace paths, with no output redirect. Before this list only
# the eleven test/build tools above auto-approved; `head`, `grep`, `wc`, `ls`
# fell through to "ask", and an unattended "ask" is a "deny" — a 7×/day
# LinkedIn round died on `co browser ... get_text | head -40` after sixteen
# clean iterations (#1481). This is the Auto *policy* for the agent's own
# calls; the remote-EXEC whitelist in host.yaml is a different gate and is
# deliberately not widened here.
_READ_ONLY_COMMANDS = {
    "head", "tail", "cat", "less", "more", "grep", "egrep", "fgrep", "rg",
    "wc", "ls", "sort", "uniq", "cut", "tr", "basename",
    "dirname", "jq", "echo", "printf", "pwd", "cd", "true", "test", "[",
    "which", "file", "stat", "diff", "date", "whoami", "hostname", "uname",
}
# `sed` and `awk` are deliberately absent. They take a *program*, and a
# program is code: `awk 'BEGIN{system("rm -rf /")}'` reads like an inspection
# and is arbitrary execution, as does `sed 's/a/b/e'` on GNU. Any rule that
# tried to keep them while excluding their execution constructs would be a
# parser in a security path, written by the person it has to outsmart. The
# inspection they are reached for has cover: `head`, `tail`, `cut`, `sort`,
# `uniq`, `wc`, `jq` and `grep` are on the list, `read_file` takes `limit`
# and `offset`, and the agent has `grep` and `glob` tools. Both still ask,
# which is what they did before 1.8.5 as well.
# Key material, recognised by where it lives and what it is called rather than
# by substring: `keys.md` is documentation and `monkey.txt` is a file. Reading
# any of this is a credential read wherever it sits, so the workspace rule is
# not what protects it — the workspace often *is* the home directory, a key
# gets committed, and `.co/keys/` holds the agent's own signing key.
_CREDENTIAL_DIRS = {".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", "keys"}
_CREDENTIAL_FILES = {
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "authorized_keys",
    ".npmrc", ".netrc", ".pgpass", ".git-credentials", ".pypirc",
    "keys.env", "credentials", "service-account.json", "id_rsa.pub",
}
_CREDENTIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".ppk")


def _is_key_material(word: str) -> bool:
    """True if this argument names key material."""
    import os

    normalised = os.path.normpath(word).replace(os.sep, "/").lstrip("/")
    parts = [part for part in normalised.split("/") if part not in ("", ".", "..")]
    if not parts:
        return False
    name = parts[-1].lower()
    return (
        any(part.lower() in _CREDENTIAL_DIRS for part in parts[:-1])
        or name in _CREDENTIAL_DIRS          # the directory itself, e.g. `ls .co/keys`
        or name in _CREDENTIAL_FILES
        or name.endswith(_CREDENTIAL_SUFFIXES)
    )
# The read-only commands that open the paths they are given. `basename`,
# `echo`, `pwd` and friends take strings, not files, and `cd` is here because
# leaving the workspace makes every later relative path a path outside it.
_PATH_READING_COMMANDS = {
    "head", "tail", "cat", "less", "more", "grep", "egrep", "fgrep", "rg",
    "wc", "ls", "sort", "uniq", "cut", "jq", "file", "stat", "diff", "cd",
}


def decision(
    effect: str, verdict: str, reason: str, scope: str, *, requires_human: bool = False
) -> dict:
    """Return the versioned, UI-safe decision recorded on a pending tool."""
    return {
        "decision": verdict,
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "source": "built-in",
        "reason": reason,
        "effect_class": effect,
        "scope": scope,
        "requires_human": requires_human,
    }


def canonical_mode(value: object) -> str | None:
    """Read one exact public mode without granting authority."""
    try:
        return mode_id(value)
    except ValueError:
        return None


def managed_delegation_permission() -> dict:
    """Build the exact co ai grant consumed by the Auto classifier."""
    return {
        "allowed": True,
        "source": "safe",
        "reason": MANAGED_DELEGATION_REASON,
        "expires": {"type": "never"},
    }


def _has_managed_delegation_grant(session: dict, tool_name: object) -> bool:
    """Recognize only the runtime grant injected by co ai for native adapters."""
    name = str(tool_name)
    if name not in MANAGED_DELEGATION_TOOLS:
        return False
    permissions = session.get("permissions")
    return (
        isinstance(permissions, dict)
        and permissions.get(name) == managed_delegation_permission()
    )


def ensure_approval_mode(agent: "Agent") -> str:
    """Canonicalize stored state through the one writer."""

    canonical = mode_of(agent.current_session)
    if canonical == FULL_ACCESS:
        return canonical
    set_mode(agent.current_session, canonical)
    return canonical


def set_approval_mode(agent: "Agent", mode: str, source: str = "user") -> str:
    """Set Read only or Auto; Host transactions remain remote authority."""
    del source
    canonical = mode_id(mode)
    if canonical not in {READ_ONLY, AUTO}:
        raise ValueError(f"Mode is not owned by Auto policy: {canonical}")
    return set_mode(agent.current_session, canonical)


def advertised_mode_state(
    session: dict | None, *, new_session: bool, allow_full_access: bool
) -> dict:
    """Return the exact public state advertised by compatibility callers."""
    del new_session
    current = mode_of(session or {})
    available = [
        {"id": READ_ONLY, "name": "Read only"},
        {"id": AUTO, "name": "Auto", "recommended": True},
    ]
    if allow_full_access:
        available.append({
            "id": FULL_ACCESS,
            "name": "Full access",
            "dangerous": True,
            "bound": "host-configured",
        })
    if current == FULL_ACCESS and not allow_full_access:
        current = AUTO
    return {
        "schemaVersion": POLICY_VERSION,
        "currentModeId": current,
        "availableModes": available,
        "policy": {"id": POLICY_ID, "version": POLICY_VERSION},
    }


def _workspace_path(args: dict) -> Path | None:
    raw = next(
        (args.get(key) for key in ("file_path", "path", "target", "filename") if args.get(key)),
        None,
    )
    return Path(str(raw)).expanduser().resolve(strict=False) if raw is not None else None


def _inside_workspace(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _command_words(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except (TypeError, ValueError):
        return []


_UNRESOLVABLE = re.compile(r"\$[A-Za-z_{(]|`")


def _reads_an_unresolvable_path(words: list[str]) -> bool:
    """True if a file argument comes from a substitution or a variable.

    `cat $(cat which_file.txt)` is a read of whatever that file names, and
    `head $HOME/.ssh/id_rsa` of whatever HOME is. Neither can be checked
    against the workspace, so neither is a checked read. Two of these passed
    before this rule, by luck: one word happened to split across the
    substitution, another happened to contain "secret". `grep 'foo$' f` is
    not affected — a bare `$` names nothing.
    """
    return any(_UNRESOLVABLE.search(word) for word in words[1:] if not word.startswith("-"))


def _reads_outside_workspace(words: list[str], root: Path) -> bool:
    """A path-looking argument that resolves outside the workspace.

    `head ~/.ssh/id_rsa` and `cat /etc/shadow` are reads, but not workspace
    reads; the read *tools* already ask for those, and the read *commands*
    hold the same line. `s/a/b/` also contains a slash and resolves inside the
    root, which is the right answer for a sed script.
    """
    for word in words[1:]:
        if word.startswith("-") or not (word.startswith(("/", "~", ".")) or "/" in word):
            continue
        path = Path(word).expanduser()
        resolved = (path if path.is_absolute() else root / path).resolve(strict=False)
        if not _inside_workspace(resolved, root):
            return True
    return False


def _classify_single_command(command: str, root: Path | None = None) -> dict:
    words = _command_words(command)
    if not words:
        return decision("command", "ask", "command could not be parsed safely", "call", requires_human=True)

    lowered = [word.lower() for word in words]
    # `VAR=value cmd ...` — the command is the first word that is not an assignment.
    while len(words) > 1 and "=" in words[0] and not words[0].startswith("-"):
        words, lowered = words[1:], lowered[1:]
    first = Path(words[0]).name.lower()
    if first in _DESTRUCTIVE_COMMANDS:
        return decision("deletion", "deny", "destructive command requires an explicit safer workflow", "call")
    if any(token in lowered for token in ("publish", "deploy", "release", "push")):
        return decision("publication", "ask", "publishing and deployment require human approval", "call", requires_human=True)
    if first in _EXTERNAL_COMMANDS:
        return decision("external_network", "ask", "external network access requires human approval", "call", requires_human=True)
    if first == "co" and len(words) > 1:
        effect = _CO_SUBCOMMAND_EFFECTS.get(words[1].lower())
        if effect:
            effect_class, verdict, reason = effect
            return decision(effect_class, verdict, reason, "call", requires_human=(verdict == "ask"))
    if first in _SENSITIVE_COMMANDS or any(
        ".env" in token or "credential" in token or "secret" in token for token in lowered
    ) or any(_is_key_material(word) for word in words[1:] if not word.startswith("-")):
        return decision("credentials", "deny", "credential access is never auto-approved", "call")

    focused = first in _FOCUSED_COMMANDS
    focused = focused or (first in {"python", "python3"} and words[1:3] == ["-m", "pytest"])
    focused = focused or (first == "uv" and len(words) > 2 and words[1] == "run" and Path(words[2]).name in _FOCUSED_COMMANDS)
    if first in _PACKAGE_RUNNERS:
        focused = any(token in lowered[1:4] for token in ("test", "lint", "build", "check", "typecheck"))
    if first == "cargo":
        focused = len(words) > 1 and words[1] in {"test", "check", "clippy", "build"}
    if first == "go":
        focused = len(words) > 1 and words[1] == "test"
    if first == "make":
        # A named verification target, and nothing that redirects make
        # somewhere else. Bare `make` runs whatever the default target is.
        targets = [w for w in words[1:] if not w.startswith("-")]
        flags = [w for w in words[1:] if w.startswith("-")]
        focused = (
            bool(targets)
            and all(t in _MAKE_VERIFICATION_TARGETS for t in targets)
            and not any(f.startswith(("-C", "--directory", "-f", "--file", "--makefile")) for f in flags)
        )
    if focused:
        return decision("verification", "allow", "focused test, lint, or build command", "workspace")
    if first in _READ_ONLY_COMMANDS:
        if first in _PATH_READING_COMMANDS and _reads_an_unresolvable_path(words):
            return decision("read_outside_workspace", "ask", "the file to read depends on the environment", "call", requires_human=True)
        if root is not None and first in _PATH_READING_COMMANDS and _reads_outside_workspace(words, root):
            return decision("read_outside_workspace", "ask", "reading outside the workspace requires approval", "call", requires_human=True)
        return decision("read", "allow", "read-only command", "workspace")
    return decision("command", "ask", "command is outside the focused verification and read-only allowlists", "call", requires_human=True)


def _redirect_targets(command: str) -> list[str]:
    """The files a command's output redirects write to.

    `2>&1` duplicates a descriptor and writes nothing; `> >(cmd)` is process
    substitution, and the inner command is classified on its own by
    _extract_subcommands. Everything else — `>`, `>>`, `2> file` — is a file
    being written, which bashlex keeps out of the word list, so this is the
    one place a write hiding behind a read-only command is seen.
    """
    import bashlex

    targets: list[str] = []

    def visit(node):
        if node.kind == "redirect" and node.type in (">", ">>") and hasattr(node.output, "word"):
            if not node.output.word.startswith(">("):
                targets.append(node.output.word)
        for attr in ("parts", "list"):
            for child in getattr(node, attr, None) or []:
                visit(child)
        for attr in ("command", "output", "input"):
            child = getattr(node, attr, None)
            if child is not None and hasattr(child, "kind"):
                visit(child)

    for node in bashlex.parse(command):
        visit(node)
    return targets


def _redirect_verdict(targets: list[str], root: Path | None) -> dict | None:
    """A redirect is a file write, and is held to the write tool's rules.

    Inside the workspace it is a reversible edit and allowed — `echo x > f`
    is what a model reaches for instead of the write tool. A control file is
    denied, a target outside the workspace is denied, and a target that
    depends on the environment (`$HOME/...`) cannot be resolved and asks.
    """
    from .approval import _is_control_file

    for target in targets:
        if "$" in target or "`" in target:
            return decision("command", "ask", "redirect target depends on the environment", "call", requires_human=True)
        if root is None:
            return decision("command", "ask", "a redirect writes a file", "call", requires_human=True)
        path = Path(target).expanduser()
        resolved = (path if path.is_absolute() else root / path).resolve(strict=False)
        if _is_control_file(str(resolved)):
            return decision("authorization_control", "deny", "agents cannot rewrite authorization control files", "call")
        if not _inside_workspace(resolved, root):
            return decision("write_outside_workspace", "deny", "writes outside the workspace are not auto-approved", "call")
    return None


_HEREDOC_OPERATOR = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def _without_heredoc_body(command: str) -> str:
    """`cat << 'EOF' > f\n...\nEOF` classified by its first line, body dropped.

    bashlex cannot parse a here-document, and an unparseable command asks —
    which is how a real model's first attempt to write main.rs was refused
    unattended: models reach for `cat << EOF > file` even when a write tool is
    offered. The body is data to the command on the first line. For a
    read-only command that is inert; for anything that executes its input
    (`bash << EOF`, `python << EOF`) the first word is not read-only and the
    command asks as before, body or no body.
    """
    header, _, _ = command.partition("\n")
    if not _HEREDOC_OPERATOR.search(header):
        return command
    return _HEREDOC_OPERATOR.sub("", header, count=1)


def _classify_command(command: str, root: Path | None = None) -> dict:
    command = _without_heredoc_body(command)
    try:
        subcommands = _extract_subcommands(command)
        targets = _redirect_targets(command)
    except Exception:
        return decision("command", "ask", "command could not be parsed safely", "call", requires_human=True)
    results = [_classify_single_command(full, root) for _, full in subcommands]
    if targets:
        verdict = _redirect_verdict(targets, root)
        if verdict is not None:
            return verdict
        # Every write target is a reversible workspace file: the read-only
        # segments feeding it are now a workspace edit, and are allowed as one.
        results = [
            decision("workspace_edit", "allow", "read-only command writing a workspace file", "workspace")
            if item["effect_class"] == "read" else item
            for item in results
        ]
    denied = next((item for item in results if item["decision"] == "deny"), None)
    if denied:
        return denied
    asked = next((item for item in results if item["decision"] == "ask"), None)
    if asked:
        return asked
    effects = {item["effect_class"] for item in results}
    count = f"{len(results)} command{'s' if len(results) != 1 else ''}"
    if effects == {"read"}:
        return decision("read", "allow", f"read-only command chain ({count})", "workspace")
    if effects == {"workspace_edit"}:
        return decision("workspace_edit", "allow", f"workspace file written by a read-only chain ({count})", "workspace")
    return decision("verification", "allow", f"focused verification chain ({count})", "workspace")


def evaluate_auto_approve(tool_name: str, args: dict, root: Path | None = None) -> dict:
    """Classify one exact Auto-profile tool call without side effects."""
    root = (root or project_root()).resolve()
    name = str(tool_name).lower()
    # Before anything else: the tools hold the same line the shell commands do.
    # `cat server.pem` was denied while `read_file("server.pem")` was allowed,
    # so a model asked for the first simply reached for the second — measured
    # through the real `co ai`, which printed "policy read-only workspace
    # operation" for a private key. A gate one tool wide is a detour.
    if name in READ_TOOLS | WORKSPACE_EDIT_TOOLS | DELETE_TOOLS:
        raw = next((args.get(key) for key in ("file_path", "path", "target", "filename", "pattern") if args.get(key)), None)
        if raw is not None and _is_key_material(str(raw)):
            return decision("credentials", "deny", "credential access is never auto-approved", "call")
    if name in READ_TOOLS:
        path = _workspace_path(args)
        if path is not None and not _inside_workspace(path, root):
            return decision("read_outside_workspace", "ask", "reading outside the workspace requires approval", "call", requires_human=True)
        return decision("read", "allow", "read-only workspace operation", "workspace")
    if name in WORKFLOW_TOOLS:
        return decision("workflow", "allow", "built-in planning or user-interaction workflow", "session")
    if name in WORKSPACE_EDIT_TOOLS:
        path = _workspace_path(args)
        if path is None:
            return decision("workspace_edit", "ask", "edit target is missing or ambiguous", "call", requires_human=True)
        from .approval import _is_control_file
        if _is_control_file(str(path)):
            return decision("authorization_control", "deny", "agents cannot rewrite authorization control files", "call")
        if not _inside_workspace(path, root):
            return decision("write_outside_workspace", "deny", "writes outside the workspace are not auto-approved", "call")
        return decision("workspace_edit", "allow", "reversible edit inside the workspace", "workspace")
    if name in DELETE_TOOLS:
        return decision("deletion", "deny", "deletion is never auto-approved", "call")
    if name in EXTERNAL_EFFECT_TOOLS:
        return decision("external_effect", "ask", "external side effects require human approval", "call", requires_human=True)
    if name in {"bash", "shell", "run", "run_in_dir", "run_background"}:
        return _classify_command(str(args.get("command", "")), root)
    if name == "kill_task":
        return decision("task_control", "ask", "stopping a running task requires approval", "call", requires_human=True)
    return decision("unknown", "ask", "unknown tools never run silently", "call", requires_human=True)


def workspace_policy_for_pending(agent: "Agent", pending: dict) -> dict | None:
    """Return a deterministic decision for any ordinary Auto session."""
    if ensure_approval_mode(agent) != AUTO:
        return None
    try:
        if _has_managed_delegation_grant(agent.current_session, pending.get("name")):
            result = decision(
                "managed_delegation",
                "allow",
                MANAGED_DELEGATION_REASON,
                "session",
            )
        else:
            result = evaluate_auto_approve(
                pending["name"], pending.get("arguments") or {}
            )
    except Exception as exc:
        result = decision(
            "policy_failure",
            "ask" if agent.io else "deny",
            f"authorization policy failed closed ({type(exc).__name__})",
            "call",
            requires_human=bool(agent.io),
        )
    if result["decision"] in ("ask", "deny"):
        granted = _explicitly_granted(agent, pending, result)
        if granted is not None:
            result = granted
    if not agent.io and result["decision"] == "ask":
        result = decision(
            result["effect_class"],
            "deny",
            f"{result['reason']}; no approval channel is available",
            result["scope"],
        )
        result["remedy"] = grant_remedy(
            pending.get("name"), pending.get("arguments") or {}, result["effect_class"]
        )
    pending["approval_policy"] = result
    record_approval_policy(agent, pending)
    return result


# Grants that somebody wrote down on purpose: the operator's own host.yaml,
# a skill's `tools:` frontmatter (declared by its author, not chosen by the
# model at runtime), and a human's in-session approval. Each of these is a
# person saying "yes, this" before the call happened, which is what an
# approval is — so the policy honours them instead of asking again.
#
# `template` is deliberately absent. Those 78 entries ship with the product
# and nobody chose them for this project, so they still buy only what they
# always did: an ordinary command, never a stronger effect.
_EXPLICIT_SOURCES = frozenset({"config", "skill", "user"})
_TEMPLATE_SOURCES = frozenset({"template", "safe"})


_VALUE_LOOKING = ("-", "/", "~", ".")


# Effects where a suggestion the operator pastes without reading should buy as
# little as possible. `rm -rf build` gets `Bash(rm -rf build)`, not
# `Bash(rm *)`: the wildcard would also cover `rm -rf /`, and a nudge in a
# refusal message is a nudge toward exactly what it says.
_SUGGEST_EXACTLY = {"deletion", "credentials", "payment", "authorization_control"}


def suggested_grant_pattern(tool_name: str, args: dict, effect_class: str | None = None) -> str:
    """The permission pattern that would allow this exact call.

    A refusal that only says "no grant allows this" leaves the operator to
    work out the syntax, the file and the right breadth from a policy name.
    This names the line to write, erring narrow: the leading verb words,
    stopping at the first argument-looking one, capped at three — so
    `co email send --to a@b.c` becomes `Bash(co email send *)`, not
    `Bash(co *)`. For a deletion, a credential or a payment it errs narrower
    still and names the command exactly.
    """
    if str(tool_name).lower() not in {"bash", "shell", "run", "run_in_dir", "run_background"}:
        return str(tool_name)
    command = str((args or {}).get("command", "")).strip()
    words = _command_words(command)
    while len(words) > 1 and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]          # VAR=value cmd ...
    if not words:
        return str(tool_name)
    if effect_class in _SUGGEST_EXACTLY:
        return f"Bash({' '.join(words)})"
    verb = []
    for word in words[:3]:
        if verb and (word.startswith(_VALUE_LOOKING) or any(c in word for c in "@=:")):
            break
        verb.append(word)
    return f"Bash({' '.join(verb)} *)" if verb else str(tool_name)


def grant_remedy(tool_name: str, args: dict, effect_class: str | None = None) -> str:
    """How to allow this call next time, in the two places that work."""
    pattern = suggested_grant_pattern(tool_name, args, effect_class)
    if pattern.startswith("Bash("):
        yaml_key = f'"{pattern}"'
    else:
        yaml_key = f'"{pattern}"'
    return (
        f"Nothing has granted this. To allow it — including unattended — write it down once:\n"
        f"  • in .co/host.yaml:\n"
        f"      permissions:\n"
        f"        {yaml_key}:\n"
        f"          allowed: true\n"
        f"          source: config\n"
        f"          reason: why you want this\n"
        f"          expires:\n"
        f"            type: never\n"
        f"  • or in the skill that needs it, in its SKILL.md frontmatter:\n"
        f"      tools:\n"
        f"        - \"{pattern}\"\n"
        f"A grant written in either place runs the call without asking again. "
        f"Narrow the pattern if it is broader than you meant."
    )


def _explicitly_granted(
    agent: "Agent", pending: dict, result: dict
) -> dict | None:
    """An explicit grant is an approval already given. Honour it.

    Before this, a grant the operator wrote by hand was discarded for every
    effect class except an unclassified command: `Bash(curl *)` in your own
    `host.yaml` was refused unattended and asked *every time* with a person
    present, and a skill's declared `tools:` bought nothing at all. Measured
    on 1.8.4: nine hand-written grants, eight ignored.

    What still cannot happen is a *broad* pattern stretching to a stronger
    power than it names. The shipped `Bash(co *)` must not imply `co deploy`
    or `co email send`, which is why template grants keep their old, narrow
    reading and why an explicit wildcard is only honoured for the effect its
    own text classifies to.
    """
    if pending.get("name") != "bash":
        return _explicitly_granted_tool(agent, pending, result)
    permissions = agent.current_session.get("permissions")
    if not isinstance(permissions, dict):
        return None
    explicit = {
        pattern: permission
        for pattern, permission in permissions.items()
        if isinstance(permission, dict) and permission.get("source") in _EXPLICIT_SOURCES
    }
    configured = dict(explicit)
    if result.get("effect_class") == "command":
        # An ordinary command is what the shipped defaults have always
        # covered, so they join in for this class only.
        configured.update({
            pattern: permission
            for pattern, permission in permissions.items()
            if isinstance(permission, dict) and permission.get("source") in _TEMPLATE_SOURCES
        })
    # A read-only segment needs no grant: `co browser ... | head -40` is the
    # granted browser command plus a filter on its output. Every other segment
    # must match a standing grant, so `co browser status && co email send ...`
    # is still an email send nobody authorized (#1481).
    command = _without_heredoc_body(str((pending.get("arguments") or {}).get("command", "")))
    try:
        root = project_root().resolve()
        segments = _extract_subcommands(command)
        needs_grant = [
            (name, full) for name, full in segments
            if _classify_single_command(full, root).get("effect_class") != "read"
        ]
        if _redirect_targets(command):
            needs_grant = list(segments)
        # The shipped `Bash(co *)` is broader than its "safe CLI" description:
        # `co` is a multiplexer, so the wildcard covers email, servers and
        # payments as well as the browser. Keep the compatibility operators
        # relied on — `co status` and `co browser ...` — and nothing else.
        # An operator who wants more names it themselves.
        if configured.get("Bash(co *)", {}).get("source") in _TEMPLATE_SOURCES:
            if not (needs_grant and all(
                full == "co status" or full.startswith("co browser ")
                for _, full in needs_grant
            )):
                configured.pop("Bash(co *)", None)
        for name, full in needs_grant:
            # `segment_permitted`, not the chain checker: the segment text has
            # had its quotes removed by the parser, so re-parsing it can raise
            # on a command that is perfectly valid as written.
            permitted, _, _ = segment_permitted(name, full, configured)
            if not permitted:
                return None
            if not _grant_names_this_effect(full, configured, root):
                return None
    except Exception:
        return None
    return decision(
        "configured_command",
        "allow",
        "operator-configured command allowlist",
        "call",
    )


def _grant_names_this_effect(command: str, configured: dict, root: Path) -> bool:
    """A wildcard may not reach a stronger effect than its own text names.

    `Bash(curl *)` classifies as external network, and so does the command it
    matches, so the operator plainly meant network access. `Bash(git *)` is an
    ordinary command while `git push origin main` is a publication, so the
    wildcard does not carry it — `Bash(git push *)` does. An exact pattern
    always names its own effect and always passes.
    """
    wanted = _classify_single_command(command, root).get("effect_class")
    for pattern, permission in configured.items():
        if not (pattern.startswith("Bash(") and pattern.endswith(")")):
            continue
        if not matches_permission_pattern("bash", {"command": command}, pattern):
            continue
        text = pattern[5:-1]
        if "*" not in text:
            return True          # named exactly, nothing to stretch
        literal = text.split("*", 1)[0].strip()
        if not literal:
            return True          # `Bash(*)` — the operator asked for everything
        if _classify_single_command(literal, root).get("effect_class") == wanted:
            return True
    return False


def _explicitly_granted_tool(
    agent: "Agent", pending: dict, result: dict
) -> dict | None:
    """The same rule for a non-bash tool, whose pattern is its name.

    `send_email` in an operator's host.yaml, or in a skill's `tools:`, is the
    operator saying this agent may send mail. It was being discarded along
    with everything else.
    """
    permissions = agent.current_session.get("permissions")
    if not isinstance(permissions, dict):
        return None
    name = str(pending.get("name", ""))
    permission = permissions.get(name)
    if not isinstance(permission, dict) or not permission.get("allowed"):
        return None
    if permission.get("source") not in _EXPLICIT_SOURCES:
        return None
    return decision(
        "configured_tool",
        "allow",
        f"explicitly granted ({permission.get('source')})",
        "call",
    )


@before_each_tool
def apply_auto_approve_policy(agent: "Agent") -> None:
    """Attach a durable semantic decision before the human approval hook."""
    pending = agent.current_session.get("pending_tool")
    if pending:
        workspace_policy_for_pending(agent, pending)


def record_approval_policy(agent: "Agent", pending: dict) -> None:
    """Attach the decision to the matching trace entry for audit and replay."""
    result = pending.get("approval_policy")
    if not isinstance(result, dict):
        return
    # The executor records the call id as `tool_id` (`id` is the trace
    # sequence number). This compared against `id`, so in a real Agent the
    # decision never reached the trace — the audit record every "UI-safe
    # decision" test asserted on existed only in tests whose pending tool had
    # no id at all. Found by the Rust e2e.
    tool_id = pending.get("id")
    for entry in reversed(agent.current_session.get("trace", [])):
        if entry.get("type") == "tool_call" and (not tool_id or entry.get("tool_id") == tool_id):
            entry["approval_policy"] = dict(result)
            return

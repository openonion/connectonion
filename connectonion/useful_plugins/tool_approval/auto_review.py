"""
Purpose: Decide, without a human, whether one tool call may run — and say why.
LLM-Note:
  Dependencies: imports from [./constants.py, ./bash_parser.py, pathlib] | imported by [tool_approval/approval.py] | tested by [tests/unit/test_auto_review.py]
  Data flow: review(tool_name, tool_args) → (allowed, reason) → approval.check_approval auto-approves and logs the reason, or falls through to the human prompt
  State/Effects: none — pure function, no I/O, no LLM call
  Integration: exposes review(tool_name, tool_args, project_dir=None)
  Errors: never raises; anything it cannot classify returns (False, reason)

Why this exists
---------------
`safe` mode asked a human before every dangerous tool. Correct, and unusable in
the two situations that matter most:

  - Unattended. A scheduled run has no human, so approval was skipped entirely
    (`if not agent.io: return`) — the strictest-looking mode became no gate at
    all, precisely where nobody was watching.
  - A visitor. Whoever holds an invite code was shown "Trust python3 for this
    session" — an administrative grant offered to someone with no way to judge
    it. That produces a rubber stamp or a freeze, never a decision.

So the question changes from *is this tool in a dangerous set* to *what would
this particular call actually do*. Reading is not writing. Writing inside the
workspace is not writing outside it. Nothing that leaves the machine, and
nothing that destroys, is ever automatic.

The bar for automatic is deliberately not "probably fine". It is: undoable by a
later turn, confined to this workspace, and invisible to anyone outside it. A
call that fails any of those goes to a human — which, under the trust model, is
the *owner*, not whoever happens to be connected.
"""

import re
from pathlib import Path

from .bash_parser import extract_commands_from_bash

# Tools that only observe. Everything here is recoverable by definition: reading
# twice is the same as reading once.
READ_ONLY_TOOLS = {
    'read_file', 'read', 'glob', 'grep', 'ls', 'list_files', 'search',
    'todo_read', 'get_state',
}

# Shell commands that only observe. Kept short on purpose — a long list is a long
# list of things to be wrong about, and anything missing merely asks a human.
READ_ONLY_COMMANDS = {
    'ls', 'cat', 'head', 'tail', 'wc', 'grep', 'rg', 'find', 'file', 'stat',
    'pwd', 'whoami', 'hostname', 'uname', 'date', 'echo', 'basename', 'dirname',
    'df', 'du', 'ps', 'env', 'which', 'type', 'sort', 'uniq', 'cut', 'awk', 'sed',
    'diff', 'md5sum', 'sha256sum', 'jq', 'tree', 'realpath',
}

# `git status` reads; `git push` publishes. The verb decides, not the binary.
READ_ONLY_SUBCOMMANDS = {
    'git': {'status', 'log', 'diff', 'show', 'branch', 'remote', 'ls-files',
            'rev-parse', 'describe', 'blame', 'stash'},
}

# Anything with a recipient. Not "risky" — *unrecallable*: once it has left this
# machine no later turn can take it back, so no reviewer should send it alone.
OUTBOUND_TOOLS = {'send_email', 'post', 'send_message', 'publish', 'upload'}
OUTBOUND_COMMANDS = {
    'curl', 'wget', 'ssh', 'scp', 'rsync', 'nc', 'ncat', 'telnet', 'ftp',
    'git-push', 'gh', 'aws', 'gcloud', 'kubectl', 'docker', 'npm', 'pip',
    'lark-cli', 'co',
}

# Destruction is the one mistake a later turn cannot repair.
DESTRUCTIVE_TOOLS = {'delete', 'remove', 'kill_task'}
DESTRUCTIVE_COMMANDS = {
    'rm', 'rmdir', 'unlink', 'shred', 'truncate', 'dd', 'mkfs', 'fdisk',
    'chmod', 'chown', 'kill', 'pkill', 'killall', 'shutdown', 'reboot',
}
DESTRUCTIVE_SUBCOMMANDS = {
    'git': {'reset', 'clean', 'push', 'rebase', 'filter-branch'},
}

WRITE_TOOLS = {'write', 'edit', 'multi_edit'}

# The files that decide what the agent may do, and who may ask it. An agent may
# write its own work; it may not rewrite its own permissions. Inside the workspace
# by path, outside it by consequence — a turn that can edit trust.md can grant
# itself anything on the next turn, which makes every other rule here advisory.
PROTECTED_PREFIXES = (
    '.co/keys', '.co/address.json', '.co/admins.txt',
    '.co/trust.md', '.co/host.yaml', '.co/schedule.yaml',
)


def _inside_workspace(raw_path: str, project_dir: Path) -> bool:
    """Whether a path stays inside the directory the agent is responsible for.

    Resolved rather than string-matched: `work/../../etc/passwd` is not inside
    the workspace no matter how it is spelled.
    """
    if raw_path.startswith('~'):
        return False
    try:
        target = (project_dir / raw_path).resolve()
        return target == project_dir or project_dir in target.parents
    except (OSError, ValueError):
        return False


def _subcommands(binary: str, raw: str) -> list[str]:
    """Every subcommand this binary is invoked with in the original line.

    extract_commands_from_bash returns binaries only — `git status` arrives as
    `git` — so the word that decides whether it reads or publishes has to come
    from the raw command. All of them, because `git status && git push` must not
    pass on the strength of its first half.
    """
    return re.findall(rf'\b{re.escape(binary)}\s+(-{{0,2}}[a-z][a-z-]*)', raw)


def _classify_command(cmd: str, raw: str = '') -> tuple[str, str]:
    """One shell command → ('read' | 'outbound' | 'destructive' | 'unknown', why)."""
    parts = cmd.strip().split()
    if not parts:
        return 'unknown', 'empty command'
    binary = Path(parts[0]).name
    sub = parts[1] if len(parts) > 1 else ''

    if binary in DESTRUCTIVE_COMMANDS:
        return 'destructive', f'`{binary}` destroys or changes what it touches'
    subs = _subcommands(binary, raw or cmd)
    if binary in DESTRUCTIVE_SUBCOMMANDS:
        bad = [x for x in subs if x in DESTRUCTIVE_SUBCOMMANDS[binary]]
        if bad:
            return 'destructive', f'`{binary} {bad[0]}` rewrites state'
    if binary in OUTBOUND_COMMANDS:
        return 'outbound', f'`{binary}` reaches outside this machine'
    if binary in READ_ONLY_SUBCOMMANDS:
        if subs and all(x in READ_ONLY_SUBCOMMANDS[binary] for x in subs):
            return 'read', f'`{binary} {subs[0]}` only reads'
        return 'unknown', f'`{binary} {subs[0] if subs else sub}` is not a known read'
    if binary in READ_ONLY_COMMANDS:
        # `sed -i` and `awk > file` edit in place; the flag decides.
        if binary in ('sed', 'awk') and '-i' in parts:
            return 'destructive', f'`{binary} -i` edits files in place'
        return 'read', f'`{binary}` only reads'
    return 'unknown', f'`{binary}` is not a command this reviewer knows'


def review(tool_name: str, tool_args: dict, project_dir: Path = None) -> tuple[bool, str]:
    """May this call run without asking anyone? Always answers with a reason.

    The reason is not decoration: an automatic decision nobody can inspect later
    is indistinguishable from no decision, and #269 asks for a record of why.
    """
    project_dir = Path(project_dir or Path.cwd()).resolve()
    name = (tool_name or '').lower()

    if name in READ_ONLY_TOOLS:
        return True, f'{name} only reads'

    if name in OUTBOUND_TOOLS:
        return False, f'{name} sends something that cannot be recalled'

    if name in DESTRUCTIVE_TOOLS:
        return False, f'{name} destroys something no later turn can restore'

    if name in WRITE_TOOLS:
        raw = tool_args.get('file_path') or tool_args.get('path') or ''
        if not raw:
            return False, 'no path given, so the blast radius is unknown'
        if any(str(raw).startswith(p) or f'/{p}' in str(raw) for p in PROTECTED_PREFIXES):
            return False, 'writes the agent\'s own identity or admin list'
        if _inside_workspace(str(raw), project_dir):
            return True, f'writes {raw}, inside the workspace'
        return False, f'writes {raw}, outside the workspace'

    if name in ('bash', 'shell', 'run', 'run_in_dir', 'run_background'):
        command = tool_args.get('command') or ''
        if not command.strip():
            return False, 'empty command'
        # Substitution hides the real command from every check below it.
        if '$(' in command or '`' in command or 'eval ' in command:
            return False, 'command substitution hides what would actually run'
        parts = extract_commands_from_bash(command)
        if not parts:
            return False, 'could not be parsed into commands'
        reasons = []
        for cmd in parts:
            kind, why = _classify_command(cmd, command)
            if kind != 'read':
                return False, why
            reasons.append(why)
        return True, '; '.join(reasons[:3])

    return False, f'{name} is an unknown tool, and unknown is not safe'

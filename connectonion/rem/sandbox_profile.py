"""A macOS seatbelt profile that keeps a REM-launched Codex from reading the owner's credentials.

`codex exec -s workspace-write` limits writes but reads the whole disk, and REM builds some
prompts from untrusted mail. With network on, a prompt-injected run could read keys.env or
~/.ssh and send it out. This profile denies those reads (and writes) at the kernel for the
wrapped process and every descendant: Codex itself, its shell tools and its MCP servers.

Codex's own seatbelt cannot start inside ours (sandbox_apply: Operation not permitted, exit 71;
see docs/testing/rem-sandbox-profile-results.md), so a wrapped Codex runs with
`-s danger-full-access` and passes `writable=` here, which moves the workspace write limit
into this profile. On Linux there is no sandbox-exec: argv comes back unchanged with
protected=False, which callers must surface (a doctor line), never swallow.

    argv, protected = wrap([codex, 'exec', '-s', 'danger-full-access', ...],
                           allow_co=[task_dir], deny=[other_worktree], writable=[root])
"""
import os
import sys
import tempfile
from pathlib import Path

SANDBOX_EXEC = '/usr/bin/sandbox-exec'

# Directories under the owner's home that hold keys, tokens or other agents' sessions.
CREDENTIAL_DIRS = ('.co', '.ssh', '.config/gh', '.aws', '.gnupg', 'Library/Keychains', '.docker',
                   '.kube', '.config/gcloud', '.azure', '.claude')
CREDENTIAL_FILES = ('.netrc', '.git-credentials', '.npmrc', '.pypirc')
# Keychain items come over mach, not from files. com.apple.securityd (the data-protection
# keychain) can be denied. com.apple.SecurityServer cannot: Codex's TLS trust check goes through
# it and every model request failed with it denied. The login keychain's cheapest door is the
# Apple-signed `security` CLI that tools like gh are trusted through, so it is unreadable and
# unrunnable here (unreadable also stops a copy, which would keep Apple's signature).
KEYCHAIN_RULES = ('(deny mach-lookup (global-name "com.apple.securityd"))',
                  '(deny file-read* process-exec (literal "/usr/bin/security"))')
# What Codex writes in ~/.codex during an exec (found by running it under this profile). Its
# config, rules, hooks, skills and binaries stay unwritable, so a run cannot plant code that
# the owner's next unsandboxed Codex would execute.
CODEX_STATE_DIRS = ('sessions', 'archived_sessions', 'log', 'shell_snapshots', 'cache', '.tmp', 'tmp',
                    'sqlite')
CODEX_STATE_FILES = ('auth.json', 'models_cache.json', 'history.jsonl', 'session_index.jsonl',
                     'session_index.jsonl.lock', '.codex-global-state.json', 'version.json',
                     'installation_id', '.sqlite-maintenance.lock')
CODEX_STATE_REGEX = r'/[a-z_]+_[0-9]+\.sqlite(-shm|-wal|-journal)?$'  # state_5.sqlite, logs_2.sqlite-wal


def _quote(path) -> str:
    text = os.path.realpath(os.fspath(path))
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ValueError(f'refusing a path with control characters: {text!r}')
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _rule(action, kind, paths) -> list[str]:
    return [f'({action} ({kind} {_quote(path)}))' for path in paths]


def _codex_state(home: Path) -> list[str]:
    codex = home / '.codex'
    # require-all keeps the home path out of the regex, so it needs no regex escaping.
    # The deny matters when ~/.codex sits under an allowed temp root (a test's fake home).
    return [*_rule('deny file-write*', 'subpath', [codex]),
            *_rule('allow file-write*', 'subpath', [codex / name for name in CODEX_STATE_DIRS]),
            *_rule('allow file-write*', 'literal', [codex / name for name in CODEX_STATE_FILES]),
            f'(allow file-write* (require-all (subpath {_quote(codex)}) (regex #"{CODEX_STATE_REGEX}")))']


def profile(home=None, *, allow_co=(), deny=(), writable=None) -> str:
    """The SBPL text. Later rules win, so the allow list follows the denies it carves from."""
    home = Path(os.path.realpath(home or Path.home()))
    co = Path(os.path.realpath(home / '.co'))
    for path in allow_co:
        if not Path(os.path.realpath(path)).is_relative_to(co) or Path(os.path.realpath(path)) == co:
            raise ValueError(f'allow_co entries must be inside {co}, not {path}')
    lines = ['(version 1)', '(allow default)']
    if writable is not None:
        lines.append('(deny file-write*)')
        roots = [*writable, '/private/tmp', '/private/var/folders', tempfile.gettempdir(), '/dev']
        lines += _rule('allow file-write*', 'subpath', roots) + _codex_state(home)
        # Parity with Codex's workspace-write, which keeps these read-only inside a writable root.
        lines += _rule('deny file-write*', 'subpath',
                       [Path(root) / name for root in writable for name in ('.git', '.codex')])
    lines += _rule('deny file-read* file-write*', 'subpath',
                   [home / name for name in CREDENTIAL_DIRS] + list(deny))
    lines += _rule('deny file-read* file-write*', 'literal', [home / name for name in CREDENTIAL_FILES])
    lines += _rule('allow file-read* file-write*', 'subpath', allow_co)
    return '\n'.join([*lines, *KEYCHAIN_RULES]) + '\n'


def prefix(**options) -> tuple[list[str], bool]:
    """argv to put before a command, and whether it is protected (False off macOS)."""
    if sys.platform != 'darwin':
        return [], False
    return [SANDBOX_EXEC, '-p', profile(**options)], True


def wrap(argv, **options) -> tuple[list[str], bool]:
    head, protected = prefix(**options)
    return [*head, *argv], protected

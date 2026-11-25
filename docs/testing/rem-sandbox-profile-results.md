# REM sandbox profile: results

2026-11-09 (Sydney), branch `sprint11/sandbox-profile` on 8a74599e5. macOS Darwin 25.6.0, codex-cli 0.162.0.
How to use it: `docs/rem-sandbox.md`.

## Nesting: Codex's seatbelt cannot start inside ours

| command | exit | result |
|---|---|---|
| `sandbox-exec -p '(version 1)(allow default)' codex sandbox -- /bin/echo inner` | 71 | `sandbox-exec: sandbox_apply: Operation not permitted` (an empty outer profile is enough to fail) |
| `sandbox-exec -p <profile> codex sandbox -- cat <canary>` | 71 | same |
| `sandbox-exec -p <profile> codex exec -s workspace-write … "run probe.sh"` | 0 | Codex starts and reaches the model. Its shell call fails with `sandbox_apply: Operation not permitted`, and the probe never ran |

Codex's native permission profiles also work: `codex sandbox -c 'permissions.rem.filesystem={":root"="read","<dir>"="none"}' -P rem -- cat <canary>` gave exit 1, Operation not permitted. We rejected them for two reasons. Only Codex's tool subprocesses run inside that sandbox, while Codex's in-process tools and its MCP servers do not. And the schema is new and version-bound.

**Decision:** wrap Codex in our profile with `-s danger-full-access` and `writable=[root, …]`. The outer profile is then the only sandbox. It confines every descendant, and it carries the workspace write limit.

Real run with that decision (`sandbox-exec -p "$(profile(writable=[ws], deny=[otherwt]))" codex exec -s danger-full-access --ephemeral --json … < /dev/null`): exit 0. Codex ran `probe.sh` and reported:

```
other-worktree-read=1    workspace-write=0    codex-home-plant=1    home-plant=1
keys-env-readable=1      codex-auth-readable=0    security-cli=126
```

Neither planted file exists afterwards. A `/usr/bin/log stream` capture during a second exec (exit 0, model replied `pong`) logged denied writes only to `~/.codex/plugins/cache/*` (plugin installs, which are code, so they are denied on purpose), `~/.codex/mcp-oauth-locks/file-store.lock`, `~/.zcompdump-*` and `~/.cache/oh-my-zsh`. It also logged denied metadata reads of `~/Library/Keychains`. None of these stopped the run.

## Keychain mach services

| profile adds | real `codex exec` | |
|---|---|---|
| deny `com.apple.SecurityServer` + `com.apple.securityd` | exit 1 | `failed to refresh available models: Connection failed`, so TLS trust broke |
| deny `com.apple.SecurityServer` only | exit 1 | same |
| deny `com.apple.securityd` only | exit 0 | `pong` |

So the profile denies `com.apple.securityd`, plus `(deny file-read* process-exec (literal "/usr/bin/security"))`. Under the profile, `security find-generic-password -s wren-no-such-item` exits 71 (it exits 44, not found, when unwrapped), and `cp /usr/bin/security` exits 1.

## Real-home check (zero-byte checks only, nothing read or printed)

Profile built for the real home: `P=$(python3 -c '…profile()')`.

| command | unwrapped | `sandbox-exec -p "$P"` |
|---|---|---|
| `/bin/test -r ~/.ssh` | 0 | **1** |
| `/bin/test -r ~/.co/keys.env` | 0 | **1** |
| `/bin/test -r ~/.config/gh` | 0 | **1** |
| `/bin/test -r ~/.codex/auth.json` | 0 | 0 |
| `/bin/dd if=~/.co/keys.env of=/dev/null count=0` | 0 | **1** |
| `/bin/dd if=~/.config/gh/hosts.yml of=/dev/null count=0` | 0 | **1** |
| `/bin/dd if=~/.codex/auth.json of=/dev/null count=0` | 0 | 0 |
| `/bin/ls ~/.ssh` | — | **1** |

`head -c0` isn't usable as a zero-byte check on macOS: BSD head rejects it (`illegal byte count -- 0`, exit 1), even unwrapped. `dd count=0` opens the file and reads nothing.

## Tests

`tests/unit/test_rem_sandbox_profile.py`, 11 tests. They were red at first: the module was missing, so collection failed. `test_without_the_profile_every_canary_is_readable` is the standing red half: all 15 canaries in the fake home are readable without the profile. The macOS-only tests skip elsewhere with a printed reason.

Unit suite, run from /private/tmp with `HOME=$(mktemp -d) OPENONION_API_KEY=test-key env -u FORCE_COLOR uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 6 --dist=worksteal`:

```
18777 passed, 19 skipped, 2944 warnings in 147.39s (0:02:27)
```

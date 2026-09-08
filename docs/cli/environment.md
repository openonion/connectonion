# Environment selection (1.8.4 implementation)

All ConnectOnion-managed dotenv settings default to `~/.co/keys.env`, regardless
of the working directory. An inherited `AGENT_CONFIG_PATH` selects a different
global directory and its `keys.env`. A dotenv file cannot redirect that path.
`co init` initializes the global configuration and identity. It rejects
`--env-file` with exit 2; omit that selector for global initialization.

Run `co` for a short command guide and configuration examples, or `co --help`
for the complete command list. `co init ./` initializes a project explicitly.

Use a project file explicitly, with the option **before** the command:

```sh
co gmail inbox
co --env-file /path/to/project/.env gmail inbox
co --env-file /path/to/project/.env auth google
co --env-file /path/to/project/.env auth microsoft
co --env-file /path/to/project/.env status
```

The selected file replaces the global env file; there is no per-key fallback.
Missing, unreadable or malformed explicitly selected files fail with exit 2
before the command runs — except `co env`, which runs on any selected file so
it can name the missing file or the broken line. Relative paths are relative
to the invocation's working directory. Absolute paths give the same selection
from any directory.

## Seeing and editing the selected file

`co env` shows what the selected file holds, which of its values the shell
overrides, and which provider record is ignored because the process supplies
another. `co env set KEY VALUE` and `co env unset KEY` edit it in place, under
the same lock provider refresh uses. Provider account fields are refused by
`set` and removed as a whole record by `unset`, so a record can never be edited
into describing two accounts. See [`co env`](env.md).

```sh
co env                                  # global ~/.co/keys.env
co --env-file /path/to/project/.env env # the project file, same selector rule
co env set OPENAI_API_KEY sk-...
```

Inherited process variables take precedence over file settings. For Google and
Microsoft, supplying any access-token, refresh-token, expiry, scope or email
variable selects the **whole process record**. Missing fields remain missing;
they are never borrowed from another source. CLI startup waits for file selection before loading settings, so a malformed
global file cannot block an explicitly selected valid file. Ordinary SDK imports
continue to load global settings eagerly. A client binds its record when
constructed. Changing the environment later requires constructing another client.

## Auth, refresh and identity

Google's Gmail, Drive, Calendar and YouTube clients share the same Google record.
Outlook and Microsoft Calendar share the Microsoft record. Existing names remain:
`<PROVIDER>_ACCESS_TOKEN`, `REFRESH_TOKEN`, `TOKEN_EXPIRES_AT`, `SCOPES`, `EMAIL`.
No second global store is created.

Consent saves a complete record to the selected file. Refresh preserves email,
scopes and refresh token when the provider omits them. A refresh of inherited
process credentials stays in memory; it cannot overwrite a file containing
another account. Use file selection for durable refreshes.

File refresh holds a bounded interprocess lock across the network call and
atomic save. A waiting process reuses a newer valid token for the same verified
email or unchanged refresh grant. An account change fails before writing. If a
legacy record has neither matching email nor matching refresh token, retry with
a fresh client; the resolver cannot prove it is still the same account. Writes
preserve unrelated settings, and use owner-only file permissions on Unix.

No scopes are invented. Missing scope metadata allows the actual provider
operation to establish permission; it is reported as incomplete metadata in
diagnostics. A successful refresh may recover the provider's actual scope
metadata. The API remains authoritative, and a denied operation exits non-zero.

The default signing identity is global too. Explicit `--env-file` uses an identity
in the selected file's adjacent `.co`, when present, otherwise the global
identity. Explicit SDK `project_identity(co_dir=...)` remains supported. Existing
project keys and files are preserved. `co create` and explicit project
initialization remain available.

## Migration from 1.8.3

PRs #1381/#1382 implemented canonical **project-first** loading. The 1.8.4 change
intentionally replaces that policy. `--env-file` is the single CLI selector.
No `co env` command existed before 1.8.4; the one added in 1.8.4 shows and
edits whichever file the selector chose, and never selects a file itself.

Applications importing `connectonion` now load only global settings. To keep an
application's project-specific environment, explicitly load its file in your own
application before importing ConnectOnion, or supply process variables through
your launcher. Those values are then caller-owned process configuration.

For CLI automation, change `co gmail ...` to `co --env-file /absolute/.env gmail
...` wherever the project account is intentional. Keep all fields for an account
in that file. Do not copy scopes or an email from a different record to make an
incomplete record appear connected. Old project files are not rewritten or
deleted automatically.

Deployment also uses the selected env. The global default excludes personal
Google/Microsoft credentials and operator identity fields from the exported
payload; explicit `--env-file` chooses the application file to export. The whole
OS environment is never exported. A `host.yaml` env path no longer implicitly
selects a project file; update the deployment command to select it explicitly.

## Recovery

| Failure | Exit | Next command |
| --- | --- | --- |
| Selected file missing, unreadable or malformed | 2 | `co env` with the same selector: it names the broken line, or `co env set` creates a missing file |
| Provider not configured or explicitly revoked | 1 | `co auth google` or `co auth microsoft`, with the same selector |
| OpenOnion broker key missing/rejected | 1 | `co auth` |
| Network/provider failure, invalid refresh response, concurrent account change | 1 | `co status`, then retry the intended read |
| Actual Google/Graph permission denial | 1 | The provider auth command printed by the failing operation |

`co env`, `co status`, `co doctor` and `co keys` inspect the same selected
sources. Default diagnostics show source/state, never token values. Keep
`--reveal` out of shared logs. A provider command that finds no token, or an
incomplete record, names the source it read and points at `co env` before its
`Next: co auth …` line. This document describes the implementation branch, not
a published 1.8.4.

The environment overview hides all values by default; `co env --json` exposes the same redacted sources for scripts. `co env get` follows whole-record provider selection rather than filling missing account fields from another source.

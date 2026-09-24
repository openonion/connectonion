---
name: co-tiktok
description: Prepare a local TikTok post plan and check, with saved browser evidence, whether a co browser tab is logged in to TikTok Studio. TikTok upload and publish are not implemented; YouTube lives in co-google.
---

# TikTok

**Always read the output, not just the exit code.** A direct `co browser`
primitive can fail with exit 0. Never use `&&` alone to decide whether to continue.

Required tool: the shell for `co` commands. This skill grants no tool permissions.
YouTube is not here: it uses the official API through the Google login, see
`co youtube --help` and the co-google skill.

| Intent | Command | Boundary |
|---|---|---|
| Prepare a TikTok post | `co tiktok post clip.mp4 --caption Demo --account @creator` | Local plan; no TikTok draft or upload |
| Check TikTok browser state | `co tiktok inspect --tab creator-tiktok` | Login or unknown surface is an error, never “ready” |

Both leaves support `--json`: stdout is one JSON object with `ok`, `mode` on
success, `next_command`, and `next_tip`. Otherwise the final stdout line is one
literal next command, including under `| cat`. Usage errors (exit 2) print the
cause and a recovery tip on stderr.

## The local plan

`post` previews by default; `--dry-run` makes that explicit. The plan carries
`plan.confirmation`, a SHA-256 digest of the exact file bytes, the caption and
the intended @handle. The @handle is what the user said, not proof of login.

`--confirm <plan.confirmation>` checks the digest, then **refuses submission**
with exit 1 and `code: submit_unavailable`. As of 2026-09-05 the real Studio URL
redirected to login. The upload form, account identity, caption editor, privacy
choices, upload-complete state and final publish control have not been observed,
so no submission adapter is shipped. Local plan acceptance is not publication
approval. The post preview points to `co browser tab ls` so the agent can find
its owned tab without guessing a name.

## Browser evidence workflow

Use the `co-browser` ownership rules: set `CO_WHO` on every call, inspect the tab
board, use one named tab per task, and never move someone else's tab. Browser
inspection operates on an existing tab and never navigates, clicks, types,
uploads, or submits. Open only the intended URL with generic primitives:

```bash
CO_WHO=creator co browser tab ls
CO_WHO=creator co browser tab open creator-tiktok --for "TikTok readiness" --needs 10m
CO_WHO=creator co browser -t creator-tiktok go_to https://www.tiktok.com/tiktokstudio/upload
CO_WHO=creator co tiktok inspect --tab creator-tiktok --json
```

Let the user log in manually if needed; never automate credentials. Login does
not authorize an upload. After this task, close only the task's own tab with the
generic tab close command; leave the browser and other tabs running.

`inspect` performs viewport screenshot → saved context → extract → exact verify.
It returns evidence paths for `.tmp/*_before.png` and the timestamped
`~/.co/browser_context/*/` folder. Keep raw captures local: an authenticated
page may contain private sidebar/account data. Do not attach them to PRs.

Bundled scripts (resolve the installed package directory to an absolute path
before a live run):

- `co-tiktok/scripts/extract-tiktok.js`
- `co-tiktok/scripts/verify-tiktok.js`

**Trust the scripts during a live run.** Do not read, `ls`, or `glob` their files,
run `node --check`, or run local tests during that run. On two failures, save
context and stop; fix scripts outside the live run. On a browser/profile/navigation
failure, stop that live attempt; do not substitute a different browser runner.

Observed selectors, 2026-09-05:

| Surface | Selectors and identity |
|---|---|
| TikTok login | `[data-e2e="login-title"]` on `/login`; exact heading text/hash verifies the login boundary |

Generated CSS classes, temporary `data-browser-agent-id` values, cookies, script
globals and localStorage are never selectors or data sources. Upload, editor and
submit selectors are unverified and deliberately absent.

Extraction returns `{ok, reason, items, selected_item, submit_supported}`. The
selected login heading carries its exact text and `text_hash`. Verification
takes `expected_item`, rescans and checks the same text/hash; the inspection as a
whole still returns `ok: false, reason: login_required`. Any other page is
`unverified_surface` — a visible file input is not readiness.

## Results and recovery

| Exit | Meaning | Next command |
|---|---|---|
| 0 | Local preview | `co browser tab ls` |
| 1 | Invalid file, caption or handle; changed confirmation; unsupported submit | Printed recovery, usually `co browser tab ls` |
| 1 | Browser ownership/evidence failure | `co browser tab ls` |
| 1 | TikTok login or unknown upload surface | Printed `co browser -t <owned-tab> get_current_url`; the user logs in, then inspect again |
| 2 | Missing argument, invalid option, unknown command | `co tiktok --help` |

Finish with the heading text, its hash, status and the exact evidence paths.
Say “local preview” or “submission unavailable” as returned. Do not claim
readiness from a login-page screenshot or live verification from mocked tests.

---
name: co-creator
description: Read YouTube video metadata, prepare and explicitly confirm YouTube uploads or metadata edits, and prepare local TikTok post plans with browser evidence. TikTok upload and publish are not implemented.
---

# YouTube and TikTok

**Always read the output, not just the exit code.** The Google login prerequisite
can print an authentication failure and exit 0. A direct `co browser` primitive
can also fail with exit 0. Never use `&&` alone to decide whether to continue.

Required tool: the shell for `co` commands. This skill grants no tool permissions.

| Intent | Command | Boundary |
|---|---|---|
| Recent YouTube uploads | `co youtube list` | Reads uploads playlist; bare `co youtube` does the same |
| A YouTube channel | `co youtube channel @YouTube` | Default target is the token's channel |
| One YouTube video | `co youtube video 1` | Last listing number, full ID, or watch/Shorts/youtu.be URL; no download |
| Prepare a YouTube upload | `co youtube put clip.mp4 --title Demo --channel UCxxxxxxxxxxxxxxxxxxxxxx` | Local preview; no upload |
| Prepare a title edit | `co youtube update 1 --title Demo` | Reads current metadata; no update without confirmation |
| Prepare a TikTok post | `co tiktok post clip.mp4 --caption Demo --account @creator` | Local plan; no TikTok draft or upload |
| Check TikTok browser state | `co tiktok inspect --tab creator-tiktok` | Login or unknown surface is an error, never “ready” |

All leaves support `--json`: stdout is one JSON object with `ok`, `mode` on
success, `next_command`, and `next_tip`. Usage errors (exit 2) use plain text,
including when `--json` was requested. Otherwise the final line is one literal
next command, including under `| cat`. Piped YouTube lists include row number,
untruncated ID, title, visibility and views as tab-separated fields. Missing
counts are null in JSON and “not returned” in text; zero remains zero.

## API input and confirmation

Connect Google with `co auth google`, then run `co youtube` like
`co gmail`. The same consent flow requests Gmail, Calendar, Drive and YouTube.
Existing users rerun that command once to approve the new permission. Login can
succeed with a partial grant and print a missing-YouTube warning; the actual
saved scopes determine which operations can run. Normal commands use the saved
Google login and refresh access tokens through the existing OAuth broker.
No YouTube webpage is used for operations.

Use the CLI to authenticate; never inspect credential files, dump GOOGLE_*
variables or print tokens. If the backend lacks YouTube authorization support,
report the printed error. Production API enablement and app approval are
operator prerequisites. A missing, expired or insufficient grant prints the
same `co auth google` recovery command. Read-only grants cannot be
used for a confirmed upload or edit.

Upload and update commands preview by default; `--dry-run` makes that explicit.
Preview output carries `plan.confirmation`, a SHA-256 digest of the exact file
bytes, account/channel, action and metadata (plus the current video ETag for an
update). Upload defaults to private and disables subscriber notifications.
Unverified API projects may force private visibility. The local preview cannot
report remaining quota, classify a Short, validate the codec, or prove processing.

Only after the user has approved that concrete plan, rerun the same command and
arguments with `--confirm <the exact plan.confirmation>`. The preview prints
that complete command with POSIX shell quoting; its presence does not grant
permission to run it. A confirmed success points to the returned video ID.
`--dry-run` and `--confirm` together are rejected. The API-selected channel must
match the plan. A changed file or metadata invalidates confirmation. Upload
uses a private temporary copy of the confirmed bytes; enough local disk for
that copy is required. Update preserves other snippet fields and excludes the
status part; its If-Match header rejects concurrent edits.

Every confirmed write consumes a local receipt before the first request. No
automatic write retries, receipt-reset command, delete, comment, schedule, or
media-download operation exists. If a request fails or the result is ambiguous,
inspect the channel/video and report uncertainty. Never remove receipts to make
the same plan execute again. Upload acceptance is distinct from processing or
publication; report the returned visibility, not the requested one.

TikTok `--confirm` checks the plan digest, then **refuses submission** with exit
1. As of 2026-09-05, the real Studio URL redirected to login. The upload form,
account identity, caption editor, privacy choices, upload-complete state, and
final publish control have not been observed. No submission adapter is shipped.
Local plan acceptance is not publication approval. The post preview points to
`co browser tab ls` so the agent can find its owned tab without guessing a name.

## TikTok browser evidence workflow

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

TikTok's target is `https://www.tiktok.com/tiktokstudio/upload`. Let the user
log in manually if needed; never automate credentials. Login does not authorize
an upload. After this task, close only the task's own tab with the generic tab
close command; leave the browser and other tabs running.

`inspect` performs viewport screenshot → saved context → extract → exact verify.
It returns evidence paths for `.tmp/*_before.png` and the timestamped
`~/.co/browser_context/*/` folder. Those contexts contain `page.html`,
`styles.css`, and `elements.json`; keep raw captures local, since an authenticated
page may contain private sidebar/account data. Do not attach raw captures to PRs.

Bundled scripts (resolve the installed package directory to an absolute path
before a live run):

- `co-creator/scripts/extract-tiktok.js`
- `co-creator/scripts/verify-tiktok.js`

**Trust the scripts during a live run.** Do not read, `ls`, or `glob` their files,
run `node --check`, or run local tests during that run. Scripts are trusted by
path. On two failures, save context and stop; fix scripts outside the live run.
On a browser/profile/navigation failure, stop that live attempt immediately;
do not substitute a different browser runner or inspect browser core source.

Observed selectors, 2026-09-05:

| Surface | Selectors and identity |
|---|---|
| TikTok login | `[data-e2e="login-title"]` on `/login`; exact heading text/hash verifies the login boundary |

The observed TikTok login surface is in the main frame. No open-shadow-root traversal or
frame selector is claimed. If the UI moves into a frame/shadow surface, save and
inspect context outside the live run before adapting a scanner. Generated CSS
classes, temporary `data-browser-agent-id` values, cookies, script globals, and
localStorage are never selectors/data sources. TikTok upload/editor/submit
selectors are unverified and deliberately absent.

TikTok extraction returns `{ok, reason, items, selected_item, submit_supported}`.
The selected login heading includes its exact title/text and `text_hash`.
Verification accepts `expected_item`, rescans and checks the same text/hash;
the overall inspection still returns `ok: false, reason: login_required`.

No wait loop or scrolling is needed. Never spend a turn on a bare wait. If a
future scan needs scrolling, batch scroll + extract and keep a fixed item budget;
never reuse action indexes after DOM changes. This slice has no action indexes,
editors, rich text, uploads, intermediate Next buttons, or final-submit scripts.
A later write adapter must verify the account, file, caption, settings and hash
before each step, capture before/after evidence, and click final publish once.

## Results and recovery

| Exit | Meaning | Next command |
|---|---|---|
| 0 | Creator read, preview or confirmed write succeeded | Printed command, e.g. `co youtube video 1` |
| 0, error text | `co auth google` has no OpenOnion login | `co auth` |
| 0, partial-grant warning | Google connected without full YouTube permission | `co auth google` |
| 1 | Missing/expired token, scope, provider failure, stale number, wrong account, changed confirmation, or unsupported TikTok submit | `co auth google` for authentication, otherwise the printed recovery |
| 1 | Browser ownership/evidence failure | `co browser tab ls` |
| 1 | TikTok login or unknown upload surface | Printed `co browser -t <owned-tab> get_current_url`; user login and a new workflow discovery pass are required |
| 2 | Missing argument, invalid option/range, unknown command | `co youtube --help` / `co tiktok --help` as printed on stdout, after the cause |

YouTube numbers refer to the immediately preceding API listing. The only listing
cache is an atomic, user-only number-to-ID map at `~/.co/youtube_last_list.json`.
Empty lists preserve it. A missing/corrupt number is never resolved by fetching
a new list. Use a full video ID when switching Google accounts; updates always check the
actual owner. TikTok inspection never overwrites these numbers.

Finish with each item's identity/title, text hash where applicable, status,
whether it was API data or visible DOM, and exact evidence paths. Say “local
preview,” “upload accepted, processing not verified,” or “submission unavailable”
as returned. Do not claim API live verification from mocked tests or readiness
from a login-page screenshot. Full TikTok publish acceptance remains unimplemented.

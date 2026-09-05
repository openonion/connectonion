# co youtube

Use the official YouTube Data API with your saved Google login, like `co gmail`.
List recent uploads, read channels/videos, and preview uploads or metadata edits.
Writes require the exact digest of the current preview.

```bash
co auth google
co youtube
co youtube --help
co youtube channel @YouTube --json
co youtube list @YouTube -n 20
co youtube video 1 --json
co youtube put clip.mp4 --title "Demo #Shorts" --channel UCxxxxxxxxxxxxxxxxxxxxxx --dry-run --json
co youtube update 1 --title "A clearer title" --dry-run --json
```

Connect once using `co auth google`. This extends the normal Google
OAuth flow with YouTube permission; subsequent commands use the saved login
and refresh tokens through the same backend as Gmail. Tokens are never supplied
as command arguments or pasted for each command. YouTube operations call the
API directly.

This requires the matching local-credential oo-api broker. Default Google login
requests YouTube alongside Gmail, Calendar and Drive; use `--scopes` to restrict
the request. Actual granted scopes are stored locally, not in a database column.
If permission is denied, expired or missing, reconnect using the
printed command. The CLI accepts read-only grants for reads but checks upload
and management permission before a confirmed write.

The operator must enable YouTube Data API for the existing Google OAuth project
and satisfy Google's app verification requirements. Authorization uses Google's
normal consent page; it does not automate a YouTube webpage. Local acceptance
in this PR uses synthetic credentials and mocked HTTP only.

## Read results

Bare `co youtube` lists the authorized channel's recent uploads.
`list` also accepts a channel ID, @handle or channel URL. It traverses the
uploads playlist, preserves order, batches metadata reads, and caps requests at
200 items and ten playlist pages. It does not spend search quota.

`video` reads metadata and counts; it does not download video or audio. It
accepts an 11-character ID, watch/Shorts/youtu.be URL, or number from the last
API listing. That number resolves only through
`~/.co/youtube_last_list.json`, an atomic file containing only the number-to-ID
map with mode 0600. Empty lists preserve the previous mapping. A missing or
corrupt number fails without fetching a replacement list. Prefer a full video
ID after changing grants; an update checks the actual owner again.

TTY output uses a table. Piped lists use tab-separated row number, full ID,
title, visibility and views. Every execution ends with one literal next
command. `--json` emits one object, including `ok` and `next_command`. Counts are
integers or null, so a missing value cannot become a fabricated zero. Missing
videos are “not returned,” not assumed deleted/private. Subscriber counts are
the possibly rounded API value.

## Confirmed writes

An upload preview is offline: it checks a regular nonempty video-named file,
hashes its bytes, and includes the intended channel, title, description,
category, privacy and notification setting. File-extension validation is not
codec/media validation. `--privacy` defaults to `private`; subscriber
notifications are disabled. No file is uploaded while making the plan.

An update preview reads the selected video and verifies that the token's
channel owns it. The preview includes the old snippet, proposed snippet and
ETag. Only title and description can be changed; omitted snippet fields are
preserved and the status part is never sent.

After the user reviews and approves the concrete plan, rerun its identical
command with `--confirm <plan.confirmation>`. There
is no broad `--yes` switch. Changed file bytes, metadata, channel or ETag invalidate
the digest. Confirmed upload creates a temporary private snapshot of the exact
bytes and sends one resumable request with chunk progress on stderr. It needs
disk space for that copy. Confirmed update sends If-Match to prevent overwriting
concurrent changes.

Before a write, an exclusive local receipt at
`~/.co/youtube_operations/<digest>.json` consumes the plan. Only its digest and
attempted state are retained, never content or tokens. A crash, timeout or
ambiguous response does not release that receipt. Inspect the account before a
new action; there is intentionally no automatic retry or receipt-reset command.
The server accepting an upload does not prove processing or public visibility.
Report the returned visibility and “processing not verified.”

The old #261 estimate of 1,600 quota units per upload is obsolete. The current
official page documents an upload-specific default bucket of 100 calls/day;
metadata update costs 50 units. Local preview cannot inspect the project's
remaining quota. Uploads from unverified projects may be restricted to private.
See [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert),
[videos.update](https://developers.google.com/youtube/v3/docs/videos/update), and
[ETag update protection](https://developers.google.com/youtube/v3/getting-started#using-etags).

## Limits

No search, analytics, captions, comments, playlist editing, deletion, scheduling
or media download ships here. TikTok is excluded from this Google-only release
and deferred until after 1.8.5.

Exit 0 means a read/preview/write result; exit 1 means an operational failure
with a sanitized cause and next command; exit 2 is a Typer usage error. Preview
mode is always explicit in output. Provider error bodies, URLs and token locals
are never printed.

---
name: co-google
description: Route Google account work to Gmail, Drive, Calendar, and YouTube CLI commands using one locally saved login.
---

# Google tools

| Task | Command family |
|---|---|
| Mail and drafts | `co gmail --help` (see co-mail-and-drive skill) |
| Files and exports | `co gdrive --help` (see co-mail-and-drive skill) |
| Events and Meet links | `co gcalendar --help` |
| Channels and videos | `co youtube --help` |

Connect with `co auth google`. Default requests Gmail send/read/modify, Calendar,
Drive and YouTube management, plus email/profile identity. It does not grant every
Google API. Google shows the actual consent screen; declined capabilities are not
invented. Tokens and actual scopes are saved on this computer, not in a remote
credential table. Restricted example: `co auth google --scopes youtube.readonly`.

## Calendar

`co gcalendar list` prints event IDs, not reusable row numbers.

```bash
co gcalendar today
co gcalendar read EVENT_ID
co gcalendar meetings --days 7
co gcalendar free 2026-09-07 --minutes 30
co gcalendar create "Review" "2026-09-07T10:00:00+10:00" "2026-09-07T11:00:00+10:00"
co gcalendar meet "Review" "2026-09-07T10:00:00Z" "2026-09-07T11:00:00Z" --attendees a@example.com
co gcalendar update EVENT_ID --title "New title"
co gcalendar delete EVENT_ID
```

Mutations above preview locally. Review the exact arguments, then add `--yes`
only with user approval. Primary calendar only. Naive timestamps mean UTC;
free slots use 09:00–17:00 UTC and do not check attendees' calendars. Empty update
fields do not clear existing fields. A transport failure may have completed a write:
inspect the listing before retrying.

## YouTube

```bash
co youtube channel
co youtube list --last 10
co youtube video 1
co youtube put clip.mp4 --title "Demo" --channel UC_CHANNEL_ID
co youtube update VIDEO_ID --title "New title"
```

Numbers belong to the most recent nonempty YouTube listing; prefer stable IDs for
writes. `put` and `update` preview by default; `--confirm DIGEST` executes one
specific preview. Never fabricate a digest or retry an uncertain write. Upload
preview is local, not proof of API approval, quota, or valid media. YouTube's
API must be enabled; unaudited projects may be restricted to private uploads.
`video` reads metadata, not video bytes. Every `--json` response includes `ok` and
`next_command`; inspect them.

## Errors and recovery

| Exit | Meaning | Next command |
|---|---|---|
| 0 | Read succeeded, local preview, or confirmed write returned | Follow the printed `next_command` / `Next:` command |
| 1 | Authorization, provider or local I/O failure | `co auth google` for authorization; otherwise `co gcalendar list` or `co youtube list` before retrying |
| 2 | Invalid command arguments | `co gcalendar --help` or `co youtube --help` |

This skill documents branch behavior, not a claim that 1.8.3 is already published.

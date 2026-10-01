# Canny feedback: `co canny`

Read your Canny boards, find the requests with the most votes, read one
request's comments, move it to planned and tell its voters, reply, and write
changelog entries. `co canny` calls Canny's REST API directly: no MCP server,
no `npx`, nothing to install beyond `connectonion`.

Reads change nothing. `status`, `comment` and `changelog create` print a
preview and change nothing until you add `--yes`.

## Set up

1. Copy your secret API key from Canny: **Settings → API**.
2. Save it, encrypted, where every project reads it:

   ```bash
   co env set CANNY_API_KEY <key> --secret
   ```

3. Changing a status or commenting needs one more setting. Canny records which
   admin made the change, and an API key does not say who you are, so tell it
   your own Canny user id once:

   ```bash
   co canny check --email you@example.com     # prints your id and whether you are an admin
   co env set CANNY_USER_ID <id>
   ```

   Only a Canny admin can change a status. Reads do not need this setting.

4. Check it:

   ```bash
   co canny check
   ```

   It prints where the key came from, the workspace (read from your boards'
   URLs, since the API has no company endpoint), the boards the key sees, and
   the acting user.

The key is looked up in this order: your shell, the selected env file
(`~/.co/keys.env`, or the file given with `co --env-file`), then the encrypted
store `co env set --secret` writes, the same lookup every `co` command uses
(`connectonion.environment.setting`). `CANNY_USER_ID` is found the same way.

## Commands

| command | what it does | changes Canny |
|---|---|---|
| `co canny check [--email <address>]` | key, workspace, boards, acting user; `--email` looks up a user's id | no |
| `co canny boards [--json]` | each board's id, post count, public or private | no |
| `co canny posts [--board <id or name>] [--status <status>] [--sort newest\|oldest\|score\|statusChanged\|trending] [-n 20] [--json]` | posts: id, votes, status, board, created, title | no |
| `co canny search "<words>" [--board ...] [-n 20] [--json]` | posts matching the words, best match first | no |
| `co canny post <id> [--json]` | one post: details, votes, status, owner, ETA, its 20 newest comments | no |
| `co canny status <id> <status> [--comment "..."] [--notify] [--yes]` | change the status; `--notify` has Canny email the non-admin voters | with `--yes` |
| `co canny comment <id> "<text>" [--internal] [--yes]` | comment as your admin user; `--internal` keeps it to your team (not on Canny's Free plan) | with `--yes` |
| `co canny changelog [-n 10] [--json]` | changelog entries, unpublished first | no |
| `co canny changelog create "<title>" --details <text or -> [--publish] [--yes]` | a new entry; a draft unless `--publish`; `-` reads the text from stdin | with `--yes` |

`--status` takes Canny's built-in statuses (`open`, `"under review"`,
`planned`, `"in progress"`, `complete`, `closed`) or any custom status your
team created, and several separated by commas. `--sort score` is most votes
first. Votes are Canny's `score`.

`--json` prints the same fields as the text listing, as one JSON object on
stdout, and moves the `Next:` line to stderr so the output stays parseable.

## The five most-voted open requests

```bash
co canny posts --status open --sort score -n 5
```

```
5 posts; more match, raise -n to see them
6a2889c586d7b8843bf4cf05    72 votes  open          Feature Requests  2026-09-30  Dark mode
...
Next: co canny post 6a2889c586d7b8843bf4cf05
```

Each row starts with the post id that `post`, `status` and `comment` take.

## Mark a request planned and tell its voters

```bash
co canny status 6a2889c586d7b8843bf4cf05 planned --comment "On the roadmap for October" --notify
```

```
Change "Dark mode" (6a2889c586d7b8843bf4cf05): open -> planned.
Comment: On the roadmap for October
Votes: 72; this emails its non-admin voters
Recorded as Canny user 6a2889c586d7b8843bf4cf07 (CANNY_USER_ID)
Nothing changed: this was a preview.
Next: co canny status 6a2889c586d7b8843bf4cf05 planned --comment 'On the roadmap for October' --notify --yes
```

Run the `Next:` line to make the change. Setting the status a post already has
is accepted by Canny but records nothing and emails no one; the preview says
so. A plain `co canny comment` emails no one; to tell voters, change the status
with `--notify`.

## Changelog

```bash
co canny changelog -n 5
cat notes.md | co canny changelog create "Dark mode" --details - --yes
```

An entry is a draft unless `--publish`. Canny does not email subscribers for
entries made through the API here; send that from Canny's changelog editor.
Canny's API has no way to delete an entry, so check the preview.

## A post you can open but no listing shows

Listings (`posts`, `search`) and a board's post count come from Canny's own
list, and Canny can keep a post out of it while the post still opens by id.
Seen on 2026-10-01 on the test account: a post made through `posts/create`
with test-like text ("[co canny test] ...", "Safe to delete.") opened with
`co canny post <id>`, took a status change and a comment, and was still absent
from `posts/list`, `search` and the board's post count an hour later. A second
post made the same way with ordinary text was listed at once and counted.
The difference Canny's API shows is in `posts/retrieve`: the listed post has
an `idea` (`source: api`) and the author's vote (`score: 1`); the hidden one
has `idea: null` and `score: 0`, and `ideas/list` does not contain it. This
is Canny's behaviour, not the request: `co canny` lists with the documented
`posts/list` call. The most likely cause is Canny's spam review (Autopilot),
which holds posts it rates as likely spam until an admin approves them; we
have not confirmed it in Canny's admin. If a post you expect is missing, open
it by id and look for it in Canny's admin inbox.

## Free plan

Canny's Free plan has no internal comments. `co canny comment --internal --yes`
is refused with `plan does not support internal comments`, and the `Next:`
line is the same comment without `--internal`, as a preview, because that
one is public.

## Rate limits

Canny allows 5 to 20 requests a second, 100 to 600 a minute and 1,000 to
15,000 an hour, depending on the plan, and answers HTTP 429 with a
`Retry-After` header past that. `co canny` waits out one `Retry-After` of up to
60 seconds and tries once more. A longer wait (an hourly window) or a second
429 exits 1 naming the seconds and the command to run again; nothing is waited
for longer than a minute, so an agent is never left blocked for an hour.

## Errors

Every failure exits 1, prints the cause on stderr, and ends with one `Next:`
line.

| exit | printed | next |
|---|---|---|
| 1 | `CANNY_API_KEY is not set in ~/.co/keys.env` | `co env set CANNY_API_KEY <key> --secret` |
| 1 | `Canny rejected the API key (HTTP <code>: ...)` | `co env set CANNY_API_KEY <key> --secret` |
| 1 | `Canny records which admin changed a status ...` (no `CANNY_USER_ID`) | `co canny check --email you@example.com` |
| 1 | `No Canny board is named "..."` | `co canny boards` |
| 1 | `Canny refused v1/posts/retrieve (HTTP 400): invalid post id` | `co canny posts` |
| 1 | `Canny refused v1/comments/create (HTTP 400): plan does not support internal comments` | the same comment without `--internal` (public) |
| 1 | `Canny's rate limit is reached (HTTP 429) ...` | the same command, after the wait |
| 2 | a usage error (unknown flag, `-n 0`) | `co canny <command> --help` |

## Not built

Creating posts, voting on behalf of users, merging posts, tags, categories
and deleting posts or comments. Canny's API has them; nothing here needed them yet.

---
name: co-canny
description: Work with Canny customer feedback through `co canny` — a weekly feedback digest, the top-voted open requests, finding duplicates, and marking a request planned while telling its voters. Use when the user mentions Canny, feature requests, feedback boards, votes, roadmap status or the Canny changelog.
---

# Canny feedback with `co canny`

`co canny --help` and each command's `--help` are the source of truth for
syntax. This skill says which command serves which goal and what to watch for;
read the command's help before the first use of each one.

## Route the request

| Goal | Start with |
|---|---|
| Is Canny connected? Who am I in Canny? | `co canny check` |
| Which boards exist | `co canny boards` |
| Most-voted open requests | `co canny posts --help` (filter by status, sort by score) |
| Does a request already exist | `co canny search --help` |
| Everything about one request: votes, comments, owner | `co canny post --help` |
| Move a request to planned / in progress / complete | `co canny status --help` |
| Reply to the people on a request | `co canny comment --help` |
| What has shipped, or announce something | `co canny changelog --help` |

Every listing row starts with the post id the next command takes. Every
command ends with one `Next:` line naming the command to run next; follow it.
Use `--json` when you will process rows yourself; the fields are the same.

## Workflows

**Weekly feedback digest.** Read, never write. List open posts sorted by
newest and by trending, then the most-voted open ones; open the few that
matter with `co canny post` to read their comments. Report each item as
title, votes, status and board, with its id so the user can act on it. The
digest is about what users asked for, so quote their words from the post,
not your paraphrase.

**Top-voted open requests.** One `co canny posts` call with the open status,
score sort and the count the user asked for. Votes are Canny's `score`.
"Open" is one status; a team may also use "under review" for untriaged
requests — check which statuses the rows show before saying "nothing else
is waiting".

**Mark a request planned and tell its voters.** Run `co canny status` with
the new status, a short `--comment` that says what happens next, and
`--notify`, first without `--yes`. Show the user the preview: it names the
current status, the vote count and who will be emailed. Only after the user
approves, run the exact command the preview printed (it ends in `--yes`).
`--notify` emails the post's non-admin voters; a plain `co canny comment`
emails no one.

## Gotchas that change a result

- **Writes preview by default.** `status`, `comment` and `changelog create`
  change nothing without `--yes`. A preview's exit 0 is not a change; say
  "previewed", not "done".
- **An acting user is required for writes.** Canny records who changed a
  status or wrote a comment, and an API key does not say who that is. The
  id lives in `CANNY_USER_ID`; `co canny check --email` finds it and prints
  the `co env set` line. Only a Canny admin can change a status.
- **Setting the status a post already has does nothing.** Canny records no
  change and emails no one. The preview says so.
- **Custom statuses are allowed.** Canny accepts any status the team created
  in its settings; the built-in ones are listed in `co canny status --help`.
- **Changelog entries do not email subscribers** when made here, published
  or not.
- **Rate limits.** A short wait is taken once automatically; after that the
  command exits 1 and names itself as the command to run again after the
  stated wait.

## Errors

Every failure exits 1 with the cause on stderr and one `Next:` line.

| Printed | Run |
|---|---|
| `CANNY_API_KEY is not set` | `co env set CANNY_API_KEY <key> --secret` with the key from Canny Settings → API |
| `Canny rejected the API key` | the same `co env set` with a fresh key |
| `Set CANNY_USER_ID` | `co canny check --email <your Canny login email>` |
| `No Canny board is named` | `co canny boards`, then pass the id or the exact name |
| `Canny refused ...` | the `Next:` line; usually `co canny posts` for a wrong post id |
| `HTTP 429` | wait the seconds it names, then the same command |

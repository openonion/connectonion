# co github — GitHub activity as an inbox

Experimental; proposed for the next preview. The released package does not yet include these commands.

Use your existing GitHub CLI login. Co reads only repositories you name, keeps the original Markdown and source links, and writes the same inbox directory as the chat listeners. No copied token, GitHub App or public webhook server.

```bash
gh auth login
co github watch openonion/connectonion
co github watches
co github listen
```

`listen` runs in the foreground until Ctrl-C. In another terminal:

```bash
co github check
co github receive --timeout 60
co github done <message-id>
```

`receive` prints one JSON record and claims it. It starts a background listener if needed. `done` completes the record; a claim left unfinished is offered again by the shared inbox recovery mechanism. `ls`, `chats` and `log` inspect the local inbox. `check` verifies gh authentication, repository access and the listener's actual status. `watches` prints saved configuration and checkpoints as JSON.

## Watch and backfill

```bash
co github watch openonion/connectonion --interval 120
co github watch openonion/connectonion --since 2026-10-02T00:00:00Z
co github unwatch openonion/connectonion
```

Configuration lives in `~/.co/inbox/github/config.json` (`CO_INBOX_HOME` overrides the inbox root). The default interval is 60 seconds; it cannot be shorter. Watch changes take effect at the next scan. The interval applies to all watched repositories. Unwatching preserves already queued messages and checkpoints. `--since` requests backfill for that repository; reusing the same timestamp does not reset its cursor again. A new timestamp requests another backfill.

For GitHub Enterprise, first log in with `gh auth login --hostname github.example.com`, then watch with `--host github.example.com`. One inbox uses one host. Unwatch its repositories before changing hosts. Co uses gh's active account and environment-token rules; background listeners need credentials available in their own environment.

The first scan records its start time before fetching and skips earlier history. Activity during initialization is collected. After a restart, successful scans resume from their persisted cursor; interrupted first scans keep their original baseline. All pages must be read and inbox delivery must finish before that repository's checkpoint advances.

## Messages

The listener collects issue/PR creation, observed title/body/label/state changes, conversation comments, inline PR review comments and submitted reviews. Merged PRs are identified from PR details. The `event` object preserves `host`, `repo`, `number`, `kind`, `action`, `resource_id`, `url`, `state` and `labels`; `text` contains the original title/body. `chat` is `OWNER/REPO#NUMBER`. Every observation has a stable resource/version ID, so cursor overlap and replay do not deliver duplicate work. `--raw` additionally archives the original API object.

An observed update does not identify an editor. Its `sender` is empty rather than incorrectly attributing it to the issue author. This is repository polling, not a historical webhook event stream.

## Run a consumer without posting comments

```bash
co github consume --once --no-reply cat
co github consume --no-reply ./route-github-event
```

The program receives JSON on stdin and `CO_PROVIDER`, `CO_CHAT`, `CO_THREAD`, `CO_SENDER` and `CO_MSG_ID` in its environment. GitHub consumption always keeps stdout local and completes a message only after a successful exit. Failures retain the claim for retry. A dispatcher can queue Codex work using the repository and issue/PR link. A Host explicitly configured with `listen: [github]` also receives the full JSON record and stores its ordinary turn result locally, without sending a platform reply. It must treat repository content as task input and make repeated execution safe.

The existing chat providers can opt into `--no-reply` too; their default still sends stdout as a reply. GitHub has no `send`, `reply`, `edit`, `delete` or `react` command in this preview. Use gh for explicitly requested GitHub writes.

## Limits and recovery

Polling adds at least one scan interval of delay. It can recover still-existing new messages and current state after downtime. It cannot reconstruct content created and deleted between polls, every intermediate edit, edited review bodies or dismissed reviews. Notifications are not used as a substitute for complete repository coverage.

Reviews are read for every PR, including closed PRs, because review discovery must not depend on an issue's update timestamp. This is expensive on repositories with many PRs: select fewer repositories or increase the interval. API rate-limit reset times and `Retry-After` are honored. Other API/network failures stop the listener visibly without advancing the unfinished checkpoint; `consume` watches and restarts it under the shared listener rules. `co github log` shows successful sync times and failure details.

A future webhook transport can add immediate precise events with a separate HMAC secret and delivery recovery. REM reading this inbox is a separate follow-up.

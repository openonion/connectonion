---
name: co-linear
description: Work with the user's Linear issues through `co linear` — list their open issues for a standup, file a bug from a report, comment on an issue and close it. Use when the user mentions Linear, a Linear issue id like ENG-123, "my tickets", "file this bug", or closing an issue.
---

# co linear

`co linear` acts in the user's Linear workspace as the user, with their
personal API key. Syntax lives in help, not here: run `co linear --help`, then
`co linear <command> --help` before the first use of a command.

**Read the output, not just the exit code.** Every failure exits 1 and ends
with one `Next:` line; run that line, it is the fix. A write without `--yes`
exits 0 after only a preview: nothing changed until you rerun it with `--yes`.

## Before anything

Run `co linear check`. If it says the key is missing, tell the user to create
one in Linear (Settings → Security & access → Personal API keys) and run the
`co env set LINEAR_API_KEY ...` command it prints. Never ask them to paste the
key into the chat.

## My open issues (standup)

1. `co linear issues --mine` — open issues only, most recently updated first.
2. For anything the user asks about, `co linear issue <id from that list>`.
3. Report from what the commands printed: id, title, state. Do not guess a
   status that is not in the output; done work needs `--state Done`.

## File a bug from a report

1. Find the team: `co linear teams`. If the user did not say which, ask.
2. Search first so you do not file a duplicate: `co linear search "<key words>"`.
   If a match exists, show it and ask whether to comment on it instead.
3. Write a title that names the symptom, and a description with steps,
   expected and actual behaviour, and where the report came from. Pass a long
   description on stdin with `--description -`.
4. Labels must exist: `co linear labels --team <key>`. Do not invent one.
5. Run `co linear create ...` without `--yes`, read the preview, then rerun
   the printed command with `--yes` when the user asked you to file it.
6. Answer with the id from `Created <id>` and its link.

## Close with a comment

1. `co linear issue <id>` — confirm it is the issue the user means.
2. `co linear comment <id> "<what was done, with the PR or commit>" --yes`.
3. `co linear states --team <team key from the issue>` — pick the completed
   state by its type (`completed`), not by guessing the word "Done".
4. `co linear update <id> --state "<that name>" --yes`.
5. Verify with `co linear issue <id>`: the state line must show it.

## Judgment

- Comments and updates notify the issue's subscribers. Do them only when the
  user asked for that change; a preview is free, `--yes` is not.
- An unknown team, state, label or email exits 1 and lists the valid names.
  Choose from that list or ask; never retry with a guessed spelling.
- `co linear` cannot delete or archive issues. Say so instead of improvising.

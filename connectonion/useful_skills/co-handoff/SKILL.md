---
name: co-handoff
description: Hand a task you discussed in this Codex or Claude Code session to another person's coding agent with `co handoff`, so they continue without the background being rewritten; and open a handoff someone sent you. Use when the user says "hand off", "hand this to <person>", "pass this task to <person>", "give this to <person>'s Codex", "交给 <人>", "转给 <人>", or asks what handoffs arrived.
---

# co handoff (experimental)

**Always read the output, not just the exit code.** Every command ends with a
`Next:` line; follow it.

## Which command

| the user wants to | run |
|---|---|
| hand the current task to someone | `co handoff send <who> "<what, in their words>"` |
| send the draft they just approved | `co handoff send <who> --draft <id> --yes` |
| check a handoff they sent | `co handoff status <id>` |
| teach a name (once per person) | `co handoff contact <name> <email-or-0x-address>` |
| see handoffs sent to them | `co handoff inbox` |
| read one | `co handoff show <id>` (add `--decisions`, `--evidence` for detail) |
| continue one in their own agent | `co handoff open <id>` (`--agent claude`, `--cd <dir>`) |

## Sending: preview, ask, then send

1. Run `co handoff send <who> "<what>"` in the directory of this session. It
   reads the end of this session (Codex: `$CODEX_THREAD_ID`; Claude Code:
   `$CLAUDE_CODE_SESSION_ID`; otherwise the newest session whose cwd is here),
   drafts goal / decisions with rejected options / state / next step / open
   questions / evidence / permissions with one model call, and prints the
   preview. Nothing is sent.
2. **Show the preview to the person and ask.** Your own `--yes` is not their
   approval. If they want changes, edit the draft file the preview names (JSON)
   or run `co handoff send <who> --draft <id> --edit`.
3. After they approve: `co handoff send <who> --draft <id> --yes`. This sends
   exactly the previewed file (same content hash); a draft is bound to its
   recipient.

No session to read (a plain terminal, another directory)? Write the notes to a
file and use `--from-file <notes.md>`.

`<who>` is a contact name, an email, or a full `0x` agent address. An unknown
name exits 1 and prints the `co handoff contact` line to add it; ask the person
for the address rather than guessing one.

## Receiving

`co handoff inbox` → `co handoff show <id>` → `co handoff open <id>`. Nothing
runs before `open`. `open` writes HANDOFF.md, excerpt.md and bundle.json to
`~/.co/handoff/received/<id>/`, starts one read-only Codex turn seeded with them
(or Claude Code with `--agent claude`), and prints `codex resume <session>` and a
one-shot `codex exec resume … "<question>"`. Opening again prints the same
session; it never creates a second one.

## Gotchas that change a result

- Delivery is the recipient agent's mailbox (`co email`). "Sent" means the mail
  service accepted it; whether they opened it is not reported back yet.
- A bundle containing anything credential-shaped, or any value of a
  KEY/TOKEN/SECRET/PASSWORD variable in your environment, is refused (exit 1).
  Remove it from the draft; never work around the scan.
- Only the summary, decisions, evidence pointers and the transcript excerpt
  leave the machine. No files, rem pages or mail are attached.
- Run `send` outside a network-less sandbox: it calls a model and oo-api.

## Exit codes

| exit | provoked by | next |
|---|---|---|
| 0 | preview shown, sent, listed, opened | the printed `Next:` |
| 1 | unknown contact name | `co handoff contact <name> <email-or-0x-address>` |
| 1 | no session for this directory | `co handoff send <who> "<what>" --from-file <notes.md>` |
| 1 | credential found in the bundle | `co handoff send <who> --draft <id> --edit` |
| 1 | `--draft` for a different recipient | `co handoff send <who> "<what>"` |
| 1 | unknown handoff id on the recipient side | `co handoff inbox` |

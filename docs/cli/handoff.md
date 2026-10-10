# co handoff (experimental)

Hand a task you discussed with your coding agent to another person's coding
agent. Their Codex (or Claude Code) continues with your decisions, the options
you rejected and why, and the exact words of the discussion. You do not rewrite
the background.

```bash
# You, in the directory where you discussed the task with Codex
co handoff contact ody ody@example.com          # once per person
co handoff send ody "the login token task"      # preview; nothing is sent
co handoff send ody --draft ho-98fb1cb3 --yes   # send exactly what you saw
co handoff status ho-98fb1cb3

# Ody, on his machine
co handoff inbox
co handoff show ho-98fb1cb3 --decisions
co handoff open ho-98fb1cb3                     # starts his own Codex session
```

## What is sent

One bundle (JSON, format `co-handoff/1`):

| field | what it holds |
|---|---|
| goal | the task, in one or two sentences |
| decisions | each decision, why, and every rejected option with its reason |
| current_state | done / in progress / not started |
| next_step | the single next concrete step |
| open_questions | proposals and undecided points |
| evidence | file paths, commands, URLs, issues named in the discussion |
| recipient_may | permissions the sender stated (empty if none) |
| excerpt | the last 40 spoken turns of the session, verbatim (each cut at 2,000 characters) |
| content_hash | covers all of the above, so the recipient can tell the copy is the one you approved |

The summary is drafted by one `llm_do` call (default model) from the excerpt
and your own words. Tool calls, tool output, reasoning and anything the client
injects (AGENTS.md, skill bodies, environment context) are not read.

Nothing else leaves the machine: no files, no co rem pages, no mail.
A bundle containing anything credential-shaped (API keys, tokens, private key
blocks, JWTs, `PASSWORD=…`) or any value of a KEY/TOKEN/SECRET/PASSWORD
variable in your environment is refused with exit 1.

## Where the session comes from

| client | file | how the current one is chosen |
|---|---|---|
| Codex | `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*-<thread>.jsonl` | `$CODEX_THREAD_ID` inside Codex, else the newest rollout whose `session_meta.cwd` is this directory |
| Claude Code | `~/.claude/projects/<cwd, non-alphanumerics as ->/<session>.jsonl` | `$CLAUDE_CODE_SESSION_ID` inside Claude Code, else the newest file there |

`--agent codex|claude` picks one client; `--from-file notes.md` skips sessions
entirely.

## Preview, edit, send

`co handoff send` previews by default: recipient, source session, the summary,
the decisions and the full excerpt, and saves the draft to
`~/.co/handoff/drafts/<id>.json`. Edit that file (or pass `--edit` to open it in
`$EDITOR`), then `--draft <id> --yes` sends exactly that file. A draft is bound
to the recipient it was prepared for.

When an agent runs the command, the preview tells it to show the preview to
the person and to send only after they approve. A preview is a gate for a
person; an agent's own `--yes` is not that person's approval.

## Recipients

`<who>` is a contact name (`co handoff contact <name> <address>`, stored in
`~/.co/handoff/contacts.json`), an email, or a full `0x` agent address, which
becomes that agent's mailbox `0x<first 10 hex>@mail.openonion.ai`. An unknown
name exits 1 and prints the exact `co handoff contact` line.

## Transport

Today the bundle travels by the recipient agent's mailbox (`co email`): every
co identity has an address, delivery works while they are offline, and no Host
is needed. The mail body opens with a readable summary; the bundle follows in a
base64 block. One small module (`connectonion/handoff/transport.py`) knows
this, so a direct agent-to-agent route can replace it.

## Opening

`co handoff open <id>` writes `HANDOFF.md`, `excerpt.md` and `bundle.json` to
`~/.co/handoff/received/<id>/`, then runs one read-only `codex exec` turn seeded
with the brief (or `claude -p` with `--agent claude`). It prints:

```
Continue it:  cd ~/.co/handoff/received/<id> && codex resume <session>
Ask one question:  cd … && codex exec resume --skip-git-repo-check <session> "<your question>"
```

`--cd <dir>` runs the session in your project instead. Opening the same
handoff again prints the existing session and creates no second one. Nothing
runs before `open`; after it, your own Codex/Claude settings decide what the
agent may do.

## Not yet

- Status after delivery: the sender sees the mail service's status, not whether
  the recipient opened the handoff, and replies do not come back to the
  original handoff.
- Finding someone's agent by email (#2353); today you exchange addresses once.
- Scoped auto-approval grants and recipient-side acceptance policies (#2351).
- Native Codex notifications: the recipient runs `co handoff inbox`.

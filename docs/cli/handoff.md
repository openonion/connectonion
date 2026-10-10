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

# Sent to an ordinary email instead: save the mail, open the file
co handoff open handoff.eml
```

## What is sent

One brief, in the same sections as the `handoff` skill (the structure Codex uses
when it compacts a conversation), plus the transcript it came from. Bundle
format `co-handoff/2`:

| section | field | what it holds |
|---|---|---|
| title | `title` | the task in one line |
| Task | `task`, `may_do` | what to do, what "done" means; what the recipient may do (only as stated) |
| Where it stands | `where_it_stands` | finished, in progress, tried |
| Decided | `decided` | each decision with its reason |
| Rejected | `rejected` | each dropped alternative with why |
| Open questions | `open_questions` | undecided points and who waits on them |
| Code and references | `references` | repository, branch, commit, PR, files by repository path |
| (sent with it) | `excerpt` | the transcript the brief was drafted from, verbatim |
| | `source` | client, session id, turns included, whether it was compacted. No local paths |
| | `content_hash` | covers everything above, so the recipient can tell the copy is the one you approved |

The brief is drafted by one `llm_do` call (default model) from the excerpt and
your own words. Tool calls, tool output, reasoning and anything the client
injects (AGENTS.md, skill bodies, environment context) are not read.

Nothing else leaves the machine: no files, no co rem pages, no mail. A bundle
containing anything credential-shaped (API keys, tokens, private key blocks,
JWTs, `PASSWORD=…`, ConnectOnion invite codes) or any value of a KEY / TOKEN /
SECRET / PASSWORD / INVITE variable in your environment is refused with exit 1.
Private paths (`/Users/<name>/…`, `/home/<name>/…`, `~/.codex/…`) are listed
under the preview so you remove or keep each knowingly.

## Where the session comes from

| client | file | how the current one is chosen |
|---|---|---|
| Codex | `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*-<thread>.jsonl` | `$CODEX_THREAD_ID` inside Codex, else the newest rollout whose `session_meta.cwd` is this directory |
| Claude Code | `~/.claude/projects/<cwd, non-alphanumerics as ->/<session>.jsonl` | `$CLAUDE_CODE_SESSION_ID` inside Claude Code, else the newest file there |

`--session <thread id | session id | path.jsonl>` picks any session;
`--agent codex|claude` picks one client; `--from-file notes.md` skips sessions.

### Compacted sessions

Both clients keep the full history on disk and mark a compaction:

- **Claude Code** writes a `user` row with `isCompactSummary: true` whose text is
  the plaintext summary. It becomes the first (`summary`) turn.
- **Codex** writes a `compacted` row. Its summary is a `compaction` item holding
  only `encrypted_content` (0 of 107 compactions on one Mac had plaintext), so it
  cannot be read. Codex's `replacement_history` keeps the user's own earlier
  messages; those become `earlier` turns.

After the last compaction come the turns that followed it (up to 40). An
uncompacted session gives its last 40 turns. Each turn is cut at 2,000
characters, a Claude Code summary at 12,000.

## Preview, edit, send

`co handoff send` previews by default: recipient, source session, the summary,
the decisions and the full excerpt, and saves the draft to
`~/.co/handoff/drafts/<id>.json`. Edit that file (or pass `--edit` to open it in
`$EDITOR`), then `--draft <id> --yes` sends exactly that file. A draft is bound
to the recipient it was prepared for.

When an agent runs the command, the preview tells it to stop, show the person
the preview and send only after they approve. **This is guidance, not
enforcement:** in two full-auto Codex runs the agent read it and sent anyway.
The real gate today is the coding client's own command approval (Codex asks
before a networked command outside its sandbox); a person-only approval is
planned with #2351/#2353.

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

`co handoff open` takes the handoff id, or the handoff email saved as a file.
Only mail to a co agent mailbox shows in `co handoff inbox`; a handoff sent to
an ordinary email (Gmail, Outlook) is opened from the saved mail: a downloaded
`.eml` (quoted-printable or base64 bodies are decoded), the text pasted into a
file, or `co email read <#> > handoff.txt`. The mail itself says so. The file
must hold the whole mail, including the `BEGIN/END CO HANDOFF BUNDLE` block;
the content hash is checked and a mismatch is printed as a warning.

`co handoff open <id>` writes `HANDOFF.md`, `excerpt.md` and `bundle.json` to
`~/.co/handoff/received/<id>/`, then runs one read-only `codex exec` turn seeded
with the brief (or `claude -p` with `--agent claude`). It prints:

```
Continue it:  cd ~/.co/handoff/received/<id> && codex resume <session>
Ask one question:  cd … && codex exec resume --skip-git-repo-check <session> "<your question>"
```

`--cd <dir>` runs the session in your project instead. Opening the same
handoff again with the same `--agent` prints the existing session and creates no
second one. Nothing
runs before `open`; after it, your own Codex/Claude settings decide what the
agent may do.

## Not yet

- Status after delivery: the sender sees the mail service's status, not whether
  the recipient opened the handoff, and replies do not come back to the
  original handoff.
- Finding someone's agent by email (#2353); today you exchange addresses once.
- Scoped auto-approval grants and recipient-side acceptance policies (#2351).
- Native Codex notifications: the recipient runs `co handoff inbox`.

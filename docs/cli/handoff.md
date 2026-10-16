# co handoff (experimental)

Hand the context of what you discussed with your coding agent to another
person's coding agent. A handoff is one message: every message you wrote in the session, word for
word, the AI's replies quoted, and where the code is. Their Codex (or Claude
Code) continues from it, and asks you for anything that is missing.

```bash
# You, in the directory where you discussed the task with Codex
co handoff contact ody ody@example.com          # once per person
co handoff send ody "the login token task"      # preview; nothing is sent
co handoff send ody --draft ho-98fb1cb3 --yes   # send it; prints the same prompt for chat
co handoff status ho-98fb1cb3 --wait            # returns when they accept or ask
co handoff answer ho-98fb1cb3 "30 days"
co handoff status ho-98fb1cb3                   # "Done, …" and any file they sent back
```

Ody does not type any of this. The mail comes from your own mailbox and reads
like a short note from you: who has been working on what with their AI, what
they talked through, and one block to paste into a new Codex or Claude Code
conversation. He pastes it, and his
agent installs co if needed, accepts by itself, tells him in a few lines what the
task is, does it, and tells you with `co handoff done` when it is finished. He
is asked only before something that cannot be undone or that leaves his
machine. The chat message `send` prints is the same block.

## The mail and the prompt

The mail is a short note, written for a person who may not know co, in the
language you wrote in (Chinese or English). The subject is "Aaron Xie passed you
some work: <title>", with no co terms in it. The body has one or two sentences:
who has been working on what with which AI, and the first thing they talked
through. Then come two ways in, the web page first:

1. **See the context Aaron is passing you**: a button to `https://o.openonion.ai/h/<id>`.
   The page shows whose context it is, what was discussed, decided and still open,
   the diagram and the conversation, in a browser, with nothing to install. Its
   own copy button does step 2.
2. **One line to paste** into a new Codex or Claude Code conversation. A
   triple-click selects it. It names the page's agent text,
   `https://o.openonion.ai/h/<id>/codex`, and the agent reads that and does the
   rest. Without network access it asks the person for it, once, in one sentence.

A sender without a name (no `git config user.name`) appears as "Someone", never
as an agent address. What was decided and what is still open reach their agent
when it accepts.

It goes from the best mailbox there is, with no option to pick:

1. **Your AI's own mail tool**, when the agent running `send` has one (a Gmail
   or Outlook MCP connector). The handoff skill has it send the mail itself,
   from your address.
2. **Your Gmail**, connected with `co auth google`.
3. **Your Outlook**, connected with `co auth microsoft`.
4. **Your agent's mailbox**, last, because a stranger may take mail from it for
   spam. The preview says so, and says how to connect your own.

The preview's last line names the mailbox. A question that waits on you, and the
note that a handoff is done, go to that mailbox from itself.

The line, as a 1.9.2b24 sender writes it:

```text
Aaron Xie handed you the context of "Add Kelvin conversion to tempconv.py" with ConnectOnion. Read https://o.openonion.ai/h/Hk3…/codex and do what it says, here in this folder, without waiting for me. If you cannot open it, ask me to allow network access.
```

What the page at `/codex` holds is the whole prompt co wrote: install co if it is
missing, `co handoff accept <code>`, do the work without waiting, ask the sender
rather than guess, and `co handoff done`. co picks the page's id itself, so the
accept code inside it can name the same handoff; the handoff and the prompt go
to the backend together (`POST /api/v1/drops`, kept 30 days). The copy in a
contact's agent inbox carries the whole prompt, so `co handoff show` and `open`
work from it, and `open` on a saved mail reads the prompt from the page.

The prompt on that page, with the code shortened and the version as a 1.9.2b22 sender wrote it:

```text
Aaron Xie handed you the context of "Add Kelvin conversion to tempconv.py" (handoff ho-5359a292). If co --version prints nothing or a version older than 1.9.2b22, install co first, which keeps to its own environment (right after a release it can wait a few minutes for PyPI, so let it finish): on macOS or Linux run curl -fsSL https://raw.githubusercontent.com/openonion/connectonion/v1.9.2b22/install.sh | CO_VERSION=1.9.2b22 sh, and on Windows run uv tool install "connectonion==1.9.2b22" then co init --yes. Then run co handoff accept coh3.… yourself; it fetches the handoff and says what to do. Do that here, in this folder, without waiting for me: the work, questions to Aaron Xie with co handoff ask, and co handoff done when it is finished. Then tell me in a few lines what Aaron Xie was working on and what you did.
```

That block becomes the first message of the recipient's thread, so it carries
nothing else. It is in the person's voice, so it says to do the work: in 1.9.2b21
its last step said "tell me what you will do", which outranked the rules accept
prints, and two Codex versions stopped there. The handoff itself waits on the backend under an id the code
carries (`POST /api/v1/drops`, kept 30 days): before they install co, the
recipient has no agent address, so the agent inbox cannot hold it for them.
`co handoff accept` fetches it, refuses it unless it is exactly what you
approved (its content hash is in the code), saves it as
`~/.co/handoff/accepted/<id>/HANDOFF.md`, prints the report part, and tells the
agent what to do next. Two more things come with it, so nothing waits on your
machine being online:

- **Your code, when they cannot fetch it,** from the one repository the handed-off
  messages worked in last; other repositories the session visited are listed, not
  sent. `--no-code` sends none, and also works on a saved draft. Commits on no remote go as
  `git format-patch` text, and uncommitted changes (new files included) as a
  diff. The preview says which ("The code goes with it: 1 commit and
  uncommitted changes …"), the credential check covers them, and the approved
  bundle records their digest. Without a remote, accept rebuilds the repository
  in the current folder and says "The code is in …"; with one, it saves the
  patches and says how to apply them to a clone. Over 1.5 MB it does not go,
  and the preview says to push.
- **The session copy**, the same redacted copy an answer used to bring, saved
  as `session.md`. Answers point to it.
- **The sender's conversation as a thread of its own**, when accept runs inside
  Codex or Claude Code. The pasted thread holds the paste, the work and the
  agent's summary; the sender's turns are in a second one, named
  `Handoff from <sender>: <title>`, each side labelled, ending in the report
  (Discussed, Concluded, Still open, the diagram) and "You can keep asking me
  here." Accept prints how to open it, and `done` prints it again, last, so the
  agent passes it on. In Codex it is in the conversation list (`/resume`, or the
  app's sidebar), because accept has Codex read it once by id (Codex lists threads
  from its own database, which takes in new files only once); when `codex` is not
  on the PATH it opens with `codex resume <id>` only. In Claude Code it is in
  `claude --resume`'s list and opens with `claude --resume <id>`. In any other
  agent there is no thread format to write, and the conversation stays in
  `session.md`.

The rules accept prints: do the work in this folder without asking the person,
ask them only before something that cannot be undone or leaves the machine,
ask the sender rather than guess, and `co handoff done` at the end. Those rules
come from the installed co, so they improve with each release instead of being
frozen into a mail.

- The version floor is the oldest release whose recipient side does everything
  the prompt promises, never the sender's own build (a dev build is on no index).
- co goes into its own environment through `install.sh`, which installs uv if
  needed and then `uv tool install`s exactly that version and runs `co init`.
  It never touches the recipient's global Python. The script is fetched from the
  floor's release tag, not from `main`, so what runs is what was released. For a
  few minutes after a release PyPI's index may not list it yet: `install.sh`
  waits for it (up to about 5 minutes) instead of failing.
- The mail has a plain-text part and an HTML part. In the HTML the prompt is in
  `<pre>` inside a framed table cell, because Outlook ignores padding and
  wrapping on `<pre>`. The agent mailbox's mail service sends only the HTML
  (plain text lost its line breaks there).
- The bundle is also hidden at the very end of the HTML, base64, for
  `co handoff open <saved mail>`. A mail to an agent mailbox is found in
  `co handoff inbox` by that block, not its subject.
- There are no `<placeholders>` in it; the mail service drops anything shaped
  like a tag.

## The code

`coh4.…` (about 190 characters) holds the sender's agent address and mailbox,
the handoff id, the bundle's content hash, a random secret, the id the handoff
waits under on the backend, the key it is sealed with (see
[Encryption](#encryption)), and a checksum. A
mistyped or cut-off code is refused; in one real run an agent retyped a longer
code and a single wrong character turned the sender's mailbox into a different
domain. Whitespace inside a code (a wrapped line) is ignored. `co handoff accept`
also takes the handoff's link, `#k=` part included, and reads the code from its
page. A `coh3` code, from 1.9.3rc4 or earlier, names a handoff the backend holds
in plaintext; it is still accepted. A `coh2` code, from
1.9.2b12 to 1.9.2b20, carries no backend id and is accepted with
`--brief HANDOFF.md`; a `coh1` code, from 1.9.2b11 or earlier, is answered by mail.

The code is **handoff-scoped**. It lets one agent mark this one handoff accepted
(the first valid acceptance wins; later ones are counted and ignored) and send
questions about it. It is **not an invite code**: presenting it to a Host
onboards no one. What it does is introduce two agents. Once the handoff is
accepted, each side makes the other its agent's contact (see
[Recipients](#recipients)), and `~/.co/handoff/peers.json` records which
handoffs each acceptor took.

## Accept, ask, answer, status

| who | command | what it does |
|---|---|---|
| recipient | `co handoff accept <code>` | fetches the handoff, checks it against the code, sends the acceptance with their agent address to the sender's agent, and keeps the brief under `~/.co/handoff/accepted/<id>/` (`--brief HANDOFF.md` for a coh2 code) |
| recipient | `co handoff ask <code> "<question>"` | sends a question about this handoff |
| recipient | `co handoff done <code> "<what you did>" [--file result.patch]` | tells the sender it is finished, with an optional file (at most 3.5 MB packed). The sender's status shows it, and the sender is also mailed once at their git `user.email`, with a patch under 20 KB inline |
| sender | `co handoff status <id>` | one line first, such as "bob finished it · their file saved · 2 questions (you answered 1)", then who accepted, each question with how it was answered ("You answered", "Answered automatically", or "Waiting on you"), and "Done, …". A file sent with `done` is saved as `~/.co/handoff/results/<id>/<name>`, and when it is a patch the Next line is the `git apply` (or `git am`) that applies it. `--verbose` adds agent addresses and the content hash |
| sender | `co handoff answer <id> "<text>"` | sends the answer to the agent that accepted; status shows it as yours |
| sender | `co handoff withdraw <id>` | takes the handoff's page and pickup down at once, instead of after 30 days; mail already delivered stays in their mailbox |
| recipient | `co handoff status <id>` | the sender's answers. With `--wait` it returns when something new arrives, or after `--timeout` seconds (default 600) with the rule to carry on and say "Assumed: …" in done. A second holder of the same code (a forwarded mail, a shared paste) is told the handoff is already accepted by someone else, and stops |

Each is a small base64 block sent to the other agent's inbox (see
[Transport](#transport)). While the sender's agent is hosted, however it was
started (`co host`, `python agent.py`, `co deploy`, `co ai`), it reads the
mailbox and the agent inbox every minute when a handoff sent in the last 14 days
is waiting, and prints
`[handoff] ho-… accepted by …`, each new question, and `[handoff] ho-… done: …` once.

### Questions are answered automatically

The sender's agent answers every question by itself; no one reviews the answer
first. The first answer carries a copy of the session the handoff came from:
the messages you approved in the preview (`--since` and `--edit` apply), each
whole, with each AI reply in full rather than quoted. Tool calls and their output
never go: in a session that ran `co rem` they are whole pages about other people
and your own mail (#2496). Credential-shaped strings, values from your keys.env
and other people's contact details are removed. The recipient's `co handoff status`
saves it as `~/.co/handoff/accepted/<id>/session.md`, so their agent searches it
instead of asking again. Later questions are answered with a pointer to that
copy, unless the question says the copy does not answer it, or asks again: then
no pointer goes, status shows it as "Waiting on you", and the mail to you says
"Waiting on you" in its subject. A requirement that only ever appeared in a
tool's output does not reach the recipient this way; they ask, and it waits on you.

It happens wherever the sender's side checks for replies: the host's watcher,
`co handoff status`, and `status --wait`. A copy cannot answer a question you
left open, so each new question is also mailed to you once, at your
`git config --global user.email` when it is set, with the
`co handoff answer <id> "…"` line that answers it, and the recipient is told a
person may still answer and to keep `status --wait` running. Handoffs drafted from a notes file
(`--from-file`) have no session to copy and are not answered automatically.

## What is sent

One message, kept the way a compaction keeps a conversation:

| part | what it holds |
|---|---|
| Report: one line on who worked on what and when, Discussed, Concluded, Still open, and a small ASCII diagram when there is something to draw | the part read first, in the mail, in HANDOFF.md and in what `accept` prints. Every line comes from the conversation |
| Task, Where it stands, Rejected | the detail under it. Task opens with your own words from `send` ("Handed off as: …"); the rest is written from your messages and the summaries below. A review stays a review, later messages override earlier ones, and permissions you gave your own AI ("merge it yourself") are never passed on |
| Code | up to three repositories the session worked in (Claude Code's `cwd`/`gitBranch` on each row; Codex's `session_meta`, `turn_context` and each command's `workdir`), most recent first: remote (any `user:token@` removed), branch, the last commit on it by the time the session last worked there (for a detached checkout, where the reflog says HEAD was), whether it is pushed, and how many files are changed but not committed |
| Issues and PRs mentioned | each `#N` in the handoff with its title, taken from `gh` output the session already read (`--json`, `view`, `list`); nothing is fetched at send time, so it works for a private repository. A number the session never looked up stays a number |
| Conversation | every message you typed in the session, word for word and never cut; under each, the AI's final reply for that turn in its own words, with a count of the running remarks it made between tools before it ("Tests first:"; the session copy has those). A message typed while the AI was busy, recorded twice by Claude Code, appears once. A reply over 800 characters keeps its start and its end, cut between lines, and says how many characters were left out. Originals, not summaries: a summary drops what its writer thought unimportant, and the reader cannot tell what is missing |
| Other people's contact details | email addresses, phone numbers (mobile, landline, 1300/1800) and IP addresses that belong to neither you nor the recipient are replaced with `[email removed]` / `[phone removed]` / `[ip removed]` everywhere: the page, the mail, and the session copy (a session that ran `co rem` has read a mailbox). So is what else points at a person: `co rem` page names (`people/[person].md`), LinkedIn ids, and the name in a mail header whose address was removed. Your own addresses, the recipient's, `git@…`, example addresses, `127.0.0.1` and `0.0.0.0` stay, and ordinary words are never touched. The preview says how many were masked. |

Not sent with the handoff: tool calls and their output, reasoning, anything the
client injects (AGENTS.md, skill bodies, environment context), and the session
file. The first automatic answer brings the session copy; for anything else the
recipient's agent asks (`co handoff ask`).

Drafting makes one model call: the report on top, written from the newest
400,000 characters of the quoted conversation. Nothing else is summarised.

A message containing anything credential-shaped (API keys, tokens, private key
blocks, JWTs, `PASSWORD=…`, ConnectOnion invite codes) or any value of a KEY /
TOKEN / SECRET / PASSWORD / INVITE variable in your environment is refused with
exit 1. Private paths (`/Users/<name>/…`, `/home/<name>/…`, `~/.codex/…`), email
addresses, phone numbers and IP addresses are listed under the preview so you remove or keep
each knowingly. Every message you typed goes, so in a session that also covered
other work, start where this task starts: `--since <N>` with N from the preview's
`[N]` list, or remove lines with `--edit`. Over 30,000 characters the preview says so: that much is
a lot to paste into a coding agent. A repository that is not pushed gets a
warning too: the recipient cannot fetch it and has only the session copy, so
push it before sending.

Bundle format `co-handoff/3`: `title`, `task`, `where_it_stands`, `decided`,
`rejected`, `open_questions`, `asked` (your words from `send`), `mentioned` (`{"1043": "title"}`), `code` (`[{repository, branch, commit, pushed,
uncommitted}]`), `conversation` (`[{at, user, ai}]`), `source` (client, session
id, message count; no local paths) and `content_hash`, which covers all of it so
the recipient can tell the copy is the one you approved.

## Encryption

What the backend holds of a handoff is ciphertext.

**The handoff itself.** `send` seals it on your machine before anything leaves:
AES-256-GCM, under a random 256-bit key made for this one handoff. The backend
stores two sealed parts. The page holds the report, the conversation, and the
prompt with the code. The pickup holds the code's patches and the session copy,
and the backend serves it only to whoever holds the code's secret. The key is
in the link's `#k=` part and in the code, and nowhere on the backend. A browser
never sends the part of a link after `#`, so the page at `o.openonion.ai/h/<id>`
decrypts in the reader's browser, and `co handoff accept` decrypts on the
recipient's machine.

What the backend can see: which agent dropped it, your name, which coding agent
the session came from, its language, its size, and when it was sent and picked
up. The prompt its page serves to an agent names no title and no code, only how
to install co and accept with the whole link.

**Where the key travels.** In the link, in the note to the person.
- From your own Gmail or Outlook, or your coding agent's own mail tool, the note
  goes through your mail provider and theirs, not through ConnectOnion.
- With neither connected, it goes from your agent's mailbox through
  ConnectOnion's mail service, and the key goes with it. The preview says so.

**After the handshake.** Once their agent accepts, each side knows the other's
agent address, which is its Ed25519 public key. From then on, every message
between the two agents is boxed to the other agent's key: X25519 `crypto_box`,
from those same keys. That covers:
- the acceptance;
- questions and answers;
- results and their files;
- the inbox copies of later handoffs.

The backend relays only ciphertext, with `[co handoff]` outside it. Opening a
box also proves which agent sent it, so a message relayed under another agent's
name is not believed. Only the two agents can read these messages.

**What this does not cover.**
- The note to the person is ordinary mail, for the first handoff and for later
  ones.
- A question that waits on you, and a finished result, are mailed to you too.
  They go from your own mailbox when one is connected.
- A handoff sent by co 1.9.3rc4 or earlier (a `coh3` code) stays plaintext on
  the backend until it expires, and so do the messages about it.

## Where the session comes from

| client | file | how the current one is chosen |
|---|---|---|
| Codex | `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*-<thread>.jsonl` | `$CODEX_THREAD_ID` inside Codex, else the newest rollout whose `session_meta.cwd` is this directory |
| Claude Code | `~/.claude/projects/<cwd, non-alphanumerics as ->/<session>.jsonl` | `$CLAUDE_CODE_SESSION_ID` inside Claude Code, else the newest file there |
| Gemini CLI | `~/.gemini/tmp/<project>/chats/session-*.json(l)` | the newest whose `projectHash` is this directory's sha256 |
| opencode | `~/.local/share/opencode/storage/session/<project>/ses_*.json` | the newest whose `directory` is this directory |
| droid | `~/.factory/sessions/<cwd, non-alphanumerics as ->/<id>.jsonl` | the newest file there |
| Grok | `$GROK_HOME` (`~/.grok`)`/sessions/<folder, encoded>/<id>/updates.jsonl` | the newest whose `summary.json` `info.cwd` is this directory |
| Cursor | Cursor's own database (`…/Cursor/User/globalStorage/state.vscdb`), read without writing to it | the conversation this folder's workspace touched last, copied to `~/.co/handoff/imported/cursor/` |

With no `--agent`, the newest session of any of them for this directory is the
one drafted. Only what was said is read: the messages and the AI's replies,
never tool calls or their output.

`--session <thread id | session id | path>` picks any session;
`--agent codex|claude|gemini|opencode|droid|cursor|grok` picks one client;
`--from-file notes.md` sends a notes file as the one message instead.

Both clients keep the whole history on disk and only mark a compaction, so the
whole conversation is read from its first message:

- **Claude Code** writes a `user` row with `isCompactSummary: true`. It is the
  client's summary, not your words, and is skipped. A message you type while
  Claude Code is mid-turn is an `attachment` row (`queued_command`,
  `origin.kind: human`) and is kept.
- **Codex** writes a `compacted` row whose `replacement_history` repeats user
  messages already in the rollout, and whose summary is encrypted. It is skipped.
  A `/goal` objective arrives inside `<codex_internal_context source="goal">`,
  repeated every turn; its `<objective>` is kept once, as "Goal: …".

## Preview, edit, send

`co handoff send` previews by default: the whole message as it will be sent, and
saves the draft to
`~/.co/handoff/drafts/<id>.json`. Edit that file (or pass `--edit` to open it in
`$EDITOR`), then `--draft <id> --yes` sends exactly that file. A draft is bound
to the recipient it was prepared for.

When an agent runs the command, the preview tells it to stop, show the person
the preview and send only after they approve. **This is guidance, not
enforcement:** in two full-auto Codex runs the agent read it and sent anyway.
The real gate today is the coding client's own command approval (Codex asks
before a networked command outside its sandbox); a person-only approval is
planned with #2351/#2353.

When the recipient is one of your contacts, the preview says how often they are
named in what they will read; `--mentions <name>` lists each place and sends
nothing. Masking removes contact details, not what the session says about the
person reading it.

Before the preview, your own coding agent reads every sentence that would go,
yours and the AI's, the whole reply and not only the quoted part, and the report
on top: Codex for a Codex session, Claude Code for a Claude Code one, on your own
plan (the other one if that one is not installed, ConnectOnion's default model if
neither is). Each sentence about someone's health, family, personal travel or
home, money, visa or legal matters, or a third party's own business is replaced
with `[removed: <why>]`, in the page and in the session copy, and a person's name
no rule caught becomes `[person]`. It removes when unsure. The preview says how
many went and from which messages; put any back with `--edit`. When the session
read your mail or your co rem pages, the preview says so: that is where the AI's
replies pick up private details.

A message you change with `--edit` goes into the session copy as you changed it,
not as the session had it. The preview also names each message that still
mentions health, visas, the law or money (签证, 睡眠, lawyer, salary…).

`--lang en` or `--lang zh` writes the report and the mail in that language; your
own words stay as you wrote them. Without it, the language is the one you wrote
in. A long handoff previews its newest messages; all of it is in the draft file.

## Recipients

`<who>` is a contact name (`co handoff contact <name> <address>`, stored in
`~/.co/handoff/contacts.json`), an email, or a full `0x` agent address, which
becomes that agent's mailbox `0x<first 10 hex>@mail.openonion.ai`. An unknown
name exits 1 and prints the exact `co handoff contact` line.

Once a handoff is accepted, the two sides know each other, at different levels,
both shown by `co trust list --global` for your global identity (`~/.co`):

- **On the sender's side the recipient's agent is a contact.** It may use the
  tools the sender's Host pre-authorises (EXEC) and Remote Browser, the same as a
  contact who joined by invite. The sender adds it when `co handoff status` (or a
  running host) sees the acceptance.
- **On the recipient's side the sender may send handoffs only.** `co handoff
  accept` puts them on the *handoffs* level: handoffs, questions, answers and
  `done` go through the agent inbox, and a Host that pre-authorises contacts does
  not count them as one. accept says so: "Aaron can send you handoffs and
  questions; they can't run tools on your machine."

Both changes are in the record (`approvals.jsonl`) with the handoff that made
them. Only the first valid acceptance counts. Each side also gets a name
for `co handoff send`: a contact you already had keeps its name and its mail
address and gains the agent's `0x` address, and anyone new is saved under
their mailbox name.

The handoffs level can be raised: `co trust add <0x…>` makes them a contact. A
policy per contact, set and raised by the Trust Agent from what co rem knows
about the two of you, is #2401 / #2407. `co trust remove <0x…>`
takes someone off the list.

## Transport

Mail is for discovery. The first handoff to someone goes to a person's mailbox,
because their agent's address is not known yet. From then on the agents know
each other: the code carries the sender's agent address, the acceptance carries
the recipient's, and each side saves the other as a contact. Every reply, and
any later handoff to that contact, goes to the other agent's inbox on the
backend (`/api/v1/messages`) instead of through the mail service. A later
handoff is also mailed to the person, the same mail as the first time: the
inbox alone tells their agent, and nobody would tell them. A contact
made by 1.9.2b11 or earlier still gets mail: its co does not read the inbox. A later
handoff to a contact therefore arrives in `co handoff inbox`, not as a mail;
`co handoff show <id>` prints where its prompt is saved.

Both work while the other side is offline, and no Host is needed. The backend
keeps an inbox message for 30 days, and reading it does not delete it, so a
second machine with the same identity reads it too. The agents' messages to each
other are boxed end to end ([Encryption](#encryption)).
`connectonion/handoff/transport.py` is the only module that knows the wire, and
`connectonion/handoff/sealing.py` the only one that knows the cryptography.

## Power-user commands: inbox, show, open

The prompt is the normal path. These remain for people who want them. `co handoff open` takes the handoff id, or the handoff email saved as a file.
Only mail to a co agent mailbox shows in `co handoff inbox`; a handoff sent to
an ordinary email (Gmail, Outlook) is opened from the saved mail: a downloaded
`.eml` (quoted-printable or base64 bodies are decoded), the text pasted into a
file, or `co email read <#> > handoff.txt`. The mail itself says so. The file
must hold the whole mail, including the `BEGIN/END CO HANDOFF BUNDLE` block;
the content hash is checked and a mismatch is printed as a warning.

`co handoff open <id>` takes the handoff over in your own coding agent, in a
folder you can find: `~/handoffs/<title>` (or `--cd <dir>`).

- **Codex**: the sender's conversation becomes a thread named
  `Handoff from <sender>: <title>`, one turn per exchange. The sender's words
  are labelled `(from <sender>, who handed this over · <date>)`, and their AI's
  replies `(<sender>'s Claude Code, in summary)`. It shows in the Codex app,
  and on a phone that remote-controls it, like any other thread.
- **The first real turn** accepts the handoff and replies with a report short
  enough for a phone: who handed what, Discussed, Concluded (each with its
  reason), Still open, a small ASCII diagram of how the conversation went, the
  next step, and "You can keep asking me here."
- **The second turn** runs in the background. It does the work in the folder,
  asks the sender what the handoff does not say, and finishes with
  `co handoff done`. Its log is `~/.co/handoff/received/<id>/work-codex.log`.
- **Claude Code** (`--agent claude`) gets the same two turns, without the
  replayed thread. (Accept, run inside Claude Code, does write one.)

Both turns run with full access in that folder (`codex exec -s danger-full-access`,
`claude --permission-mode bypassPermissions`). Opening the same handoff again
prints the existing session and creates no second one.

The replay is written in Codex's own session format
(`$CODEX_HOME/sessions/…/rollout-*.jsonl`, with the turn events as well as the
messages, and the name in `session_index.jsonl`). Codex has no public API for
injecting history, so this was verified against codex-cli 0.162.1. If
`codex exec resume` refuses the file, open falls back to one turn seeded with
the whole brief on stdin.

## Not yet

- Finding someone's agent by email (#2353); today you exchange addresses once.
- Scoped auto-approval grants (#2351). The send approval is the preview; an agent
  running with full auto-approval can still pass `--yes` itself.
- A notification pushed into a running Codex or Claude Code session. Today the
  agent runs `co handoff status <id> --wait` in the background, which returns when
  an acceptance, question or answer arrives; `co ai` also prints them.

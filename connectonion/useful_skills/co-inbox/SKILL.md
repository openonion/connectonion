---
name: co-inbox
description: Drive `co feishu` / `co lark` — a chat bot as a directory of files. Use when an agent must receive messages from a Feishu or Lark group, reply to them, or run a command per message. Covers setup by QR, the nine verbs, the queue's guarantees, and every exit code.
---

# The inbox

A Feishu or Lark bot, as a directory. One process writes messages into it; you
read them. Nothing here knows what an agent is.

**Always read the output, not just the exit code.** `listen` prints nothing on
a clean hour, and `consume` runs commands whose own failures it reports on
stderr while continuing.

## Which command

| you want to | run |
|---|---|
| set it up, from nothing | `co auth feishu` |
| set it up, reusing a bot you already have | `co auth feishu --app-id cli_…` |
| check it is configured | `co feishu check` |
| take the next message and act on it yourself | `co feishu receive` |
| run a program for every message, forever | `co feishu consume -- <command>` |
| answer a message you took | `co feishu reply <id> "text"` |
| decide not to answer one | `co feishu done <id>` |
| send without being asked | `co feishu send <chat> "text"` |
| see what is waiting | `co feishu ls` |
| watch it work | `co feishu log -f` |
| hold the connection yourself | `co feishu listen` |

`co lark …` is the same nine verbs against Lark. Pick by where your bot lives;
the credentials are separate (`FEISHU_APP_*` and `LARK_APP_*`).

## The 80%

```bash
co auth feishu                      # scan the QR; the app exists, keys saved
co feishu check                     # names what is still missing, if anything
# add the bot to a group and @ it
co feishu ls                        # what is waiting
m=$(co feishu receive)              # take one; blocks until there is one
echo "$m" | jq -r .text
co feishu reply "$(echo "$m" | jq -r .id)" "on it"
```

Or hand every message to a program and let it loop:

```bash
co feishu consume -- claude -p      # its stdout becomes the reply
co feishu consume -- codex exec -
co feishu consume -- ./answer.sh
```

`consume` gives the command the message JSON on stdin and these variables:
`CO_PROVIDER`, `CO_CHAT`, `CO_THREAD`, `CO_SENDER`, `CO_MSG_ID`, `CO_CHAT_DIR`.

## The message

Seven fields, identical on every provider:

```json
{"id":"om_9f8e","chat":"oc_a1b2","thread":null,"sender":"on_7c6d",
 "text":"look at today's failed deploys","mentioned":true,"at":"2026-09-02T10:31:07Z"}
```

`chat` is where a reply goes. `id` is all `reply` needs — it looks up the chat
and thread itself. The provider's own payload is not included unless the
listener was started with `--raw`, so contact names and group titles never
reach a prompt by accident.

## Gotchas that change what you report

- **Taking a message is a claim, and claims expire.** `receive` moves the file
  from `new/` to `cur/`. If you neither `reply` nor `done` within an hour, it
  goes back to `new/` and somebody else gets it. A long job is fine —
  `consume` renews the claim while your command runs — but a script that takes
  a message and then sleeps is not.
- **`done` is not optional.** A message you decided to ignore stays claimed
  until it expires, then comes back. `done <id>` is how you say the silence was
  deliberate.
- **A reply happens once.** `reply <id>` refuses a second reply to the same id;
  `--again` is the override. Feishu also dedupes on its side for an hour.
- **Two consumers never get the same message**, because taking one is
  `rename(2)`. Running two is safe and is how you scale; the loser just gets
  the next one.
- **`listen` is the only writer and there is one of it.** A second `listen` on
  the same directory exits 1 rather than competing. `receive` and `consume`
  start one in the background if none is running.
- **Nothing is deleted.** `received.jsonl` keeps every message forever, so
  `grep` is your history and disk is your limit.
- **`--json` is not a flag here.** Every verb that returns data already prints
  one JSON object per line.

## Where it lives

```text
~/.co/inbox/feishu/          # $CO_INBOX_HOME moves the whole root
├── received.jsonl           # every message, appended
├── sent.jsonl               # every reply, and every send that failed
├── done.jsonl               # what was deliberately not answered
├── new/  cur/               # the queue, and what is claimed
└── log                      # connected, reconnecting, send failed
```

`ls new/` is the unread count. `tail -f received.jsonl` is a live view. You do
not need any command in this skill to read it.

## Exit codes

| exit | means | run next |
|---|---|---|
| 0 | it worked | the tip the command printed |
| 1 | the platform refused, or a listener is already running | `co feishu log` |
| 2 | wrong arguments | `co feishu <verb> --help` |
| 3 | not configured | `co auth feishu` |
| 124 | `receive` waited and no message came | `co feishu ls` |

Every one of these prints a line naming the command to run next. A refusal
that names no command is a bug — report it rather than guessing.

## When it is not set up

`co feishu check` exits 3 and names each missing piece. The usual answer is
`co auth feishu`: it creates the application by QR and writes both values. If
the bot already exists and is already in the groups you need,
`co auth feishu --app-id cli_…` authorizes that one instead, keeping its groups
and permissions — a freshly created application is in no group at all.

`listen` additionally needs the SDK, and says so: `pip install lark-oapi`.

## What this does not do

It does not decide who may command an agent. Anything that can read a file can
read this directory, and the only filter the tool applies is the platform's own
— a group message must @ the bot. Sender allowlists belong to whatever consumes
the directory.

It does not guarantee delivery across a reconnect. As of 1.8.5b1 that gate has
not passed: a message sent while the listener's connection was down was not
recovered in the observed window. Treat a gap as possible message loss until
that is retested.

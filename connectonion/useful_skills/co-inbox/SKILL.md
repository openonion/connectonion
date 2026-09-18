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
| **find out which conversations exist** | `co feishu chats` |
| **read one conversation back** | `co feishu log --chat <id>` |
| watch it work | `co feishu log -f` |
| hold the connection yourself | `co feishu listen` |

`co lark …` is the same verbs against Lark. Pick by where your bot lives; the
credentials are separate (`FEISHU_APP_*` and `LARK_APP_*`).

### Finding a conversation

`send` and `reply` need a chat id, and until you have one there is nothing to
paste. `chats` is where ids come from — one tab-separated row per conversation,
id first, so `cut -f1` gives you exactly the thing the other verbs take:

```bash
$ co whatsapp chats
126121882435737@lid       direct  4  4  2026-09-17T04:59:17Z  Eric Fu  你好
120363410170505910@g.us   group   7  2  2026-09-17T05:00:24Z  Eric Fu  @bot 开始
#  id                     kind    messages  for-us  last activity  who  what
```

`for-us` is how many of them were addressed to the bot — the gap between the two
counts is the conversation happening around it.

Then read one back, including everything that never named the bot:

```bash
co whatsapp log --chat 120363410170505910@g.us -n 50
co whatsapp log --chat 120363410170505910@g.us --since 7d
co whatsapp log --sender "Eric Fu"          # by name or by id
```

A filtered `log` answers from the record and stops; `-f` tails the whole inbox.
`-n` keeps the **most recent** N, because a conversation is read backwards from
its last turn.

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

Ten fields, identical on every provider:

```json
{"id":"om_9f8e","chat":"oc_a1b2","thread":null,"sender":"on_7c6d",
 "sender_name":"Eric Fu","text":"look at today's failed deploys","kind":"text",
 "quoted":null,"mentioned":true,"at":"2026-09-02T10:31:07Z"}
```

`sender_name` is who that id belongs to — WhatsApp senders arrive as
`126121882435737@lid`, which tells nobody who spoke. Empty when the platform has
no name for them; **use `sender` as the key and `sender_name` only to address
somebody**, because a name is not unique and can change.

`chat` is where a reply goes. `id` is all `reply` needs — it looks up the chat
and thread itself. The provider's own payload is not included unless the
listener was started with `--raw`, so contact names and group titles never
reach a prompt by accident.

**`kind` is how you tell a photo from an empty message.** `text` is anything you
can read as words; otherwise it is the platform's own word for what arrived —
`image`, `video`, `audio`, `document`, `sticker`, `location`, `contact`. Those
come through with `text` empty, because the body is not text, and without
`kind` they are indistinguishable from someone sending nothing at all. Answer
them by saying what you cannot read yet rather than by guessing at silence:

```bash
case "$(jq -r .kind <<<"$MESSAGE")" in
  text)  ;;                     # the normal path
  image|video|audio|document)
    echo "I can see you sent a $(jq -r .kind <<<"$MESSAGE"), but I can't read one yet." ;;
  *) exit 0 ;;                  # nothing to say
esac
```

A `kind` this list does not name is still the platform's name for it, lowercased
— new message types appear faster than releases do, and arriving as something
beats arriving as nothing.

**Not everything with a `kind` is somebody typing.** These join the record so a
conversation reads back correctly, and only the ones actually about the bot set
`mentioned`:

| `kind` | what happened | wakes a consumer |
|---|---|---|
| `edit` | they changed a message they already sent | like any message |
| `reaction` | somebody put an emoji on one | never |
| `undecryptable` | a message arrived that could not be decrypted | direct only |
| `joined` | **the bot was added to a group** | yes |
| `group-info` | the group was renamed or reconfigured | never |

`undecryptable` is the one worth handling: the message exists and cannot be
read, which is different from nothing arriving. `joined` is the bot's first
sight of a room — usually the moment to introduce itself.

**`quoted` is what the message is replying to**, and `null` when it is not a
reply. Somebody quoting a line and writing "this one is wrong" gives you three
words and a pronoun; the quote is the noun.

```json
"quoted": {"id":"om_7a1c","sender":"on_9d4e","text":"deploy 41 is live",
           "kind":"text","from_me":true}
```

`from_me` is the field that changes what you do. **Replying to the bot and
replying to somebody else in the same group are different events**, and
"answer when addressed" cannot be implemented without telling them apart — a
reply to another person is group chatter you should stay out of. `mentioned`
already reads this same value, so the two never disagree; use `quoted.from_me`
when you need the reason rather than the verdict.

```bash
QUOTED=$(jq -r '.quoted.text // empty' <<<"$MESSAGE")
[ -n "$QUOTED" ] && PROMPT="They are replying to: $QUOTED"$'\n'"$PROMPT"
```

## The conversation around it

A group asks things across several messages — *"the price sheet is wrong"*,
*"it's missing the cleaning column"*, *"@bot recompute"* — and the bot is handed
only the third. `--context N` adds the N turns before it in that chat:

```bash
co whatsapp receive --context 20
co whatsapp consume --context 20 -- claude -p
```

```json
"context": [
  {"at":"…","from":"them","sender":"on_7c6d","text":"the price sheet is wrong","kind":"text"},
  {"at":"…","from":"them","sender":"on_7c6d","text":"it's missing the cleaning column","kind":"text"},
  {"at":"…","from":"us","sender":"","text":"looking now","kind":"text"}
]
```

Your own replies are in it (`from: "us"`), because a transcript where the bot's
answers are missing reads as though it never responded — a model given that will
apologise for ignoring someone it already helped.

**Opt-in, and zero by default.** Without the flag the line is byte-identical to
before. Context costs tokens, and in a busy group it is also other people's
messages leaving the machine, so it is asked for rather than assumed. Messages
that never named the bot are in it: `mention_only` decides *when you speak*, not
what you are allowed to know.

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

It does not recover a gap without the scope for it. History recovery reads back
what arrived while the listener was down, and that needs the bot scope
`im:message.group_msg`. Without it every pass fails, the checkpoint is held
rather than advanced, and `co <provider> check` exits 1 and prints a link that
grants it — so check that before reporting a gap as message loss. Measured on a
live tenant 2026-09-15: with the scope, a message posted during a 90-second gap
was recovered and queued exactly once.

It does not recover a conversation this inbox has never seen. Recovery reconciles
only chats already in `received.jsonl`, and in a group it admits only messages
that mention the bot — unrelated discussion during a gap is dropped on purpose,
not lost.

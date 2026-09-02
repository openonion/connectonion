# Feishu and Lark CLI (`co feishu`, `co lark`)

Turn a Feishu bot into a directory of files. Every message someone sends the
bot becomes one line in a log and one file in a queue; anything that can read
a file can answer it. `co lark` is the same tool against Lark (Feishu outside
China) with its own credentials.

This calls Feishu directly through the official SDK's long connection. It
dials out, so it runs on a laptop behind NAT with no public address, no
OpenOnion credential, and nothing billed.

## Setup

1. Create a self-built application at <https://open.feishu.cn/app> (Lark:
   <https://open.larksuite.com/app>). Enable the **bot** capability.
2. Under *Permissions* add `im:message.group_at_msg:readonly` (group messages
   that @ the bot) and `im:message:send_as_bot` (reply). Add
   `im:message.p2p_msg:readonly` if people will message the bot directly.
3. Under *Events*, choose **long connection** and subscribe to
   `im.message.receive_v1`. No request URL is needed.
4. Publish the application to your tenant, then put its credentials in your
   global credential file:

   ```dotenv
   # ~/.co/keys.env
   FEISHU_APP_ID=cli_xxx
   FEISHU_APP_SECRET=xxx
   # Lark uses its own pair
   LARK_APP_ID=cli_yyy
   LARK_APP_SECRET=yyy
   ```

5. Install the SDK and check:

   ```bash
   pip install lark-oapi
   co feishu check
   ```

`check` exits 3 and names the missing item if anything above is incomplete.
Add the bot to a group, @ it, and it is listening.

## The directory

```text
~/.co/feishu/
├── inbox.jsonl      every message received, one JSON line, appended, never deleted
├── outbox.jsonl     every message sent, and every send that failed
├── new/             messages nobody has taken yet, one file each
│   └── 1756808267-om_9f8e
├── cur/             taken but not yet replied; back to new/ after an hour
├── log              the tool's own log: connected, reconnecting, send failed
└── listen.lock      pid of the running listener
```

The file in `new/` and the line in `inbox.jsonl` are the same bytes:

```json
{"id":"om_9f8e","chat":"oc_a1b2","thread":null,"sender":"on_7c6d",
 "text":"@OpsAgent look at today's failed deploys","mentioned":true,"at":"2026-09-02T10:31:07Z"}
```

`chat` is where it came from; reply there and the answer lands beside the
question. `sender` is the person's `union_id`. `mentioned` is whether the bot
was @'d (always true in a direct message). Nothing else from Feishu is kept
unless you start `listen --raw`, so group titles and contact cards never reach
a prompt by accident.

You do not need the commands below to consume it:

```bash
ls ~/.co/feishu/new/                      # how many are waiting
tail -f ~/.co/feishu/inbox.jsonl          # watch live
grep on_7c6d ~/.co/feishu/inbox.jsonl | jq -r .text
mv ~/.co/feishu/new/X ~/.co/feishu/cur/   # take one; rename is atomic, two takers never collide
```

A second application gets its own directory: `CO_FEISHU_HOME=~/.co/feishu-ops co feishu listen`.

## The verbs

```bash
co feishu listen                 # hold the connection, write the directory; Ctrl-C stops
co feishu receive                # block until a message arrives, take it, print it as one JSON line
co feishu receive -t 300         # give up after 5 minutes (exit 124, like timeout(1)); -t 0 looks once
co feishu send oc_a1b2 "all green"
echo "all green" | co feishu send oc_a1b2          # text from stdin, like mail
co feishu reply om_9f8e "fixed"                     # back to the chat and thread that message came from
co feishu check                  # credentials, connectivity, listener, unread; exit 3 on a problem
co feishu ls                     # unread: id, chat, sender, text
co feishu log -f                 # inbox.jsonl, following
```

`receive` starts a background `listen` if none is running, so there is no
daemon to remember. `listen` in the foreground is for watching it work and
for `systemd`; one listener per directory.

`reply ID` needs only the id: chat and thread are read from `inbox.jsonl`. It
refuses to answer the same message twice unless you pass `--again`, so a loop
that re-runs cannot double-post. `send` and `reply` print the id Feishu gave
the new message and exit 1 with Feishu's own reason if it was refused.

## Any agent, two lines

```bash
m=$(co feishu receive)                       # {"id":"om_9f8e","chat":"oc_a1b2","text":"...",...}
echo "done, all green" | co feishu reply om_9f8e
```

Or let the tool run the loop for you:

```bash
co feishu serve -- claude -p                 # one claude per message; its stdout is the reply
co feishu serve -- codex exec -
co feishu serve -- ./answer.sh
```

`serve` runs the command with the message JSON on stdin and these variables:
`CO_PROVIDER`, `CO_CHAT`, `CO_THREAD`, `CO_SENDER`, `CO_MSG_ID`, and
`CO_CHAT_DIR` (a per-chat directory the command may keep its own state in).
Non-empty stdout is sent back as the reply; empty stdout or a non-zero exit
sends nothing and is noted in `log`.

## What the tool does for you

- Acknowledges Feishu within its three-second window by doing nothing in the
  handler but writing the two files; the agent runs elsewhere.
- Writes the log line and the queue file before acknowledging, so a crash
  after the acknowledgement loses nothing.
- Drops redelivered messages by id, against the log, so a duplicate is dropped
  after a restart too.
- Returns a taken-but-unanswered message to `new/` after an hour, so a
  consumer that died mid-task does not make it vanish.
- Reconnects on its own and writes each attempt to `log`.
- Retries a rate-limited send three times with backoff. Feishu allows five
  messages per second per group, shared with every bot in that group.

## The free edition's API quota

Feishu's free edition (基础免费版) caps **all self-built apps in a tenant,
together, at 10,000 counted API calls a month** since November 2024, and
refuses counted calls for the rest of the month once it is spent (error
`99991403`). Paid editions lift it. Feishu raised the free cap to 1,000,000
in June 2026 as a limited-time change; the admin console (管理后台 > 费用中心
> 权益数据) shows the number that applies to you today.

What this tool spends, per Feishu's own list of what counts:

| call | counted? | when |
|---|---|---|
| receiving a message over the long connection | no (event subscription) | every message |
| `tenant_access_token` | no (authentication) | every process, at most once |
| `bot/v3/info` | yes | once per `listen` start and per `check` |
| `messages/{id}/reply`, `messages` (send) | yes | once per `reply` or `send` |

So 10,000 a month is 10,000 replies, and listening costs nothing. Do not poll
`check` on a timer: a bot that probed itself every minute is how others burnt
the whole month in a week.

## What it does not do

It does not decide who may command an agent. Feishu's `group_at_msg` scope
already limits what reaches the bot to messages that @ it; anything finer,
such as an allowlist of senders, belongs to whatever consumes the directory.
It does not carry images, files or cards (a non-text message arrives as its
type in brackets, `[image]`), and it does not stream partial replies.

Messages are plain text on disk in a directory only you can read. The log
grows; rotate it with `logrotate` like any other.

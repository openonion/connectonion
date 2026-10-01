# Slack CLI (`co slack`)

> **Experimental.** `co slack` was tested against fakes, not yet a live
> workspace. Edit, delete and react are not implemented and say so. It is in
> 1.8.9 so people can try listen and reply on a workspace of their own; tell us
> what breaks. The read verbs (`channels`, `history`, `thread`, `search`) and
> `co auth slack` are newer still and equally untested on a live workspace.

Turn a Slack app you own into a directory of files. Every message your bot can
see becomes one line in a log and one file in a queue; anything that can read a
file can answer it. The same verbs as [`co discord`](discord.md), against a
different platform.

```bash
co slack check                          # both tokens, listener, connection, unread count
co slack listen                         # hold the Socket Mode connection; every message → ~/.co/inbox/slack/
co slack receive                        # block for the next message, take it, print one JSON line
echo "on it" | co slack reply C0123456789:1727500000.123456   # a reply, in that message's thread
co slack send C0123456789 "deployment finished"
co slack done C0123456789:1727500000.123456   # took it, decided not to answer
co slack consume -- claude -p           # one command per message, stdout is the reply
co slack ls                             # what is waiting
co slack chats                          # which channels have spoken
co slack log -f                         # everything, as it arrives

co slack channels                       # the channels and DMs the bot is in, from Slack
co slack history ops -n 20              # what #ops said lately, oldest first
co slack thread C0123456789:1727500000.123456   # a message and its replies
co slack search "deploy failed" --in ops       # needs SLACK_USER_TOKEN
```

The listener uses Slack's **Socket Mode**: it dials out to Slack over a
WebSocket, so there is no public URL, no port opened, and no OpenOnion
credential involved.

## Setup

```bash
co auth slack
```

It prints a link that creates the app from a manifest already filled in:
Socket Mode on, the events subscribed, the Messages tab on, and every scope the
inbox and the read verbs need. Then three clicks and three pastes:

1. Open the link, pick your workspace, click **Create**. (If the form opens
   empty, choose **From a manifest** → JSON and paste the manifest it printed.)
2. **Install App** → **Install to Workspace** → **Allow**. Copy the **Bot User
   OAuth Token** (`xoxb-…`) and, for `co slack search`, the **User OAuth Token**
   (`xoxp-…`).
3. **Basic Information** → **App-Level Tokens** → **Generate Token and Scopes**,
   add `connections:write`, and copy the `xapp-…` token. A manifest cannot make
   this one.

Each token is asked for at a hidden prompt, never as an argument (it would sit
in your shell history). Without a terminal, pipe them in, in any order; the
prefixes tell them apart:

```bash
printf '%s\n' "$BOT" "$APP" "$USER" | co auth slack
```

Every token is checked with Slack before anything is written: `auth.test` for
the bot and user tokens, `apps.connections.open` for the app-level token. One
that Slack rejects exits 1 and saves nothing. Scopes a token lacks (read from
Slack's `x-oauth-scopes` header) are listed with the step that adds them, and
the tokens that work are saved anyway. They go to the selected env file
(`~/.co/keys.env` unless `co --env-file` says otherwise):

```dotenv
SLACK_BOT_TOKEN=xoxb-...     # reads channels, posts replies
SLACK_APP_TOKEN=xapp-...     # opens the Socket Mode connection
SLACK_USER_TOKEN=xoxp-...    # optional: co slack search runs as you
```

Press Enter at a prompt to keep the token already set, so running it again to
add the user token later changes nothing else.

Then invite the bot to every channel it should hear or read:
`/invite @YourBot` in that channel. `co slack check` tests both tokens, and
names any read scope the bot token is missing.

The tokens are read only by the local process. They are never sent to
OpenOnion, never written into the inbox, and never included in an error.
`co status` and `co keys` show whether they were found and hide their values.

### By hand

The manifest is the same app you would build by hand:

| where in the app settings | what |
|---|---|
| Socket Mode | on, with an app-level token that has `connections:write` |
| OAuth & Permissions → Bot Token Scopes | `chat:write`, `app_mentions:read`, `im:history`, `channels:history`, and for the read verbs `channels:read`, `groups:read`, `im:read`, `groups:history`, `users:read` |
| OAuth & Permissions → User Token Scopes | `search:read`, `users:read` (only for `co slack search`) |
| Event Subscriptions → bot events | `message.im`, `app_mention`, and optionally `message.channels` |
| App Home | Messages Tab on, with "Allow users to send … messages" ticked |

Any time you change scopes, Slack asks you to reinstall; do it, or the new scope
is not in the token.

## What lands

- **A direct message to the bot**: always, with `mentioned: true`.
- **A channel message that @mentions the bot**: always, with `mentioned: true`.
- **A message in a thread the bot started or has replied in**: when
  `message.channels` is subscribed, with `mentioned: true`, so a conversation
  can continue without an @mention on every turn.
- **Any other channel message** the bot can see (with `message.channels`):
  written with `mentioned: false`, like Discord, so `log` and `chats` still show
  the room; `co ai` and `consume` answer only what is addressed to the bot.
- **Never**: messages from bots (including this one), edits, deletions, joins,
  and other system subtypes.

With `message.channels` and `app_mention` both on, Slack sends an @mention
twice, once as each event. Both have the same id, so the inbox keeps one.

## What a message looks like

```json
{"id":"C0123456789:1727500000.123456","chat":"C0123456789","thread":"1727499000.000100",
 "sender":"U0123456789","sender_name":"","text":"<@U0BOT00000> check the failed deployment",
 "kind":"text","quoted":null,"mentioned":true,"at":"2024-09-28T05:06:40Z"}
```

- **`id`** is `<channel>:<ts>`. Slack's `ts` is unique only within a channel,
  so the channel is part of the id.
- **`chat`** is the channel id: `D…` for a direct message, `C…` for a channel,
  `G…` for a private one.
- **`thread`** is the thread's root `ts` when the message is in a thread, else
  `null`.
- **`sender_name`** is filled only when Slack includes a profile in the event;
  looking names up would need another scope, so it does not.
- **`kind`** is `text`, or `image` / `audio` / `video` / `document` for a file
  shared with no text; the text is then `[image]` and so on. The file is not
  downloaded (that would need `files:read`).

## Sending

`co slack reply <id>` answers **in the thread** of the message: in the thread
it came from, or a new thread under it if it was a top-level message. That is
Slack's own advice (reply to the thread's root, never to a reply). `co slack
send <channel> "text"` posts at the top of the channel; add `--reply-to <id>`
to post in that message's thread instead.

The text goes to Slack as typed: Slack reads its own *mrkdwn* (`*bold*`,
`<https://x|link>`, `<@U123>` to mention someone), not Markdown.

Slack advises keeping a message under 4,000 characters and truncates one over
40,000 rather than refusing it. `co slack` refuses anything over 40,000 before
anything is sent, because a silently cut answer is worse than an error; under
that, a long message shows with Slack's "Show more". One rate limit (HTTP 429)
is waited out, as long as Slack's `Retry-After` says (at most 30 seconds), and
retried; a second is reported.

Slack has no idempotency key for a post (Discord's nonce has no Slack
equivalent). If a reply times out after Slack accepted it, retrying it posts it
a second time; look at the thread first.

`co slack edit`, `delete` and `react` exist so the verbs match every other
provider, and say plainly that they are not wired up for Slack yet.

## Reading the workspace

The inbox only has what arrived while a listener ran, and only what was
addressed to the bot or said where it listens. `channels`, `history`, `thread`
and `search` ask Slack directly, through its Web API, so an agent can answer
"what did #ops say about the deploy today?" without having been there.

```bash
co slack channels                        # id, #name or @person, kind, member count
co slack history ops -n 50               # latest 50, oldest first
co slack thread C0123456789:1727500000.123456
co slack search "deploy failed" --in ops --from alice -n 10
```

Each message prints as its local time, author, id and reply count, then its
text indented beneath:

```text
2024-09-28 15:10  Alice  C0123456789:1727500200.000200  (2 replies)
  @Bob deploy failed on staging
```

`--json` prints the same as one object per line, in the inbox's own field names:

```json
{"id":"C0123456789:1727500200.000200","chat":"C0123456789","thread":null,"at":"2024-09-28T05:10:00Z",
 "sender":"U0ALICE001","sender_name":"Alice","text":"@Bob deploy failed on staging","replies":2}
```

- **Names, not ids.** Authors and `<@U…>` mentions are shown by display name,
  looked up once per person per run (`users.info`, which is why `users:read`
  is in the manifest).
- **Channels by name.** `history` and `thread` take an id or a name: `ops`, or
  `'#ops'` in quotes, because an unquoted `#` starts a comment in bash.
- **Answering what you read.** The ids are the inbox's own `<channel>:<ts>`.
  `co slack send <channel> "text" --reply-to <id>` answers in that message's
  thread. `co slack reply` is for messages the inbox received, since it marks
  them answered there.
- **Threads.** `thread` given the id of a reply reads the whole thread from its
  root. `history` shows a thread's first message with its reply count; the
  replies themselves are in `thread`.
- **Search runs as you.** Slack's `search.messages` refuses bot tokens, so
  `search` uses `SLACK_USER_TOKEN` (`xoxp-`, scopes `search:read` and
  `users:read`) and sees what you can see, not just the bot's channels.
  Without that token it exits 1 and says how to add it. `--in` and `--from`
  become Slack's own `in:#ops` and `from:@alice`; other modifiers (`before:`,
  `has:link`) can go in the text.

The [co-slack skill](../../connectonion/useful_skills/co-slack/SKILL.md) walks
an agent through the two common asks: "what did #ops say today" and "find the
message about X and reply in its thread".

Everything here is read-only. When Slack refuses, the error says why and what
to run next, and the command exits 1:

| Slack says | means | next |
|---|---|---|
| `missing_scope` | the token lacks the scope Slack names | add it under OAuth & Permissions, Reinstall to Workspace, `co slack check` |
| `not_in_channel` | the bot was never invited | `/invite @YourBot` in that channel |
| `channel_not_found` | no such channel for this token | `co slack channels` |
| `invalid_auth`, `token_revoked` | the token no longer works | `co auth slack` |

One rate limit (HTTP 429) is waited out as long as Slack's `Retry-After` says,
at most 30 seconds; a second is reported.

## When the connection drops

Every event Slack sends is acknowledged by its envelope id **after** it is
written to the inbox. If the write fails (a full disk), Slack is not told, so it
sends the event again; a message the inbox already has is logged as a
duplicate and not queued twice.

Slack refreshes a Socket Mode connection every few hours: it sends a
`disconnect` message, and the listener asks for a new URL and reconnects. A
dropped network does the same, with backoff up to 30 seconds. Nothing is
replayed across a full restart of the listener beyond what Slack itself
retries.

Some failures no reconnect can fix, and those end `listen` with exit 3 and the
thing to do: a token Slack rejects (`invalid_auth`, `token_revoked`), an
`xoxb-` token where the `xapp-` one belongs (`not_allowed_token_type`), and
Socket Mode being switched off in the app settings (`link_disabled`).

## Upgrades reach the listener

A running listener keeps the code it started with, so after an upgrade it
restarts itself in place once no send is in flight, and `check` names both
versions while they differ. A listener started before version tracking cannot
do that; replace it with one command:

```bash
co slack listen --restart     # stop the running listener, start a background one on the installed code
```

The details are the same for every provider; see
[WhatsApp: Upgrades reach the listener](whatsapp.md#upgrades-reach-the-listener).

To have your own agent answer, list the channel in `~/.co/host.yaml` under
`listen:` as `slack` and run `co ai`, exactly as for Feishu.

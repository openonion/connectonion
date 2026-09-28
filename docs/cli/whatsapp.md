# WhatsApp CLI (`co whatsapp`)

Turn a WhatsApp number into a directory of files. Every message the number
receives — including in groups a person created and added it to — becomes one
line in a log and one file in a queue; anything that can read a file can answer
it. The same nine verbs as `co feishu`, against a different platform.

```bash
pip install 'connectonion[whatsapp]'
brew install libmagic                  # a system library pip cannot supply; see Setup
co whatsapp listen                     # scan the QR once; every message → ~/.co/inbox/whatsapp/
co whatsapp receive                    # next message as one JSON line
echo "on it" | co whatsapp reply 3EB0A1
co whatsapp consume -- claude -p       # one command per message, stdout is the reply
```

## Read this before you link a number

This links a **companion device**, the same mechanism as WhatsApp Web: the
phone stays the account, and this becomes one of the four devices it allows
alongside itself. That has two consequences worth knowing before you scan
anything.

**Use a number you have dedicated to this.** Never a personal number, never an
employee's main number. A linked device sees every chat the number is in, so
pointing it at a personal number puts that person's private conversations
through your queue and, if you wire an agent to it, through a model. Buy a SIM
or use a spare handset.

**WhatsApp's terms do not cover this.** Automated use of the consumer client is
against the Business Messaging Policy, and Meta bans numbers for it. Nobody can
promise you a number will survive. That is the price of the one thing the
official API cannot do, and it is why this is an extra you opt into rather than
something installed by default.

## Why not the official API

The WhatsApp Cloud API is the supported route and it is genuinely better —
until you need groups. It cannot join a group a human created; there is no join
endpoint at all. It can only create groups itself, they cap at 8 participants,
and creating them at all requires an Official Business Account, which is
granted on merit and filed through a solutions provider. If your use is "a bot
sits in the customer group we already made and answers when we @ it", the Cloud
API has no path to it. This does.

Use the Cloud API instead whenever you can: one-to-one customer messaging,
notifications, anything you would ship to your own users.

## Setup

```bash
pip install 'connectonion[whatsapp]'

# …and libmagic, which the extra cannot install for you:
brew install libmagic        # macOS
apt install libmagic1        # Debian/Ubuntu
dnf install file-libs        # Fedora/RHEL
pip install python-magic-bin # Windows (this one does bundle the library)

co whatsapp listen
```

The extra installs neonize, which imports `python-magic` — a *binding* to the
system library `libmagic`. pip installs the binding; the library it binds to
comes from the OS. So `pip install 'connectonion[whatsapp]'` succeeds and the
first `co whatsapp listen` still stops, with libmagic named and the command for
your platform. Install it once and it does not come back.

A QR code appears in the terminal. On the phone, **Settings → Linked devices →
Link a device**, and scan it. The pairing is stored at
`~/.co/inbox/whatsapp/session.db` (or wherever `WHATSAPP_SESSION` points) and
that file *is* the linked device: copy it and you have copied the device,
delete it and the device is unlinked. It is created mode 0700 with the rest of
the inbox.

```bash
co whatsapp check                # says what is missing, if anything
```

`check` exits 3 and names the missing item: the extra, an unlinked device, or a
bundled protocol implementation old enough to start failing.

## The directory

```
~/.co/inbox/whatsapp/
├── received.jsonl      every message ever received
├── sent.jsonl          every reply
├── own.jsonl           what the account owner typed on their phone (a record, never queued)
├── new/                unread, one file each
├── cur/                taken by a consumer
├── outbox/             replies waiting for the listener (see below)
├── media/              photos, documents and voice notes, as they arrived
├── session.db          the linked device
└── log
```

Identical to every other provider — [DD-063](../design-decisions/063-one-directory-three-verbs.md)
has the interface, and [feishu.md](feishu.md) documents the verbs in full,
because they behave the same here.

`chat` is the group JID (`1203630000000@g.us`) for a group message and the
peer's JID (`447700900123@s.whatsapp.net`) for a direct one, so `reply` lands
where the question was asked either way.

## Photos, documents and voice notes

A media message arrives with `kind` set to what it is — `image`, `video`,
`audio`, `document`, `sticker` — and the bytes are fetched as it arrives, into
`media/`. The record names the file:

```json
{"id":"3EB0…","chat":"447700900123@s.whatsapp.net","kind":"image","text":"",
 "media":{"path":"/Users/you/.co/inbox/whatsapp/media/3EB0….jpg",
          "mime":"image/jpeg","size":184320}}
```

So a consumer that receives this can open the file, and one that cannot read
images can at least say which file it is declining to read.

**Why at arrival and not on demand.** The media keys live in the protobuf
envelope, and the queue record does not keep it, so a later `download <id>`
would have nothing to download from. WhatsApp also drops media from its own
servers after a while. The moment the message arrives is the only moment the
file is reliably reachable.

**When it fails, it says so.** An expired or unreachable file leaves
`{"media":{"error":"…"}}` on the record and a line in `log`, and writes no
file — a zero-byte document is worse than an error, because a consumer reads
it as an empty document. Anything over 64 MB is refused the same way rather
than filling the disk the inbox lives on.

**What `kind` means.** It names what a person sent: `text`, `image`, `audio`
and so on. WhatsApp also attaches delivery metadata to messages
(`messageContextInfo` on nearly every group message, and a
`senderKeyDistributionMessage` the first time someone posts to a group). That
metadata never names the kind. Until #1858 it did, and 46% of one owner's
group messages arrived as `kind: "messagecontextinfo"`, so a consumer that
answered only `text` skipped them. A frame that carries nothing but that
metadata is not a message and is not recorded. Before #1837 it was recorded,
and because the sender's real first message shares its id, the real message
was then dropped as a duplicate.

## Groups: when the bot answers

In a group, `mentioned` is true when the message @-mentions the linked number,
replies to something it said, or writes its number in the text. In a direct
message it is always true. Set `mention_only` on the channel and the agent
answers only those; leave it off and it answers everything in the group.

Until the connection is up the number is not yet known, so nothing in a group
counts as addressed. A `mention_only` channel stays quiet for that moment
rather than answering everyone in it.

## Sending needs the listener running

WhatsApp allows one connection per linked device. There is no REST endpoint to
post to — every byte rides the socket `co whatsapp listen` is holding, and a
second process opening the same session would present the same device identity
and take the connection away from the listener.

So `co whatsapp send` and `co whatsapp reply` do not connect. They write the
text to `outbox/`, the listener picks it up and sends it, and the answer comes
back the same way. With no listener running they start one in the background
first, the way `receive` does (#1860). Before that, 5 of one owner's 7 failed
sends were a 30-second wait for a listener nobody had started. If the listener
cannot start, or starts and never answers, `send` says so:

```
No listener answered in 30s, so nothing was sent. WhatsApp allows one connection
per linked device, so sending goes through the listener rather than opening a
second one. Next: co whatsapp listen
```

"Nothing was sent" is a promise, and it holds. Before the failure is printed the
request is withdrawn from `outbox/` in one atomic step; the listener claims a
request with the same kind of step, so exactly one of them has it. If the
listener got there first, `send` waits for its answer instead of reporting a
failure. A request whose sender is gone — killed, or long since told it failed —
is thrown away by the next listener with a line in `log`, never sent late.

So `send` and `reply` work without the extra installed while a listener is
running. With no listener and no extra, nothing could ever send, so they exit 3
at once and print the pip command, as `check` does.

## Upgrades reach the listener

A listener is a long-running process, and upgrading `co` does not change the
code a running process has loaded. One owner's listener ran from 21 September
through six releases. The media download added on the 22nd never ran for it,
so every photo anyone sent arrived with no file, while `check` said all was
well (#1859). This applies to every provider's `listen`, not only WhatsApp.

- The listener records the version it started with in `listener.json`.
- Once a minute it compares that with the installed version. After an upgrade
  it restarts itself in place (same pid, same session file, no re-pairing),
  waiting until no send is in flight. The log says `installed 1.8.9b15,
  running 1.8.9b13: restarting`. WhatsApp holds messages for an offline device
  and delivers them on reconnect, so nothing is lost in the gap.
- `check` names both versions while they differ.
- A restarted or auto-started listener keeps the flags the last one was
  started with (`--raw`), recorded in `listener.json` (#1882). Before, a
  replacement came back bare, and the raw archive and real names quietly
  stopped.
- Every listener exit leaves a line in `log`: `stopped by SIGTERM`,
  `stopped by listen --restart (pid N)`, or the exception. `--restart` stops a
  listener running in the foreground (a tmux pane, say) and starts the new one
  in the background; it says so.
- The background listener starts in the inbox directory, so a connectonion
  checkout in whatever directory you ran the command from is never what it
  loads (#1878). A restart is tried once per installed version: if the
  versions still differ after it, the log says so and it is not retried.
- A listener started before this existed cannot restart itself. `check` says
  `listener started before version tracking`, and one command replaces it:

```bash
co whatsapp listen --restart     # stop the running listener, start a background one
```

## Sending photos and files

```bash
co whatsapp send 447700900123@s.whatsapp.net --image ./shortlist.png "Tonight's three options"
co whatsapp send 447700900123@s.whatsapp.net --file ./itinerary.pdf
co whatsapp send 120363…@g.us --image ./map.png --reply-to 3EB0C127D8F1A2B4E5F6
co whatsapp reply 3EB0C127D8F1A2B4E5F6 --image ./map.png "Here it is"
```

A rating card, a map screenshot or a rendered itinerary used to be flattened
into a wall of text, and data-heavy text is exactly what people skip in a group
chat (#1856).

- `--image PATH` sends a photo: JPEG, PNG or WebP, up to 16 MB, shown inline in
  the chat. Any other type, or a bigger picture, goes as `--file`.
- `--file PATH` sends any file up to 100 MB as a document, with its file name
  and type, so the phone offers to open it.
- The text is the caption. It is optional, and it is read as Markdown like any
  send unless `--plain`. With `--image` or `--file` an omitted caption means no
  caption: stdin is not read, so a script cannot hang waiting for one.
- `reply MESSAGE_ID --image PATH` / `--file PATH` answers a received message with
  an attachment, in its chat and quoting it, the way an agent answers text.
- `--reply-to` quotes a message, as with text. `react` and `delete` work on the
  id it prints. `edit` changes text only, so it does not apply.
- It goes through the same `outbox/` as text, and like text starts a listener
  when none is running.
  The request carries the file's absolute path and the listener reads the file
  from there; the file only has to stay put until the id is printed.
- Checked before anything is queued: a missing or empty file, both options at
  once, a picture WhatsApp will not show inline, or a file over the limit exits
  1 with a sentence naming the fix. Nothing is sent.
- `sent.jsonl` records the caption as `text` and the attachment as
  `media: {kind, path, size}`, so `log` shows what went out.

`co feishu send`, `co lark send`, `co discord send` and `co slack send` accept the same two
options and refuse them, sending nothing; only WhatsApp implements them so far.

## The protocol snapshot

The extra pins `neonize` exactly rather than with `>=`. The wheel carries a
compiled snapshot of whatsmeow's WhatsApp protocol implementation, so a version
bump is a protocol change and deserves to be a deliberate one.

The flip side is that the snapshot goes stale, and WhatsApp changing something
under an old one fails in ways that do not name themselves. `check` reads the
snapshot's date out of the shared library and says so once it is more than six
months old.

## Environment

| Variable | Default | What it does |
|---|---|---|
| `WHATSAPP_SESSION` | `~/.co/inbox/whatsapp/session.db` | Where the linked device is stored |
| `CO_INBOX_HOME` | `~/.co/inbox` | Moves the whole inbox root, every provider with it |

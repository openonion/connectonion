# Outlook CLI (co outlook)

Manage email, contacts and your calendar from your Outlook account right in
the terminal — the same Microsoft Graph access your agents get from the
[Outlook tool](../useful_tools/outlook.md) and the
[Microsoft Calendar tool](../useful_tools/microsoft_calendar.md), as commands.

Outlook is one product with three panes — Mail, Calendar, People — and
`co outlook --help` is grouped the same way: **Mail**, **Send**,
**Scheduled sends**, **Contacts**, **Calendar**.

## Quick Start

```bash
# Connect your Microsoft account (one-time)
co auth microsoft

# Check your inbox (the zero-arg default)
co outlook

# Read message #3 from the inbox list
co outlook read 3
co outlook read 3 --mark-read

# Send a message
co outlook send alice@example.com "Hello" "Thanks for the meeting today!"

# Save and find contacts
co outlook contact add "Zhou Yifei" zhou@example.com
co outlook contact search yifei

# Your calendar
co outlook calendar today
co outlook calendar teams "Design review" 2026-09-10T10:00:00Z 2026-09-10T11:00:00Z --attendees a@x.com --yes
```

That's the whole surface. Everything below is detail. Every command ends by
naming the next one — including when its output is piped — so an agent driving
`co outlook` never has to guess a command name.

## Setup

`co outlook` needs a connected Microsoft account:

```bash
co auth microsoft
```

This opens the Microsoft OAuth flow and saves `MICROSOFT_*` credentials
(access token, refresh token, scopes, email, expiry) to the global
`~/.co/keys.env`, or to the file named by `co --env-file PATH auth microsoft`.
A project directory never selects credentials on its own.

The stored access token is used for as long as it is valid; a refresh happens
only within five minutes of its expiry or after Microsoft Graph answers 401.
Before 1.8.4 every command discarded the stored token and went through the
refresh broker first, so an oo-api outage made a perfectly reachable mailbox
look expired (#1312).

Microsoft credentials remain CLI-local. oo-api performs the OAuth exchange and
refresh as a stateless proxy, while Outlook saves rotated tokens back to the
selected env file; the backend does not retain the token pair.

Contact commands require `Contacts.ReadWrite` and calendar commands require
`Calendars`. If you authenticated before those were requested, run
`co auth microsoft` once more to grant them — a refresh cannot widen scopes.
See [Microsoft Integration](../integrations/microsoft.md) for all requested
scopes.

## Commands

### `co outlook contact` — Manage contacts

Contacts start deliberately small: a display name and one email address.

```bash
# Create
co outlook contact add "Zhou Yifei" zhou@example.com

# List (25 by default)
co outlook contact list
co outlook contact list -n 50

# Find by a case-insensitive name or email substring
co outlook contact search yifei
co outlook contact search gmail.com -n 10
```

`list` and `search` print a Rich table in a terminal. When output is piped,
each contact is a tab-separated `name`, `email`, and full Microsoft Graph ID,
so scripts do not receive truncated values.

### `co outlook` — Show the inbox

With no subcommand, prints your most recent emails. Same as `co outlook inbox`.

```bash
co outlook
```

### `co outlook inbox` — List received email

```bash
co outlook inbox                 # last 10
co outlook inbox -n 25           # last 25  (alias: --last)
co outlook inbox -u              # only unread  (alias: --unread)
```

Unread messages are marked with a green `●`. The leftmost `#` is the email's
number — pass it to `co outlook read`. The numbering is cached (in
`~/.co/outlook_last_inbox.json`), so `read 3` still finds the right message
in a later shell session.

**Options**
- `--last, -n` — how many to show (default: 10)
- `--unread, -u` — only unread messages

### `co outlook read <#>` — Read one message

```bash
co outlook read 3
co outlook read 3 --mark-read
```

Prints the full body (sender, subject, date, content). Accepts the `#` from
your last listing (inbox or search) or a full Graph message ID. The message is
left unread by default. Use `--mark-read` when opening it should consume it;
that opt-in needs the `Mail.ReadWrite` scope.

### `co outlook reply <#> <message>` — Reply

```bash
co outlook reply 3 "Sounds good, see you then."
```

Sends a threaded reply to an email from your last listing. Use `-` as the
message to read the reply body from stdin, and `--at +2h` (or a UTC ISO
time) to schedule the reply like a scheduled send. A scheduled reply is a
reply draft that Exchange holds until then, so it needs the `Mail.ReadWrite`
scope and shows up in `co outlook scheduled` like any other scheduled send.

**Options**
- `--cc` — CC recipients (comma-separated); the reply stays in its thread
- `--bcc` — BCC recipients (comma-separated)
- `--attach, -a FILE` — attach a local file; repeat for multiple
- `--at` — schedule delivery: `+30m`, `+2h`, or a UTC ISO time

**Copying a third person** — `--cc` and `--bcc` are set on Graph's reply
action (or on the deferred reply draft when `--at` is used), so the message
keeps its `In-Reply-To` / `References` headers and lands in the existing
conversation. Before 1.8.4b1 the only way to copy someone was a fresh
`co outlook send` with "RE:" in the subject, which the recipient saw as a new,
history-less thread (#1247):

```bash
co outlook reply 3 "Looping in Sam so he has the context." --cc sam@example.com
```

**Attachments** — same files, limit, and flag as `send`, still a real reply:

```bash
co outlook reply 3 "Signed copy attached." \
    --attach signed.pdf --attach cover.png
```

The files ride on Graph's reply action, so the message stays in the original
conversation instead of going out as a new email. Attachments and `--at`
combine — a scheduled reply keeps its files (they are added to the reply
draft before it is scheduled).

### `co outlook send <to> <subject> <message>` — Send

```bash
co outlook send bob@example.com "Subject line" "Body text"
```

All three arguments are positional and required. `to`, `--cc`, and `--bcc`
take comma-separated addresses for multiple recipients.

**Options**
- `--cc` — CC recipients (comma-separated)
- `--bcc` — BCC recipients (comma-separated)
- `--attach, -a FILE` — attach a local file; repeat for multiple
- `--at` — schedule delivery: `+30m`, `+2h`, or a UTC ISO time

**Attachments** — screenshots, PDFs, images, anything:

```bash
co outlook send bob@example.com "Report" "See attached." \
    --attach report.pdf --attach screenshot.png
```

> Graph's `sendMail` limit is ~3MB total across attachments. A human invoking
> the CLI may explicitly name a file outside the project; agent-facing
> `Outlook()` tools remain limited to project files.

**Scheduling** — the message is created as a draft carrying a deferred-send
time, and Exchange holds it until then. Creating the draft needs the
`Mail.ReadWrite` scope, which `co auth microsoft` grants by default; a token
issued before that scope was added needs one more `co auth microsoft`:

```bash
co outlook send bob@example.com "Reminder" "Standup in 30." --at +30m
co outlook send bob@example.com "Launch" "We're live!" --at 2026-07-06T15:30:00Z
```

`+30m` / `+2h` are relative to now; anything else is taken as a UTC ISO time.
The confirmation names the way back, because a scheduled send is the one you
are most likely to want to take back (#1314):

```
✓ Scheduled for 2026-09-09T22:30:00Z to bob@example.com
  From: you@example.com
  Cancel before it goes out: co outlook scheduled, then co outlook cancel <#>
Next: co outlook scheduled
```

**Long bodies** — pass `-` as the message to read the body from stdin:

```bash
co outlook send alice@example.com "Weekly update" - < body.txt
```

### `co outlook sent` — List sent email

```bash
co outlook sent            # last 10
co outlook sent -n 25      # last 25
```

### `co outlook search <query>` — Search

```bash
co outlook search "quarterly report"
co outlook search invoice -n 25
```

Matches subject and body via Microsoft Graph search.

### `co outlook scheduled` / `co outlook cancel <#>` — Manage scheduled sends

```bash
co outlook scheduled      # what's queued, and when it sends
co outlook cancel 1       # cancel it before Exchange sends it
```

Shows every email waiting for scheduled delivery (deferred-send drafts),
numbered for cancel, with recipient, subject, and local send time:

```
                     ⏰ Outlook — scheduled sends
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ To                          ┃ Subject                ┃ Sends at     ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ tamara.berryman@unsw.edu.au │ RE: Access to the MCIC │ Jul 07 08:00 │
└─────────────────────────────┴────────────────────────┴──────────────┘
```

Scheduled emails sit in Drafts until delivery time; `cancel` deletes the
pending message so it never goes out. (Some Exchange work/school tenants
reject the delete with 403 — there, use Outlook's own "Cancel Send".)

### `co outlook calendar` — Your calendar

The Microsoft half of what `co gcalendar` does for Google, leaf for leaf
(`teams` where Google has `meet`). Event IDs are stable Graph IDs, never row
numbers. Reads run at once; every write previews by default and prints the
exact `--yes` command that performs it.

| Command | Python method on `MicrosoftCalendar` |
|---|---|
| `list --days 7 -n 20` | `list_events` |
| `today` | `get_today_events` |
| `read EVENT_ID` | `get_event` |
| `meetings --days 7` | `get_upcoming_meetings` |
| `free 2026-09-10 --minutes 30` | `find_free_slots` |
| `create TITLE START END [--attendees … --location … --description …]` | `create_event` |
| `teams TITLE START END --attendees EMAILS` | `create_teams_meeting` |
| `update EVENT_ID --title … --start … --end …` | `update_event` |
| `delete EVENT_ID` | `delete_event` |

```bash
co outlook calendar                                 # bare = upcoming events
co outlook calendar today
co outlook calendar free 2026-09-10 --minutes 30
co outlook calendar create "Standup" 2026-09-10T09:00:00+10:00 2026-09-10T09:15:00+10:00
# {"mode": "preview", "operation": "create", ...}
# No changes made.
# Next: co outlook calendar create Standup 2026-09-10T09:00:00+10:00 2026-09-10T09:15:00+10:00 --yes
```

Times: an ISO offset is converted to UTC, and a naive time means UTC — Graph
receives every event with `timeZone: UTC`. `update` preserves omitted fields;
empty strings do not clear a field. `free` covers 09:00–17:00 UTC on this
calendar only, not attendees'. Needs the `Calendars` scope.

Exit 0 is a read, a preview, or a successful write; 1 is an operational failure
with a recovery command; 2 is invalid arguments. A Graph error prints its HTTP
status and a next command, never the response body.

## Same functions, in your agent

The CLI is a thin wrapper over the [Outlook tool](../useful_tools/outlook.md),
so anything `co outlook` does, your agent can do too:

```python
from connectonion import Agent, Outlook

outlook = Outlook()
agent = Agent("assistant", tools=[outlook])

agent.input("Check my inbox and send the report to alice@example.com")
```

Or call it directly:

```python
outlook = Outlook()
outlook.list_inbox(last=10, unread=True)
outlook.add_contact("Zhou Yifei", "zhou@example.com")
outlook.list_contacts(max_results=25)
outlook.search_contacts("yifei")
outlook.send(
    "alice@example.com", "Report", "See attached.",
    attachments=["report.pdf"],
    send_at="2026-07-06T15:30:00Z",
)
```

## Troubleshooting

Each failure names the layer that actually broke, so the printed `Next:` line
is the fix (#1313). Three layers can fail, and each has its own command:

| Printed cause | Layer | Next command |
|---|---|---|
| `Microsoft account not connected` | no local record | `co auth microsoft` |
| `Microsoft <scope> permission missing` (Mail, `Contacts.ReadWrite`, `Calendars`) | record predates the scope | `co auth microsoft` — a refresh cannot widen scopes |
| `No OpenOnion API key …` / `OpenOnion authentication failed while refreshing provider access.` | your OpenOnion key is missing or dead; the Microsoft grant is fine | `co auth` |
| `Microsoft authorization expired or was revoked.` | Microsoft rejected the refresh token | `co auth microsoft` |
| `Microsoft access token is expiring and the saved record has no refresh token.` | incomplete local record | `co auth microsoft` |
| `Microsoft Graph API error (HTTP nnn).` | Graph refused the call; the body is never printed | the command's own next step (`co outlook inbox`, `co outlook calendar list`) |

Other cases:
- **`No email #N in your inbox`** → the number is out of range; run
  `co outlook inbox` to refresh the listing.
- **`co outlook cancel` rejected with 403** → some Exchange work/school
  tenants lock deferred messages against API deletion; use Cancel Send in
  Outlook instead. On personal outlook.com accounts cancel works normally.

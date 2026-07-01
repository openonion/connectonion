# ConnectOnion Email (co email)

Every agent gets its own email address. `co email` lets you send and read from
it right in the terminal — no separate mail client, no Gmail OAuth.

Your address is derived from your agent's identity, e.g.
`0x7a9f3b2c@mail.openonion.ai`. It's activated by `co auth`.

## Quick Start

```bash
# Check your inbox (the zero-arg default)
co email

# Send a message
co email send alice@example.com "Hello" "Thanks for trying ConnectOnion!"

# Read message #42 from the inbox list
co email read 42
```

That's the whole surface. Everything below is detail.

## Commands

### `co email` — Show the inbox

With no subcommand, prints your most recent emails. Same as `co email inbox`.

```bash
co email
```

### `co email inbox` — List received email

```bash
co email inbox                 # last 10
co email inbox --last 25       # last 25  (alias: -n 25)
co email inbox --unread        # only unread  (alias: -u)
```

Unread messages are marked with a green `●`. The leftmost `#` is the email's
id — pass it to `co email read`.

**Options**
- `--last, -n` — how many to show (default: 10)
- `--unread, -u` — only unread messages

> Note: `--unread` filters the fetched page locally, so `--last 10 --unread`
> means "unread among your 10 most recent," not "your 10 most recent unread."

### `co email read <#>` — Read one message

```bash
co email read 42
```

Prints the sender, subject, date, and body, then marks the message read.

> Reads from your 100 most recent messages. An email older than that won't be
> found by id yet (see [Limitations](#limitations)).

### `co email send <to> <subject> <message>` — Send

```bash
co email send bob@example.com "Subject line" "Body text"
```

All three arguments are positional and required. HTML is auto-detected: if the
body contains tags (`<...>`), it's sent as HTML, otherwise as plain text.

```bash
# Plain text
co email send bob@example.com "Hi" "Just checking in."

# HTML (auto-detected)
co email send bob@example.com "Receipt" "<h1>Paid</h1><p>Thanks!</p>"
```

## Customizing your address (paid)

The two commands below spend ConnectOnion credits. Each shows you the price or
new quota first, then applies it — nothing is charged unless you opt in.

### `co email name <name>` — Claim a readable address

By default your address is derived from your agent's key
(`0x7a9f3b2c@mail.openonion.ai`). Claim a human-readable one instead:

```bash
co email name aaron          # check if aaron@openonion.ai is free + its price
co email name aaron --buy    # claim it (one-time charge from your credits)
```

Without `--buy` it only **checks availability** and prints the one-time price
(returned live by the backend, so it's always current). Add `--buy` to claim
it — the price is deducted from your credit balance and the name becomes your
sending address.

```bash
$ co email name aaron
✓ aaron@openonion.ai is available — $5.00 one-time, from credits
Claim it: co email name aaron --buy

$ co email name aaron --buy
✓ Claimed aaron@openonion.ai
  Your address: aaron@openonion.ai
```

> Prices here are illustrative — the real figure is whatever the check command
> prints. If the name is taken you'll see why (`✗ … — unavailable`).

### `co email upgrade <tier>` — Raise your sending quota

Free agents can send a limited number of emails per month. Upgrade to `plus`
or `pro` for a higher monthly quota, billed from your credits:

```bash
co email upgrade plus                        # higher monthly quota
co email upgrade pro --alias support         # pro tier + a mailbox alias
co email upgrade pro --domain mail.acme.com  # send from your own domain
```

**Options**
- `--domain, -d` — send from your own domain (plus/pro)
- `--alias, -a` — mailbox alias, e.g. `support` → `support@…`

```bash
$ co email upgrade plus
✓ Upgraded to plus
  Address: aaron@openonion.ai
  Quota:   5,000/month
  Balance: $12.50
```

> The quota and balance shown come straight from the server response, so they
> reflect your account rather than fixed doc values.

## Setup

Email requires authentication once:

```bash
co auth
```

This saves `OPENONION_API_KEY` and sets `AGENT_EMAIL` / `IS_EMAIL_ACTIVE=true`.
If you run an email command before authenticating you'll get a prompt to run
`co auth` first.

## Same functions, in your agent

The CLI is a thin wrapper over two tool functions you can hand to any agent:

```python
from connectonion import Agent
from connectonion.useful_tools import send_email, get_emails

agent = Agent("mailer", tools=[send_email, get_emails])
agent.input("Check my inbox and reply to anything urgent.")
```

So anything `co email` does, your agent can do too. See
[send_email](../useful_tools/send_email.md) and
[get_emails](../useful_tools/get_emails.md).

## Limitations

- **`read` only sees your recent 100 messages.** The backend has no
  single-email endpoint yet, so `read` lists and filters by id client-side.
- **No `reply` yet.** To reply, copy the sender into `send`:
  `co email send <their-address> "Re: ..." "..."`.
- **Long / multi-line bodies** are awkward as a shell argument. For now, quote
  carefully; piping a body from a file is not wired up.

## Troubleshooting

- **"No API key found"** → run `co auth`.
- **"AGENT_EMAIL not found"** → run `co auth` to activate email.
- **Authentication failed (401)** → token expired, re-run `co auth`.
- **Rate limit exceeded (429)** → you've hit your tier's send quota; check
  `co status`.

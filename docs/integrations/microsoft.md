# Microsoft Integration (`co auth microsoft`)

Connect Outlook Mail and Microsoft Calendar to ConnectOnion:

```bash
co auth
co auth microsoft
```

The second command opens Microsoft's consent page. After consent, oo-api keeps
the Microsoft refresh token encrypted on the server. The client stores only
non-secret connection metadata and asks oo-api for a short-lived access token
when an Outlook or Calendar tool needs one.

## What is stored locally

The project `.env` contains metadata, not Microsoft bearer tokens:

```bash
MICROSOFT_CONNECTED=true
MICROSOFT_SCOPES=Mail.ReadWrite,Mail.Send,Calendars.Read,Calendars.ReadWrite
MICROSOFT_EMAIL=you@example.com
```

The same metadata is updated in `~/.co/keys.env` when that file exists. An
existing `MICROSOFT_ACCESS_TOKEN`, `MICROSOFT_REFRESH_TOKEN`, or
`MICROSOFT_TOKEN_EXPIRES_AT` entry is removed during authentication.

Do not put a Microsoft refresh token in an application `.env` file. It is a
long-lived credential and is managed by oo-api.

## Token refresh behavior

- Microsoft controls the access-token lifetime and reports it in the token
  response. It is commonly around 60–90 minutes, but the client does not assume
  a fixed one-hour lifetime.
- oo-api returns the cached access token while it has more than five minutes
  remaining.
- At five minutes or less, oo-api uses its encrypted refresh token and stores
  Microsoft's rotated refresh token atomically.
- If Microsoft Graph rejects an apparently valid access token with `401`, the
  client asks oo-api to refresh it and retries that Graph request once.
- If Microsoft requires interaction, the command reports that you must run
  `co auth microsoft` again.

There is no periodic “refresh the refresh token” timer. The refresh token is
used only when a new access token is required.

## Permissions

The integration requests delegated Microsoft Graph permissions:

| Scope | Purpose |
| --- | --- |
| `Mail.ReadWrite` | Read, update, move, and archive mailbox messages |
| `Mail.Send` | Send messages |
| `Calendars.Read` | Read calendar events |
| `Calendars.ReadWrite` | Create, update, and delete events |
| `User.Read` | Show which Microsoft account is connected |
| `offline_access` | Let oo-api renew access without repeated sign-in |

Only approve these permissions for a Microsoft account whose mailbox and
calendar you intend the agent to use.

## Use Outlook

```python
from connectonion import Agent, Outlook

outlook = Outlook()
agent = Agent("outlook-assistant", tools=[outlook])

agent.input("Show my unread email")
agent.input("Send alice@example.com a short project update")
```

Useful methods include `read_inbox`, `get_sent_emails`, `search_emails`,
`get_email_body`, `send`, `reply`, `mark_read`, `mark_unread`, and
`archive_email`.

The terminal interface is documented in [`co outlook`](../cli/outlook.md).

## Use Microsoft Calendar

```python
from connectonion import Agent, MicrosoftCalendar

calendar = MicrosoftCalendar()
agent = Agent("calendar-assistant", tools=[calendar])

agent.input("What is on my calendar this week?")
agent.input("Find a free one-hour slot tomorrow afternoon")
```

Useful methods include `list_events`, `get_today_events`, `get_event`,
`create_event`, `update_event`, `delete_event`, `create_teams_meeting`, and
`find_free_slots`.

## How the authorization flow works

1. The CLI authenticates to oo-api with `OPENONION_API_KEY` and requests a new
   authorization transaction.
2. oo-api creates a random, short-lived state value and PKCE verifier.
3. The CLI opens Microsoft's authorization page and polls the matching status
   endpoint.
4. Microsoft's callback is exchanged by oo-api. The access and refresh tokens
   are encrypted and associated with the OpenOnion account.
5. The CLI saves only `MICROSOFT_CONNECTED`, scopes, and optional email.

Starting another flow does not delete a working connection. The connection is
replaced only after a new authorization succeeds.

## Troubleshooting

If ConnectOnion authentication is missing or expired:

```bash
co auth
```

If Microsoft authorization was cancelled, timed out, revoked, or requires
interaction:

```bash
co auth microsoft
```

To inspect local connection metadata without revealing any Microsoft token:

```bash
co keys
```

Removing `MICROSOFT_*` metadata locally only hides the connection from that
client; it does not revoke the server-held Microsoft authorization. To revoke
the Microsoft grant, remove OpenOnion from the Microsoft account's consent/app
permissions page. A first-class `co auth microsoft --disconnect` command is not
yet available.

## Security notes

- Protect `OPENONION_API_KEY`: it authorizes oo-api to obtain short-lived
  Microsoft access tokens for the connected account.
- Never commit `.env`, `~/.co/keys.env`, or bearer tokens.
- Reauthenticate only when prompted; periodic manual refresh-token rotation is
  unnecessary.
- Revoke the Microsoft grant when the integration is no longer needed.

## Related

- [Outlook CLI](../cli/outlook.md)
- [CLI authentication](../cli/auth.md)
- [Google integration](google.md)

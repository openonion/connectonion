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
MICROSOFT_SCOPES=Mail.ReadWrite,Mail.Send,Calendars.ReadWrite
MICROSOFT_EMAIL=you@example.com
```

The same metadata is updated in `~/.co/keys.env` when that file exists. An
existing `MICROSOFT_ACCESS_TOKEN`, `MICROSOFT_REFRESH_TOKEN`, or
`MICROSOFT_TOKEN_EXPIRES_AT` entry is removed during authentication.

Do not put a Microsoft refresh token in an application `.env` file. It is a
long-lived credential and is managed by oo-api.

## Token refresh behavior

- Microsoft controls the access-token lifetime and reports it in the token
  response. It is commonly around 60–90 minutes; CAE tokens can last 20–28
  hours. The client does not assume a fixed lifetime.
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

Microsoft documents a 90-day default refresh-token lifetime for this web flow,
but the token can be revoked earlier. Active use normally rotates it whenever a
new access token is needed; after extended inactivity or a policy/revocation
event, run `co auth microsoft` again.

## Permissions

The integration requests delegated Microsoft Graph permissions:

| Scope | Purpose |
| --- | --- |
| `Mail.ReadWrite` | Read, update, move, and archive mailbox messages |
| `Mail.Send` | Send messages |
| `Calendars.ReadWrite` | Read, create, update, and delete events |
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

1. The CLI first binds a random local port on `127.0.0.1`, then authenticates to
   oo-api and starts a short-lived authorization transaction.
2. oo-api creates random state and PKCE values. Microsoft still returns to the
   registered HTTPS oo-api callback; the local URI is never registered with
   Microsoft and never receives a token.
3. After consent, the HTTPS callback validates state, stores only a hash of the
   one-use authorization code, and redirects that code to the initiating CLI's
   loopback listener. It does not exchange or activate Microsoft tokens.
4. The CLI constant-time checks the returned authorization ID and submits the
   code to oo-api with `OPENONION_API_KEY`.
5. oo-api exchanges the code, encrypts the access/refresh pair, and replaces the
   existing connection atomically. The CLI saves only connected status, scopes,
   and optional email.

Starting another flow does not delete a working connection. The connection is
replaced only after a new authorization succeeds.

The browser must run on the same computer as the CLI. A browser on another
machine cannot reach the CLI's `127.0.0.1` listener; this is intentional account
binding, not a network configuration to bypass.

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

Microsoft references:

- [Access-token lifetime](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens#token-lifetime)
- [Refresh-token lifetime and rotation](https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens)
- [Cache-first token acquisition](https://learn.microsoft.com/en-us/entra/identity-platform/msal-acquire-cache-tokens)

## Related

- [Outlook CLI](../cli/outlook.md)
- [CLI authentication](../cli/auth.md)
- [Google integration](google.md)

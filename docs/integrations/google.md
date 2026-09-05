# One local Google login

The 1.8.3 candidate connects Gmail, Drive, Calendar and YouTube with one consent
flow. This describes the candidate, not an already-published package.

```bash
co auth
co auth google
co gmail inbox
co gdrive list
co gcalendar list
co youtube channel
```

## Names and permissions

| CLI | Python tool | Default scopes |
|---|---|---|
| `co gmail` | `Gmail` | `gmail.readonly`, `gmail.send`, `gmail.modify` |
| `co gdrive` | `GDrive` | `drive` |
| `co gcalendar` | `GoogleCalendar` | `calendar` |
| `co youtube` | `YouTube` | `youtube` |

Identity also requests `userinfo.email` and `userinfo.profile`. These are broad
permissions on supported services, not all Google APIs. Google controls consent;
we save the actual grant, never assume every requested capability succeeded.

Limit a login explicitly:

```bash
co auth google --scopes youtube.readonly
co auth google --scopes gmail.readonly,gmail.send,drive.readonly,calendar.readonly
```

The allowed short names are the default scopes plus `drive.readonly`,
`calendar.readonly`, `youtube.readonly` and `youtube.upload`.
Restricted requests do not ask Google to combine earlier grants. They do not
revoke earlier grants elsewhere; use Google Account permissions to revoke.

## Where credentials live

The CLI creates an ephemeral encryption key and a loopback callback. oo-api keeps
only existing expiring OAuth state/PKCE data. After consent it exchanges the code,
seals the token bundle for that CLI and redirects it to `127.0.0.1`.
No Google credential row or scope column is created or updated. No Google
schema/data migration is required.

The CLI saves `GOOGLE_ACCESS_TOKEN`, `GOOGLE_REFRESH_TOKEN`,
`GOOGLE_TOKEN_EXPIRES_AT`, `GOOGLE_SCOPES` and `GOOGLE_EMAIL` in
`~/.co/keys.env` (or `AGENT_CONFIG_PATH/keys.env`) with owner-only permissions.
An existing project `.env` is updated too; no new project credential file is
created. Cancellation preserves the old login. Inspect with `co status`, never
by printing credential files.

Refresh sends the locally held refresh token over TLS to the stateless oo-api
broker. Its Google application secret stays on the server. User tokens exist
there transiently during exchange, not in durable storage. Returned rotation and
scopes are saved locally. Google content requests go directly from this computer
to Google.

## Python API

```python
from connectonion import Gmail, GDrive, GoogleCalendar, YouTube

print(Gmail().read_inbox(last=5))
print(GDrive().list_recent(last=5))
print(GoogleCalendar().list_events(days_ahead=7))
print(YouTube().channel())
```

See [Gmail](../cli/gmail.md), [Drive](../cli/gdrive.md),
[Calendar](../cli/gcalendar.md), and [YouTube](../cli/youtube.md) for command and
confirmation rules. Direct Python methods can write: invoke them only for
user-approved actions. Meet links use Calendar conference data, not a separate
Meet API. No separate Docs, Sheets, Photos, Contacts or Analytics command groups
ship in this release.

## Upgrade and recovery

Deploy with the matching local-token CLI. Older clients that expect server-side
polling or bodyless refresh must upgrade. Legacy database rows are untouched, not
migrated or reset; the new flow never reads them. Existing local refresh tokens
remain usable.

For missing, denied or expired authorization, run `co auth google`. Keep the CLI
running on the same computer as the browser; consent waits up to five minutes.
Account switches replace the old login only after successful handoff. Revoke in
[Google Account permissions](https://myaccount.google.com/permissions), then remove
local GOOGLE_* entries without printing or committing them. A remote dashboard
cannot erase local credentials.

Operators must enable the APIs and satisfy Google's verification requirements.
YouTube consent is not proof of upload approval, processing or available quota.

References: [Google OAuth](https://developers.google.com/identity/protocols/oauth2/web-server),
[YouTube uploads](https://developers.google.com/youtube/v3/docs/videos/insert).

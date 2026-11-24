# Notion sign-in: what the OpenOnion service must do

`co auth notion` (the CLI side, in this repository) works only once the
OpenOnion service (oo-api) offers the three endpoints below. They follow the
Google and Microsoft brokers exactly: the service exchanges and refreshes
tokens, seals the first result to a key only the CLI holds, and **stores no
Notion token**. Until they exist, `co auth notion` says
`The Notion sign-in service is not available (HTTP 404)`, changes nothing, and
asks for a pasted token instead (as `co auth notion --paste` does), saved
encrypted as `NOTION_API_KEY`.

Notion's own contract, which this follows:
[Authorization](https://developers.notion.com/guides/authorization/overview),
[Create a token](https://developers.notion.com/reference/create-a-token),
[Refresh a token](https://developers.notion.com/reference/refresh-a-token).

## Register the integration once

In Notion's developer portal, create a **public** (OAuth) integration:

| setting | value |
|---|---|
| Redirect URI | `https://<oo-api host>/api/v1/oauth/notion/callback` (the only one) |
| Capabilities | Read content, Update content, Insert content |
| User information | "Read user information including email addresses" — optional; it is what fills `notion_email` |
| Installation scope | any workspace (it cannot be changed later) |

Keep `NOTION_OAUTH_CLIENT_ID` and `NOTION_OAUTH_CLIENT_SECRET` in the
service's secrets. The secret never reaches a user's computer: that is why the
exchange happens here.

## 1. `GET /api/v1/oauth/notion/init`

Called by the CLI with `Authorization: Bearer <OpenOnion token>`.

| query | |
|---|---|
| `handoff_public_key` | 64 hex characters, a Curve25519 public key, new for each sign-in |
| `handoff_url` | `http://127.0.0.1:<port>/callback`; refuse anything that is not loopback |

Answer `200 {"auth_url": "..."}` where `auth_url` is

```
https://api.notion.com/v1/oauth/authorize?client_id=<id>&response_type=code&owner=user
    &redirect_uri=<the registered callback>&state=<state>
```

`state` is opaque, single use and short lived (10 minutes), and binds the
OpenOnion account, `handoff_public_key` and `handoff_url`; a signed or
encrypted value keeps the service stateless. The CLI opens the page only if it
is `https://api.notion.com/v1/oauth/authorize` with `owner=user` and a `state`,
and accepts the browser's return only with that same `state`.

## 2. `GET /api/v1/oauth/notion/callback`

Notion sends the browser here with `code` and `state`, or `error`
(`access_denied` when the user cancels).

1. Verify `state`; recover `handoff_public_key` and `handoff_url` from it.
2. Exchange the code: `POST https://api.notion.com/v1/oauth/token`, HTTP Basic
   `client_id:client_secret`, the `Notion-Version` Notion's token endpoint
   requires, body
   `{"grant_type": "authorization_code", "code": ..., "redirect_uri": <the registered callback>}`.
3. Build the payload (JSON; strings only; omit a field rather than send null):

   | field | from Notion's answer |
   |---|---|
   | `access_token` | `access_token` (required) |
   | `refresh_token` | `refresh_token`, when not null |
   | `expires_at` | Notion gives no lifetime: now + 1 hour, ISO 8601 with offset (required). The CLI also renews on any 401 |
   | `bot_id` | `bot_id` (required): the installation, used to tell one grant from another |
   | `workspace_id` | `workspace_id` (required) |
   | `workspace_name` | `workspace_name`, when not null |
   | `notion_email` | `owner.user.person.email`, when `owner.type` is `user` and the email was given |
   | `scopes` | the capabilities registered, comma separated: `read_content,update_content,insert_content` |

4. Seal it: `SealedBox(PublicKey(bytes.fromhex(handoff_public_key))).encrypt(payload)`,
   base64url, and redirect (302) to
   `<handoff_url>?state=<state>&ciphertext=<sealed>`.
5. On `error`, or a failed exchange, redirect to
   `<handoff_url>?state=<state>&error=<code>[&reason=<at most 120 characters>]`.
   Never put Notion's response body in the reason.

## 3. `POST /api/v1/oauth/notion/refresh`

Called with `Authorization: Bearer <OpenOnion token>` and
`{"refresh_token": "..."}`.

1. `POST https://api.notion.com/v1/oauth/token`, Basic auth as above, body
   `{"grant_type": "refresh_token", "refresh_token": ...}`.
2. Answer `200` with `access_token`, `refresh_token` (the new one — Notion
   invalidates the old), `expires_at` (now + 1 hour), `bot_id`,
   `workspace_id`, and `workspace_name` when given. Plain JSON over TLS, as the
   Google and Microsoft refresh endpoints answer.
3. Errors:

   | case | answer |
   |---|---|
   | Notion says `invalid_grant` (revoked, removed in Notion, already rotated) | `401 {"detail": {"error": "reauth_required"}}` → the CLI says `co auth notion` |
   | the OpenOnion token is not valid | `401` with any other detail → the CLI says `co auth` |
   | Notion unavailable | `502`/`503` → the CLI keeps the saved record and says to try again |

The CLI serialises refreshes per env file and adopts a record another process
renewed, so the service needs no locking of its own.

## What the CLI checks, so the service need not

- The consent URL is Notion's own; the returned `state` matches it.
- The handoff opens only with this command's one-time key, and has
  `access_token`, `expires_at` (in the future), `bot_id` and `workspace_id`.
- A refresh that answers for another `bot_id` is refused; the saved record is
  kept.

`tests/unit/test_notion_auth.py` stands in for this service with exactly this
contract; a service that passes the same exchange works with the CLI.

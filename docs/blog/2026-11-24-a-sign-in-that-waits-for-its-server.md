# A sign-in that waits for its server

`co auth notion` was meant to be one browser step: open Notion, pick the
workspace and the pages co may use, done. Notion makes that possible through a
public integration and OAuth, and the token exchange needs the integration's
client secret. A secret shipped inside a CLI is not a secret, so the exchange
has to happen on a server, the OpenOnion service, the way it already does for
Google and Microsoft. The CLI half is here: a one-time key, a callback on
127.0.0.1, Notion's own consent page and nothing else opened, and a result
sealed so that only this command can read it. The server half does not exist
yet. Its three endpoints are written down in
`docs/integrations/notion-oauth-broker.md`.

Shipping a sign-in that only says "HTTP 404" would have made the default way to
connect Notion a dead end. The Asana review had already settled what a co sign-in
owes the person: the machine does what it can, and the person does only what
only they can. Asana does it in the co browser; Notion's part cannot be done
without the server. So when the sign-in service does not offer Notion, or the
person has no OpenOnion sign-in, `co auth notion` says so and moves on to the
part that works today: it opens Notion's token page and asks for the token,
hidden. It checks the token with Notion before saving it, encrypted, as
`NOTION_API_KEY`. A token Notion refuses is never saved. `--paste` goes
straight there.

When the server arrives, nothing else has to change. The order a credential is
used in is fixed and printed by `co notion check`: a key exported in the shell,
then the sign-in, then the saved key. Signing in never deletes a saved key, and
`co env unset NOTION_ACCESS_TOKEN` goes back to it. A sign-in renews itself when
Notion says it has expired, one renewal at a time because Notion rotates its
refresh tokens.

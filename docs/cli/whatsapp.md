# WhatsApp mailbox (preview)

`co whatsapp` uses Meta's WhatsApp Cloud API for outbound messages and the O API
as a durable webhook inbox. The access token stays on the operator's machine. The
app secret and verify token are sent once to the authenticated O API binding
endpoint and encrypted at rest.

Set these values in `~/.co/keys.env` (never pass them on the command line):

```dotenv
OPENONION_API_KEY=...
WHATSAPP_WABA_ID=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_APP_SECRET=...
WHATSAPP_VERIFY_TOKEN=...
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_GRAPH_VERSION=v23.0
```

Register the webhook routing, then save the returned binding id:

```bash
co whatsapp bind
# add WHATSAPP_BINDING_ID=<printed-id> to ~/.co/keys.env
co whatsapp check
co whatsapp listen
```

Meta must be configured with the callback URL printed by `bind`, the same verify
token, and the `messages` webhook field. The Graph API version is deliberately
explicit so Meta version changes cannot silently alter delivery.

Inbound events are claimed with a lease and ACKed only after the seven-field
message has been durably stored in the local mailbox. A failed local write is
NACKed for retry. Duplicate provider message ids are harmless. Replies are text
only; outside Meta's 24-hour customer-service window the CLI exits with a clear
template-required policy error. Live Meta acceptance remains an external release
gate because fixtures cannot validate app review, WABA subscription, or account
permissions.

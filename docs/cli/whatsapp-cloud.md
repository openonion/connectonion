# WhatsApp Cloud API CLI (`co whatsapp-cloud`) — preview

A WhatsApp **Business** number on Meta's official Cloud API, as a directory of
files. Meta's webhook lands in O API; a listener on your machine claims each
message, writes it to `~/.co/inbox/whatsapp-cloud/`, and only then tells O API
it arrived. Replies go from your machine straight to Meta.

```bash
co whatsapp-cloud bind                 # once: register Meta's webhook with O API
co whatsapp-cloud check
co whatsapp-cloud receive              # next message as one JSON line
echo "on it" | co whatsapp-cloud reply wamid.HBgLMTE
co whatsapp-cloud consume -- claude -p
```

> **Preview.** This is wired and unit-tested against fakes. It has not been run
> against a live Meta app, and it needs O API's messaging inbox
> (openonion/oo-api#227), which is not deployed yet. Until it is, `listen`
> stops at once with that reason rather than polling an empty route.

## `co whatsapp-cloud` is not `co whatsapp`

They share a platform and nothing else. Pick by the kind of number you have.

| | `co whatsapp` | `co whatsapp-cloud` |
|---|---|---|
| what it is | a **linked device** on an ordinary WhatsApp number, like WhatsApp Web | Meta's **Business Cloud API** for a registered business number |
| sign-in | scan a QR on the phone | a Meta app, a WABA, and a Cloud API access token |
| groups a person created | yes — the reason it exists | **no**: the Cloud API cannot join a group |
| Meta's terms | automating the consumer app is against them; numbers get banned | the supported, sanctioned route |
| when you may message | any time | free text only within **24 hours** of the customer's last message; after that, only an approved template |
| how messages arrive | the listener's own socket to WhatsApp | Meta → O API webhook → the listener polls O API |
| how replies leave | through the running listener (one socket per device) | direct HTTPS to Meta from any process; no listener needed to send |
| `edit` / `delete` | yes | no — the Cloud API has neither, and the CLI says so |
| install | `pip install 'connectonion[whatsapp]'` plus libmagic | nothing extra |
| inbox directory | `~/.co/inbox/whatsapp/` | `~/.co/inbox/whatsapp-cloud/` |
| credentials | `WHATSAPP_SESSION` (the linked device) | `WHATSAPP_CLOUD_*`, below |

Both can run on the same machine at once; they never read each other's files.
Use the Cloud API whenever the conversation is one-to-one with your own
customers. Use `co whatsapp` only when the bot has to sit in a group a person
made.

## Setup

You need a Meta app with the WhatsApp product, a WhatsApp Business Account
(WABA) and a phone number registered on it, and an OpenOnion account
(`co auth`). Put these in `~/.co/keys.env` with `co env set` — never on a
command line, where they end up in shell history and `ps`:

```bash
co env set WHATSAPP_CLOUD_WABA_ID 900800700
co env set WHATSAPP_CLOUD_PHONE_NUMBER_ID 100200300   # Meta's id for the number, not the number
co env set WHATSAPP_CLOUD_ACCESS_TOKEN <token>        # a system-user token for the app
co env set WHATSAPP_CLOUD_APP_SECRET <app secret>     # App settings → Basic
co env set WHATSAPP_CLOUD_VERIFY_TOKEN <16+ random characters you choose>
co env set WHATSAPP_CLOUD_GRAPH_VERSION v23.0         # pinned on purpose; see below
```

Then register the webhook routing and save the id it prints:

```bash
co whatsapp-cloud bind
# binding-…
# In the Meta app, set the WhatsApp webhook callback URL to
#   https://oo.openonion.ai/api/v1/messaging/webhooks/whatsapp/<binding id>,
# the verify token to the same value, and subscribe the `messages` field.
co env set WHATSAPP_CLOUD_BINDING_ID <binding id>
co whatsapp-cloud check
```

`check` exits 3 and names each missing item with the command that fixes it. It
also asks O API whether the binding belongs to your account and asks Meta
whether the token can see the phone number id.

## What each secret is for, and where it goes

| Variable | Leaves this machine? | Why |
|---|---|---|
| `WHATSAPP_CLOUD_ACCESS_TOKEN` | only to Meta | sends replies; O API never sees it |
| `WHATSAPP_CLOUD_APP_SECRET` | once, to O API, in `bind` | O API checks Meta's webhook signature with it; stored encrypted |
| `WHATSAPP_CLOUD_VERIFY_TOKEN` | once, to O API, in `bind` | answers Meta's subscription challenge; O API keeps a hash |
| `OPENONION_API_KEY` | to O API | whose inbox to claim from |

Every error the provider prints is scrubbed of all four before it reaches the
terminal, the log, or `sent.jsonl`. `co keys` lists the three WhatsApp secrets
masked.

## Delivery

O API does not treat an accepted webhook as a delivered message. It stores the
signed event; the listener claims it under a 60-second lease, writes it to the
inbox, and only then ACKs. A write that fails (a full disk) is NACKed and
retried in 30 seconds; a listener that dies holding a claim lets the lease
lapse. A redelivered message id is ACKed and not queued twice.

The message has the same fields as every other provider. `chat` and `sender`
are both the customer's number, because the Cloud API only has direct
conversations, and `mentioned` is always true. Non-text messages arrive with
`text` like `[image]`; O API does not yet download media or send `kind`.

## Sending

`send` and `reply` work from any process, with or without a listener, because
they are plain HTTPS to Meta. Text is read as Markdown and translated to
WhatsApp's marks exactly as `co whatsapp` does; `--plain` sends it as typed.
`reply` quotes the original; `react` puts an emoji on a message.

Outside the 24-hour customer-service window Meta refuses free text (error
131047). The CLI says so and **exits 3**, not 1: resending will not help until
the customer writes again or you send an approved template, which this CLI does
not do yet.

## Why the Graph version is pinned

Meta versions the Graph API and retires old versions on a schedule. Letting a
request float to "latest" means a Meta release can change what a send does
with no change on your side. `WHATSAPP_CLOUD_GRAPH_VERSION` must be spelled
`vNN.N`; when Meta retires it, `check` will fail with Meta's own words and you
move it on purpose.

## Exit codes

| exit | means | run next |
|---|---|---|
| 0 | it worked | the tip the command printed |
| 1 | Meta or O API refused, or a listener is already running | `co whatsapp-cloud log` |
| 3 | not configured, the 24-hour window is closed, or O API has no inbox for you | `co whatsapp-cloud check` |
| 124 | `receive` waited and no message came | `co whatsapp-cloud ls` |

## Environment

| Variable | Required for | What it is |
|---|---|---|
| `WHATSAPP_CLOUD_WABA_ID` | `bind` | the WhatsApp Business Account id |
| `WHATSAPP_CLOUD_PHONE_NUMBER_ID` | everything | Meta's id for the business number |
| `WHATSAPP_CLOUD_ACCESS_TOKEN` | `send`, `reply`, `react`, `check` | the Cloud API token |
| `WHATSAPP_CLOUD_APP_SECRET` | `bind` | the Meta app secret |
| `WHATSAPP_CLOUD_VERIFY_TOKEN` | `bind` | the webhook verify token you chose |
| `WHATSAPP_CLOUD_BINDING_ID` | `listen`, `check` | printed by `bind` |
| `WHATSAPP_CLOUD_GRAPH_VERSION` | everything | e.g. `v23.0` |
| `CO_INBOX_HOME` | — | moves the whole inbox root, every provider with it |

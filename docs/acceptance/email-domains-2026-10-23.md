# Hosted mailbox domain audit — 2026-10-23

## Before

The production `/api/v1/email/addresses` exposed mail.openonion.ai,
steadmail.com, trustxmail.com and oakinbox.com. Resend only had
mail.openonion.ai verified. The three branded domains had not been registered
with Resend. steadmail.com and oakinbox.com lacked inbound MX records.
trustxmail.com had Cloudflare MX records; its catch-all could not be inspected.

## Work performed

Registered the three branded domains with Resend in ap-northeast-1. Added each
domain's Resend DKIM TXT, SPF TXT, return-path MX and tracking CNAME in its
Cloudflare zone. Requested verification. The provisioning command lives in
oo-api `scripts/configure_email_domains.py`, defaults to read-only inspection,
and refuses conflicting DNS or an existing active catch-all to another target.

## Outstanding acceptance

All three branded domains are now verified by Resend. Cloudflare's production
token could manage DNS but Email Routing API requests returned HTTP 403. The
Cloudflare browser session required login. The owner was asked to provide
Email Routing Rules/Settings permissions or sign in before enabling inbound
routing. No claim is made that the branded domains can receive email yet.

No mailbox was bought and no message was sent to establish live end-to-end
acceptance. Package regression tests do not establish DNS or mail delivery.

## Independent experience review

A separate AI reviewer used a technology-founder, marketing and UI perspective.
This is a role review; no human founder participation is claimed.

| Priority | Evidence and user impact | Fix and recheck |
| --- | --- | --- |
| P1 | `is_default` was written but not read by implicit sends; mail could leave with the wrong sender. | Read the owned default before legacy tier settings. Regression follows the real sender selection into the provider payload. |
| P1 | Two branded domains had no incoming MX; the API nevertheless offered all three for purchase. | Add deployment domain allowlisting; only enable branded domains after routing/delivery acceptance. Verify production `/email/addresses` after deploying. |
| P2 | Mail showed only the derived address and did not distinguish destination mailboxes. | Show actual default, owned-mailbox filter and every message's To. Review filter and message expansion on desktop and mobile. |
| P2 | Old rendered docs advertised a Plus custom domain and implied a new name always overrides the default. | Correct hosted-domain examples and preserve-selected-default semantics in rendered and raw Markdown docs. |
| P2 | Mail's help summary lost its native disclosure marker. | Restore the marker; recheck the actual mobile render. |

Actually inspected `/cli/email` at 1440×1000 and 390×844, with its new details
collapsed and expanded. Inspected the real MailTab component through a temporary
local fixture: normal, empty, mail-loading error and address-loading error at
390px and 1440px; mailbox filtering, body expansion and help expansion. No
whole-page horizontal overflow was observed. The fixture was removed before
commit and is not shipped. This does not cover authenticated production states,
real mailbox purchases, Cloudflare routing or live mail delivery.

![Mail component on mobile, local fixture](email-domains-2026-10-23/mail-mobile.png)

![CLI email docs, desktop details expanded](email-domains-2026-10-23/docs-desktop.png)

## Follow-up verification for 1.9.3rc19

The fresh SDK/CLI email suite passed 114 tests. Backend regression passed 907
with 200 skipped; eleven ownership contracts ran against real local PostgreSQL.
The additional contract checks a unified inbox across different names and all
four hosted domains; selecting a default sender does not split received mail.
New setup checks cover signed-out access, settings authorization failure, and
backend-disabled reserved domains without attempting a purchase.

A fresh production inspection still found all three branded sender domains
verified in Resend and Cloudflare Email Routing API requests rejected with 403.
This round does not establish branded-domain incoming delivery. The live owner
account was read only; no mailbox purchase or message send was used as a test.

An independent AI role reviewer approved the new CLI and PostgreSQL contracts
and rechecked the actual public `/cli/email`, `/releases`, and domain Design
Journal pages on desktop and mobile before publication. No new blocking issue
was found. The current public preview was rc18 at that inspection; rc19 labels
and installation instructions require a post-publication recheck. Screenshot
capture failed in this round; page reads and layout checks succeeded. This
coverage does not establish every page or live delivery acceptance.

## Live routing follow-up after publication

The shell's dedicated CLOUDFLARE_API_TOKEN_EMAIL can read catch-all rules and
Workers (HTTP 200). The production DNS token cannot. The dedicated token still
receives 403 from POST `/email/routing/dns`, whose documented requirement is
Zone Settings Write. The provisioner now selects that dedicated routing token
while retaining the ordinary token for sender DNS.

Actual catch-all inspection found openonion.ai routed to openonion-email-worker,
steadmail.com and oakinbox.com disabled, and trustxmail.com already routed to a
separate verify-code worker. No existing catch-all was overwritten.

The deployed primary worker currently parses PostalMime and POSTs a signed
backend webhook. A real provider self-test to the owner's existing primary
address was returned by the authenticated received-mail API (one matching
message). The CLI send attempt itself was rejected at the monthly 100-message
quota, so this is provider-to-inbox acceptance, not a CLI-send pass. No quota
upgrade or branded mailbox purchase was made. The three branded domains still
lack accepted incoming delivery; their new-address choices remain disabled.

## Approved trustxmail.com migration and acceptance

The owner explicitly selected moving all trustxmail.com mail from verify-code
to Agent Mail. The old enabled catch-all was backed up before PUT of the new
rule. Read-back confirmed it is enabled and targets openonion-email-worker.
The separate verification-code worker itself was not edited or deleted.

A synthetic internal recipient was checked to ensure it did not belong to
another account. A provider test to that address produced one matching row in
email_received. This proves the trustxmail.com incoming route into the mail
store; the address was not purchased, so it is not an owner's API inbox test.
The existing primary-address test independently returned one message through
the owner's authenticated received-mail API. No account quota or tier changed.

Both the live service environment and deployment repository variable now allow
mail.openonion.ai and trustxmail.com. The service restarted successfully, and
CLI domain discovery and price preview use the new list without a purchase.
steadmail.com and oakinbox.com remain gated: the dedicated token still receives
403 on settings/enable operations. The operator token-selection fix passed all
908 backend tests (201 skipped) and independent review; its PR is merged.

## Final hosted-domain activation and owned-inbox acceptance

The dedicated email token still received 403 on the Zone Settings endpoint, but
it could update catch-all rules. The ordinary DNS token added the same three
Cloudflare receiving MX records and root SPF as the already working trust zone
to steadmail.com and oakinbox.com. Both enabled catch-alls now target
`openonion-email-worker`. Public DNS returned the new records. A real provider
message to a checked unclaimed internal recipient on each domain created one
matching `email_received` row. No other account's mailbox was used.

Production `EMAIL_ADDRESS_DOMAINS` and the oo-api repository variable now both
list `mail.openonion.ai,steadmail.com,trustxmail.com,oakinbox.com`. The restarted
service was healthy; the authenticated address API and `co email domains` showed
all four. Aaron's account owns `aaron@trustxmail.com`,
`aaron@steadmail.com`, and `aaron@oakinbox.com` alongside its primary
`aaron.xie@mail.openonion.ai`. The last two purchases cost $9.90 each and kept
the primary address as default.

One real provider message to each branded owned address produced three results
in Aaron's authenticated merged inbox. Filtering separately by each address
returned exactly its matching message and echoed the applied address filter.
The source CLI listed all four owned addresses and read the oakinbox test
through `co email inbox --address`. This acceptance covers real incoming
delivery and shared ownership; the exhausted account monthly send quota still
prevents claiming a successful account CLI send. No quota upgrade was bought.

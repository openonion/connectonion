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

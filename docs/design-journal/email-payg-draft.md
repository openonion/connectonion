# Draft: an email price the sender can authorize

Status: implementation draft; no PyPI release or public launch is claimed.

The mailbox should remain useful without a subscription: 100 sends included each UTC month, then $0.003 per accepted send from existing credits. Legacy clients default to a zero-dollar cap. A caller must explicitly authorize paid overflow; a quota change cannot silently convert a previously free send into a paid send.

A hold reserves either the final free unit or the exact credit amount before network dispatch. A persisted send ID, provider key and processing lease bind delivery recovery to the same message. A definitive initial rejection refunds; an uncertain delivery stays visible until confirmation or a 24-hour expiry with periodic automatic hold release. Retrying an edited message with a new ID while its original may already be delivered is deliberately unavailable in the web composer.

Keeping this state only in Sent would let deletion or address transfers erase charges and duplicate protection. The ledger therefore retains the original payer independently of mailbox history; full account migration moves ownership. Alternatives were a hard monthly quota or a mandatory tier purchase. PAYG keeps small occasional senders working and makes each cost reviewable, at the expense of durable accounting and recovery state.

Validation and release links will be recorded after the backend, web and reviewed CLI deployment are verified. Publication remains pending; do not describe this draft as a released package.

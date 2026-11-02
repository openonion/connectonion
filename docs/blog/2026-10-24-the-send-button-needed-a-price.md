# The Send button needed a price

Deployment draft. This change is under review in [PR #2676](https://github.com/openonion/connectonion/pull/2676); no PyPI release is claimed here.

The mailbox opened, the reader worked, and the composer offered a Send button. The account had already used its hundred included emails for the month. The button did not say that. Only after writing a reply would the sender discover the quota wall.

A monthly subscription was the wrong next step for someone who needed to send one more message. The agreed behavior is a fresh included allowance each UTC month, then three tenths of a cent for an accepted email, paid from existing credits. There is no automatic top-up. But making the server accept paid overflow would also change every script that already calls `send_email`. A script expecting a free send must not discover a charge afterward.

The caller therefore carries the price it has agreed to pay. The SDK and CLI default to zero; `--max-cost 0.003` explicitly allows that one email to use paid overflow. Included sends still cost zero. If another tab spends the final free unit between the quote and the click, a zero-dollar request stops before dispatch and returns the new price.

The harder case came after clicking. A timeout can mean the provider accepted the email but its answer was lost. Editing the draft and generating a new send ID would make another delivery possible. The saved attempt now retains its original message, sender, key and budget. Status checks do not resend. A retry uses that same attempt; a confirmed result is charged once. An initial definite rejection releases its hold, while an uncertain attempt expires after 24 hours and is released by maintenance without an automatic resend.

An independent AI review exercised this with real PostgreSQL transactions, including simultaneous claims on the final free unit, duplicate retries, history deletion, account migration and concurrent expiry cleanup. In the browser fixture, two requests after an uncertain result produced one accepted message. These are measured local checks, not a claim that every production failure has been observed.

The visible change is a small price beside Send. The consequence is that the sender can decide before paying, and can recover after uncertainty without quietly creating another email.

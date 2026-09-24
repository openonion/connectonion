# A retry that sends twice

On 23 September several Wiki investigations read one Outlook mailbox at once,
Microsoft Graph throttled them with 429s, and the run died on requests that
would have succeeded a few seconds later. The fix was a small loop: on 429,
503 or 504, wait as long as Graph asks and try again. It went into the one
function every Outlook call goes through, which is where a fix like that
belongs — and why it quietly covered more than it was written for.

The review before 1.8.8 found the other thing that function does: it sends
mail. `POST /me/sendMail`, reply and draft send all pass through the same loop.
A 429 is Graph saying "no, not yet"; nothing happened, and asking again is
safe. A 504 is Graph's gateway saying it stopped waiting — and the mailbox
behind it has often finished the job by then. Retrying that one does not
recover a lost request. It delivers the same email a second time, to a
customer, where it cannot be taken back.

So the loop now asks what the request was before deciding it can be repeated:
a 429 is retried for anything, a 503 or 504 only for a read. A send that hits a
gateway timeout is reported as the failure it might be, and the caller — a
person, or an agent that can check Sent Items — decides, instead of the
transport deciding to send it again.

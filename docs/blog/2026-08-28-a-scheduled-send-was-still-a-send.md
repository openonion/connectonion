# A Scheduled Send Was Still a Send

On August 22, a `co outlook send --at ...` command printed a reassuring
`Scheduled` message. The mailbox told a different story: the recipient
received a copy immediately, while another copy remained queued for the
requested time. The command had created a duplicate without giving the
caller a useful warning.

The confusing part was the property that looked like the answer. The
deferred-send time was attached to a message sent through Microsoft Graph's
`/me/sendMail` endpoint. That endpoint is an immediate-send operation; the
timestamp did not turn it into a draft. Exchange could therefore deliver
one message and retain the deferred copy.

The fix follows the boundary instead of trusting the property. An immediate
send still uses `/me/sendMail`. A scheduled send now creates a draft through
`/me/messages`, with the deferred-send property attached before the draft is
stored. Exchange owns delivery from there, and the scheduled item remains
visible to the existing listing path. The scheduled branch also checks for
`Mail.ReadWrite` before making a network request, because draft creation
needs that scope.

The regression tests inspect the actual HTTP method, URL, payload, extended
property, request count, and missing-scope failure. They also keep replies on
the threaded reply endpoint. The lesson is simple: a delivery instruction is
only meaningful when it is sent through an endpoint that honors the delivery
lifecycle.

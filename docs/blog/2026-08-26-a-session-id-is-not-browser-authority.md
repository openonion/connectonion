# A Session ID Is Not Browser Authority

*2026-08-26*

The shortest route to a remote browser already existed: execute `co browser` as
a remote shell command. It could open a page. It could also skip the contract we
actually needed.

A shell result cannot answer who owns the browser session after reconnect, what
an idempotent retry means, or whether a copied session ID grants control. Adding
more verbs to that path would make the demo grow faster than its authority
model.

## Bind ownership before adding power

The first Remote Browser OIP frame therefore does less. It starts, lists,
inspects, diagnoses, and stops an owner-bound session. The Host takes the owner
from the authenticated connection; the request has no owner field to spoof. The
session ID locates a record but grants nothing. A different authenticated caller
gets the same not-found result as an invented ID.

The service also refuses to become another browser implementation. It opens a
named tab in the existing concurrent daemon and records the lifecycle in one
atomic, private registry. Repeating Start with the same request ID returns the
same session. Repeating Stop returns the same tombstone. Restarting Host reloads
the authority instead of manufacturing a new one.

## The missing navigation verb is the feature

It is tempting to add `open` next and call direct mode usable. A URL allowlist at
the command edge would be theatre. The first URL can redirect; its hostname can
resolve differently; the page can fetch private and link-local subresources.
Until one policy covers the entire request chain, navigation stays absent and
diagnosis says so explicitly.

Relay stays absent for a similar reason. Signed OIP commands authenticate a
caller, but they do not hide browser-control plaintext from the Relay. The
service returns a typed secure-channel error instead of silently weakening the
route.

This is a narrow preview, but it establishes the part that is hardest to retrofit:
identity, authority, retry, reconnect, and refusal semantics. Page actions can be
added after their network boundary is executable, not merely described.

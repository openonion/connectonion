---
# Open Trust (Development)
# Every caller is allowed — the signature is still required

default: allow
---

# Open Trust

For development and testing. Every identity is allowed: no whitelist, no
onboarding, nobody to ask.

Requests are still signed. The levels decide *who may act* — `open` says anyone,
`careful` says admin, whitelisted and contacts, `strict` says the whitelist only.
None of them decides whether a request is authenticated at all:
`extract_and_authenticate` refuses an unsigned one before it reads the level.

    POST /input  (no signature)  ->  401 unauthorized: signed request required

So `curl` on its own will not reach an agent on this level. Use `co call`,
`connect()`, or any client that signs — `address.generate()` is enough of an
identity, because this level does not care which one it is.

**WARNING:** Never use in production. Anyone who can sign anything can run this
agent's tools.

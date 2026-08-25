# The Bill and the Counter Disagreed

The chat said a managed model had used a handful of ordinary input and output
tokens. The account balance said something else. Both numbers came from the
same request, yet the line beside the answer could not explain the charge.
Cached input made the mismatch worse: a warm request could be much cheaper
without the client being able to say which input was new, read from cache, or
written into cache for the next turn.

The first instinct was to improve the client's pricing table. That would have
made the arithmetic look more complete while leaving the authority in the
wrong place. OpenAI, Google, and Anthropic report different usage shapes;
reasoning tokens, cache writes, long-context tiers, and provider pricing can all
change the amount settled by the managed backend. Reconstructing that charge
again on the user's machine creates two bills for one call.

We moved the boundary instead. The backend now normalizes provider usage before
settlement and records the exact token classes and pricing snapshot used for
the debit. Core carries that contract through its trace, and the React client
preserves it without translating it back into a provider-specific approximation.
Older Hosts and direct-provider sessions still keep their existing, smaller
usage shape.

The useful UI is deliberately modest. A completed turn can say how much input
was new, how much came from cache, whether the provider charged for a cache
write, how much output was billed, and the final server cost. It does not expose
the command or wire details that produced those numbers. A historical event
that only knows `42 tokens` still says exactly that; it does not invent a
zero-valued breakdown to fill the new layout.

The measurement that mattered was not whether one total could be made to add
up locally. It was whether the same normalized fields survived the backend,
Core, React, and browser without loss. The focused Core suite passed 93 checks,
the React suite passed 141, and desktop and phone browser flows showed the same
new-versus-cached accounting without horizontal overflow. One charge now has
one source of truth, and the client can finally explain it.

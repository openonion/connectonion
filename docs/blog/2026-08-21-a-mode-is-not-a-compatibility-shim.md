# A Mode Is Not a Compatibility Shim

Defining three mode names was the easy part. The runtime still contained years
of helpful behavior around them: old session keys were translated, public
aliases remained callable, and Full access could prompt the agent into another
turn after a checkpoint. Each behavior had once made an upgrade gentler. In a
permission boundary, they also made the effective contract larger than the one
we claimed to ship.

The dangerous case was not a malformed request. It was a plausible old value.
If a stored `:danger-full-access` marker silently became `full-access`, a new
client had manufactured current authority from stale state. If a Plan value
shared the mode channel, a progress preference could be mistaken for a policy
decision. If Full access continued by itself, a bounded approval bypass had
become an autonomous loop.

The 1.7 runtime now treats the Host acknowledgement as the only authority. Core
stores only `mode` and, for bounded Full access, `turns_left`. One writer changes
that state. Unknown or legacy stored fields are removed and the session returns
to Auto. The Python client rejects an acknowledgement whose mode, budget, or
advertised choices do not satisfy the same contract.

Provider adapters may still translate at their private edge. Claude and Codex
do not need identical internal words; users do need identical public meaning.
That boundary lets the provider evolve without leaking another vocabulary into
React, O Chat, documentation, or durable session state.

The regression suite follows the awkward paths rather than only the happy
button click: fresh sessions for every participant, old stored state, duplicate
advertisements, invalid budgets, reconnect acknowledgements, completed turns,
and expiry back to Auto. The full unit suite and package build then exercise the
rest of the system around those checks.

Compatibility is valuable for data. It is unsafe when it guesses authority.
For a mode, rejecting ambiguity is the migration path.

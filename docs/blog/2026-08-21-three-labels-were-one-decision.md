# Three Labels Were One Decision

The same coding session could be called **Default** in one client,
`:workspace` on the wire, and `auto_approve` inside a provider. Each name made
sense where it was introduced. Together they made a user answer an impossible
question: what authority does the agent have right now?

This was more than inconsistent copy. The old vocabulary had accumulated
aliases, participant-specific defaults, and a Plan value beside permission
values. A reader could translate one spelling into another, but every
translation became a second policy engine. During reconnects and rolling
upgrades, an old browser and a new Host could therefore agree on a label while
disagreeing about its authority.

The 1.7 contract makes the public decision intentionally small. There are only
three exact identifiers: `read-only`, `auto`, and `full-access`. Every
participant starts in Auto. Unknown stored values are discarded to Auto rather
than translated, because stale authority must never become current authority
through a helpful compatibility layer.

Plan is gone from this schema. Planning work still exists as Todo List progress,
but it does not grant or remove permission. Full access is also narrower than
its old name suggested: it bypasses approval only for a bounded number of
completed user-driven turns, then expires to Auto. It never invents another
turn.

The contract fixture is shared byte for byte by Core, React, and O Chat. That
gives the release train one question to test at every boundary: did this value
come from the authoritative Host, and is it one of the three values the user
can actually see?

The lesson is simple. Permission vocabulary is part of the security boundary.
If one choice has three names, it will eventually have three meanings.

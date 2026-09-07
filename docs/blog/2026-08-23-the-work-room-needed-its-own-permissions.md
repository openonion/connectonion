# The Work Room Needed Its Own Permissions

RC1 had three Host permission modes and a working Codex conversation. It also
had a hole that only became obvious in the release screenshots: opening the
Work Room removed the permission controls a Codex user expects to find there.
The remote client showed the provider's work, but it could not control how the
provider would do its next piece of work.

Copying the outer Read Only, Auto, and Full Access buttons into the panel would
have made the screenshot busier without fixing the model. Those controls bound
the whole Host. Codex separately combines a sandbox boundary with a reviewer:
Ask for approval and Approve for me can share the same workspace boundary while
making different approval decisions. Claude Code has a different native set
again. Flattening either provider into three generic labels loses real policy.

The Work Room now receives a finite provider-owned catalog with a selected
option, native profile identifier, reviewer, risk, and Host-enforced
selectability. Codex keeps Read Only, Ask for approval, Approve for me, and Full
Access distinct. Claude Code keeps Plan, Default, Accept edits, Auto, and Bypass
permissions. The outer COAI mode remains the ceiling, and individual action
approvals remain a third, separate boundary.

Changing a selection is a transaction rather than a cosmetic toggle. The
browser signs the invocation ID, the exact revision it saw, and one advertised
option. Host verifies the session owner, Operator role, latest durable state,
and outer ceiling before acknowledging a newer revision. Elevated access also
requires a separate confirmation. Until that acknowledgement arrives, the UI
does not pretend the choice changed.

This matters when several ordinary failures overlap. A stale tab cannot
overwrite a newer choice. A reader cannot promote itself to Operator. Lowering
the outer mode immediately reconciles stored native profiles to the narrower
ceiling. Reconnecting replays the canonical selection, while malformed or old
clients simply receive no usable selector. A selection applies to subsequent
provider work and never rewrites an already-running action.

Eleven transaction and WebSocket tests cover the new boundary, and the full
Core suite passes 7,164 tests with 18 environment-specific skips. The companion
React candidate validates acknowledgements without optimistic updates, while O
Chat exercises the real selector and its separate elevated confirmation at
desktop, tablet, and mobile widths.

The release lesson is narrower than "add more controls." A remote coding client
must preserve the provider's own concepts where they change authority. The
outer Host, the provider session, and a single protected action are related,
but they are not the same permission—and the interface should not claim that
they are.

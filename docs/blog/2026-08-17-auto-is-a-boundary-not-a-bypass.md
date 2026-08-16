# Auto Is a Boundary, Not a Bypass

During a long Codex Work Room test, the task itself was ordinary: write a small
C program, compile it, run its tests. The confusing part was at the bottom of
the chat. The operator saw a mode called **Default**, while the Work Room said
that Codex was waiting for a decision. They asked the obvious question: “Is
Auto actually on, or will I still have to approve this?”

That question exposed a product bug, not a naming nit. The stable line spoke
about an auto-approval plugin, the preview line called the same idea a Host
permission profile, and an older session could still carry a legacy marker.
It was too easy to read one of those things as permission for the browser to do
whatever the next provider request required.

At first, renaming the visible button looked like the smallest fix. It would
have made the screenshot nicer, but it would not have answered the operator's
real question after a refresh or a rolling upgrade. A client can remember a
conversation; it must not decide an authorization default. We changed the
shape of the decision instead: the Host starts a session in Read only, owns the
durable profile, and advertises only the choices it is willing to enforce.

The resulting **Auto** profile is deliberately boring. It covers a small,
deterministic class of reversible work inside the selected workspace. A request
outside that boundary still asks or is denied. Delete operations, credentials,
external control, and out-of-workspace writes do not become safe because a
button has a friendly label. Planning remains a workflow state; it is not a
permission grant.

The regression followed the moment that had caused the confusion: reconnect a
browser carrying an old-looking session, choose the advertised profile, then
ask for work that crosses the boundary. The Host keeps the owner and policy
state, while the policy tests distinguish an allowed local edit from an
ambiguous or destructive action.

This is not the future model-reviewed Auto mode. That needs its own reviewer
and acceptance evidence. For now, Auto means something an operator can answer
in one sentence: *the Host may do this narrow kind of workspace work without
asking again; everything broader remains under review.*

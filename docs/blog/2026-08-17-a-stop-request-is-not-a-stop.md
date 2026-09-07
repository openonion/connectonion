# A Stop Request Is Not a Stop

During the long native Codex Work Room test, the operator pressed **Stop**
while Codex was still running. The old browser path immediately looked stopped.
That made the screen feel fast, but it left the only important question
unanswered: had the Host actually found that exact provider process and asked
it to stop, or had the browser merely changed its own state?

The first tempting repair was another optimistic message: “Stopping…”. It
looked a little more honest, but it still allowed the client to move on without
knowing whether the target invocation was live, whether the Host had accepted
the request, or whether the connection had dropped before it arrived. A green
or red card cannot turn uncertainty into an operating-system fact.

The turning point was treating Stop as a small protocol transaction. The
browser now gives each request an ID. The Host checks its live provider
invocation registry, forwards an interrupt only for that exact active
invocation, and answers with an explicit accepted or rejected acknowledgement.
The React client waits for that acknowledgement. A rejection restores a retry
action; a lost acknowledgement asks the operator to reconnect rather than
pretending the provider stopped. Only a terminal provider lifecycle event
changes the Work Room to **Stopped**.

The acceptance run follows the same distinction. It proves an accepted Stop
targets the current Codex invocation without cancelling the outer turn, proves
a Host refusal leaves an enabled retry action, and exercises the browser at
desktop and phone widths. The protocol tests also reject an interrupt for a
provider invocation that is no longer live.

The reusable rule is simple: a UI request is intent, an acknowledgement is
delivery, and a terminal event is outcome. They belong to different states and
should never be rendered as if they were the same fact.

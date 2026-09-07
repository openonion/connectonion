# The Second Connection Was Still the First

The Codex run had succeeded. The Work Room showed the same provider session,
the follow-up returned the exact confirmation string, and the parent transcript
contained both completed cards. Then we reloaded the page and the Host said:

`already authenticated: open a new connection`

That answer sounded reasonable. The browser had opened a new WebSocket. The
surprise was that, from the Host's point of view, it had not opened a new
connection at all.

OIP sessions commonly travel through the relay. The relay multiplexes browser
traffic to a Host using the application session ID. On reload, the new browser
socket can send its signed `CONNECT` before the close from the old socket has
been delivered and processed. Both frames briefly occupy the same logical
relay queue. The second physical connection therefore arrives inside the first
`run_ws_session` loop, where the connection is already authenticated.

The existing rule rejected every second `CONNECT`. It was added for a good
reason: an authenticated socket must not replace its caller, downgrade signed
commands, point at another recipient, or switch sessions. Removing that guard
would fix reload by reopening a security boundary.

The useful distinction was not first versus second. It was change versus
reattach.

A reload now gets one narrow path. The Host verifies the fresh signature again,
then requires the same caller, recipient, signed-command capability, supported
OIP protocol, and application session. If all of those are equal, it republishes
`CONNECTED` and the authenticated profile. It does not start a second forwarder
for a running agent. If any field differs, the old rejection remains. Reusing
the same signature still fails the replay guard.

The first public alpha taught us that “verifies the fresh signature again” was
still too broad. The implementation reused the whole first-connect gate, so it
also repeated the mutable trust decision: read the contact lists, decide whether
the caller must onboard, and consult policy. A brand-new session connected, but
its first Send raced another equivalent `CONNECT` through that second policy
read. A local missing-file error became `misconfigured: [Errno 2]` in the browser,
and the actual `INPUT` never reached the Host.

That was not a reason to weaken reauthentication. It was a reason to name its
two halves. A first connection proves the signed identity and authorizes it under
current policy. An equivalent reattach must prove the signed identity, recipient,
freshness, replay claim and current blacklist again, then show that every bound
connection field is unchanged. It must not ask onboarding/contact policy to
authorize the same still-live connection twice, nor re-read admin lists and
rebuild permission authority that connection already owns. It republishes the
existing mode, profile, transcript, and dashboard state to the new physical
browser socket. Custom verifiers retain their existing gate unless they
explicitly provide the same narrow reattach half.

The tests make the boundary visible. One session-loop test puts two freshly
signed, equivalent `CONNECT` frames into the same logical stream and expects two
`CONNECTED` replies for the same session. Six negative cases try to change the
identity, recipient, capability, session, protocol, or reuse a signature. Every
one is rejected. A regression makes trust policy raise the exact missing-file
error and proves reattach never calls it; another makes admin/mode initialization
raise the same error and proves it is not repeated. A newly blacklisted caller is
still refused. Together with the existing Host, relay, replay, profile, and
command-signing coverage, 76 focused tests passed in the follow-up run.

The production screenshot was the important measurement. Before this change,
the transcript proved that Codex had finished while a red authentication error
claimed the page was broken. That contradiction exposed two different bugs:
O Chat held on to a cleared error, and the Host created a new error during
reload. Fixing only the banner would have made the first screenshot cleaner and
the next refresh fail again.

Connection identity is a stack of names: physical WebSocket, relay route,
authenticated caller, OIP application session, and provider session. In the
simple case they begin and end together, so it is tempting to treat them as one
thing. Reload is where they separate. The browser connection can be new while
the relay route and application session are deliberately old. A correct
reconnect policy preserves that continuity without letting any authority move.

The lesson is small enough to reuse: idempotence is not the absence of a
security check. It is the security check that proves nothing changed.

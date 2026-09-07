# Authorise in Advance, So Nobody Signs at 3am

The question behind ConnectOnion's remote-browser design was ordinary for
anyone who has run something overnight: a laptop that's sometimes on, a home
desktop that's always on but sits behind a residential NAT, and a server with
a real address that runs the browser. Route the browser's traffic through the
desktop's connection, and a scheduled task can survive the laptop being
closed. The awkward part was never the routing — it was who gets to say yes,
and when.

The obvious shape is a live handshake: the browser asks, the desktop is
online, the desktop signs, off it goes. That shape breaks the moment the task
is scheduled. Nobody is required to be at a keyboard at 3am, so nothing that
happens at 3am should require a decision made at 3am. The three parties are
better described by role than by machine: **P**, who owns the egress and
decides who may use it; **D**, the developer's agent, who holds an
authorisation and can go offline; and **B**, the browser, who shows up later
and presents it.

A direct grant — P signs a credential naming B — covers the simple case: a
chain of length one, holder equal to presenter, no delegation in the middle.
The chain gets interesting where the topology forces P and B to never meet as
peers. In a reverse tunnel, P is the one behind NAT, so P dials out to B, not
the other way round. That inverts the naive rule "trust whoever connected" —
under that rule P would be verifying itself, and the credential would protect
nothing. The check that actually matters binds to the identity *using* the
credential, the one B can independently authenticate, never to whichever side
happened to open the socket. Who dials is an accident of NAT topology; who is
authorised is the design.

The rest follows from taking "in advance" seriously. `delegable_to` is a
pinned list signed at issuance — an empty list refuses every delegation
rather than defaulting open. `renewable_until` sets a ceiling nobody, not
even the grantor at renewal time, can push past — the pre-authorised decision
is the one that's allowed to move, not a fresh one made under time pressure.
And verification returns two identities on purpose: `egress_for`, whoever is
actually using the network right now, and `accountable`, whoever is on the
hook for it — because a worker rotates in a way an account never should, and
conflating the two would make usage untraceable to a person the moment the
worker changed.

Fifteen tests carry the design, and the one that matters most is named for
the failure it prevents: `test_presenter_binding_refuses_the_dialing_party`.
It hands P the chain that authorises B, has P present it — since P is the one
making the connection — and asserts that this fails. If that test ever turns
green, the reverse tunnel has quietly become a way for the proxy to grant
itself its own egress.

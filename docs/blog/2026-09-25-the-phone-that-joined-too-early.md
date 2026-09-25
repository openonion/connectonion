# The phone that joined too early

A re-tester was checking that one conversation could be open on two devices, a
laptop and a phone, on 1.8.8b9. Everything passed. Then they tightened the
script. They restarted the host, waited about fourteen seconds, paired both
devices on one session, and had the laptop ask a question straight away.

The laptop got its answer, `ALPACA`. The phone got `CONNECTED` and then nothing
for the rest of that turn: no copy of the question, no stream, no `OUTPUT`. Its
Home page and agent profile arrived only after the turn had finished. They ran
it four times and got the same result four times. They tried 1.8.7 and it
behaved the same way. They tried waiting six seconds before asking, and the
phone saw everything.

## Reading the clue

The six seconds were the clue. A bug that disappears when you wait is a race,
and the fresh restart suggested what the host was busy with. The first time a
new host process renders a Home snapshot it has cold work to do, and that takes
a few seconds.

On `CONNECT`, the host verifies the signature, merges the session, sends
`CONNECTED`, sends the agent profile, and then renders and sends the Home
snapshot. Only after all of that returned did the socket loop add the
connection to the session's viewers. That list is how a turn started on one
device reaches the others. When the laptop's `INPUT` arrives, the host reads
the list once and starts a forwarder for each device on it.

So for the length of that first render, the phone was in an odd state. It was
authenticated and had been told which session it was in, but it was not on the
list. The laptop's turn started during that window, found only the laptop, and
never checked again. When the phone was added a moment later, the turn had
already been fanned out without it. That also explains why the Home page came
late: the phone's socket was still working through its own `CONNECT` while the
laptop's turn ran.

The code was not wrong line by line. Each step made sense on its own. The
problem was the order: a slow, cosmetic step came before the step that made
the connection count. Nothing in the protocol required the snapshot to finish
before the device could receive frames. The code happened to be written in
that order, and nobody had joined a session fast enough to notice.

## The fix, and where the line goes

The fix moves one call. The connection joins the viewers as soon as `CONNECTED`
has been sent, before the profile and the snapshot. We picked that point
carefully. Any earlier, and a fast turn could send the phone a `user_message`
before the phone knew its session, which a client cannot place. At that point,
the phone's first frame is always `CONNECTED`, and anything after it belongs to
a session the phone already knows about.

The test that caught it makes the phone's Home render wait, with no time limit,
until the laptop's turn has finished. Before the fix, the phone waits for an
`OUTPUT` that never comes. After it, the phone sees the question and then the
answer, while its Home page is still rendering.

The same re-test turned up other places where the system reported something
that was not true: a restarted host was reported as an auth error, a session
with intact history came back as `new`, and a timed-out turn showed as `idle`.
Those fixes are in the same pull request.

## What we took from it

Whenever there is a list of who should hear about something, look at what runs
before a new member is added to it. Slow work in that gap is time during which
a new member exists but hears nothing. The fix does not make that work faster.
It adds the member before starting it.

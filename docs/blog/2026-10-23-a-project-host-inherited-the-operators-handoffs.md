# A project Host inherited the operator's handoffs

An isolated browser acceptance run opened a fresh Host with its own signing
identity, an explicit configuration directory, no relay and no chat channels.
The browser task had not run when unrelated handoff notices began appearing
in its log.

The Host was isolated at the request boundary. Its startup work was not.
`host()` called `_create_handoff_lifespan()` without passing the configuration
directory. The watcher then selected the ambient configuration, where the
operator's pending handoffs lived. That watcher can update seen records,
remember peers and send notifications or automatic replies. Starting it is
more than reading a status feed.

The run was stopped and its evidence retained. The private log was enough to
confirm that global persistence paths had executed. It was not enough to
establish every possible outbound effect, so this is not a claim that no
notification occurred. No private handoff contents are included here, and
historical records are not reset as a repair: resetting them could cause
repeated notifications or session copies.

The bounded change passes the Host's configuration directory into startup and
starts the existing watcher only when that resolved directory owns the
configured handoff store. A different project Host does not start an ambient
watcher. A matching configured directory retains the original start and
shutdown behavior. The owner's CLI watcher is unchanged.

This deliberately does not implement project handoff queues by temporarily
switching process environment. A watcher runs on a thread, and changing an
environment variable would change the meaning of configuration for every
other thread too. Per-project handoff transport and persistence would need
an explicit contract of their own.

The regressions use temporary directories and a watcher spy: separate Host
ownership never starts the watcher, matching and normalized directory paths
retain start/shutdown, and the public Host passes its directory through. They
do not read a real mailbox, global handoff records or customer data. This
source change still requires its normal PR checks and release acceptance;
the browser pacing patch is a separate change.

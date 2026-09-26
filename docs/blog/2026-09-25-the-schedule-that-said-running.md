# The schedule that said "running"

An agent had a fifteen-minute report on its schedule. One morning the Home page
said the report was `running`, and it still said `running` at lunch. Nothing
was running. The log had one red line from hours earlier, `tick failed: control
center: network blip`, and after it, every minute, `report still running,
skipping this tick`.

The scheduler works in two steps on purpose. First it claims each due entry by
writing `status: running` into `.co/schedule-state.json`, under a lock every
worker respects, so no second copy can start. Then it runs what it claimed. Between
those two steps sat the tick's housekeeping: the Control Center's own turn and
session compaction. When the Control Center call raised, the tick stopped right
there. The claim was already written, so the run never started, and every later
tick trusted the claim and skipped the entry. The mark that keeps one copy
running had become a mark that kept zero copies running until someone restarted
the agent.

Looking for how that happened turned up two more cases of the same kind,
where the state file says one thing and the processes say another.

`co schedule run report` sets a `run_requested` flag and promises a run within
a minute. If the report was already mid-run, the run finished by rewriting the
entry's state from scratch, keeping only `paused`, and the request was erased
along with the old status. The CLI had promised a run, and it never happened.

An `exec:` entry runs through a shell with a ten-minute timeout. On timeout
Python kills the shell. The script under the shell was never told, kept
running, and finished some time later, while the state said `failed`. The next
tick then started a second copy beside it.

In each case the state record was treated as a report on what the processes
were doing, when it was really a promise about what they would do. A promise
has to hold even when something else fails. So:

- Claimed runs are started as tasks the moment they are claimed, before
  anything else in the tick is allowed to raise, and the tick waits for them
  even when its housekeeping fails. A `running` mark now always has a run
  behind it.
- A run request is consumed by the claim, which is the run it asked for, and
  nothing else erases it. A request that arrives during a run survives until
  the next one.
- An `exec:` command gets its own process group, and a timeout kills the whole
  group. When the state says `failed: timed out`, nothing from that run is
  still going.

The tests for all three work the same way. They make the thing next to the
promise fail (a Control Center tick that raises, a request that lands
mid-run, a script that forks a second shell) and then check the promise still
held: the entry ran, the request is still there, the orphan never touched its
file.

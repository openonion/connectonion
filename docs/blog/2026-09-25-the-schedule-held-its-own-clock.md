# The schedule held its own clock

We were asked a simple question about the scheduler: is it documented, and is
there a better design? Reading it to answer the first question turned up two
ways a schedule could stop without anyone noticing.

The first was ordering. Each minute the Host took a lock, then ran every due
entry one after another before letting go. The lock exists so that four
workers do not start four copies of the same job, and it did that. But it
also meant a ten-minute entry delayed every other entry by ten minutes. An
agent turn has no time limit, so one turn that hung stopped the whole
schedule, and the session compaction that runs on the same tick, until
someone restarted the process.

The second was start-up. If an agent booted with nothing scheduled, the clock
was never started. Entries are re-read every minute, but only once the clock
is running. So when a user asked the agent to "do this every morning" and it
wrote `schedule.yaml`, nothing happened until the next restart, and nothing
said so.

The fix is mostly removal. The lock now covers deciding what is due, not
running it. Each due entry is written as `running` in the state file before
it starts, and then runs as its own task. That one mark does three jobs that
used to be done separately: it keeps a second copy from starting, in this
process or another worker; it is what the Home page shows while a job works;
and it survives a crash, so start-up can say "the agent stopped during this
run" instead of leaving the entry looking busy forever. The in-memory set that
tried to do the first two is gone. So is the rule that skipped the clock when
the file was empty.

We did not add a timeout for a hung turn. A thread cannot be killed safely,
and a timeout that only stops waiting leaves the turn running while the entry
looks finished. With each entry isolated, a hung turn now costs only itself,
and the Home page shows it as running for as long as it really is.

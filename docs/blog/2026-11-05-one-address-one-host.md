# One address, one Host

Ask a question about the stop button and you sometimes find a second agent.
After `co host` learned to stop cleanly, the next question was what `co host
--stop` should stop. The obvious answer is "the Host". That turned out to
have no single meaning, because a laptop can easily run several.

`co ai` serves a Host. So does a project's `co host`, and so does the
background service from `co init --background`. `co rem open` starts its own
`co ai`, detached, when it finds nothing to read through. None of them gives
its project a key of its own, so all four serve the address in `~/.co`. Each
one connects to the relay, announces that address, and re-announces it every
sixty seconds to stay registered.

The relay keeps one socket per address, the most recent announcer's. To find
out what that means for two Hosts sharing an address, we measured it. One
throwaway identity, two Hosts on ports 8711 and 8712, and the relay's entry
for the address read every fifteen seconds for four minutes. It never
settled: twelve samples pointed at 8712 and four at 8711, switching on each
heartbeat. A call to that address went to whichever Host had spoken most
recently. If one was a coding agent and the other a project with different
tools, the caller couldn't tell which one was answering.

The old code already knew about sharing. Since #642 a Host writes
`served_by.json` next to the key and warns when a different project used it
last. It only warns, and the reason it gives is a good one: the agent that
claimed the key may be the one restarting, and a stale claim that blocks a
restart is worse than a message. A JSON file can't tell a live claim from
one a crash left behind.

A lock can. The Host now takes an exclusive lock on `host.lock` next to the
key before it binds a port, and keeps it for as long as the process lives.
The OS drops the lock when the process dies, however it dies, so the stale
claim that justified only warning can't happen any more. A second Host on the
address is refused and told where the first one is:

```text
[host] 0x3ae5aab6… is already served on this computer by 'a' in /Users/you/a (pid 72209, http://localhost:8731). One address, one Host: the relay would pick between them at random.
       Use that one, or stop it first: co host --stop
```

The lock is taken before the port check for the same reason. When the port
is held by this address's own Host, "already served by it" is the true
answer and "port in use" is a misleading one.

Next to the lock sits `host.json`, which records who holds it: the pid, the
port, the project, and the launchd job when there is one. That record is
what makes the stop button work from anywhere. `co host --status` and `co
host --stop` used to look only for a service named after the current folder,
so the background service could only be found from a directory nobody had
been told about. Now any folder finds the one Host. A launchd job is stopped
as a job, because killing only its pid makes KeepAlive start it again: on a
real service the stop held for twenty seconds with the port free. `co status`
gets a "Host on this computer" line. `co rem open` reads through the Host
that is already serving instead of starting another.

The lesson is about where state lives. "Who is serving this key" was a
question about a running process, and it had been stored in a file that
outlives the process. Storing it in something that dies with the process,
the lock, let the warning become a refusal.

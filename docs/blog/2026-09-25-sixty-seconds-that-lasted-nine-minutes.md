# Sixty seconds that lasted nine minutes

A tester hosted the co-ai template on 1.8.8b7 and drove it from Python, the way
the README shows:

```python
connect(addr).input("run cat /outside/file", timeout=60)
```

The file was outside the project, so the agent asked for approval before
running `cat`. The call came back after 519 seconds. It had asked for sixty.

Nothing in that run was broken on its own terms. The agent sent
`approval_needed` and waited, which is what it should do before reading outside
its folder. The Host sent a PING every thirty seconds so the relay would not
drop an idle socket, which is what keepalives are for. The client wrapped each
`recv()` in `wait_for(..., timeout=60)`, which is how you stop one read from
hanging. The client had no branch for `approval_needed`, so it filed the event
under "stream event" and read the next frame. That was the next PING, and the
sixty seconds started over.

Each piece was reasonable, but together they meant nothing could end the call.
The timeout checked the wrong thing. It asked "has the socket been quiet for a
minute?" when the caller had asked "give up after a minute". A socket that is
alive and waiting is never quiet. The more carefully the Host kept the
connection up, the longer the client waited.

So `timeout` is now a deadline for the whole call. Every read waits only for
the time that is left, and when it runs out, the error names the session: "the
turn may still be running on the host in session 1a24…: agent.stop()
interrupts it". The Python client had no `stop()` until now, though the Host
had accepted `INTERRUPT` from the other clients all along. Now it does.

The deadline makes the call end, but ending sixty seconds later with nothing
still wastes the minute. The client had been given a question and ignored it.
Now `approval_needed` and `ask_user` go to the caller. Pass `on_approval=` or
`on_ask=` and the answer goes back in the same call. The answer names the
request it answers, because #1692 is making the Host refuse answers that do
not. With no callback, a question still returns `done=False`, as documented.
Before this fix, the next `input()` sent the answer as a brand-new prompt in a
new session, and the turn that asked kept waiting on the Host. Now it goes back
as the answer. An approval without a callback fails at once with the tool, its
arguments, the session, and the two ways out: `respond_to_approval()` or
`stop()`.

The same tester also killed the Host partway through a turn. The client raised
a bare `ConnectionClosedError 1012`, and the docs said the client "automatically
polls GET /sessions/{id}". That sentence was true of the TypeScript client. We
thought about making it true of Python as well, and found that polling cannot
work there. A Host that restarted has lost the turn along with its thread, so
there is no result to poll for. What can work is reopening the session: when
the socket closes, the network blinked, or the relay reconnected, but the Host
may still be running the turn. So the client reconnects with the session id and
the last event it saw. If `CONNECTED` says the turn is still running, the stream
picks up where it stopped. If not, the error says so and names the session. The
prompt is never sent again. The tester's prompt was harmless, but the next one
might run a tool, and running a tool twice could do real damage.

The lesson we are keeping is about timeouts and keepalives. A timeout on
silence cannot sit under a protocol whose job is to never be silent: the
keepalive defeats it every time. The caller's patience is a deadline, and a
deadline counts down whatever the socket is doing.

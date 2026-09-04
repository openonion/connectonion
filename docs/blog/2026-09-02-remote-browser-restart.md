# When a Remote Browser Restarted, the Lock Did Not

The failure looked like a proxy problem, but it began one restart earlier. A
host process had opened a shared Remote Browser session, then the machine
restarted. The session registry survived because it is deliberately persisted;
the private browser daemon did not. On the next start, the registry still said
that an active session owned the shared proxy, so the new daemon was refused
before it could do useful work. Every later attempt received
`REMOTE_SESSION_PROXY_LOCKED`, even though there was no browser left to hold
the lock.

The misleading part was the source of truth. The session file is durable
history, not proof that a runtime is alive. Treating its `active` status as a
live daemon claim made a clean host restart indistinguishable from a real
concurrent browser. The error message also called the product “WTF Browser,”
which made the recovery path harder to recognize.

The fix makes the boundary explicit at the start of a new session. When the
service has a private daemon target, it checks the daemon's existing liveness
sidecar before applying the proxy lock. If the owner is gone, runtime-only
active sessions become stopped, their timestamps are updated, and the stale
shared-proxy selection is removed. Only then does the normal start path bind a
new session to the new daemon. Embedded test seams keep their existing
behavior because they do not own a private daemon target to inspect.

The regression test exercises the failure as a restart: it creates a persisted
shared session, leaves the daemon liveness record absent, verifies the stale
proxy file is cleared, and starts a replacement session with a different proxy
binding. The focused unit and daemon lifecycle tests pass together (15 passed),
and the lock message now names Remote Browser consistently. The durable session
file still records the old session as stopped, so later status and stop calls
retain an auditable tombstone instead of silently forgetting what happened.

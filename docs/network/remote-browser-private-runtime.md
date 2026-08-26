# Remote Browser private runtime

Remote Browser lifecycle uses the existing `BrowserDaemon` and
`AsyncBrowserCore`, but it does not attach to the ordinary local `co browser`
instance. The Host derives a private target from its durable Remote Browser
state path and starts the same daemon implementation with explicit authority.

This is delivery step 3 of
[DD-056](../design-decisions/056-remote-browser-egress-gateway.md). It isolates
the runtime and wires the loopback gateway into Chromium's requested launch
configuration. It does **not** expose navigation or claim that Chromium's
effective network behavior has passed the native bypass vectors required by
step 4.

## Isolation contract

Each Host state file deterministically selects one private runtime with its own:

- native Unix socket or Windows named-pipe namespace;
- lifetime PID and singleton-lock sidecars;
- persistent browser profile;
- daemon log;
- Windows IPC authentication key; and
- ephemeral authenticated egress gateway credential.

The local `co browser` namespace and profile remain unchanged. Local and private
daemons can run at the same time and stop independently. Long project paths are
hashed into short endpoint names so Darwin's `AF_UNIX` limit cannot collapse
the isolation contract into a launch failure.

The private runtime directory is mode `0700` on POSIX. The Windows auth key is
created through the existing atomic, per-file HMAC-key path. Gateway passwords
are never command-line arguments and are excluded from dataclass
representations. The session registry, state file, log path, errors, and command
results contain no proxy credential.

## Start and stop order

```text
start gateway -> build immutable launch policy -> build browser -> bind IPC

stop admission -> close browser -> stop gateway -> remove owned IPC state
```

If the gateway cannot start or the browser cannot be constructed, the daemon
never binds its IPC endpoint. If the gateway stops serving later, every daemon
command returns `EGRESS_GATEWAY_UNAVAILABLE` before a tab or browser mutation.
There is no Direct fallback.

## Requested Chromium launch policy

The daemon passes one immutable policy directly to `AsyncBrowserCore`; private
launch does not consult `BROWSER_PROXY` or `CO_BROWSER_PROFILE_DIR`. The policy
requests:

- the authenticated gateway at exactly `http://127.0.0.1:<ephemeral-port>`;
- Chromium's subtractive `<-loopback>` proxy-bypass rule;
- `MAP * ~NOTFOUND, EXCLUDE 127.0.0.1` host-resolver rules;
- QUIC disabled;
- non-proxied WebRTC UDP disabled;
- extensions disabled;
- Service Workers blocked; and
- a dedicated persistent profile with downloads accepted.

The proxy value rejects non-loopback hosts, alternate spellings, paths,
userinfo, query strings, fragments, empty credentials, and fallback proxy
lists. These tests prove the configuration requested from Playwright. They do
not prove that a pinned Chromium build honored every switch or that every
request class used the proxy; those are the native zero-socket assertions in
the next delivery step.

## Verification and rollback

The focused matrix runs on Linux, macOS, and Windows with Python 3.10–3.13. It
checks namespace separation, secret-safe launch values, gateway-before-bind and
browser-before-gateway ordering, fail-closed gateway loss, environment
independence, concurrent local/private native daemons, and signed OIP lifecycle
reconnection through the private target.

Rollback removes the private target selection and daemon launch mode together.
Remote Browser then returns to lifecycle-only operation with navigation still
unavailable. Rollback must never point Remote Browser at the ordinary local
daemon or remove the gateway while leaving page commands enabled.

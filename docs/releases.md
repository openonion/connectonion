# Release channels

ConnectOnion has two release channels:

- **Stable** is the default `pip install connectonion` channel. It is the version
  recommended for production agents.
- **Preview** contains alpha, beta, and release-candidate builds for features
  that are still being exercised end to end. Install one explicitly, for
  example: `pip install connectonion==1.7.0a2`.

Preview releases never replace the stable recommendation on the documentation
site, and GitHub marks them as pre-releases rather than latest releases.

## Current channels

- Stable: `1.6.4`
- Preview candidate: `1.7.0a2`

The second alpha delivers the first end-to-end native browser ACP slice. The
Host exposes an authenticated `/acp` WebSocket selected through explicit,
fail-closed discovery; binds the caller to one virtual workspace and private,
bounded session and attachment storage; and verifies payment onboarding before
issuing a one-use browser ticket. Permissions, cancellation, modes, thoughts,
plans, tool activity, reconnect, and resume stay on the shared ACP lifecycle.

The supported browser protocol owner is `@connectonion/react`, whose reviewed
`0.4.2-alpha.2` artifact is pinned by O Chat and exercised in desktop and mobile
browser tests. The retired standalone TypeScript SDK is not part of this
release path. The native endpoint is a direct loopback or TLS/WSS preview; it
does not claim end-to-end encryption through an untrusted relay.

Normal upgrades stay on stable. Preview testers opt in explicitly:

```bash
python -m pip install --pre --upgrade connectonion
python -m pip install connectonion==1.7.0a2
```

## Design Journal

Release notes record what changed. A Design Journal post records the problem,
alternatives, decision, tradeoffs, evidence, and what would make us revisit it.
Meaningful feature-train launches, the first beta and RC, stable releases, and
material architecture or workflow decisions receive a new or substantially
updated post.

Maintenance-only patches stay in release history unless they contain a reusable
design lesson. Drafts can be prepared with the candidate, but the public post
must not claim that a version is available until PyPI and its GitHub Release are
visible.

The current release-train decision is documented in
[Why Alpha, Beta, and RC Come Before ConnectOnion 1.7 LTS](https://docs.connectonion.com/blog/alpha-beta-rc-before-lts).

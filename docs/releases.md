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

- Stable: `1.6.0`
- Preview candidate: `1.7.0a2`

The second alpha completes the Host side of the browser-facing ACP session
contract: bound permission identity, negotiated cancellation, authoritative
mode state and transactions, public thoughts, and canonical TodoList plans.
The supported browser consumer is `@connectonion/react`; the retired standalone
TypeScript SDK is not part of this release path.

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

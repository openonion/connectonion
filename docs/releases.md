# Release channels

ConnectOnion has two release channels:

- **Stable** is the default `pip install connectonion` channel for production.
- **Preview** contains opt-in alpha, beta, and release-candidate builds.

Preview releases never replace the stable recommendation. Install one with
`--pre` or pin its exact version.

## Current release work

- Stable patch target: `1.6.8`
- Preview target: `1.7.0a5`
- Browser client target: `@connectonion/react@0.4.2-alpha.4`

The preview uses OIP 0.1 as the only first-party browser protocol. The Python
Host serves the authenticated `/ws` connection; `@connectonion/react` owns the
browser client; O Chat consumes the exact React prerelease. Codex and Claude
Code remain native backend provider adapters and publish their normalized
activity through OIP.

Alpha 5 removes the abandoned alternate transport, generic coding-agent edge,
SDK dependency, CLI flags, gateway, exports, tests, fixtures, and product docs.
It also includes owner onboarding that mints one private invite on a fresh
installation and reveals it only through an explicit `co keys --reveal` action.

Normal upgrades stay on stable. Preview testers opt in explicitly:

```bash
python -m pip install --pre --upgrade connectonion
python -m pip install connectonion==1.7.0a5
```

## Design Journal

Release notes record what changed. A Design Journal post records the problem,
alternatives, decision, tradeoffs, evidence, and what would make us revisit it.
Meaningful feature-train launches, phase promotions, stable releases, and
material architecture decisions receive a new or substantially updated post.

The OIP-only decision is recorded in
[DD-053](design-decisions/053-oip-only-browser-and-native-coding-adapters.md).

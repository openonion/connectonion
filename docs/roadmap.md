# Roadmap

ConnectOnion's release order, as of 2026-09-28. Track progress on
[GitHub](https://github.com/openonion/connectonion/milestones).

Stable is **1.8.8**. The current preview is named in
[`VERSIONING.md`](../VERSIONING.md) under `## Current Version` and in
[Release channels](releases.md).

## Now: 1.8.9, the fix line ending in stable

1.8.9 is fixes, documentation and doc tests
([#1722](https://github.com/openonion/connectonion/issues/1722) tracks every
issue and PR in it). Features already open as PRs ship in the last preview;
nothing new starts on this line. Stable 1.8.9 follows once that preview's
end-to-end evidence is complete (see [VERSIONING.md](../VERSIONING.md) for what
earns a stable release).

## Next: 1.9.x, new features

- Agent-owned watches through the session event runtime
  ([#1788](https://github.com/openonion/connectonion/issues/1788)).
- Agentic investigation: an agent searching prepared evidence files, not a
  reader of chunk digests
  ([#1850](https://github.com/openonion/connectonion/issues/1850)).
- OneNote as a Wiki source
  ([#1886](https://github.com/openonion/connectonion/issues/1886)).
- WhatsApp voice notes an agent can answer
  ([#1861](https://github.com/openonion/connectonion/issues/1861)) and
  @mentions in group sends
  ([#1862](https://github.com/openonion/connectonion/issues/1862)).
- The other issues labelled `[1.9]` on GitHub.

## Longer-term work

- secure agent-to-agent networking and relay transport;
- production deployment, health monitoring, and environment management;
- stronger interactive debugging and time-travel inspection;
- documentation and tutorial expansion.

# Roadmap

ConnectOnion's development roadmap. Track progress on
[GitHub](https://github.com/openonion/connectonion/milestones).

## Current milestone

### 1.7.0 — OIP and native coding adapters

The 1.7 preview train delivers one authenticated browser lifecycle over OIP:
onboarding, reconnect, session state, approvals, permission profiles,
interruption, plans, and nested provider activity.

Release order:

1. Remove the abandoned alternate transport and generic provider edge.
2. Publish the matching Python and `@connectonion/react` previews.
3. Pin that exact React version in O Chat and deploy its preview.
4. Run browser acceptance with onboarding, a normal prompt, and real Codex
   delegation; repeat Claude Code acceptance when its adapter changes.
5. Promote alpha to beta only after desktop/mobile reconnect, approval, cancel,
   and provider-card evidence is complete.

The architecture and release evidence are defined by
[DD-053](design-decisions/053-oip-only-browser-and-native-coding-adapters.md)
and [issue #1045](https://github.com/openonion/connectonion/issues/1045).

## Longer-term work

- secure agent-to-agent networking and relay transport;
- production deployment, health monitoring, and environment management;
- stronger interactive debugging and time-travel inspection;
- Microsoft OAuth and additional managed integrations;
- documentation and tutorial expansion.

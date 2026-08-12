# Roadmap

ConnectOnion's development roadmap. Track progress on [GitHub](https://github.com/openonion/connectonion/milestones).

## Current Milestones

### 1.7.0 — ACP + coding-agent preview train

The 1.7 preview train makes one coding-agent lifecycle available to editors,
CLIs, and the browser without removing ConnectOnion's authentication and trust
boundary.

**Merge order:**

1. [#895](https://github.com/openonion/connectonion/issues/895) — native `/acp`
   WebSocket behind signed admission and exact browser-Origin tickets
2. [#896](https://github.com/openonion/connectonion/issues/896) — complete the
   shared principal model and bind canonical permission profiles to it;
   collaboration `default` / `plan` remains React-owned
3. [#893](https://github.com/openonion/connectonion/issues/893) — migrate
   `@connectonion/react` and O Chat from `/ws` to native ACP
4. [#894](https://github.com/openonion/connectonion/issues/894) — run direct
   conformance, security, and browser reconnect gates before beta promotion
5. [#898](https://github.com/openonion/connectonion/issues/898) — separately
   decide and review an end-to-end secure relay channel before relay ACP ships

The parent design and exit criteria live in
[#892](https://github.com/openonion/connectonion/issues/892). The legacy `/ws`
path remains a bounded compatibility fallback during the preview; it is not
renamed or presented as ACP. #897's signed `_meta` proposal is not relay
encryption and is deferred until #898 decides whether it has a narrower
post-decryption provenance role.

### Launch the Network (Q4 2025)

Implement the ConnectOnion peer-to-peer network protocol where agents discover and collaborate using public keys as addresses.

**Features:**
- Message-based architecture (ANNOUNCE/FIND/TASK)
- Relay nodes for NAT traversal
- Encrypted peer-to-peer communication
- Contact/stranger management
- Managed keys API (`co/` prefix) - **Done**

### Multi-Agent Trust System (Q1 2026)

Build a trust system for secure multi-agent collaboration.

**Features:**
- Agent-to-agent trust verification
- Trust levels for remote agents (open/tested/strict)
- Behavior-based trust scoring
- Trust policies for agent networks

### co deploy - Agent Deployment (Q1 2026)

One-command deployment for production agents.

**Features:**
- `co deploy` CLI command
- Deploy to cloud providers (AWS, GCP, etc.)
- Automatic HTTPS and domain setup
- Environment management (dev/staging/prod)
- Health monitoring and auto-restart

### AI Auto-Coding (Q2 2026)

Enable AI agents to automatically write, debug, and improve code.

**Features:**
- `auto_debug_exception` for runtime debugging - **Done**
- Code generation tools
- Automated testing
- AI-powered refactoring

## Open Features

### Debugging & Development
- [ ] Implement AI Help Mode for interactive debugging assistance
- [ ] Implement step mode for debugging all tool executions
- [ ] Implement modify result command for time-travel debugging
- [ ] Implement inspect command for viewing agent state
- [ ] Implement retry command for re-executing tools
- [ ] Implement update prompt command for mid-execution changes

### Documentation
- [ ] Create tutorial video series
- [ ] Update docs website with current features
- [ ] Create comprehensive auto-debug documentation
- [ ] Create templates/ documentation folder with individual template guides
- [ ] Document Claude Code plugin templates for AI vibe coding

### Platform
- [ ] Add Microsoft OAuth integration (`co auth microsoft`)
- [ ] Add conflict detection for duplicate tool names
- [ ] Session logging and eval system

## Recently Completed

- Google OAuth integration (`co auth google`)
- React-mode plugin example
- Managed keys API (`co/` prefix)
- Auto-detect base64 image results for vision models
- Network feature API design (serve/connect)

## Contributing

Want to contribute? Check [open issues](https://github.com/openonion/connectonion/issues) or join our [Discord](https://discord.gg/4xfD9k8AUF).

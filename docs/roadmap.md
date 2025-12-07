# Roadmap

ConnectOnion's development roadmap. Track progress on [GitHub](https://github.com/openonion/connectonion/milestones).

## Current Milestones

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

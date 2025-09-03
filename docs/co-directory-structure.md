# The .co Directory Structure

The `.co` directory is the heart of every ConnectOnion project. It contains project metadata, agent identity, and runtime information. This document explains what's inside and why.

## Directory Overview

```
.co/
├── config.toml          # Project and agent configuration
├── keys/                # Agent cryptographic keys (git-ignored)
│   ├── agent.key        # Private signing key (Ed25519)
│   ├── recovery.txt     # 12-word recovery phrase
│   └── DO_NOT_SHARE     # Warning file about key security
├── docs/                # Embedded documentation
│   └── connectonion.md  # Framework reference (offline access)
└── history/             # Agent behavior logs (created at runtime)
    └── behavior.json    # Execution history and metrics
```

## config.toml Reference

The `config.toml` file contains all project and agent configuration:

```toml
# Project metadata
[project]
name = "my-agent"                           # Project name (defaults to directory name)
created = "2025-01-03T10:00:00Z"           # ISO 8601 creation timestamp
framework_version = "0.0.1b8"               # ConnectOnion version used

# CLI information
[cli]
version = "1.0.0"                           # CLI version
command = "co init --template meta-agent"   # Command used to create project
template = "meta-agent"                     # Template type (meta-agent, playwright)

# Agent configuration
[agent]
address = "0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
short_address = "0x3d40...660c"            # Truncated for display
created_at = "2025-01-03T10:00:00Z"        # When keys were generated
algorithm = "ed25519"                       # Cryptographic algorithm
default_model = "gpt-4o-mini"              # Default LLM model
max_iterations = 10                         # Max tool-calling iterations
```

## Keys Directory

The `keys/` directory contains your agent's cryptographic identity. **This directory should NEVER be committed to version control.**

### agent.key
- **Format**: Binary Ed25519 private key (32 bytes)
- **Purpose**: Signs messages for agent-to-agent communication
- **Security**: Should be encrypted at rest (future feature)

### recovery.txt
- **Format**: 12-word BIP39 mnemonic phrase
- **Purpose**: Recover agent identity on new machines
- **Example**: `canyon robot vacuum circle tornado diet depart rough detect theme sword scissors`
- **Security**: Store securely, never share, enables full key recovery

### DO_NOT_SHARE
- **Format**: Plain text warning file
- **Purpose**: Reminds developers these are private keys
- **Content**: 
  ```
  ⚠️ WARNING: PRIVATE KEYS - DO NOT SHARE ⚠️
  
  This directory contains private cryptographic keys.
  NEVER share these files or commit them to version control.
  Anyone with these keys can impersonate your agent.
  ```

## Agent Address Format

The agent address is a hex-encoded Ed25519 public key:

```
0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
```

- **Prefix**: `0x` (indicates hexadecimal, familiar from Ethereum)
- **Length**: 66 characters total (0x + 64 hex characters)
- **Content**: Direct encoding of 32-byte Ed25519 public key
- **Property**: Can be converted back to public key for signature verification

### Why This Format?

1. **No Information Loss**: The address IS the public key (not a hash)
2. **Direct Verification**: Can verify signatures without additional data
3. **Familiar Format**: Developers recognize the 0x prefix
4. **Fast Signatures**: Ed25519 provides 70,000 signatures/second

## History Directory

Created at runtime when the agent executes:

### behavior.json
```json
{
  "agent_name": "my-agent",
  "sessions": [
    {
      "started_at": "2025-01-03T10:30:00Z",
      "messages": [...],
      "tool_calls": [...],
      "ended_at": "2025-01-03T10:35:00Z"
    }
  ]
}
```

Tracks all agent interactions for debugging and analysis.

## Security Considerations

### What's Git-Ignored

The following should ALWAYS be in `.gitignore`:

```gitignore
# ConnectOnion sensitive files
.co/keys/          # Private keys - NEVER commit
.co/history/       # May contain sensitive data
.co/cache/         # Temporary files
.env               # API keys
```

### What's Safe to Commit

These files are safe to version control:

- `.co/config.toml` - Contains public address, not private keys
- `.co/docs/` - Reference documentation
- Everything else in the project

## Progressive Disclosure

The `.co` directory follows ConnectOnion's philosophy of progressive disclosure:

1. **Day 1**: User never looks inside `.co`, everything just works
2. **Week 1**: User discovers their agent has an address in `config.toml`
3. **Month 1**: User learns about recovery phrases when setting up new machine
4. **Advanced**: User understands the Ed25519 cryptography when building network features

## Common Operations

### View Your Agent Address
```bash
$ cat .co/config.toml | grep address
address = "0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
```

### Backup Your Agent Identity
```bash
$ cp -r .co/keys ~/secure-backup/
```

### Recover Agent on New Machine
```bash
$ co init
$ co recover --phrase "your twelve word recovery phrase here"
```

### Check Framework Version
```bash
$ cat .co/config.toml | grep framework_version
framework_version = "0.0.1b8"
```

## FAQ

### Q: Why save the recovery phrase in plain text?

**Pragmatism over dogma.** Most developers would lose their keys without this. Advanced users can encrypt the directory. We chose usability for the 90% case.

### Q: Can I regenerate my keys?

No, and you shouldn't want to. Your address is your agent's identity. Changing it would break all existing connections. Use the recovery phrase to restore keys instead.

### Q: Why not use Ethereum keys for compatibility?

Ed25519 is 3x faster for signatures (70k/sec vs 20k/sec). For an agent network exchanging thousands of messages, performance matters more than blockchain compatibility.

### Q: Is the address a real Ethereum address?

No. It looks like one (0x prefix, hex format) for familiarity, but it's an Ed25519 public key, not an Ethereum address. You cannot receive ETH at this address.

## Summary

The `.co` directory encapsulates everything unique about your ConnectOnion project:
- **Identity**: Your agent's cryptographic address
- **Configuration**: Project and agent settings
- **Documentation**: Offline reference materials
- **History**: Runtime behavior tracking

Most users never need to understand these details. The system generates everything silently and it just works. But when you need to know, everything is transparent and well-documented.
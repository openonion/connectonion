# The .co Directory Structure

ConnectOnion uses two `.co/` directories: a global one (`~/.co/`) for shared settings and a project one for local config.

## Global Directory (`~/.co/`)

Created automatically on first `co` command. Stores your identity and shared API keys.

```
~/.co/
├── config.toml          # Global configuration (address, default model)
├── keys.env             # Shared API keys (.env format)
├── keys/                # Cryptographic identity
│   ├── agent.key        # Ed25519 private key (NEVER SHARE)
│   ├── recovery.txt     # 12-word recovery phrase
│   └── DO_NOT_SHARE     # Warning file
├── logs/                # Agent activity logs ({agent_name}.log)
└── sessions/            # YAML session logs for eval/replay
```

## Project Directory (`.co/`)

Created by `co create` or `co init`. Contains project-specific runtime data.

```
.co/
├── keys/                # Project keys (if independent identity)
│   ├── agent.key        # Private signing key (Ed25519)
│   ├── recovery.txt     # 12-word recovery phrase
│   └── DO_NOT_SHARE     # Warning file
├── logs/                # Agent activity logs ({agent_name}.log)
└── sessions/            # YAML session logs for eval/replay
```

## config.toml Reference

The `config.toml` file exists only in the global `~/.co/` directory:

```toml
[connectonion]
framework_version = "0.0.7"
created = "2025-01-15T10:30:00.000000"

[cli]
version = "1.0.0"

[agent]
address = "0x7a9f3b2c8d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a"
short_address = "0x7a9f...7f8a"
email = "0x7a9f3b2c@mail.openonion.ai"
created_at = "2025-01-15T10:30:00.000000"
algorithm = "ed25519"
default_model = "co/gemini-2.5-pro"
max_iterations = 10

[auth]
token = "eyJhbGciOiJI..."  # JWT for network auth
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

## Logs and Sessions

Created at runtime when agents execute.

### `logs/` - Plain Text Activity Logs

Each agent writes to `{agent_name}.log`:

```
2025-01-15 10:30:00 [assistant] Task: What is 2+2?
2025-01-15 10:30:01 [assistant] Tool: calculate("2+2") -> 4
2025-01-15 10:30:02 [assistant] Result: The answer is 4
```

### `sessions/` - YAML Session Logs

Detailed per-session logs for eval and replay:

```yaml
# sessions/assistant_2025-01-15_103000.yaml
agent: assistant
model: co/gemini-2.5-pro
started_at: "2025-01-15T10:30:00Z"
turns:
  - input: "What is 2+2?"
    tools_called: ["calculate"]
    result: "The answer is 4"
    duration_ms: 1234
```

## Security Considerations

### What's Git-Ignored

The following should ALWAYS be in `.gitignore`:

```gitignore
# ConnectOnion sensitive files
.co/keys/          # Private keys - NEVER commit
.co/logs/          # May contain sensitive data
.co/evals/      # Session data
.env               # API keys
```

### What's Safe to Commit

Project `.co/` directories typically contain only runtime data (keys, logs, sessions) which should all be git-ignored. The project code itself is safe to commit.

## Progressive Disclosure

The `.co` directory follows ConnectOnion's philosophy of progressive disclosure:

1. **Day 1**: User never looks inside `.co`, everything just works
2. **Week 1**: User discovers their agent has an address in `config.toml`
3. **Month 1**: User learns about recovery phrases when setting up new machine
4. **Advanced**: User understands the Ed25519 cryptography when building network features

## Common Operations

### View Your Agent Address
```bash
cat ~/.co/config.toml | grep address
```

### Backup Your Identity
```bash
cp -r ~/.co/keys ~/secure-backup/
# Or just save the recovery phrase
cat ~/.co/keys/recovery.txt
```

### Add API Key
```bash
echo "NEW_API_KEY=xxx" >> ~/.co/keys.env
```

### Check Framework Version
```bash
cat ~/.co/config.toml | grep framework_version
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
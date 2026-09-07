# oo

Use ConnectOnion's live Agent protocol and its signed public skill distribution
without confusing the two.

## Install

```bash
co copy oo
# → .co/skills/oo/SKILL.md
```

## Usage

```text
/oo 0x<64 hex characters> review this API design
/oo set up my publishable identity
/oo publish my writing skills
/oo follow 0x<64 hex characters>
/oo list my subscriptions
```

## What it covers

The skill routes five related jobs:

- connect to a remote Agent over OIP;
- create the global `~/.co/` identity and skill library with `co setup`;
- review and publish selected skill bodies with `co announce`;
- follow and refresh a publisher with `co sub`;
- list or remove local subscriptions.

It deliberately keeps three layers separate:

| Layer | Purpose |
|---|---|
| OIP | Live authenticated CONNECT, INPUT, EXEC, events, OUTPUT and session control |
| ANNOUNCE/profile-v2 | Signed public identity, metadata, bodies and monotonic revision |
| `co sub` | Address-pinned, verified pull/sync and local coding-agent fan-out |

There is no publisher accept/reject queue and no automatic update push. A
subscription is a locally stored publisher address plus explicit `co sub` syncs.

## Shareability boundary

ConnectOnion 1.8 publishes the `SKILL.md` body, not a complete skill directory.
The workflow therefore keeps a skill private if it needs sibling scripts,
references, assets, private files, secrets, or undeclared applications. Every
skill's name and description are public profile metadata; `publish: true`
controls whether the body is public as well.

On sync, the CLI verifies the publisher's profile-v2 signature and monotonic
revision before exposing content, and strips a remote `tools:` grant before
fan-out. Authentication proves provenance, not quality or safety.

## Core commands

```bash
co setup --name <alias> --bio "<one-line bio>"
co announce --dry-run
co announce

co sub sync <0xaddress>
co sub
co sub list
co sub remove <address-or-local-alias>
```

First-time follows require the full address obtained through a trusted channel.
An alias becomes usable only after a valid profile has pinned it locally.

## See also

- [Skill library and manifests](../cli/skills.md)
- [Publishing profile format](../network/protocol/announce-message.md)
- [`co sub`](../cli/sub.md)
- [OIP WebSocket protocol](../network/websocket-protocol.md)
- [Built-in Skills](README.md)

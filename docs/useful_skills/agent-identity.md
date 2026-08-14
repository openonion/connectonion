# agent-identity

Establish which address an agent really has, which account pays for it, and why a
second source disagrees.

## Install

```bash
co copy agent-identity
# → .co/skills/agent-identity/SKILL.md
```

## Usage

```
/agent-identity
```

Reach for it when:

- you are about to send someone an agent address or a `chat.openonion.ai/…` link
- `/info` and a config file disagree about who an agent is
- an agent's model calls are billing an account you did not expect
- two machines answer as the same agent

## The problem it solves

An agent has one identity and several things that look like it:

```
.co/keys/agent.key   the identity     signs, is addressed, is trusted
OPENONION_API_KEY    the payer        whose credits the tokens come out of
.env AGENT_ADDRESS   a written note   describes the first. Never consulted.
```

Nothing keeps them in agreement, and nothing complains when they drift. An agent
can be cryptographically itself while billing someone else's account and sending
mail as a third party — with every status command reporting success.

## What the skill does

1. **Address from the agent** — `curl /info`, never from `.env`, `servers.yaml`, or
   the hostname. `AGENT_ADDRESS` does not set the address; `address.load()` reads
   the keypair and takes only `AGENT_EMAIL` / `IS_EMAIL_ACTIVE` from the
   environment.
2. **Payer from the token** — decode the JWT in `OPENONION_API_KEY` and check
   `/api/v1/auth/me`. Notes that `/api/v1/auth` silently *creates* an account for
   any key that authenticates, so "it authenticated" proves nothing about whose
   account it is.
3. **Explain a mismatch** — derive what the agent's name *would* give
   (SLIP-0013 `agent://<name>`) and read the three possible outcomes. An agent that
   minted its own identity earlier keeps it, because a deploy never overwrites one —
   that mismatch is correct and must not be "fixed".
4. **Two hosts, one address** — same name plus same phrase is the same key by
   design, not a leak. The real hazard is that each host keeps its own business
   state, so both do the same work and both report success. Establish which host is
   real with evidence; do not stop either one unilaterally.
5. **Repoint a wrong payer** — fix the project `.env` as well as the server file,
   since `_sync_env` rewrites the server copy from the project copy on every deploy.
   Take the email from the auth response rather than computing it locally.

It also states what cannot be repaired afterwards: `usage_logs` records nothing
identifying the machine or agent, so two processes sharing one API key produce
indistinguishable rows and the bill cannot be split later.

## See also

- [agent-identity.md](../agent-identity.md) — the mechanism in full
- [key-derivation.md](../key-derivation.md) — BIP-39 → SLIP-0010 → SLIP-0013
- [network/deploy.md](../network/deploy.md) — what a deploy syncs, keeps, excludes

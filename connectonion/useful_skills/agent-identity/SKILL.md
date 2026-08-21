---
name: agent-identity
description: Establish which address an agent really has, which account pays for it, and why a second source disagrees — before publishing an address, after a confusing deploy, or when two hosts answer as one agent. Use when about to send someone an agent address or chat link, when `/info` and a config file disagree, when an agent bills the wrong account, or when two machines report the same address.
---

# Agent identity

An agent has one identity and several things that look like it. Nearly every
"which address is this" question is really "which of them am I reading".

```
.co/keys/agent.key   the identity     signs, is addressed, is trusted
OPENONION_API_KEY    the payer        whose credits the tokens come out of
.env AGENT_ADDRESS   a written note   describes the first. Never consulted.
```

Nothing keeps them in agreement, and drift is silent. Read each from its own
source; never infer one from another.

## Step 1 — Get the address from the agent

**Before sending an address or a `chat.openonion.ai/…` link to anyone**, ask the
agent, not a file:

```bash
curl -s localhost:8000/info \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])'
```

Remote:

```bash
co server ssh <server> -- "curl -s localhost:\$(cat /srv/<agent>/.co/port)/info" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])'
```

Never copy the address from any of these — all are records, not facts:

| Source | Why it drifts |
|---|---|
| `AGENT_ADDRESS` in any `.env` | **It does not set the address.** `address.load()` reads the keypair; the environment only supplies `AGENT_EMAIL` and `IS_EMAIL_ACTIVE` |
| `~/.co/servers.yaml` | written when the server was registered |
| the hostname (`nw-map-10e68f6d`) | a DNS label fixed the day the VM was created |

If you already published an address taken from a config file, verify it against
`/info` before assuming it worked — and if it is wrong, say the address was wrong
when sent rather than that someone broke it.

## Step 2 — Get the payer from the token

Billing follows the JWT, not the keypair. Decode it; do not read `AGENT_ADDRESS`
sitting next to it.

```bash
grep '^OPENONION_API_KEY=' .env | cut -d= -f2- | cut -d. -f2 | python3 -c \
  'import sys,base64,json; p=sys.stdin.read().strip(); p+="="*(-len(p)%4); \
   print(json.loads(base64.urlsafe_b64decode(p))["public_key"])'
```

Then confirm the account is the one you meant, and has money:

```bash
curl -s -H "Authorization: Bearer $KEY" https://oo.openonion.ai/api/v1/auth/me
```

Balance is `credits_usd − total_cost_usd`; there is no balance endpoint.

Two traps:

- **`/api/v1/auth` creates an account for any key that authenticates.** A wrong key
  does not error — it becomes a fresh, empty, working account. "It authenticated"
  proves nothing about *whose* account it is.
- **`co status` reports the local `.co/` identity's balance, not the payer's.** In a
  project whose `.env` names a different account, it shows the wrong number
  confidently.

If the payer is a person's account rather than the agent's, see Step 5.

## Step 3 — When `/info` disagrees with what the name derives

A deployed identity is derived from the operator's recovery phrase and the agent's
**name** (SLIP-0013 path `agent://<name>`). Compute what the name *would* give:

```bash
python3 -c '
from pathlib import Path
from mnemonic import Mnemonic
from nacl.signing import SigningKey
from connectonion import address
from connectonion.derive import derive_path, identity_uri, slip13_path
d = address.load(Path.home()/".co")
seed = Mnemonic("english").to_seed(d["seed_phrase"])
sk = SigningKey(derive_path(seed, slip13_path(identity_uri("AGENT-NAME"))))
print("0x"+bytes(sk.verify_key).hex())'
```

| Result | Meaning | Action |
|---|---|---|
| matches `/info` | deploy derived it | nothing |
| differs, agent works | it minted its own key earlier (`co init`, or `--own-identity`) and the deploy preserved it — a deploy never overwrites an identity | **leave it.** Both numbers are correct |
| differs from the address you gave someone | you copied from a config file | re-read from `/info`, correct the recipient |

Do not "repair" the second row by deleting `agent.key`. That is the agent's
identity; deleting it makes a different agent.

## Step 4 — When two hosts answer as the same agent

Same name + same phrase = same derived key. **Two machines reporting one address is
derivation working, not a stolen key.** Check for a duplicate deploy before treating
it as an incident:

```bash
# same address from two hosts?
for h in host-a host-b; do
  co server ssh $h -- "curl -s localhost:8000/info" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["name"], d["address"][:18])'
done
```

It is still an operational problem, for a different reason: each host keeps its
**own** business state (a `sent.json`, a cursor, a dedupe ledger) and neither knows
about the other. Both will do the same work on the same subject and **both will
report success** — so downstream someone receives two of everything.

Confirm both are actually live before deciding anything:

```bash
co server ssh <host> -- "journalctl -u <agent> --since '20 min ago' --no-pager | tail -5"
```

**Do not stop either host on your own** — stopping the wrong one takes the live
agent offline. Establish which host is the real one, with evidence (which is
registered in `co server ls`, which has the fuller state file, which was written to
most recently), and let the owner decide.

## Step 5 — When an agent bills someone else's account

The default path causes this, so expect it rather than treat it as rare:

```
co create      copies the global ~/.co/keys.env — AGENT_ADDRESS, AGENT_EMAIL and
               the API key — into the new project's .env
co deploy --to _sync_env writes the project .env wholesale to
               /etc/connectonion/<agent>.env, rewriting only AGENT_CONFIG_PATH
```

The agent is then cryptographically itself and financially the operator. Nothing
errors.

To correct it, set all of these to the agent's own identity **in the project `.env`
as well as on the server** — `_sync_env` rewrites the server file from the project
file on every deploy, so a server-only fix is undone by the next deploy:

- `OPENONION_API_KEY` — authenticate with the agent's own `agent.key` against
  `POST /api/v1/auth` (`{public_key, signature, message}`, message
  `ConnectOnion-Auth-{public_key}-{timestamp}`) and use the returned token
- `AGENT_EMAIL` — use the `email.address` the auth response returns. **Do not
  hand-compute it**; the backend is authoritative and the local fallback format has
  differed from it
- `AGENT_ADDRESS` — cosmetic, but make it agree so the next reader is not misled

Then restart and verify at the point it protects — the agent answering, with the
right address, on its own balance:

```bash
co server ssh <host> -- "systemctl restart <agent>"
sleep 15   # binding takes ~10s; an empty curl right after restart is not a crash
co server ssh <host> -- "curl -s localhost:8000/health; curl -s localhost:8000/info"
co server ssh <host> -- "journalctl -u <agent> -n 30 --no-pager | grep -i balance"
```

`systemctl is-active` says `active` for a process that answers nothing. The health
endpoint and the startup balance line are the checks that mean something.

## What cannot be fixed afterwards

`usage_logs` records `(public_key, timestamp, model, tokens, cost_usd)` and nothing
identifying the machine or agent — `prompt` and `response` columns exist but are not
written. **Two processes sharing one API key produce indistinguishable rows.** The
bill cannot be split later; attribution has to be right at call time.

Server rental is separable — every charge also lands in `payments` as
`server:<machine_type>` — but token spend between two agents on one key is not.

## See also

- `docs/agent-identity.md` — the mechanism in full
- `docs/key-derivation.md` — BIP-39 → SLIP-0010 → SLIP-0013, per-server SSH keys
- `docs/network/deploy.md` — what a deploy syncs, keeps and excludes

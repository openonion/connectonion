# Agent identity — where it comes from, and what can disagree with it

An agent has one identity and two things that look like it. Most confusion about
"which address is this agent" is really about which of the three you are reading.

```
.co/keys/agent.key   ──▶  the identity        signs, is addressed, is trusted
OPENONION_API_KEY    ──▶  the payer           whose credits the tokens come out of
.env AGENT_ADDRESS   ──▶  a written note      describes the first one. Not consulted.
```

Nothing keeps the three in agreement. They are set at different moments by
different commands, and when they drift apart nothing fails loudly — which is why
this page exists.

---

## The identity: derived from a phrase and a name

`co deploy --to` does not let the server invent an identity. It derives one from
the operator's recovery phrase and the agent's **name**
(`server_commands.derived_agent_identity`, called at `deploy_to_server.py:1015`):

```
recovery phrase ──BIP-39──▶ seed ──SLIP-0010──▶ tree
                                                 │
                    agent://<name> ──SLIP-0013──▶ m/13'/A'/B'/C'/D' ──▶ agent.key
```

The path is a hash of the identity URI, so **the name is the path**. Two
consequences follow, and both are the point rather than side effects:

- **An address can be printed before the agent exists**, and recomputed after its
  disk is gone. Letting a server mint a key on first boot gives an address nobody
  can predict and nobody can recover — the failure mode moves from "changes every
  deploy" up to "changes every machine", which is rarer and therefore worse.
- **The same name always gives the same identity.** Deploy `naturewill-mapping` to
  two machines and both are the same agent, holding the same private key. That is
  not a leak; it is derivation working. See [Two machines, one identity](#two-machines-one-identity).

Names are trimmed and lowercased before hashing, so `LinkedIn` and `linkedin` are
one identity. A mistyped name is a *different* key rather than an error.

The full derivation — why hardened-only, why no watch-only, how SSH keys come off
the same tree — is in [key-derivation.md](key-derivation.md).

### When the author must not hold the key

`co deploy --to --own-identity` skips derivation and mints the key on the machine.
Use it for an agent handed to a customer: otherwise the author can re-derive the
customer's private key from their own phrase, whatever they intend. The trade is
stated plainly at `deploy_to_server.py:1011` — only that machine can ever be that
agent, so losing the disk loses the identity.

### A deploy never overwrites an identity

The remote half is guarded (`deploy_to_server.py:352`):

```bash
if [ ! -f "$keys_dir/agent.key" ]; then
  # write the derived key
fi
```

> overwriting an identity is not a thing a deploy may do

So an agent that already has a key keeps it, including one that was minted locally
by `co init` long before it was ever deployed. This is why an agent's live address
can legitimately differ from what its name derives to:

```
derived  agent://naturewill  →  0x8f7c1216…      ← what the name would give
running  naturewill.service  →  0xfae4e0d62c…    ← what it actually is
```

Both numbers are correct. The agent predates the derivation scheme, the deploy
preserved it, and nothing is broken. Do not "fix" this by deleting the key.

`.co/keys/` is also excluded from the deploy rsync, so the identity is never sent
in the tarball and never deleted by `--delete`.

---

## `AGENT_ADDRESS` does not set the address

This is the single most expensive misreading in this system.

`address.load()` computes the address from the signing key on disk. From the
environment it takes **only** `AGENT_EMAIL` and `IS_EMAIL_ACTIVE`
(`address.py:305`):

```python
email = os.getenv("AGENT_EMAIL", f"{address[:10]}@mail.openonion.ai")
email_active = os.getenv("IS_EMAIL_ACTIVE", "").lower() == "true"
```

There is no reader of `AGENT_ADDRESS` anywhere that determines an address.
`project_cmd_lib.py:67` says so outright: *"The address is read from the keypair,
not from keys.env's AGENT_ADDRESS."*

An `AGENT_ADDRESS` line is a **written note about** the key. It can be stale, it
can name a different account entirely, and the agent will keep answering as its
real self the whole time. Observed on one machine at one moment:

```
/etc/connectonion/naturewill-mapping.env :  AGENT_ADDRESS=0x10e68f6dff…
curl localhost:8000/info                 :  0xcf1619cb4c…
```

Both true simultaneously. The env line was a leftover; the agent had never once
used it.

**So: read an agent's address from the agent.** Config files, `servers.yaml`, and
the server hostname (`nw-map-10e68f6d`, fixed the day the VM was created) are all
records, not facts.

```bash
curl -s localhost:8000/info | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])'
```

`AGENT_EMAIL` is different — it **is** consulted, and it does override the derived
mailbox. A wrong value there really does change who the agent sends mail as.

---

## Billing is a separate axis

Who pays is decided by the JWT in `OPENONION_API_KEY`, not by `agent.key`. Every
model call bills the `public_key` inside that token (`llm/billing.py:236`):

```
usage_logs(public_key, model, tokens, cost_usd)  +  users.total_cost_usd += cost
```

`usage_logs` has no column naming the machine or the agent. Two processes sharing
one API key produce rows that are **indistinguishable after the fact** — there is
no way to split the bill later. Attribution has to be right at call time or it is
gone.

Two more properties worth knowing before you debug a balance:

- **`/api/v1/auth` creates an account for any key that authenticates.** A wrong or
  rotated key does not error; it silently becomes a fresh, empty, working account.
  `_token_for_this_account` (`project_cmd_lib.py:1083`) exists because one $180
  server was bought against an account nobody meant to use.
- **Balance = `credits_usd − total_cost_usd`.** There is no balance endpoint;
  `/api/v1/balance` is 404.

Server rental is charged on the same `total_cost_usd`, but every charge also lands
in `payments` as `server:<machine_type>` (`servers/service.py:234`), so server fees
*can* be separated from token spend after the fact. Token spend between two agents
sharing a key cannot.

---

## How the three drift apart

The default path does it for you:

```
co create
  └─ create.py:348 — "Always copy from global keys.env
                      (includes AGENT_ADDRESS, AGENT_EMAIL, and API keys)"
        the operator's own identity lands in the new project's .env
                              ↓
co deploy --to
  └─ _sync_env (deploy_to_server.py:659)
        writes the project .env wholesale to /etc/connectonion/<agent>.env,
        rewriting only AGENT_CONFIG_PATH
                              ↓
the agent starts
  ├─ address  ← .co/keys/agent.key         its own, correct
  ├─ email    ← AGENT_EMAIL                the operator's
  └─ billing  ← OPENONION_API_KEY          the operator's
```

The agent is cryptographically itself and financially you. Nothing reports an
error, `co status` looks fine, and the spend accumulates on a personal account.

Because `_sync_env` rewrites the file from the project `.env` on **every** deploy,
correcting the server copy alone is undone by the next deploy. Fix the project
`.env` too, or the fix is one you have to remember to reapply.

---

## Two machines, one identity

Deploying the same name twice gives two machines the same key. Cryptographically
this is fine — it is one agent with two bodies. Operationally it usually is not:

- Each body keeps its **own** business state (a `sent.json`, a cursor, a dedupe
  ledger). Neither knows about the other's.
- So both will do the same work on the same subject, and **both will report
  success**. Downstream, someone gets two of whatever the agent produces.

When two hosts answer with one address, the question is not "was the key stolen"
but "did we deploy this name twice". Decide which host is the real one before
touching either — stopping the wrong one takes the live agent offline.

---

## Checking an agent, in order

```bash
# who it actually is — from the agent, not from a file
curl -s localhost:8000/info | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])'

# who pays — decode the JWT, do not trust AGENT_ADDRESS beside it
grep '^OPENONION_API_KEY=' .env | cut -d= -f2- | cut -d. -f2 | python3 -c \
  'import sys,base64,json; p=sys.stdin.read().strip(); p+="="*(-len(p)%4); \
   print(json.loads(base64.urlsafe_b64decode(p))["public_key"])'

# what the name would derive to — to tell "minted its own" from "wrong key"
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

Three outcomes when `/info` and the derived address disagree:

| | meaning |
|---|---|
| `/info` == derived | normal — deploy derived it |
| `/info` != derived, agent works | it minted its own identity earlier and the deploy preserved it. Correct, leave it |
| `/info` != the address you gave someone | you copied the address from a config file. Re-read from `/info` |

---

## See also

- [key-derivation.md](key-derivation.md) — the tree itself: BIP-39, SLIP-0010,
  SLIP-0013 paths, per-server SSH keys, and the retired HKDF scheme
- [network/deploy.md](network/deploy.md) — what a deploy syncs, keeps and excludes
- `.claude/skills/co-部署与排障` (platform repo) — the operational checklist

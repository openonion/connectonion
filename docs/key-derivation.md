# Key derivation — one phrase, a tree of keys

Your twelve words are a BIP-39 recovery phrase, and every key ConnectOnion uses is
derived from it through **SLIP-0010**: the standard Ledger, Trezor, Solana and Brave
all use for Ed25519.

```
twelve words ──BIP-39──▶ seed ──SLIP-0010──▶ a tree of keys
```

That matters for one practical reason: **the phrase means something outside our
software.** If ConnectOnion disappeared tomorrow, any SLIP-0010 implementation
recovers your keys from those words.

## The account key

```
m/13'/…   derived from the identity URI  https://oo.openonion.ai
```

Paths come from **SLIP-0013**, the authentication-identity scheme — the same one
`trezor-agent` uses for SSH. The path is a hash of the identity's URI:

```
path = m/13' / A' / B' / C' / D'      A..D = SHA256(index_le || uri)[:16]
```

The name *is* the path, so a name always returns the same key, and a key can be
derived before anything using it exists.

The cost is that the path is opaque — `m/13'/1444947841'/…` doesn't say which
identity it is — and a mistyped name is a different key rather than an error. Names
are therefore trimmed and lowercased before hashing: `LinkedIn` and `linkedin` are
one identity.

## Hardened-only, deliberately

SLIP-0010 offers **no public derivation** on Ed25519, so there is no xpub and no
watch-only. That is the property we want, not a limitation we tolerate.

Non-hardened derivation has an inverse: `child = parent + t`, where `t` is computable
from public data, so `parent = child − t`. One leaked child private key plus the
public tree recovers the parent — and the parent generates everything else.

Agent identities and SSH keys **live on servers**, which get breached, snapshotted,
and handed to other people. Under SLIP-0010 that exposes one key. The watch-only we
give up answers a question nobody here asks: balances live in a database row keyed by
public key and need a signature to read.

Passing a non-hardened index raises rather than quietly deriving something else.

## What changed, and what it means for you

Identity used to be derived like this:

```python
seed = mnemo.to_seed(seed_phrase)
signing_key = SigningKey(seed[:32])   # a bare slice — no BIP, no SLIP, no path
```

A slice of the seed corresponds to no standard, so those twelve words could only ever
be restored by ConnectOnion itself. No hardware wallet could hold an agent identity.

**Every address derived from a phrase has therefore moved once.** This happened while
the project was small enough for that to be affordable; the alternative was carrying
the bespoke slice forever.

### If you have an agent from before the switch

**It keeps working, and its address does not change.** `.co/keys/agent.key` holds the
key that identity has always used, and that file is what gets loaded.

What changed is the phrase beside it. Those twelve words now derive a *different* key,
so:

> `co auth recover` with your old phrase gives you a **new, empty agent** — not the
> one you have been using.

`co status` says so when it sees a key that predates the switch:

```
⚠ This identity was created before ConnectOnion adopted SLIP-0010 key derivation.
  It keeps working. But your recovery phrase now derives a different address,
  so 'co auth recover' with those words gives you a new, empty agent — not this one.
  Keep .co/keys/agent.key backed up; the phrase alone no longer restores it.
```

So: **back up `.co/keys/agent.key`**. For a pre-switch identity it is the only copy.

To move onto the current scheme, generate a fresh identity and migrate what points at
the old address — whitelists, the agent's email, anything a counterparty recorded.
There is no in-place upgrade, because the address *is* the identity.

## Reference

`connectonion/derive.py`:

| Function | Purpose |
|---|---|
| `derive_path(seed, path)` | The 32-byte key at a path — hand it to `SigningKey()` |
| `master_key(seed)` | SLIP-0010 master key and chain code |
| `slip13_path(uri, index=0)` | `m/13'/A'/B'/C'/D'` for an identity URI; `index` is the rotation counter |
| `identity_uri(name)` | `agent://<name>`, canonicalised |
| `ssh_uri(user, host)` | `ssh://<user>@<host>`, matching `trezor-agent` |
| `ACCOUNT_URI` | `https://oo.openonion.ai` — the account identity |

## SSH keys

One key per server, from the same tree:

```
ssh://root@<server>  ──SLIP-0013──▶  m/13'/…  ──▶  the key for that server only
```

`co keys --ssh` prints the set — one line per registered server — and `--write`
caches the private halves under `~/.co/ssh/id_ed25519_<server>`. The cache is
exactly that: the phrase is the original, so losing a file costs a
re-derivation, not access.

Two properties this buys, neither of which the old scheme could offer:

- **A snapshot of one machine does not open the others.** Each server's key is
  derived from its own URI.
- **Rotation without re-keying the identity.** Bump the URI's index and the old
  key stops being derived; the agent's address is untouched.

The paths match what `trezor-agent` derives, so a hardware key can stand in for
the file cache.

### What was retired

Until #427 step 4, SSH access used a second construction — HKDF over the label
`connectonion:ssh:v1` — producing **one key for every server**, installed into
`authorized_keys` at provisioning and offered on every connection. It could not
be switched in one commit: the public line was already on every machine
provisioned before the tree existed, and there is no way back into a server
except a key it already trusts.

So it went in the order the migration required — install the per-server key
alongside the old one, backfill existing machines on every deploy, verify each
server opens with its own key alone, and only then stop deriving the shared one.

## See also

- [co-directory-structure.md](co-directory-structure.md) — where keys live on disk
- [cli/setup.md](cli/setup.md) — `co init`, `co auth`

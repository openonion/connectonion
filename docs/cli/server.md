# co server

A server you own, that a deploy goes *onto* — not a container that is rebuilt and
thrown away each time.

```bash
co server new prod                       # have one created for you
co server add prod --ssh you@1.2.3.4     # or register one you already have
co server ls                             # what you can deploy to
co server check prod                     # preflight
co server ssh prod                        # a shell on it
co deploy --to prod                       # put an agent there
```

---

## Why a server rather than a container

The cloud path (`co deploy`) rebuilds an image and starts a fresh container every
time. That is fine until you want any of this:

- **an identity that survives.** A redeploy used to mint a new agent address, which
  changed the agent's email and voided every trust relationship other agents had
  granted it.
- **history that is continuous.** `.co/logs/` and `.co/evals/` are what a dashboard
  shows about the past.
- **a fix you made by hand at 2am to still be there tomorrow.** With an image as the
  source of truth it is discarded on the next deploy.

On your own server the deploy syncs code and restarts a systemd unit. `.co/` is never
touched, so all three hold.

---

## co server new

Has a server created for you, and registers it locally so you never type an IP.

```
$ co server new prod

  name          prod
  region        australia-southeast1
  machine       e2-small — 2 vCPU (shared), 2 GB — fine for one agent
  cost          $30 / month — $360.00 for 12 months, charged now
  your balance  $500.00 → $140.00 after
  expires       2027-07-31 — the server stops on that date unless renewed

? Create it? (y/N)
```

**This is the only `co` command that spends a large discrete amount.** Everything else
is free or costs fractions of a cent, so the prompt says the price, what your balance
becomes, and when the term ends. `--yes` skips it; nothing else does.

The machine is created in **Sydney**, boots Ubuntu 24.04, and carries the SSH key
derived from your recovery phrase — nothing else is installed. The first
`co deploy --to` sets up python, the venv, systemd and Caddy.

| Flag | |
|---|---|
| `--machine e2-medium` | 4 GB, for browser agents |
| `--yes` | skip the price confirmation |

---

## co server add

Registers a machine you already have. Takes an **ssh target, not a credential** — we
shell out to `ssh`, so your agent and `~/.ssh/config` do the work.

```bash
co server add pi --ssh pi@192.168.1.50
```

Everything downstream is the same code as a server we created. The one difference: a
hand-registered machine has no hostname of ours, so the deploy sets up no https for it.

---

## co server ls

What you can deploy to — reconciled against what you are **billed** for.

```
NAME     TARGET          LAST CHECK            BILLING
prod     co@1.2.3.4      ok                    until 2027-07-31
ghost    co@5.6.7.8      not registered here   until 2027-07-31

1 server(s) you are billed for are not registered on this machine: ghost
  co server add <name> --ssh <target>   to use one from here
  co server destroy <name>              to stop paying for one
```

`~/.co/servers.yaml` is a cache; the backend is the ledger. The row that only the
backend can produce — **billed for, not registered here** — is a server you are paying
for that `co` would otherwise never show you: created on another laptop, or dropped
with `co server forget`.

Offline or unauthenticated, the BILLING column is omitted and your local targets still
list. "We could not ask" and "you own nothing" are different answers and are never
collapsed.

---

## co server check

Preflight, so "it doesn't work on my box" stays answerable. Ubuntu 24.04, python
3.11+, systemd, enough disk — and it names the requirement that failed rather than
reporting a generic failure.

---

## co server ssh

```bash
co server ssh prod                                   # a shell
co server ssh prod 'journalctl -u myagent -f'        # logs
co server ssh prod 'systemctl status myagent'
```

---

## forget vs destroy

Two commands on purpose, because one of them stops the billing and the other does not.

| | what it does | the machine |
|---|---|---|
| `co server forget prod` | drops the local entry | keeps running, keeps billing |
| `co server destroy prod` | tears it down | gone, and the unused term is refunded |

A single "remove" would mean one of two failures depending on which it implemented:
you believe you stopped paying and are billed for a year, or you tidy your config and
delete production.

`destroy` asks you to **type the name back**, not y/N — a reflex "y" is exactly how
the second one happens. The refund is the unused part of the term, credited back:

```
$ co server destroy prod
✓ prod destroyed
$150.41 of $360.00 refunded to your credit — the unused part of the term.
```

---

## What lives on the server

```
/srv/<agent>/            code, rsynced each deploy
/srv/<agent>/.venv       dependencies
/srv/<agent>/.co/        identity/logs preserved; project config and skills synced
/etc/systemd/system/<agent>.service
/etc/caddy/Caddyfile     the hostname, proxied to the agent
```

Paths listed in the project's root `.gitignore` are also preserved. Use that for
runtime-generated directories inside the project, such as `work/` or `state/`.

`systemctl` gives what the container was for: `Restart=always` for crash recovery,
`enable` for start-on-boot, journald for logs.

---

## See also

- [deploy.md](../network/deploy.md) — the three ways to deploy
- [host.md](../network/host.md) — what `host()` does

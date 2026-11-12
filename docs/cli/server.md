# co server

A server you own, that a deploy goes *onto* — not a container that is rebuilt and
thrown away each time.

```bash
co server new prod                       # have one created for you
co server add prod --ssh you@1.2.3.4     # or register one you already have
co server ls                             # what you can deploy to, and what each costs
co server invoice prod                   # its monthly invoices
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
$ co server new prod --machine e2-standard-4 --disk 200

  name          prod
  region        australia-southeast1
  machine       e2-standard-4 — 4 vCPU, 16 GB
  disk          200 GB pd-balanced — 20 GB included, $0.18 / GB / month beyond
  cost          $222.40 / month — charged at the end of each month from credits; nothing is charged now
  your balance  $500.00 — covers one month, which is required

? Create it? (y/N)
```

**Servers are billed monthly, in arrears.** Nothing is charged when the server is
created. Each month is charged from your credits when it ends, and the first charge
date is printed once the server exists. Your balance has to cover one month to
create one, on top of a month of each server you already have, and nothing may be
unpaid; when it is short the command stops (before asking, when it can tell) and
nothing is created.
`--yes` skips the prompt; nothing else does.

The machine is created in **Sydney** by default, boots Ubuntu 24.04, and carries the
SSH key derived from your recovery phrase — nothing else is installed. The first
`co deploy --to` sets up python, the venv, systemd and Caddy.

| Flag | |
|---|---|
| `--machine e2-medium` | another size; the list and the prices come from the backend |
| `--disk 200` | a larger disk, one of the sizes the backend offers (20 GB is included) |
| `--region asia-southeast1` | provision somewhere other than Sydney |
| `--yes` | skip the price confirmation |

An unknown `--machine` lists what is on sale with its monthly price, so
`co server new prod --machine list` is the way to see them. The 16 GB
`e2-standard-4` and 32 GB `e2-highmem-4` are for agents that run browsers or
models.

Each region has its own quota — Sydney's runs out after 4 live servers (a GCE
external-address ceiling, not ours) — so `--region` is also the way out once you hit
it:

```bash
co server new backup --region asia-southeast1
```

**Against a backend that still charges 12 months up front**, the prompt says so —
`$30 / month — $360.00 for 12 months, charged now` — and `--disk` is refused rather
than ignored. The CLI reads which kind of backend it is talking to from
`/servers/pricing` and never quotes one while the other is about to charge you.

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
NAME     TARGET           LAST CHECK            BILLING
prod     co@1.2.3.4       ok                    $222.40/mo · next charge 2026-12-12 · $74.13 so far
lab      co@5.6.7.8       never checked         suspended for non-payment — $30.00 unpaid, disk kept
ghost    co@9.9.9.9       not registered here   $30.00/mo · next charge 2026-12-01 · $10.00 so far

1 server(s) you are billed for are not registered on this machine: ghost
  co server add <name> --ssh <target>   to use one from here
  co server destroy <name>              to stop paying for one

Balance $100.00 does not cover the next month of these servers ($282.40).
A month left unpaid stops the server, then deletes it. Top up before 2026-12-01.
```

For each server: the monthly price, the next charge date, what this month has
accrued so far (what a destroy now would charge), and anything unpaid. Below the
table, whether your balance covers the next month of all of them together. A
server bought on the old 12-month term shows `prepaid until <date>` instead.

Creating another server is refused while any month is unpaid, and the balance it
needs is this server's month on top of a month of every server you already have.

A month your balance cannot pay suspends the server (stopped, disk kept) and, if
it stays unpaid, deletes it. A resumed server comes back on a new IP; `ls` notices
the address no longer matches your local entry and prints the `co server add`
line that updates it.

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
| `co server destroy prod` | tears it down | gone; the used part of this month is charged |

A single "remove" would mean one of two failures depending on which it implemented:
you believe you stopped paying and are still billed, or you tidy your config and
delete production.

`destroy` asks you to **type the name back**, not y/N — a reflex "y" is exactly how
the second one happens. It says what it will charge before you type, and prints the
amount and the invoice afterwards:

```
$ co server destroy prod
This destroys the machine 'prod' and everything on it.
The used part of this month (about $74.13) is charged now, and the monthly billing stops.

✓ prod destroyed
$111.20 charged for the used part of this month — invoice SRV-2026-11-000124.
```

If your balance cannot pay it, the amount is recorded as unpaid and charged at your
next top-up, and the command says so. A server on the old 12-month term refunds the
unused part of its year instead, as an amount: `$150.41 of $360.00 refunded`.

---

## co server invoice

Every monthly charge, and the final part-month of a destroyed server, has an invoice.

```bash
co server invoice prod                             # list them
co server invoice prod --month 2026-12             # print the ones issued that month
co server invoice prod --month 2026-12 --pdf prod-2026-12.pdf
co server invoice prod --pdf latest.pdf            # just the latest one
co server invoice --all --month 2026-12            # every server's, for one month
co server invoice prod --month 2026-12 --json      # the backend's JSON
```

```
INVOICE SRV-2026-12-000123   PAID
Issued    2026-12-12
Bill to   Fictional Widgets Pty Ltd
Server    prod (e2-standard-4, 200 GB disk)
Period    2026-11-12 to 2026-12-12, 30 days

Description                                                 Months   Per month      Amount
e2-standard-4 server                                             1     $190.00     $190.00
200 GB pd-balanced disk: 180 GB beyond the 20 GB included        1      $32.40      $32.40
                                                                     Total USD     $222.40
```

The months are UTC and select by the date the invoice was issued. `--all` without
`--month` means this month. Every amount and line is the backend's; the CLI adds
nothing up. `--pdf` writes one A4 page per invoice with exactly that text. A
backend that still bills 12 months up front issues no server invoices, and the
command says so.

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

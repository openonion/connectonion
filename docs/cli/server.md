# co server

A server you own, that a deploy goes *onto* — not a container that is rebuilt and
thrown away each time.

```bash
co server new prod                       # have one created for you
co server add prod --ssh you@1.2.3.4     # or register one you already have
co server ls                             # what you can deploy to, and what each costs
co server invoice prod                   # its invoices (monthly billing)
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

Has a server created for you, and registers it locally so you never type an IP. It
shows the price and how it is charged, then asks.

How a server is charged is the backend's decision, and the prompt states whichever
one applies. The CLI reads it from `/servers/pricing` and never quotes one way of
charging while the backend is about to use the other:

- **Monthly, in advance** (oo-api with monthly billing): the first month is charged
  when the server is created; each next month is charged from your credits when it
  starts; a destroy refunds the unused part of the month.
- **12 months up front** (the backend before it): the year is charged at create,
  and the prompt says `$30 / month — $360.00 for 12 months, charged now`.

On the monthly backend:

```
$ co server new prod --machine e2-standard-4 --disk 200

  name          prod
  region        australia-southeast1
  machine       e2-standard-4 — 4 vCPU, 16 GB
  disk          200 GB pd-balanced — 20 GB included, $0.18 / GB / month beyond
  cost          $222.40 / month — first month charged now, then at the start of each month from credits; destroy refunds the unused part
  your balance  $500.00 → $277.60 after the first month

? Create it? (y/N)
```

The first month is charged when the server is created, and the date it is paid until
is printed once the server exists. Each next month is charged from your credits as it
starts. Your balance has to cover that first month, and nothing may be owed on the
account; when it is short the command stops (before asking, when it can tell) and
nothing is created or charged. If the machine cannot be created, the month is
refunded in full.
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

Against the 12-months-up-front backend, `--disk` is refused rather than ignored, and
the balance line shows what is left after the charge.

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
prod     co@1.2.3.4       ok                    $222.40/mo · paid until 2026-12-12, renews from credits
lab      co@5.6.7.8       never checked         suspended for non-payment — $30.00 unpaid, disk kept
ghost    co@9.9.9.9       not registered here   $30.00/mo · paid until 2026-12-01, renews from credits

1 server(s) you are billed for are not registered on this machine: ghost
  co server add <name> --ssh <target>   to use one from here
  co server destroy <name>              to stop paying for one

lab owes $30.00 and is stopped; it is deleted on 2026-12-01 unless you top up.

Balance $100.00 does not cover the next month of these servers ($282.40).
A month left unpaid stops the server, then deletes it. Top up before 2026-12-01.
```

For each server: the monthly price, the date it is paid until (when the next month
is charged), and anything owed. Below the
table, whether your balance covers the next month of all of them together. A
server bought on the old 12-month term shows `prepaid until <date>` instead.

Creating another server is refused while any month is unpaid, and the balance it
needs is this server's month on top of a month of every server you already have.

A month your balance cannot pay suspends the server (stopped, disk kept) and, if
it stays unpaid, deletes it. For a server that owes, `ls` prints the date it stops
and the date it is deleted: the backend's `unpaid_since` (the end of the oldest unpaid
month) plus the days in its `pricing.unpaid` timeline. A resumed server comes back on a new IP; `ls` notices
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
| `co server destroy prod` | tears it down | gone; the unused part of this month is refunded (old 12-month term: the unused part of the year) |

A single "remove" would mean one of two failures depending on which it implemented:
you believe you stopped paying and are still billed, or you tidy your config and
delete production.

`destroy` asks you to **type the name back**, not y/N — a reflex "y" is exactly how
the second one happens. It says what it will refund before you type, and prints the
amount and the credit note afterwards:

```
$ co server destroy prod
This destroys the machine 'prod' and everything on it.
The disk, the agent's identity, its logs — none of it is recoverable.
The unused part of this month (about $111.20) is refunded to your credits, and the monthly billing stops.

? Type the server name to confirm (prod): prod

Destroying prod …
✓ prod destroyed
$111.20 refunded to your credits for the unused part of this month — credit note SRV-2026-11-000124.
co server invoice prod SRV-2026-11-000124   to see it
```

A server whose month in progress was never paid (it is in its grace days) has nothing
to refund: the days it ran are owed instead, and the command says the total you still
owe for it, which is charged at your next top-up. A server on the old 12-month term
refunds the unused part of its year instead, as an amount: `$150.41 of $360.00 refunded`.

---

## co server invoice

Every monthly charge, and the final part-month of a destroyed server, has an invoice.

```bash
co server invoice prod                                  # list them
co server invoice prod 1                                # print one, by its row in the list
co server invoice prod SRV-2026-12-000123               # or by its number
co server invoice prod SRV-2026-12-000123 --pdf SRV-2026-12-000123.pdf
co server invoice prod --month 2026-12                  # print the ones issued that month
co server invoice --all --month 2026-12                 # every server's, for one month
co server invoice prod --month 2026-12 --json           # the backend's JSON
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
nothing up. `--pdf` writes that text to A4 pages, each invoice starting on its own
page, long lines wrapped. `--pdf` with no number or month writes the one invoice a
server has, and refuses to guess when there are more. `--pdf` and `--json` do not
combine, and `--all` takes no server name.

The PDF uses the built-in Courier font, which draws Western European text only
(the cp1252 character set). A bill-to name or address in another script, such as
Chinese, is left out of the PDF with a line saying so, and the account address is
shown in its place; `co server invoice <name> <number>` prints the full text. A
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

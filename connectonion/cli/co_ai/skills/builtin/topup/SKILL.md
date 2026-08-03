---
name: topup
description: Check the OpenOnion balance and open the recharge page with the user's own key pre-filled. Reports the balance in plain money, says how long it lasts at $0.10/hour of browser time, and hands over a purchase link that needs no login — the key is already in it. If connectonion is not installed yet, install it first (install-connectonion). Use when the user says "top up", "add credit", "recharge", "check my balance", "how much do I have left", "充值", or a paid action failed because the balance is empty.
tools:
  - Bash(python *)
  - Bash(python3 *)
  - Bash(py *)
  - Bash(co *)
  - Bash(curl *)
  - shell
  - read_file
---

# Top-up Skill

Answer one question — *"how much do I have, and how do I add more"* — and hand back a
recharge link the person can click without logging in, because their own key is already
in it.

**Assume the person may not be technical.** They came to run a browser or an agent, not to
learn about public keys. Do the lookup *for* them; say the result in plain money.

## Step 0: Is connectonion here at all?

```bash
co --version
```

- **It runs** → go to Step 1.
- **It does not** → this machine has no `co` yet. Run the **install-connectonion** skill
  first (it installs `co`, and its `co init` step creates the key this skill needs), then
  come back here. Do not ask the user to install anything by hand — the install skill does it.

## Step 1: The key that identifies this account

The recharge page fills in from the account's public key, and it lives in `~/.co`. Read it —
never type it, never show its full value in logs:

```bash
python3 -c "from connectonion import address; from pathlib import Path; d=address.load(Path.home()/'.co'); print(d['address'] if d else '')"
```

- **Prints a `0x…` address** → that is `KEY`. Keep it.
- **Prints nothing** → the account was never created. Run **install-connectonion** (its
  `co init` writes the key), then retry this step. On Windows use `py -3` or `python`.

## Step 2: The balance

Ask the API with the stored token — `co` already has it, so this needs nothing from the
user. `/auth/me` returns `balance_usd` directly (credits minus what has been spent):

```bash
TOKEN=$(python3 -c "from connectonion.cli.commands.project_cmd_lib import load_api_key; print(load_api_key() or '')")
curl -s https://oo.openonion.ai/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

Read `balance_usd` from the JSON. (Verified against production: `/auth/me` gives
`balance_usd`; `/api/v1/tokens/balance` gives the raw `credits_usd` and `total_spent_usd`
whose difference is the same number — use `/auth/me`, it does the subtraction.)

There is **no `co status --balance`** — `co status` only lists credential sources, not the
money. The API call above is the read.

> **Recovery — the token names a different account.** If the balance looks wrong or the
> call is refused, the stored token may predate a key migration. Run `co auth` once to
> refresh it, then retry. (This is the openonion/oo-api#67 case — the CLI re-authenticates
> itself, you just have to let it.)

## Step 3: Say it in money, and in hours

Browser time is **$0.10/hour**. Turn the balance into something a person acts on:

```
Balance: $BALANCE
That is about $HOURS hours of browser time at $0.10/hour.
```

`HOURS = BALANCE / 0.10`. Round down; a partial hour is not a promise. If the balance is
**zero or low**, say it plainly and without alarm — the recharge link is the answer, not a
warning.

## Step 4: The recharge link, key already in it

Hand over exactly this, with `KEY` substituted — no login, no re-typing the key:

```
https://o.openonion.ai/purchase?key=KEY
```

Tell the person: *open it, pick a top-up, pay — the credit lands on this same account and
both `co` and the browser draw from it.* One balance, one link.

**Set expectations about the page, because it will not match your words otherwise.** The
purchase page shows fixed top-up packages (currently around \$0.99, \$19.90, \$109.90), and
it is worded for API credit — it does **not** say "browser hours." That is not a wrong page:
it is the same `credits_usd` browser time bills against. Tell the person plainly: *the page
sells credit in fixed amounts; any of them adds to the one balance, and browser time draws
from it at \$0.10/hour.* Do not promise an arbitrary-amount field the page does not have.

## The plain-language summary

Close with the money facts and nothing else — no key value, no token, no table:

```
  💰  Balance:        $12.40   (~124 hours of browser time at $0.10/h)
  🔗  Add credit:     https://o.openonion.ai/purchase?key=0x10e6…5508
```

Adjust: **balance is healthy** → one calm line, still offer the link for later. **Balance is
empty** → lead with the link, "add any amount to start." **No `co` and the user declined to
install** → say the top-up needs connectonion and stop; do not fake a balance.

## Notes

- **One balance for everything.** LLM calls (`co/*` models), agent email, and browser time
  all draw from the same `credits_usd`. Topping up here funds all of them — do not imply a
  separate "browser wallet."
- **The link needs no account on our side.** `?key=` is the whole identity the page needs;
  Stripe returns the credit to that key via webhook. There is nothing to log in to.
- **Never print or store the key's full value** beyond the URL the user is meant to click.
  The summary shows a truncated form (`0x10e6…5508`); the link is the one place it appears in full.
- **$0.10/hour is the browser rate**, single session. Multi-session is an enterprise
  conversation, not something this skill quotes.
- The purchase page is live at `https://o.openonion.ai/purchase` (verified 200). The bare
  `https://openonion.ai/purchase` is **not** the page — always use the `o.` host.

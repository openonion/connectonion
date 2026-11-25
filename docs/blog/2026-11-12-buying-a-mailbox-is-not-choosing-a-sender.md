---
title: "Buying a mailbox is not choosing a sender"
date: 2026-11-12
tags: [email, cli, defaults]
---

# Buying a mailbox is not choosing a sender

An account sent everything from its `0x…@mail.openonion.ai` address, the one derived from its key. It bought a second mailbox with `co email setup <alias> --buy`. From then on every send that did not pass `--from` went out as the new mailbox, including mail from other agents and scripts on the same key. Nobody had asked for that, and nothing said it had happened. Then `co email default 0x…` refused the old address: "not one of this account's own addresses".

## Why it happened

The server flagged a new address as the default when the account had no stored address yet. The derived `0x…` address is never stored, because it belongs to the key by construction. So on any account that had no stored address yet — every account still sending from its `0x…` address — the first purchase took the default. Choosing a default only looked at stored rows, so the derived address could not be chosen back.

## The rule now

A stored address is the default only if it is flagged. If nothing is flagged, the derived `0x…` address is the default. Buying never sets the flag unless you ask:

```sh
co email setup ops --domain steadmail.com --buy            # Default sender is still 0x…@mail.openonion.ai
co email name ops --buy                                    # same rule for a custom name
co email setup ops --domain steadmail.com --buy --default  # Default sender is now ops@steadmail.com
co email default 0x1234567890@mail.openonion.ai            # back to the derived address
```

`co email addresses` now always lists the derived address, so you can see which address is the default.

## The awkward part

Accounts that already hit this keep the default the server gave them. The database cannot tell "the purchase set this" from "the owner chose this": both are the same flag, and choosing a default recorded nothing else. Flipping those accounts back would overwrite some choices owners made on purpose. So we leave them alone, and the buy output now names the default every time. Against an older server that does not report it, the CLI tells you to check `co email addresses`.

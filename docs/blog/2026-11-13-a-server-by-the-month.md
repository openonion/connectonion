---
title: "A server by the month"
date: 2026-11-13
tags: [server, billing, cli, design]
---

# A server by the month

Mira runs a browser agent for a small shop. It opens forty tabs a day, and on the 2 GB machine `co server new` sold her by default, Chromium kept running out of memory. She wanted 16 GB for a month to find out whether that was enough. `co server new` could not sell her that: the largest machine was 4 GB, and every machine was a year charged up front. Trying one cost a year of credit.

So the backend changed what it sells, and the CLI had to change what it says. That second part turned out to be the harder one.

## What changed

Servers are now billed monthly, in arrears. Creating one charges nothing; each month is charged from credits when it ends; destroying one charges the part of the month it ran. There are 16 GB and 32 GB machines, and `--disk` takes the sizes the backend lists. `co server ls` shows each server's next charge, what it has used so far this month and anything unpaid, and whether the balance covers the next month. `co server invoice prod 1` prints an invoice, and `--pdf` saves it.

## The awkward part

This CLI ships before the backend does. Until the monthly backend is live, the one in production still charges a year at create, and an upgraded CLI talks to it. The easy mistake was to print "nothing is charged now" against a backend that was about to take $360.

So no sentence about money is written into the CLI as a fact. The CLI reads `/servers/pricing`, and only when that says `monthly_in_arrears` does it print the monthly terms. Otherwise it prints the old prompt, word for word, and refuses `--disk` rather than ignoring it. The help text and the docs say "shows the price and how it is charged, then asks", which is true on both backends.

The same rule applied to the numbers. Every amount on screen comes from the backend: the month's price after create, what a destroy would cost now, an invoice's total. The one figure the CLI works out itself is the quote before create, by the formula the backend publishes. After create, the backend's own figure replaces it.

Review caught two places where the words were still wrong. A server that already owes is not charged when it is destroyed; the used part is added to its debt. The first draft said "charged now" anyway. And an invoice email told people to run `--pdf` with no invoice named, so the CLI picked the newest invoice. An old email would have saved a newer invoice under the old number. Now a number or a row picks the invoice, and `--pdf` alone refuses to guess when there is more than one.

## What we measured

Each command was run against a mocked monthly backend and a mocked copy of today's. Against today's, `co server new` printed the 12-month prompt, `$360.00 for 12 months, charged now`, unchanged. Against the monthly one it printed `$222.40 / month` for a 16 GB machine with a 200 GB disk, and `$0.00 charged now` after create. The PDF of that month's invoice was read back with pypdf and showed the backend's total, $222.40. pypdf was already a dependency, so the PDF added no package. A bill-to name in Chinese, which the PDF's built-in font cannot draw, is replaced by the account address and a note instead of a row of question marks. `co audit` passed the hard rules and the model review for `new`, `ls`, `destroy` and `invoice`.

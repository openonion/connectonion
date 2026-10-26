---
description: co email setup quoted a price for names the purchase endpoint will not sell. The preview now asks the same read-only name check the charge uses.
tags: [Email, CLI]
---

# The price for a name that cannot be bought

Someone setting up a second mailbox tried `admin` on trustxmail.com, and then
tried `Bad_Alias!`. Both times the terminal answered with a price, $9.90 from
credits, and a command to copy: add `--buy`. That line is the only promise the
preview makes. Running it did not buy anything. The server refused `admin` as
reserved, and it refused the other name because a mailbox local part may only
be letters, numbers, and single dots. The balance was the same afterwards.

The rule was never a secret. `co email name` already asks
`/email/check-name` before it mentions a price, and the purchase of an extra
address uses that same validator: three to twenty characters, those letters
and dots, a reserved list, and not the automatic mailbox shape of `0x` plus
ten hex digits. Setup had looked at the domain menu and the price table and
stopped there. It treated every alias as something the account might own.

Copying the reserved list into the CLI would have made a second copy of a
rule that lives next to the charge. The next name the server reserves would
have been quoted a price again. Setup now asks the read-only check first,
with the same lowercased local part it would send. When that check says the
name itself cannot be sold, the refusal is the whole answer. There is no
price and no `--buy` line, and the purchase is not posted.

A name that is only taken is a different answer. The preview still shows the
price, because which hosted domain is free is decided when you buy, and a
taken address is not charged. The price stays a promise only for a name the
server is willing to consider.

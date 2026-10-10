---
description: oo-api names an agent's mailbox 0x plus ten hex characters; six places in the client wrote 0x plus eight. One function now owns the rule.
tags: [Email, Identity]
---

# Two characters short

Parrot, one of our always-on agents, has a mailbox:
`0xadfeca14cb@mail.openonion.ai`. oo-api gave it that name, and it is in
Parrot's `keys.env`. While building `co handoff`, we needed to work out
another agent's mailbox from its `0x` address, and the obvious line of code
for that was already in the client:

```python
f"{address[:10]}@mail.openonion.ai"   # 0xadfeca14@mail.openonion.ai
```

That is `0x` plus eight hex characters. The server uses `0x` plus ten,
`public_key[:12]`. Mail to the short form goes nowhere, and nothing bounces
in a way an agent would notice.

## Why nobody saw it

Most people never hit the wrong line. When you run `co auth`, oo-api sends
back the real mailbox, and that value wins. The short form only appeared in
the fallbacks: a server reply with no email in it, `co reset`, a deploy whose
account call came back empty, `send_email` reading an old `config.yaml`, and
`generate()` and `recover()` themselves, which put the short form into every
fresh identity until `co auth` replaced it.

That made it the worst kind of bug. Everyone writing a new fallback copied
the line that was already there. There were six copies, and two tests pinned
the wrong length, so the copies looked correct.

## One rule

The fix isn't changing `10` to `12` six times. That would leave six places to
get wrong again. `address.agent_email(address)` is now the only code that
builds a mailbox from an address. It returns `0x` and ten hex characters,
and its docstring names the oo-api function it mirrors. Every fallback calls
it.

A test looks for any other `[:N]}@mail.openonion.ai` in the package and fails
if it finds one. The next person writing a fallback gets pointed to the
function, not to a seventh copy.

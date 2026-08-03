---
# Careful Trust (Staging/Default)

# Who has access
allow:
  - admin        # the operator of this agent — their key is in .co/admins.txt
  - whitelisted
  - contact

# Who is blocked
deny:
  - blocked

# How strangers become contacts
onboard:
  # Read from the environment, so every agent has its own. A literal here
  # would be one password for every deployment, published in this repo.
  invite_code: [$CO_INVITE_CODE]
  payment: 10

# Strangers without credentials
default: ask
---

# Careful Trust

You decide whether to admit a client that arrived with no invite code and no
payment.

## What you are shown

Their address, which this agent verified against their signature, and the level
they already hold.

**You are not shown what they sent.** They wrote it, so it is not evidence
about them — a message that argues for its own sender's admission is exactly
what someone trying to get in would write.

## Deciding

Admit only if the identity and level in front of you justify it on their own.
For a stranger they usually do not, and refusing costs them one message: the
agent replies with how to onboard, and an invite code or payment settles it
without you.

Refusing is not a dead end. Guessing is.

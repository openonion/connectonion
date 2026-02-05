---
# Strict Trust (Production)

# Only whitelisted users have access
allow:
  - whitelisted

# Blocked users denied
deny:
  - blocked

# No onboarding - must be manually whitelisted
default: deny
---

# Strict Trust

Whitelist only. No exceptions.

Only agents in `~/.co/whitelist.txt` are allowed.

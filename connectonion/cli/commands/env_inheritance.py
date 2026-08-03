"""What a new project inherits from the machine that made it.

Shared by `co init` and `co create`, which each build the project .env
from ~/.co/keys.env and had drifted into doing it differently.
"""

# Credentials that authorise reaching into someone's personal accounts. They
# live in ~/.co/keys.env because a tool integration put them there — `co gmail
# auth`, `co outlook auth` — and they belong to that machine's operator, not to
# every project made on it.
#
# `co init` used to copy the whole of keys.env into the new project's .env. On a
# machine with Gmail and Outlook connected that meant live OAuth *refresh*
# tokens in every project directory, with a .gitignore written only when the
# directory was already a git repo — one `git add .` from being published — and
# `co deploy` then delivering them to a server made for an unrelated agent.
#
# A prefix rule rather than a list of names, so a scope or an expiry field added
# next to them later is covered without anyone remembering to.
PERSONAL_ACCOUNT_PREFIXES = ('GOOGLE_', 'MICROSOFT_')


def is_personal_account_credential(key: str) -> bool:
    """Whether this keys.env entry authorises access to a person's own account."""
    return key.startswith(PERSONAL_ACCOUNT_PREFIXES)



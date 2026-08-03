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


# Values that are true of the machine rather than of the project. A project .env
# travels — cloned, rsynced, deployed — and an absolute home directory is right
# in exactly one place.
#
# AGENT_CONFIG_PATH is the whole list so far. #438 removed the line that wrote
# it, and `co deploy` rewrites it for the server, but neither covers the route
# it actually arrives by: it sits in ~/.co/keys.env on machines where an older
# release put it there, and keys.env is copied key by key.
MACHINE_LOCAL_KEYS = ('AGENT_CONFIG_PATH',)


def describes_this_machine(key: str) -> bool:
    """Whether this keys.env entry would be wrong anywhere else."""
    return key in MACHINE_LOCAL_KEYS



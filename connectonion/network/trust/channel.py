"""Who a chat-channel sender is to this agent, under the same policy as a web caller (#3340).

An agent served by `co host` admits callers by `host.yaml` trust and the
`.co/` lists, keyed by agent address. A person writing to the same agent
through `co whatsapp consume` was outside that policy, so a deployment kept a
second file of phone numbers and roles for its handler to read.

Here a sender is a channel identity in those same lists:

    whatsapp:+61400000000      a person, by phone number (what an owner knows)
    whatsapp:120363...@g.us    a group, whose members get its level

The sender's identity comes from the authenticated session, never from the
message text or the display name. A sender the channel cannot resolve to a
phone (an unmapped LID) is a stranger, and a group's level never stands in
for them.
"""
from pathlib import Path
from typing import Optional

from .tools import _check_list, is_admin, is_blocked

# What CO_CALLER_TRUST says, the same words a web caller of `co host` gets.
LEVELS = ("admin", "whitelist", "contact", "stranger")
# The policy's `allow:` names for each level.
_ALLOW_NAME = {"admin": "admin", "whitelist": "whitelisted", "contact": "contact"}


def _own_level(identity: str, co_dir: Optional[Path]) -> str:
    """The level an entry gives on its own, without any group."""
    if is_admin(identity, co_dir):
        return "admin"
    if _check_list("whitelist", identity, co_dir):
        return "whitelist"
    if _check_list("contacts", identity, co_dir):
        return "contact"
    return "stranger"


def channel_level(identity: str, group: str = "", co_dir: Optional[Path] = None) -> str:
    """blocked, admin, whitelist, contact or stranger for a sender, in a group or not.

    Blocked wins over everything, the person's or the group's. Then a person's
    own entry wins over the group's (so an admin is admin in any group). A
    member with no entry of their own gets the group's level. An unresolved
    sender is a stranger even in a listed group.
    """
    if (identity and is_blocked(identity, co_dir)) or (group and is_blocked(group, co_dir)):
        return "blocked"
    if not identity:
        return "stranger"
    own = _own_level(identity, co_dir)
    if own != "stranger" or not group:
        return own
    return _own_level(group, co_dir)


def admits(level: str, policy: dict) -> bool:
    """Whether the host's own fast rules let this level in.

    `default: ask` has no one to ask on a chat channel, and no invite code or
    payment travels over it, so it reads as deny there.
    """
    if level == "blocked":
        return False
    if _ALLOW_NAME.get(level) in (policy.get("allow") or []):
        return True
    return policy.get("default", "deny") == "allow"


def host_policy(co_dir: Path) -> dict:
    """The fast-rule config of this project's `host.yaml` trust, as `co host` reads it."""
    from ..host.config import load_host_config
    from .trust_agent import TrustAgent
    trust = load_host_config(co_dir).get("trust", "careful")
    return TrustAgent(str(trust), co_dir=co_dir).config

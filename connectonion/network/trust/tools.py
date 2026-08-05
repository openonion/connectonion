"""
Purpose: Provide tool functions for trust agents to verify other agents
LLM-Note:
  Dependencies: imports from [pathlib, typing] | imported by [.factory, .fast_rules] | tested by [tests/unit/test_trust_functions.py]
  Data flow: Fast rules call is_whitelisted/is_blocked/is_contact directly → returns bool for instant decisions | Trust agents call check_whitelist/check_blocklist/get_level → returns strings for LLM interpretation
  State/Effects: Reads/writes ~/.co/{whitelist,blocklist,contacts}.txt files | Supports wildcard patterns with * | promote_*/demote_*/block/unblock modify list files
  Integration: exposes fast rule helpers (is_*), trust agent tools (check_*, get_level), state modifiers (promote_*, demote_*, block, unblock) | Used by factory.py and fast_rules.py
  Performance: Simple file I/O | No network calls | O(n) list lookup

Trust Levels (stored in ~/.co/):
  - stranger: Not in any list (default for unknown clients)
  - contact: In contacts.txt (onboarded via invite/payment)
  - whitelist: In whitelist.txt (fully trusted)
  - blocked: In blocklist.txt (denied access)
"""

import re
from pathlib import Path
from typing import List, Callable


def list_file(list_name: str) -> Path:
    """Where one of this agent's trust lists lives — beside its identity.

    These used to sit in a single ~/.co/ shared by every agent on the machine,
    while the address they are compared against came from the project's .co/.
    One box hosting two agents meant one whitelist: an address promoted while
    poking at a throwaway agent was promoted on the production one too, with
    nothing in either agent's directory recording it.

    `admins.txt` was moved for exactly this reason. These three are the rest of
    the same list, and whitelist is the one that grants.
    """
    return _project_co_dir() / f"{list_name}.txt"


# One line per list per process. The entries in the old global file are not read
# — reading them would be the bug this moved away from — so saying where they
# went is the only thing left to do. Silence here is a colleague who cannot
# connect and no reason anywhere.
_announced_legacy = set()


def _mention_a_legacy_list(list_name: str) -> None:
    legacy = Path.home() / ".co" / f"{list_name}.txt"
    if list_name in _announced_legacy or not legacy.exists():
        return
    _announced_legacy.add(list_name)
    if not legacy.read_text(encoding="utf-8").strip():
        return
    print(f"[trust] {legacy} is no longer read — these lists now live beside "
          f"each agent, in its own .co/. Copy the lines you still want into "
          f"{list_file(list_name)}.")


# The `.co/` that belongs to this agent. A blocked address read from the wrong
# list comes back a stranger, so this one fails open. See connectonion/project.py.
from ...project import project_co_dir as _project_co_dir


def _admins_file(co_dir: Path = None) -> Path:
    """Where this agent's admin list lives — beside its identity, not in $HOME.

    The list used to be the single global ~/.co/admins.txt while the address it is
    compared against came from the project's .co/, so every agent on one machine
    shared one set of admins: making someone admin of one deployed agent made them
    admin of all of them. Scope it the same way the identity is scoped.
    """
    return (Path(co_dir) if co_dir else _project_co_dir()) / "admins.txt"


def _check_list(list_name: str, agent_id: str) -> bool:
    """Check if agent_id is in a list file. Supports `*` wildcards.

    A line matches the whole identifier, not part of it. `trusted-*` used to be
    implemented as `line.replace('*', '') in agent_id` — an unanchored substring
    test that let `un-trusted-hacker` satisfy a whitelist entry meant to grant a
    prefix. On the whitelist that fails open, which is the direction that costs
    something: `is_whitelisted()` is built on this, so the grant is real.

    Comparison folds case. Addresses are generated lowercase (address.py:64),
    but an admin pastes what a UI showed them, and `block("0xABCDEF…")` that
    silently blocks nobody is worse than one that errors — it reported success.
    """
    list_path = list_file(list_name)
    if not list_path.exists():
        _mention_a_legacy_list(list_name)
        return False
    # An unreadable file is not an empty file.
    #
    # This used to be `except Exception: return False`, which is the safe
    # direction for whitelist and contacts and fail-open for blocklist: a
    # blocklist.txt saved as GBK by a Windows editor, or left root-owned by a
    # deploy, raises on read and every blocked address is admitted. Same
    # swallow, safe one way and dangerous the other, which is why it lasted —
    # the direction that matters is the one nobody tests.
    #
    # Absent is an answer, and still returns False above. Unreadable is a
    # question this agent cannot answer, so it says which file and stops.
    try:
        content = list_path.read_text(encoding='utf-8')
    except OSError as exc:
        raise OSError(f"cannot read {list_path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise UnicodeDecodeError(
            exc.encoding, exc.object, exc.start, exc.end,
            f"{list_path} is not UTF-8 — an editor may have saved it in a "
            f"local code page; re-save it as UTF-8"
        ) from None

    agent_id = agent_id.strip().lower()
    for line in content.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if _matches(agent_id, line.lower()):
            return True
    return False


def _matches(agent_id: str, pattern: str) -> bool:
    """Whole-string match where `*` is the only metacharacter.

    Deliberately not `fnmatch`: it also gives meaning to `?` and `[seq]`, which
    were literal here before. That cuts both ways and both ways are wrong — a
    blocklist entry like `agent[1]` would stop matching itself, and a `?`
    anywhere in a whitelist line would start matching identifiers its author
    never wrote down. Escaping everything but `*` keeps the vocabulary exactly
    as documented.
    """
    expr = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.fullmatch(expr, agent_id) is not None


def check_whitelist(agent_id: str) -> str:
    """
    Check if an agent is on the whitelist.

    Args:
        agent_id: Identifier of the agent to check

    Returns:
        String indicating if agent is whitelisted or not
    """
    if _check_list("whitelist", agent_id):
        return f"{agent_id} is on the whitelist"
    return f"{agent_id} is NOT on the whitelist"


def check_blocklist(agent_id: str) -> str:
    """
    Check if an agent is on the blocklist.

    Args:
        agent_id: Identifier of the agent to check

    Returns:
        String indicating if agent is blocked or not
    """
    if _check_list("blocklist", agent_id):
        return f"{agent_id} is BLOCKED"
    return f"{agent_id} is not blocked"


def is_whitelisted(agent_id: str) -> bool:
    """Check if agent is whitelisted. Returns bool for fast rules."""
    return _check_list("whitelist", agent_id)


def is_blocked(agent_id: str) -> bool:
    """Check if agent is blocked. Returns bool for fast rules."""
    return _check_list("blocklist", agent_id)


def test_capability(agent_id: str, test: str, expected: str) -> str:
    """
    Test an agent's capability with a specific test.
    
    Args:
        agent_id: Identifier of the agent to test
        test: The test to perform
        expected: The expected result
        
    Returns:
        Test description for the trust agent to evaluate
    """
    return f"Testing {agent_id} with: {test}, expecting: {expected}"


def verify_agent(agent_id: str, agent_info: str = "") -> str:
    """
    General verification of an agent.
    
    Args:
        agent_id: Identifier of the agent
        agent_info: Additional information about the agent
        
    Returns:
        Verification context for the trust agent
    """
    return f"Verifying agent: {agent_id}. Info: {agent_info}"


def _add_to_list(list_name: str, client_id: str) -> bool:
    """Add client_id to a list file."""
    list_path = list_file(list_name)
    list_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if already in list
    if _check_list(list_name, client_id):
        return True

    # Append to file
    with open(list_path, 'a', encoding='utf-8') as f:
        f.write(f"{client_id}\n")
    return True


def _remove_from_list(list_name: str, client_id: str) -> bool:
    """Remove client_id from a list file."""
    list_path = list_file(list_name)
    if not list_path.exists():
        return True

    content = list_path.read_text(encoding='utf-8')
    lines = [line for line in content.strip().split('\n')
             if line.strip() and line.strip() != client_id]
    list_path.write_text('\n'.join(lines) + '\n' if lines else '', encoding='utf-8')
    return True


# === Verification ===

def verify_invite(client_id: str, invite_code: str, valid_codes: list[str]) -> str:
    """
    Verify invite code. Promotes to contact if valid.

    Args:
        client_id: Client to verify
        invite_code: The invite code provided
        valid_codes: List of valid invite codes

    Returns:
        Result message
    """
    if invite_code in valid_codes:
        promote_to_contact(client_id)
        return f"Invite code valid. {client_id} promoted to contact."
    return f"Invalid invite code for {client_id}."


def verify_payment(client_id: str, amount: float, required_amount: float) -> str:
    """
    Verify payment. Promotes to contact if sufficient.

    Args:
        client_id: Client to verify
        amount: Payment amount received
        required_amount: Required payment amount

    Returns:
        Result message
    """
    if amount >= required_amount:
        promote_to_contact(client_id)
        return f"Payment verified. {client_id} promoted to contact."
    return f"Insufficient payment for {client_id}. Required: {required_amount}, got: {amount}"


# === Promotion ===

def promote_to_contact(client_id: str) -> str:
    """Stranger → Contact"""
    _add_to_list("contacts", client_id)
    return f"{client_id} promoted to contact."


def promote_to_whitelist(client_id: str) -> str:
    """Contact → Whitelist"""
    _add_to_list("whitelist", client_id)
    return f"{client_id} promoted to whitelist."


# === Demotion ===

def demote_to_contact(client_id: str) -> str:
    """Whitelist → Contact"""
    _remove_from_list("whitelist", client_id)
    _add_to_list("contacts", client_id)
    return f"{client_id} demoted to contact."


def demote_to_stranger(client_id: str) -> str:
    """Contact → Stranger"""
    _remove_from_list("contacts", client_id)
    _remove_from_list("whitelist", client_id)
    return f"{client_id} demoted to stranger."


# === Blocking ===

def block(client_id: str, reason: str = "") -> str:
    """Add to blocklist."""
    _add_to_list("blocklist", client_id)
    return f"{client_id} blocked. Reason: {reason}"


def unblock(client_id: str) -> str:
    """Remove from blocklist."""
    _remove_from_list("blocklist", client_id)
    return f"{client_id} unblocked."


# === Queries ===

def get_level(client_id: str) -> str:
    """Returns: stranger, contact, whitelist, or blocked."""
    if is_blocked(client_id):
        return "blocked"
    if is_whitelisted(client_id):
        return "whitelist"
    if _check_list("contacts", client_id):
        return "contact"
    return "stranger"


def is_contact(client_id: str) -> bool:
    """Check if client is a contact."""
    return _check_list("contacts", client_id)


def is_stranger(client_id: str) -> bool:
    """Check if client is a stranger (not contact, whitelist, or blocked)."""
    return get_level(client_id) == "stranger"


def get_trust_verification_tools() -> List[Callable]:
    """
    Get the list of trust verification tools.

    Returns:
        List of trust verification functions
    """
    return [
        check_whitelist,
        check_blocklist,
        promote_to_contact,
        promote_to_whitelist,
        demote_to_contact,
        demote_to_stranger,
        block,
        unblock,
        get_level,
    ]


# === Admin Management ===

def load_admins(co_dir: Path = None) -> set:
    """
    Load admins list: self address (default) + the agent's .co/admins.txt.

    Args:
        co_dir: Project .co directory (for self address). Defaults to cwd/.co

    Returns:
        Set of admin addresses
    """
    admins = set()

    if co_dir is None:
        co_dir = _project_co_dir()

    # Self address is always admin. Through get_self_address, which reads
    # `.co/keys/` and falls back to the older `.co/address.json` — this used to
    # read address.json alone, a file nothing has written since keys moved. So
    # is_super_admin(self) was True while is_admin(self) was False, and
    # ws_admin gates on is_admin *before* it reaches the super-admin check:
    # ADMIN_ADD and ADMIN_REMOVE were unreachable by the one account they exist
    # for. Same shape as #579 and #614 — a gate compared against a value the
    # resolver never produces for that identity.
    self_address = get_self_address(co_dir)
    if self_address:
        admins.add(self_address)

    # Additional admins from this agent's own admins.txt
    # Same reasoning as _check_list, and the cost is higher since #579: the
    # approval dialog is admins-only, so an admins.txt that cannot be read does
    # not merely lose a permission — every approval the owner attempts comes
    # back "you are stranger", naming the wrong reason, about a file nothing
    # mentions.
    admins_file = _admins_file(co_dir)
    if admins_file.exists():
        try:
            content = admins_file.read_text(encoding='utf-8')
        except OSError as exc:
            raise OSError(f"cannot read {admins_file}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise UnicodeDecodeError(
                exc.encoding, exc.object, exc.start, exc.end,
                f"{admins_file} is not UTF-8 — an editor may have saved it in "
                f"a local code page; re-save it as UTF-8"
            ) from None
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                admins.add(line)

    return admins


def is_admin(client_id: str, co_dir: Path = None) -> bool:
    """Check if client is an admin."""
    return client_id in load_admins(co_dir)


def get_self_address(co_dir: Path = None) -> str | None:
    """The agent's own address — who a payment onboarding is paid to.

    Read the same way every other part of the codebase reads it. It used to be
    read straight out of ``.co/address.json``, a file `co create` has not
    written for some time: keys live in ``.co/keys/``. So this answered None for
    every project made since, which is not a visible error anywhere —
    ONBOARD_REQUIRED simply goes out with no payment address for the card to
    show, and `verify_payment` returns False before it asks anything. Paid
    onboarding could not succeed, and the card could not say where to send the
    money (openonion/oo-chat#28).

    ``address.json`` is still honoured, because a project created before the
    move has one and nothing else.
    """
    import json

    if co_dir is None:
        co_dir = _project_co_dir()

    # The identity this project acts as -- its own key, else the machine's,
    # which is what the host serves under. Loading the directory alone came
    # back empty for a project with no key of its own, so the payment door had
    # no address to send a stranger to (#716).
    from ...project import project_identity

    keys = project_identity(co_dir)
    if keys and keys.get("address"):
        return keys["address"]

    addr_file = co_dir / "address.json"
    if addr_file.exists():
        try:
            addr_data = json.loads(addr_file.read_text(encoding='utf-8'))
            return addr_data.get('address')
        except Exception:
            pass
    return None


def is_super_admin(client_id: str, co_dir: Path = None) -> bool:
    """Check if client is super admin (self address)."""
    return client_id == get_self_address(co_dir)


def add_admin(admin_id: str, co_dir: Path = None) -> str:
    """Add an admin to this agent's .co/admins.txt. Super admin only."""
    admins_file = _admins_file(co_dir)
    admins_file.parent.mkdir(parents=True, exist_ok=True)

    # Check if already admin
    existing = set()
    if admins_file.exists():
        existing = {line.strip() for line in admins_file.read_text(encoding='utf-8').splitlines()
                    if line.strip() and not line.startswith('#')}

    if admin_id in existing:
        return f"{admin_id} is already an admin."

    with open(admins_file, 'a', encoding='utf-8') as f:
        f.write(f"{admin_id}\n")

    return f"{admin_id} added as admin."


def remove_admin(admin_id: str, co_dir: Path = None) -> str:
    """Remove an admin from this agent's .co/admins.txt. Super admin only."""
    admins_file = _admins_file(co_dir)

    if not admins_file.exists():
        return f"{admin_id} is not an admin."

    lines = admins_file.read_text(encoding='utf-8').splitlines()
    new_lines = [line for line in lines if line.strip() != admin_id]

    if len(new_lines) == len(lines):
        return f"{admin_id} is not an admin."

    admins_file.write_text('\n'.join(new_lines) + '\n' if new_lines else '', encoding='utf-8')
    return f"{admin_id} removed from admins."
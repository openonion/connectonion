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

from pathlib import Path
from typing import List, Callable


CO_DIR = Path.home() / ".co"


def _check_list(list_name: str, agent_id: str) -> bool:
    """Check if agent_id is in a list file. Supports wildcards."""
    list_path = CO_DIR / f"{list_name}.txt"
    if not list_path.exists():
        return False
    try:
        content = list_path.read_text(encoding='utf-8')
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line == agent_id:
                return True
            if '*' in line:
                pattern = line.replace('*', '')
                if pattern in agent_id:
                    return True
        return False
    except Exception:
        return False


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
    CO_DIR.mkdir(parents=True, exist_ok=True)
    list_path = CO_DIR / f"{list_name}.txt"

    # Check if already in list
    if _check_list(list_name, client_id):
        return True

    # Append to file
    with open(list_path, 'a', encoding='utf-8') as f:
        f.write(f"{client_id}\n")
    return True


def _remove_from_list(list_name: str, client_id: str) -> bool:
    """Remove client_id from a list file."""
    list_path = CO_DIR / f"{list_name}.txt"
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
    Load admins list: self address (default) + ~/.co/admins.txt.

    Args:
        co_dir: Project .co directory (for self address). Defaults to cwd/.co

    Returns:
        Set of admin addresses
    """
    import json

    admins = set()

    # Self address is always admin (from project's .co/address.json)
    if co_dir is None:
        co_dir = Path.cwd() / ".co"

    addr_file = co_dir / "address.json"
    if addr_file.exists():
        try:
            addr_data = json.loads(addr_file.read_text(encoding='utf-8'))
            if addr_data.get('address'):
                admins.add(addr_data['address'])
        except Exception:
            pass

    # Additional admins from ~/.co/admins.txt
    admins_file = CO_DIR / "admins.txt"
    if admins_file.exists():
        try:
            for line in admins_file.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    admins.add(line)
        except Exception:
            pass

    return admins


def is_admin(client_id: str, co_dir: Path = None) -> bool:
    """Check if client is an admin."""
    return client_id in load_admins(co_dir)


def get_self_address(co_dir: Path = None) -> str | None:
    """Get self address (super admin) from .co/address.json."""
    import json

    if co_dir is None:
        co_dir = Path.cwd() / ".co"

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


def add_admin(admin_id: str) -> str:
    """Add an admin to ~/.co/admins.txt. Super admin only."""
    CO_DIR.mkdir(parents=True, exist_ok=True)
    admins_file = CO_DIR / "admins.txt"

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


def remove_admin(admin_id: str) -> str:
    """Remove an admin from ~/.co/admins.txt. Super admin only."""
    admins_file = CO_DIR / "admins.txt"

    if not admins_file.exists():
        return f"{admin_id} is not an admin."

    lines = admins_file.read_text(encoding='utf-8').splitlines()
    new_lines = [line for line in lines if line.strip() != admin_id]

    if len(new_lines) == len(lines):
        return f"{admin_id} is not an admin."

    admins_file.write_text('\n'.join(new_lines) + '\n' if new_lines else '', encoding='utf-8')
    return f"{admin_id} removed from admins."
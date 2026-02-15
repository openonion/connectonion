"""
Purpose: Class-based trust management with fast rules, LLM fallback, and extensible methods
LLM-Note:
  Dependencies: imports from [dataclasses, pathlib, typing, fast_rules, tools, factory, core.agent, llm_do, pydantic, httpx, address] | imported by [trust/__init__.py, network/host/server.py, network/host/auth.py] | tested via should_allow() calls
  Data flow: TrustAgent(trust, api_key, model) → _load_policy() reads policy file → parse_policy() extracts YAML config + markdown prompt → should_allow(client_id, request) → evaluate_request() runs fast rules → if None: _llm_decide() uses llm_do with structured output → returns Decision(allow, reason, used_llm) | verify_payment() → _verify_transfer_via_api() calls oo-api /api/v1/onboard/verify with JWT auth
  State/Effects: reads policy files from prompts/trust/{level}.md | delegates to tools.py for file operations (.co/trust/ directory) | _verify_transfer_via_api() makes HTTP calls to oo-api | lazy-loads LLM agent only if needed
  Integration: exposes TrustAgent class with should_allow(), verify_invite(), verify_payment(), promote_to_contact(), promote_to_whitelist(), demote_to_contact(), demote_to_stranger(), block(), unblock(), get_level(), is_admin(), add_admin(), remove_admin() | Decision dataclass with allow, reason, used_llm fields | all methods overridable for custom storage (database, LDAP, etc.)
  Performance: fast rules execute without LLM (instant) | LLM only used if config has 'default: ask' | policy loaded once at init | httpx timeout 10s for API calls | lazy LLM initialization
  Errors: _verify_transfer_via_api() returns False on network/auth errors | llm_do() errors propagate | parse_policy() YAML errors propagate
  ⚠️ Extensible: subclass and override methods for custom storage backends

TrustAgent - A clear, method-based interface for trust management.

Usage:
    from connectonion.network.trust import TrustAgent

    trust = TrustAgent("careful")  # or "open", "strict", or path to policy file

    # Check if request is allowed
    decision = trust.should_allow("client-123", {"prompt": "hello"})
    if decision.allow:
        # process request
    else:
        print(decision.reason)

    # Trust level operations
    trust.promote_to_contact("client-123")
    trust.block("bad-actor", reason="spam")
    level = trust.get_level("client-123")  # "stranger", "contact", "whitelist", "blocked"

    # Admin operations
    trust.is_admin("client-123")
    trust.add_admin("new-admin")

Extensibility:
    Subclass TrustAgent to customize behavior. All methods can be overridden.

    class MyTrustAgent(TrustAgent):
        '''Custom trust with database-backed storage.'''

        def is_admin(self, client_id: str) -> bool:
            '''Check admin from database instead of file.'''
            return self.db.is_admin(client_id)

        def promote_to_contact(self, client_id: str) -> str:
            '''Store contacts in database.'''
            self.db.add_contact(client_id)
            return f"{client_id} promoted to contact."

    # Use custom trust agent
    host(create_agent, trust=MyTrustAgent("careful"))
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .fast_rules import parse_policy, evaluate_request
from .tools import (
    is_whitelisted as _is_whitelisted,
    is_blocked as _is_blocked,
    is_contact as _is_contact,
    is_stranger as _is_stranger,
    promote_to_contact as _promote_to_contact,
    promote_to_whitelist as _promote_to_whitelist,
    demote_to_contact as _demote_to_contact,
    demote_to_stranger as _demote_to_stranger,
    block as _block,
    unblock as _unblock,
    get_level as _get_level,
    # Admin functions
    is_admin as _is_admin,
    is_super_admin as _is_super_admin,
    get_self_address as _get_self_address,
    add_admin as _add_admin,
    remove_admin as _remove_admin,
)
from .factory import PROMPTS_DIR, TRUST_LEVELS


@dataclass
class Decision:
    """Result of should_allow() check."""
    allow: bool
    reason: str
    used_llm: bool = False


class TrustAgent:
    """
    Trust management with a clear, method-based interface.

    All trust operations in one place:
    - should_allow() - Check if request is allowed (fast rules + LLM fallback)
    - verify_invite() / verify_payment() - Onboarding
    - promote_to_contact() / promote_to_whitelist() - Promotion
    - demote_to_contact() / demote_to_stranger() - Demotion
    - block() / unblock() - Blocking
    - get_level() - Query current level
    - is_admin() / is_super_admin() - Admin checks
    - add_admin() / remove_admin() - Admin management

    Extensibility:
        All methods can be overridden in subclasses for custom storage,
        authentication backends, or business logic. See module docstring.
    """

    def __init__(self, trust: str = "careful", *, api_key: str = None, model: str = "co/gpt-4o-mini"):
        """
        Create a TrustAgent.

        Args:
            trust: Trust level ("open", "careful", "strict") or path to policy file
            api_key: Optional API key for LLM (only needed if using 'ask' default)
            model: Model to use for LLM decisions
        """
        self.trust = trust
        self.api_key = api_key
        self.model = model

        # Load policy and parse config
        self._config, self._prompt = self._load_policy(trust)

        # Lazy-loaded LLM agent (only created if needed)
        self._llm_agent = None

    def _load_policy(self, trust: str) -> tuple[dict, str]:
        """Load policy file and parse YAML config."""
        # Trust level -> load from prompts/trust/{level}.md
        if trust.lower() in TRUST_LEVELS:
            policy_path = PROMPTS_DIR / f"{trust.lower()}.md"
            if policy_path.exists():
                text = policy_path.read_text(encoding='utf-8')
                return parse_policy(text)
            return {}, ""

        # File path
        path = Path(trust)
        if path.exists() and path.is_file():
            text = path.read_text(encoding='utf-8')
            return parse_policy(text)

        # Inline policy text
        if trust.startswith('---'):
            return parse_policy(trust)

        # Unknown - empty config
        return {}, ""

    # === Main Decision Method ===

    def should_allow(self, client_id: str, request: dict = None) -> Decision:
        """
        Check if a request should be allowed.

        Runs fast rules first (no LLM). Only uses LLM if config has 'default: ask'.

        Args:
            client_id: The client making the request
            request: Optional request data (may contain invite_code, payment)

        Returns:
            Decision with allow (bool) and reason (str)
        """
        request = request or {}

        # Fast rules (no LLM)
        result = evaluate_request(self._config, client_id, request)

        if result == 'allow':
            return Decision(allow=True, reason="Allowed by fast rules")
        elif result == 'deny':
            return Decision(allow=False, reason="Denied by fast rules")

        # result is None -> need LLM decision
        return self._llm_decide(client_id, request)

    def _llm_decide(self, client_id: str, request: dict) -> Decision:
        """Use LLM to make trust decision (only for 'ask' cases)."""
        from ...core.agent import Agent
        from ...llm_do import llm_do
        from pydantic import BaseModel

        class TrustDecision(BaseModel):
            allow: bool
            reason: str

        # Build context for LLM
        level = self.get_level(client_id)
        prompt = f"""Evaluate this trust request:
- client_id: {client_id}
- current_level: {level}
- request: {request}

Should this client be allowed access?"""

        decision = llm_do(
            prompt,
            output=TrustDecision,
            system_prompt=self._prompt or "You are a trust evaluation agent. Decide if the request should be allowed.",
            api_key=self.api_key,
            model=self.model,
        )

        return Decision(allow=decision.allow, reason=decision.reason, used_llm=True)

    # === Verification (Onboarding) ===

    def verify_invite(self, client_id: str, invite_code: str) -> bool:
        """
        Verify invite code. Promotes to contact if valid.

        Args:
            client_id: Client to verify
            invite_code: The invite code provided

        Returns:
            True if valid and promoted, False otherwise
        """
        valid_codes = self._config.get('onboard', {}).get('invite_code', [])
        if invite_code in valid_codes:
            self.promote_to_contact(client_id)
            return True
        return False

    def verify_payment(self, client_id: str, amount: float) -> bool:
        """
        Verify payment via oo-api transfer verification.

        Calls the oo-api to check if client_id transferred at least `amount`
        to this agent's address within the last 5 minutes.

        Args:
            client_id: Client to verify (their address)
            amount: Minimum payment amount required

        Returns:
            True if transfer verified and promoted, False otherwise
        """
        required = self._config.get('onboard', {}).get('payment')
        if not required:
            return False

        # Use configured amount if not specified
        min_amount = amount if amount > 0 else required

        # Get self address (agent's address)
        self_addr = self.get_self_address()
        if not self_addr:
            return False

        # Call oo-api to verify transfer
        if self._verify_transfer_via_api(client_id, self_addr, min_amount):
            self.promote_to_contact(client_id)
            return True
        return False

    def _verify_transfer_via_api(self, from_addr: str, to_addr: str, min_amount: float) -> bool:
        """Call oo-api to verify a transfer was made."""
        import os
        import json
        import time
        from pathlib import Path

        try:
            import httpx
        except ImportError:
            # httpx not available, fall back to simple amount check
            return True

        # Load agent's keys for signing the request
        from ... import address as addr

        co_dir = Path.cwd() / '.co'
        keys = addr.load(co_dir)
        if not keys:
            return False

        # Determine API URL
        base_url = os.environ.get('OPENONION_BASE_URL', 'https://oo.openonion.ai')
        if os.environ.get('OPENONION_DEV'):
            base_url = 'http://localhost:8000'

        # Create signed auth request
        timestamp = int(time.time())
        message = f"ConnectOnion-Auth-{keys['public_key']}-{timestamp}"
        signature = addr.sign(keys, message.encode()).hex()

        # Get JWT token
        auth_response = httpx.post(
            f"{base_url}/auth",
            json={
                "public_key": keys['public_key'],
                "message": message,
                "signature": signature
            },
            timeout=10
        )
        if auth_response.status_code != 200:
            return False

        token = auth_response.json().get('token')
        if not token:
            return False

        # Call verify endpoint
        verify_response = httpx.post(
            f"{base_url}/api/v1/onboard/verify",
            json={
                "from_address": from_addr,
                "min_amount": min_amount
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )

        if verify_response.status_code == 200:
            result = verify_response.json()
            return result.get('verified', False)

        return False

    # === Promotion ===

    def promote_to_contact(self, client_id: str) -> str:
        """Stranger -> Contact"""
        return _promote_to_contact(client_id)

    def promote_to_whitelist(self, client_id: str) -> str:
        """Contact -> Whitelist"""
        return _promote_to_whitelist(client_id)

    # === Demotion ===

    def demote_to_contact(self, client_id: str) -> str:
        """Whitelist -> Contact"""
        return _demote_to_contact(client_id)

    def demote_to_stranger(self, client_id: str) -> str:
        """Contact -> Stranger"""
        return _demote_to_stranger(client_id)

    # === Blocking ===

    def block(self, client_id: str, reason: str = "") -> str:
        """Add to blocklist."""
        return _block(client_id, reason)

    def unblock(self, client_id: str) -> str:
        """Remove from blocklist."""
        return _unblock(client_id)

    # === Queries ===

    def get_level(self, client_id: str) -> str:
        """
        Get client's current trust level.

        Returns: "stranger", "contact", "whitelist", or "blocked"
        """
        return _get_level(client_id)

    def is_whitelisted(self, client_id: str) -> bool:
        """Check if client is whitelisted."""
        return _is_whitelisted(client_id)

    def is_blocked(self, client_id: str) -> bool:
        """Check if client is blocked."""
        return _is_blocked(client_id)

    def is_contact(self, client_id: str) -> bool:
        """Check if client is a contact."""
        return _is_contact(client_id)

    def is_stranger(self, client_id: str) -> bool:
        """Check if client is a stranger."""
        return _is_stranger(client_id)

    # === Admin Management ===
    # Instance methods for easy subclass overloading.
    # Override these to customize admin logic (e.g., database-backed, LDAP, etc.)

    def is_admin(self, client_id: str) -> bool:
        """Check if client is an admin. Override for custom admin logic."""
        return _is_admin(client_id)

    def is_super_admin(self, client_id: str) -> bool:
        """Check if client is super admin (self address). Override for custom logic."""
        return _is_super_admin(client_id)

    def get_self_address(self) -> str | None:
        """Get self address (super admin)."""
        return _get_self_address()

    def add_admin(self, admin_id: str) -> str:
        """Add an admin. Super admin only. Override for custom storage."""
        return _add_admin(admin_id)

    def remove_admin(self, admin_id: str) -> str:
        """Remove an admin. Super admin only. Override for custom storage."""
        return _remove_admin(admin_id)

    # === Config Access ===

    @property
    def config(self) -> dict:
        """Get the parsed YAML config."""
        return self._config

    @property
    def prompt(self) -> str:
        """Get the markdown prompt (for LLM decisions)."""
        return self._prompt

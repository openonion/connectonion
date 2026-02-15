"""
Purpose: Public API for trust verification system with TrustAgent interface
LLM-Note:
  Dependencies: imports from [trust_agent, factory, fast_rules] | imported by [network/host/server.py, network/host/auth.py, network/__init__.py] | tested via TrustAgent usage
  Data flow: module exports TrustAgent class and helper functions → users import and create TrustAgent("careful") → TrustAgent delegates to factory for policy loading and tools for file operations
  State/Effects: no direct state (delegates to TrustAgent, factory, tools) | reads policy files | reads/writes .co/trust/ directory via tools
  Integration: exposes TrustAgent, Decision, get_default_trust_level(), validate_trust_level(), TRUST_LEVELS, parse_policy() | single entry point for trust operations | __all__ controls public API
  Performance: imports are static (no lazy loading) | TrustAgent cached per instance
  Errors: no error handling at module level (errors from TrustAgent/factory propagate)

Trust verification system for agent networking.

Usage:
    from connectonion.network.trust import TrustAgent

    trust = TrustAgent("careful")  # or "open", "strict", or path to policy

    # Access control
    decision = trust.should_allow("client-123", {"prompt": "hello"})

    # Trust level operations
    trust.promote_to_contact("client-123")
    trust.block("bad-actor", reason="spam")
    level = trust.get_level("client-123")  # "stranger", "contact", "whitelist", "blocked"

    # Admin operations
    trust.is_admin("client-123")
    trust.add_admin("new-admin")

TrustAgent is the single interface for all trust operations.
Subclass to customize behavior (e.g., database-backed admin storage).
"""

from .trust_agent import TrustAgent, Decision
from .factory import get_default_trust_level, validate_trust_level, TRUST_LEVELS
from .fast_rules import parse_policy

__all__ = [
    # TrustAgent - the single interface
    "TrustAgent",
    "Decision",
    # Helpers
    "get_default_trust_level",
    "validate_trust_level",
    "TRUST_LEVELS",
    "parse_policy",
]

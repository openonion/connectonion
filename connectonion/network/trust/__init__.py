"""
Purpose: Trust verification system module re-exporting factory, prompts, and verification tools
LLM-Note:
  Dependencies: imports from [factory.py, prompts.py, tools.py] | imported by [network/__init__.py, network/host/auth.py, network/host/server.py] | tested by [tests/network/test_trust.py]
  Data flow: re-exports trust agent creation utilities and trust level prompts
  State/Effects: no state
  Integration: exposes create_trust_agent(trust_spec) → Agent, get_default_trust_level() → str, validate_trust_level(level), TRUST_LEVELS dict, TRUST_PROMPTS dict, get_trust_prompt(level) → str, get_trust_verification_tools() → list | used by host() for access control policies
  Performance: trivial
  Errors: none
Trust verification system for agent networking.

This module contains:
- factory: Trust agent creation and configuration
- prompts: Pre-configured trust prompts for different levels
- tools: Verification tools for trust agents
"""

from .factory import create_trust_agent, get_default_trust_level, validate_trust_level, TRUST_LEVELS
from .prompts import TRUST_PROMPTS, get_trust_prompt
from .tools import get_trust_verification_tools

__all__ = [
    "create_trust_agent",
    "get_default_trust_level",
    "validate_trust_level",
    "TRUST_LEVELS",
    "TRUST_PROMPTS",
    "get_trust_prompt",
    "get_trust_verification_tools",
]

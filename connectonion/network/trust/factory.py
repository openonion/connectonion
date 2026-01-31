"""
Purpose: Factory for creating trust verification agents with policies.

String Resolution Priority:
  1. Trust level ("open", "careful", "strict")
  2. File path (if exists)
  3. Inline policy text

LLM-Note:
  Dependencies: [os, pathlib, typing, .prompts, .tools] | imported by [host/server.py] | tested by [tests/unit/test_trust.py]
  Data flow: trust param → check env default → resolve by priority → return Agent or None
  Errors: TypeError (invalid type) | FileNotFoundError (Path doesn't exist)
"""

import os
from pathlib import Path
from typing import Union, Optional

from .prompts import get_trust_prompt
from .tools import get_trust_verification_tools


# Trust level constants
TRUST_LEVELS = ["open", "careful", "strict"]


def get_default_trust_level() -> Optional[str]:
    """
    Get default trust level based on environment.
    
    Returns:
        Default trust level or None
    """
    env = os.environ.get('CONNECTONION_ENV', '').lower()
    
    if env == 'development':
        return 'open'
    elif env == 'production':
        return 'strict'
    elif env in ['staging', 'test']:
        return 'careful'
    
    return None


def create_trust_agent(trust: Union[str, Path, 'Agent', None], api_key: Optional[str] = None, model: str = "gpt-5-mini") -> Optional['Agent']:
    """
    Create a trust agent based on the trust parameter.

    Args:
        trust: Trust configuration:
            - None: Check CONNECTONION_TRUST env, else return None
            - Agent: Return as-is (must have tools)
            - Path: Read file as policy
            - str: Resolved by priority:
                1. Trust level ("open", "careful", "strict")
                2. File path (if file exists)
                3. Inline policy text

    Returns:
        Agent configured for trust verification, or None
    """
    from ...core.agent import Agent  # Import here to avoid circular dependency
    
    # If None, check for environment default
    if trust is None:
        env_trust = os.environ.get('CONNECTONION_TRUST')
        if env_trust:
            trust = env_trust
        else:
            return None  # No trust agent
    
    # If it's already an Agent, validate and return it
    if isinstance(trust, Agent):
        if not trust.tools:
            raise ValueError("Trust agent must have verification tools")
        return trust
    
    # Get trust verification tools
    trust_tools = get_trust_verification_tools()
    
    # Handle Path object
    if isinstance(trust, Path):
        if not trust.exists():
            raise FileNotFoundError(f"Trust policy file not found: {trust}")
        policy = trust.read_text(encoding='utf-8')
        return Agent(
            name="trust_agent_custom",
            tools=trust_tools,
            system_prompt=policy,
            api_key=api_key,
            model=model
        )
    
    # Handle string: trust level > file path > inline policy
    if isinstance(trust, str):
        if trust.lower() in TRUST_LEVELS:
            return Agent(
                name=f"trust_agent_{trust.lower()}",
                tools=trust_tools,
                system_prompt=get_trust_prompt(trust.lower()),
                api_key=api_key,
                model=model
            )

        path = Path(trust)
        if path.exists() and path.is_file():
            return Agent(
                name="trust_agent_custom",
                tools=trust_tools,
                system_prompt=path.read_text(encoding='utf-8'),
                api_key=api_key,
                model=model
            )

        return Agent(
            name="trust_agent_custom",
            tools=trust_tools,
            system_prompt=trust,
            api_key=api_key,
            model=model
        )
    
    # Invalid type
    raise TypeError(f"Trust must be a string (level/policy/path), Path, Agent, or None, not {type(trust).__name__}")


def validate_trust_level(level: str) -> bool:
    """
    Check if a string is a valid trust level.
    
    Args:
        level: String to check
        
    Returns:
        True if valid trust level, False otherwise
    """
    return level.lower() in TRUST_LEVELS
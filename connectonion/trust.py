"""
Purpose: Factory and coordinator for creating trust verification agents with policies
LLM-Note:
  Dependencies: imports from [os, pathlib, typing, trust_agents.py, trust_functions.py] | imported by [agent.py] | tested by [tests/test_trust.py]
  Data flow: receives trust param from Agent.__init__ → get_default_trust_level() checks CONNECTONION_ENV → create_trust_agent() validates trust param → returns Agent with trust verification tools OR None | trust param can be: None (no trust), str ("open"/"careful"/"strict" levels OR markdown policy OR file path), Path (markdown file), Agent (custom trust agent)
  State/Effects: reads markdown files if Path/file path provided | checks os.environ for CONNECTONION_ENV and CONNECTONION_TRUST | creates Agent instances with trust_verification_tools from trust_functions.py | no writes or global state
  Integration: exposes create_trust_agent(trust, api_key, model), get_default_trust_level(), validate_trust_level(level), TRUST_LEVELS constant | used by Agent.__init__ to create self.trust | trust agents get tools from get_trust_verification_tools() and prompts from get_trust_prompt()
  Performance: lazy creation (only when trust param provided) | environment checks are fast | file I/O only for custom policies
  Errors: raises TypeError for invalid trust type | raises ValueError for invalid trust level string | raises FileNotFoundError for missing policy files | heuristic detection for ambiguous strings (checks if file exists before treating as inline policy)
"""

import os
from pathlib import Path
from typing import Union, Optional

from .trust_agents import TRUST_PROMPTS, get_trust_prompt
from .trust_functions import get_trust_verification_tools


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
    Create or return a trust agent based on the trust parameter.
    
    Args:
        trust: Can be:
            - None: No trust agent (returns None)
            - str: Trust level ("open", "careful", "strict") or markdown policy/file path
            - Path: Path to markdown policy file
            - Agent: Custom trust agent (returned as-is)
    
    Returns:
        An Agent configured for trust verification, or None
        
    Raises:
        TypeError: If trust is not a valid type
        ValueError: If trust level is invalid
        FileNotFoundError: If trust policy file doesn't exist
    """
    from .agent import Agent  # Import here to avoid circular dependency
    
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
    
    # Handle string parameter
    if isinstance(trust, str):
        trust_lower = trust.lower()
        
        # Check if it's a trust level
        if trust_lower in TRUST_LEVELS:
            return Agent(
                name=f"trust_agent_{trust_lower}",
                tools=trust_tools,
                system_prompt=get_trust_prompt(trust_lower),
                api_key=api_key,
                model=model
            )
        
        # Check if it looks like a trust level but isn't valid
        # (single word without path separators or newlines)
        if '\n' not in trust and '/' not in trust and '\\' not in trust and ' ' not in trust and len(trust) < 20:
            # It's a single word, probably meant to be a trust level
            if not os.path.exists(trust):  # And it's not a file
                raise ValueError(f"Invalid trust level: {trust}. Must be one of: {', '.join(TRUST_LEVELS)}")
        
        # Check if it's a file path (contains path separators or ends with .md)
        if '/' in trust or '\\' in trust or trust.endswith('.md'):
            path = Path(trust)
            if not path.exists():
                raise FileNotFoundError(f"Trust policy file not found: {trust}")
            policy = path.read_text(encoding='utf-8')
            return Agent(
                name="trust_agent_custom",
                tools=trust_tools,
                system_prompt=policy,
                api_key=api_key,
                model=model
            )
        
        # Check if it's a single-line string that could be a file
        if '\n' not in trust and len(trust) < 100:
            # Could be a file path without obvious markers
            path = Path(trust)
            if path.exists():
                policy = path.read_text(encoding='utf-8')
                return Agent(
                    name="trust_agent_custom",
                    tools=trust_tools,
                    system_prompt=policy,
                    api_key=api_key,
                    model=model
                )
        
        # It's an inline markdown policy
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
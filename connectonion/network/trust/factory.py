"""
Factory for creating trust verification agents with policies.

Policy files use YAML frontmatter for fast rules + markdown body for LLM prompts:

    ---
    allow: [whitelisted, contact]
    deny: [blocked]
    onboard:
      invite_code: [BETA2024]
      payment: 10
    default: ask
    ---
    # LLM Prompt for trust evaluation...

Fast rules execute without LLM (zero tokens, instant). Only 'default: ask' triggers LLM.

String Resolution Priority:
  1. Trust level ("open", "careful", "strict") → loads from prompts/trust/{level}.md
  2. File path (if exists)
  3. Inline policy text
"""

import os
from pathlib import Path
from typing import Union, Optional

from .tools import get_trust_verification_tools
from .fast_rules import parse_policy


# Path to trust policy files (at repo root: prompts/trust/)
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts" / "trust"


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
    DEPRECATED: Use TrustAgent instead.

    >>> from connectonion.network.trust import TrustAgent
    >>> trust = TrustAgent("careful")
    >>> trust.should_allow("client-123")

    This function returns a regular Agent, which lacks TrustAgent methods
    like should_allow(), promote_to_contact(), etc.

    Args:
        trust: Trust configuration (see TrustAgent for new API)

    Returns:
        Agent configured for trust verification, or None
    """
    import warnings
    warnings.warn(
        "create_trust_agent() is deprecated. Use TrustAgent instead: "
        "from connectonion.network.trust import TrustAgent; trust = TrustAgent('careful')",
        DeprecationWarning,
        stacklevel=2
    )
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
            # Load from prompts/trust/{level}.md
            policy_path = PROMPTS_DIR / f"{trust.lower()}.md"
            if policy_path.exists():
                policy_text = policy_path.read_text(encoding='utf-8')
                config, markdown_body = parse_policy(policy_text)
                return Agent(
                    name=f"trust_agent_{trust.lower()}",
                    tools=trust_tools,
                    system_prompt=markdown_body,
                    api_key=api_key,
                    model=model
                )
            # Fallback if file doesn't exist
            raise FileNotFoundError(f"Trust policy file not found: {policy_path}")

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
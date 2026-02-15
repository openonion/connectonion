"""
Purpose: Parse YAML frontmatter from policies and execute fast rules without LLM
LLM-Note:
  Dependencies: imports from [yaml, typing, tools] | imported by [trust/factory.py, trust/trust_agent.py] | tested via TrustAgent.should_allow()
  Data flow: parse_policy(policy_text) → splits on '---' delimiters → yaml.safe_load() → returns (config: dict, markdown_body: str) | evaluate_request(config, client_id, request) → checks deny list (blocked) → checks allow list (whitelisted, contact) → tries onboarding (invite_code or payment) → returns 'allow', 'deny', or None (needs LLM)
  State/Effects: calls tools.py functions (is_blocked, is_whitelisted, is_contact, promote_to_contact) which read/write .co/trust/ files | no direct file I/O in this module
  Integration: exposes parse_policy(policy_text), evaluate_request(config, client_id, request) | used by TrustAgent to parse policies and execute zero-cost fast rules before LLM | returns None when LLM needed (default: ask)
  Performance: zero LLM tokens for fast rules | O(n) checks against allow/deny lists | promote_to_contact() writes to file but rare (onboarding only) | YAML parsing is fast
  Errors: yaml.safe_load() errors propagate | gracefully handles missing frontmatter (returns empty config)

Parse YAML config from trust policy files and execute fast rules.

Config format:
    allow: [whitelisted, contact]  # Who has access
    deny: [blocked]                 # Who is blocked
    onboard:                        # How strangers become contacts
      invite_code: [CODE1, CODE2]
      payment: 10
    default: deny                   # allow | deny | ask
"""

import yaml
from typing import Optional
from .tools import is_whitelisted, is_blocked, is_contact, promote_to_contact


def parse_policy(policy_text: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from markdown policy file.

    Returns:
        (config_dict, markdown_body)
    """
    if not policy_text.startswith('---'):
        return {}, policy_text

    end = policy_text.find('---', 3)
    if end == -1:
        return {}, policy_text

    yaml_content = policy_text[3:end].strip()
    markdown_body = policy_text[end + 3:].strip()

    config = yaml.safe_load(yaml_content) or {}
    return config, markdown_body


def evaluate_request(config: dict, client_id: str, request: dict) -> Optional[str]:
    """
    Evaluate request using fast rules (no LLM).

    Config format:
        allow: [whitelisted, contact]  # Who has access
        deny: [blocked]                 # Who is blocked
        onboard:                        # How strangers become contacts
          invite_code: [CODE1]
          payment: 10
        default: deny                   # allow | deny | ask

    Args:
        config: Parsed YAML config
        client_id: The client making request
        request: Request data (may contain invite_code, payment, etc.)

    Returns:
        'allow', 'deny', or None (needs LLM)
    """
    # 1. Check deny list first (blocked users)
    deny_list = config.get('deny', ['blocked'])
    for condition in deny_list:
        if condition == 'blocked' and is_blocked(client_id):
            return 'deny'

    # 2. Check allow list (whitelisted, contacts)
    allow_list = config.get('allow', [])
    for condition in allow_list:
        if condition == 'whitelisted' and is_whitelisted(client_id):
            return 'allow'
        if condition == 'contact' and is_contact(client_id):
            return 'allow'

    # 3. Try onboarding (stranger → contact)
    onboard = config.get('onboard', {})

    # Check invite code
    valid_codes = onboard.get('invite_code', [])
    request_code = request.get('invite_code')
    if request_code and request_code in valid_codes:
        promote_to_contact(client_id)
        return 'allow'

    # Check payment
    required_payment = onboard.get('payment')
    request_payment = request.get('payment', 0)
    if required_payment and request_payment >= required_payment:
        promote_to_contact(client_id)
        return 'allow'

    # 4. Default action for strangers without onboarding
    default = config.get('default', 'deny')

    if default == 'allow':
        return 'allow'
    elif default == 'deny':
        return 'deny'
    elif default == 'ask':
        return None  # Needs LLM evaluation

    return 'deny'  # Safe fallback

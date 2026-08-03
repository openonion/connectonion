"""
Purpose: Parse YAML frontmatter from policies and execute fast rules without LLM
LLM-Note:
  Dependencies: imports from [yaml, typing, tools] | imported by [trust/factory.py, trust/trust_agent.py] | tested via TrustAgent.should_allow()
  Data flow: parse_policy(policy_text) → splits on '---' delimiters → yaml.safe_load() → returns (config: dict, markdown_body: str) | evaluate_request(config, client_id, request) → checks deny list (blocked) → checks allow list (whitelisted, contact) → tries onboarding (invite_code or payment) → returns 'allow', 'deny', or None (needs LLM)
  State/Effects: calls tools.py functions (is_blocked, is_whitelisted, is_contact, promote_to_contact) which read/write .co/trust/ files | no direct file I/O in this module
  Integration: exposes parse_policy(policy_text), evaluate_request(config, client_id, request) | used by TrustAgent to parse policies and execute zero-cost fast rules before LLM | returns None when LLM needed (default: ask)
  Performance: zero LLM tokens for fast rules | O(n) checks against allow/deny lists | promote_to_contact() writes to file but rare (onboarding only) | YAML parsing is fast
  Errors: yaml.safe_load() errors propagate, naming the policy file when the caller passed one | gracefully handles missing frontmatter (returns empty config)

Parse YAML config from trust policy files and execute fast rules.

Config format:
    allow: [whitelisted, contact]  # Who has access
    deny: [blocked]                 # Who is blocked
    onboard:                        # How strangers become contacts
      invite_code: [CODE1, CODE2]
      payment: 10
    default: deny                   # allow | deny | ask
"""

import io

import yaml
from typing import Optional
from .tools import is_whitelisted, is_blocked, is_contact, is_admin, promote_to_contact


def parse_policy(policy_text: str, source: str = None) -> tuple[dict, str]:
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

    # Handed to PyYAML as a named stream rather than a bare string. A typo in a
    # policy still stops the host — that is the right outcome for a config file
    # it cannot understand — but the parser's own error then reads
    #
    #   in ".co/trust/custom.md", line 3, column 29
    #       allow: [whitelisted, contact
    #                                   ^
    #
    # instead of naming "<unicode string>". Which file, which line, and the text
    # itself, from the library, with nothing caught and re-raised.
    stream = io.StringIO(yaml_content)
    if source:
        stream.name = source
    config = yaml.safe_load(stream) or {}
    return config, markdown_body


def _resolve_codes(codes) -> list:
    """Turn what the policy declares into the codes that actually open the door.

    `$NAME` reads NAME from the environment — which on a deployed agent is the
    root-owned 0600 env file, the same channel every other secret takes, and the
    one thing `co deploy` neither rsyncs nor overwrites.

    An unset variable resolves to *nothing*, never to the placeholder and never
    to a default. That last part is the whole point: the shipped policy used to
    carry `invite_code: [OpenOnion]`, a constant published in this repository
    and printed by every agent on startup, and a stranger who typed it was
    admitted as a contact in five seconds (#561). A missing code is a closed
    door, not an open one.
    """
    import os as _os
    out = []
    for code in codes or []:
        text = str(code)
        if text.startswith('$'):
            value = _os.environ.get(text[1:], '').strip()
            if value:
                out.append(value)
        elif text:
            out.append(text)
    return out


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
    import logging
    logger = logging.getLogger("connectonion.trust.fast_rules")

    # The id goes out whole. The operator's next move after reading this line is to
    # paste it into admins.txt or whitelist.txt, and a prefix cannot be pasted — one
    # that reads like a complete short id even less so.
    #
    # The config does not go out at all: it carries the agent's invite codes, and it
    # was being printed at warning level on every single request.
    logger.warning(
        f"[FAST_RULES] Evaluating client_id={client_id} "
        f"allow={config.get('allow', [])} default={config.get('default', 'deny')}"
    )

    # 1. Check deny list first (blocked users)
    deny_list = config.get('deny', ['blocked'])
    for condition in deny_list:
        if condition == 'blocked' and is_blocked(client_id):
            logger.warning(f"[FAST_RULES] Client {client_id} is BLOCKED, returning 'deny'")
            return 'deny'

    # 2. Check allow list (whitelisted, contacts)
    allow_list = config.get('allow', [])
    for condition in allow_list:
        # An admin is the agent's operator — the person who deployed it and whose
        # key `co deploy` wrote into .co/admins.txt. They were the one identity
        # never consulted here, so a freshly deployed agent answered its own
        # owner with "requires onboarding", for a machine they had just paid for
        # and installed their key on.
        #
        # Each of these says so on the way out. A log that recorded only the denials
        # left "did not grow" meaning either *allowed* or *never asked*, and those are
        # the two states an operator debugging a silent client most needs to separate.
        if condition == 'admin' and is_admin(client_id):
            logger.warning(f"[FAST_RULES] Returning 'allow' — {client_id} is admin")
            return 'allow'
        if condition == 'whitelisted' and is_whitelisted(client_id):
            logger.warning(f"[FAST_RULES] Returning 'allow' — {client_id} is whitelisted")
            return 'allow'
        if condition == 'contact' and is_contact(client_id):
            logger.warning(f"[FAST_RULES] Returning 'allow' — {client_id} is contact")
            return 'allow'

    # 3. Try onboarding (stranger → contact)
    onboard = config.get('onboard', {})

    # Check invite code
    valid_codes = _resolve_codes(onboard.get('invite_code', []))
    request_code = request.get('invite_code')
    if request_code and request_code in valid_codes:
        promote_to_contact(client_id)
        # Promotion is durable — this client is a contact from now on. That is a
        # change to who can reach the agent, so it belongs in the record. The code
        # itself does not.
        logger.warning(
            f"[FAST_RULES] Returning 'allow' — {client_id} onboarded by invite code, "
            f"promoted to contact"
        )
        return 'allow'

    # Check payment
    required_payment = onboard.get('payment')
    request_payment = request.get('payment', 0)
    if required_payment and request_payment >= required_payment:
        promote_to_contact(client_id)
        logger.warning(
            f"[FAST_RULES] Returning 'allow' — {client_id} onboarded by payment, "
            f"promoted to contact"
        )
        return 'allow'

    # 4. Default action for strangers without onboarding
    default = config.get('default', 'deny')
    logger.warning(f"[FAST_RULES] No match, using default={default}")

    if default == 'allow':
        logger.warning(f"[FAST_RULES] Returning 'allow' (default)")
        return 'allow'
    elif default == 'deny':
        logger.warning(f"[FAST_RULES] Returning 'deny' (default)")
        return 'deny'
    elif default == 'ask':
        logger.warning(f"[FAST_RULES] Returning None (needs LLM)")
        return None  # Needs LLM evaluation

    logger.warning(f"[FAST_RULES] Returning 'deny' (fallback)")
    return 'deny'  # Safe fallback

"""
Purpose: Parse bash command chains and validate ALL commands are permitted
LLM-Note:
  Dependencies: imports bashlex (external) | imports from [../skills.py (matches_permission_pattern)] | imported by [tool_approval/approval.py] | tested by [tests/integration/test_bash_chain_permissions.py]
  Data flow: receives bash command string → bashlex.parse() builds AST → extract_from_node() recursively finds command names → returns List[str] of command names | check_bash_chain_permitted() validates each command against permissions dict → returns (bool, reason) tuple
  State/Effects: no persistent state | no side effects | pure validation functions
  Integration: exposes extract_commands_from_bash(command) → List[str], check_bash_chain_permitted(command, permissions) → (bool, reason) | called by approval.py check_approval() for bash tool validation
  Performance: bashlex parsing is fast for typical commands | recursive AST traversal is O(n) where n=nodes in tree
  Errors: bashlex.ParsingError bubbles up if invalid bash syntax | fallback to command.split()[0] if no AST nodes found

Security:
    ⚠️ CRITICAL: Prevents sneaking dangerous commands via chaining
    Example: "ls && rm -rf /" must check BOTH ls AND rm permissions
    If ANY command in chain lacks permission → whole chain rejected

Parsing Strategy:
    Uses bashlex AST to handle:
        - Pipes: "cat file | grep test" → ["cat", "grep"]
        - And chains: "pwd && ls -F" → ["pwd", "ls"]
        - Or chains: "test -f x || echo missing" → ["test", "echo"]
        - Semicolons: "cd /tmp; ls" → ["cd", "ls"]
        - Command substitution: "echo $(date)" → ["echo", "date"]

    Extracts only command names (no args):
        "npm install -g pkg" → ["npm"]
        "git commit -m 'msg'" → ["git"]

Architecture:
    extract_commands_from_bash(command):
        1. bashlex.parse(command) → AST nodes
        2. extract_from_node() recursively visits nodes
        3. node.kind == 'command' → get first word from parts
        4. return list of command names

    check_bash_chain_permitted(command, permissions):
        1. extract_commands_from_bash(command) → ["ls", "pwd"]
        2. for each command: check matches_permission_pattern()
        3. if any unpermitted → return (False, None)
        4. else → return (True, "safe chain (N commands)")
"""


def extract_commands_from_bash(command: str) -> list[str]:
    """Parse bash command chain into individual command names.

    Uses bashlex AST to handle: pipes, &&, ||, ;, command substitution, etc.

    Examples:
        "pwd && ls -F" → ["pwd", "ls"]
        "cat file | grep test" → ["cat", "grep"]

    Args:
        command: Bash command string

    Returns:
        List of command names (just names, no args)
    """
    import bashlex

    parts = bashlex.parse(command)
    commands = []

    def extract_from_node(node):
        """Recursively extract commands from AST node."""
        if node.kind == 'command':
            # Get first word (command name)
            for part in node.parts:
                if part.kind == 'word':
                    commands.append(part.word)
                    break
        elif hasattr(node, 'parts'):
            # Recurse into child nodes
            for part in node.parts:
                extract_from_node(part)

    for tree in parts:
        extract_from_node(tree)

    return commands if commands else [command.split()[0] if command.split() else command]


def check_bash_chain_permitted(command: str, permissions: dict) -> tuple[bool, str, str]:
    """Check if ALL commands in bash chain are permitted.

    For "pwd && ls -F", checks if BOTH pwd AND ls are allowed.
    If ANY command lacks permission, whole chain is rejected.

    Args:
        command: Bash command (may be chain)
        permissions: Session permissions dict

    Returns:
        (permitted, reason, source) tuple - source comes from permission that matched
    """
    from .approval import matches_permission_pattern

    commands = extract_commands_from_bash(command)
    unpermitted = []
    matched_source = 'config'  # Default source

    for cmd_name in commands:
        found = False
        for pattern, perm in permissions.items():
            if perm.get('allowed') and matches_permission_pattern('bash', {'command': cmd_name}, pattern):
                found = True
                matched_source = perm.get('source', 'config')  # Get source from permission
                break
        if not found:
            unpermitted.append(cmd_name)

    if unpermitted:
        return False, None, None

    reason = f"safe chain ({len(commands)} commands)" if len(commands) > 1 else "permitted"
    return True, reason, matched_source

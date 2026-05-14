"""
Purpose: Parse bash command chains and validate ALL commands are permitted
LLM-Note:
  Dependencies: imports bashlex (external) | imports from [../skills.py (matches_permission_pattern)] | imported by [tool_approval/approval.py] | tested by [tests/unit/test_bash_parser.py]
  Data flow: receives bash command string → bashlex.parse() builds AST → extract_from_node() recursively finds subcommands → check_bash_chain_permitted() validates each full subcommand against permissions dict → returns (bool, reason, source) tuple
  State/Effects: no persistent state | no side effects | pure validation functions
  Integration: exposes extract_commands_from_bash(command) → List[str], check_bash_chain_permitted(command, permissions) → (bool, reason, source) | called by approval.py check_approval() for bash tool validation
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

    _extract_subcommands returns (cmd_name, full_subcommand) pairs:
        "pwd && ls -F" → [("pwd", "pwd"), ("ls", "ls -F")]
        "git status"   → [("git", "git status")]

    Full subcommand text is used for 'when' field matching, so:
        Bash(ls *)    matches "ls -F" and bare "ls" (* = zero-or-more args)
        Bash(git *)   matches "git status", "git diff --staged"
        Bash(npm test) matches "npm test" exactly

Architecture:
    extract_commands_from_bash(command):
        1. bashlex.parse(command) → AST nodes
        2. extract_from_node() recursively visits nodes
        3. node.kind == 'command' → get first word from parts
        4. return list of command names (for external callers / tests)

    _extract_subcommands(command):
        1. bashlex.parse(command) → AST nodes
        2. extract_from_node() recursively visits nodes
        3. node.kind == 'command' → join all word parts → (name, full_text)
        4. return list of (cmd_name, full_subcommand) tuples

    check_bash_chain_permitted(command, permissions):
        1. _extract_subcommands(command) → [("ls", "ls -F"), ("pwd", "pwd")]
        2. for each (name, full_cmd): check matches_permission_pattern(full_cmd)
        3. if pattern matched AND permission has 'when' field:
               fnmatch(full_cmd, when.command)
               Example: fnmatch("ls -F", "ls *") → True
               Example: fnmatch("timeout 300 bash ...", "npm test") → False
        4. if any unpermitted → return (False, None, None)
        5. else → return (True, reason, source)
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
        """Recursively extract commands from AST node, including substitutions."""
        if node.kind == 'command':
            first_word_added = False
            for part in node.parts:
                if part.kind == 'word' and not first_word_added:
                    commands.append(part.word)
                    first_word_added = True
                _recurse(part)
        else:
            _recurse(node)

    def _recurse(node):
        for attr in ('parts', 'list'):
            for child in getattr(node, attr, []) or []:
                extract_from_node(child)
        sub = getattr(node, 'command', None)
        if sub is not None:
            extract_from_node(sub)

    for tree in parts:
        extract_from_node(tree)

    return commands if commands else [command.split()[0] if command.split() else command]


def _extract_subcommands(command: str) -> list[tuple[str, str]]:
    """Extract (cmd_name, full_subcommand) pairs from a bash command chain.

    Returns the full subcommand text (including args) alongside the command name,
    so permission checks can match the complete command against patterns like 'ls *'.

    Examples:
        "pwd && ls -F"      → [("pwd", "pwd"), ("ls", "ls -F")]
        "git status"        → [("git", "git status")]
        "cat f | grep foo"  → [("cat", "cat f"), ("grep", "grep foo")]

    Args:
        command: Bash command string (may be a chain)

    Returns:
        List of (cmd_name, full_subcommand) tuples
    """
    import bashlex

    result = []

    def extract_from_node(node):
        if node.kind == 'command':
            words = [p.word for p in node.parts if p.kind == 'word']
            if words:
                result.append((words[0], ' '.join(words)))
            # Also descend into each part to capture $(...) / `...` subcommands.
            for part in node.parts:
                _recurse(part)
        else:
            _recurse(node)

    def _recurse(node):
        for attr in ('parts', 'list'):
            for child in getattr(node, attr, []) or []:
                extract_from_node(child)
        sub = getattr(node, 'command', None)
        if sub is not None:
            extract_from_node(sub)

    for tree in bashlex.parse(command):
        extract_from_node(tree)

    if not result:
        parts = command.split()
        return [(parts[0], command)] if parts else [(command, command)]
    return result


def check_bash_chain_permitted(command: str, permissions: dict) -> tuple[bool, str, str]:
    """Check if ALL commands in bash chain are permitted.

    For "pwd && ls -F", checks if BOTH pwd AND ls -F are allowed.
    If ANY subcommand lacks permission, whole chain is rejected.

    Uses full subcommand text for permission matching, so:
      - 'ls *' permission matches "ls -F" and bare "ls" (* = zero-or-more args)
      - 'git diff *' matches "git diff --staged" but NOT "git status"
      - A 'bash' key with when={command: 'npm test'} matches "npm test" but NOT "timeout 300 bash ..."

    Args:
        command: Bash command (may be chain)
        permissions: Session permissions dict

    Returns:
        (permitted, reason, source) tuple - source comes from permission that matched
    """
    import fnmatch
    from .approval import matches_permission_pattern

    subcommands = _extract_subcommands(command)
    unpermitted = []
    matched_source = 'config'  # Default source

    for cmd_name, full_cmd in subcommands:
        found = False
        for pattern, perm in permissions.items():
            if not perm.get('allowed'):
                continue
            # Check pattern against full subcommand (e.g. "ls -F" vs "Bash(ls *)")
            if not matches_permission_pattern('bash', {'command': full_cmd}, pattern):
                continue
            # If permission has a 'when' field, validate the full subcommand against it.
            # "cmd *" also matches bare "cmd" (no args) — * means zero-or-more args.
            when_config = perm.get('when')
            if when_config:
                cmd_pattern = when_config.get('command', '')
                if cmd_pattern and not fnmatch.fnmatch(full_cmd, cmd_pattern):
                    # Also accept bare command when pattern is "cmd *" (no args case)
                    bare = cmd_pattern[:-2] if cmd_pattern.endswith(' *') else None
                    if not (bare and full_cmd == bare):
                        continue
            found = True
            matched_source = perm.get('source', 'config')
            break
        if not found:
            unpermitted.append(cmd_name)

    if unpermitted:
        return False, None, None

    reason = f"safe chain ({len(subcommands)} commands)" if len(subcommands) > 1 else "permitted"
    return True, reason, matched_source

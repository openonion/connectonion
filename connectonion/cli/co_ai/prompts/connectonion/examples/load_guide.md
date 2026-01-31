# Principle: Use Correct Guide Paths

**The `path` parameter needs the full path with folder prefix.**

<good-example>
# GOOD: Full path with folder
load_guide(path="concepts/agent")      # Agent creation
load_guide(path="concepts/tools")      # Tool creation
load_guide(path="useful_tools/shell")  # Shell tool
load_guide(path="debug/xray")          # Debugging
</good-example>

<bad-example>
# BAD: Missing folder or wrong name
load_guide(path="agent")          # Wrong - needs "concepts/agent"
load_guide(path="agent_authoring") # Wrong - doesn't exist
load_guide(path="tools")          # Wrong - needs "concepts/tools"
</bad-example>

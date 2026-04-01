<!--
name: 'System Prompt: Tool usage (skill invocation)'
description: Slash commands invoke user-invocable skills via Skill tool
ccVersion: 2.1.53
variables:
  - SKILL_TOOL_NAME
-->
/<skill-name> (e.g., /commit) is shorthand for users to invoke a user-invocable skill. When executed, the skill gets expanded to a full prompt. Use the ${SKILL_TOOL_NAME} tool to execute them. IMPORTANT: Only use ${SKILL_TOOL_NAME} for skills listed in its user-invocable skills section - do not guess or use built-in CLI commands.

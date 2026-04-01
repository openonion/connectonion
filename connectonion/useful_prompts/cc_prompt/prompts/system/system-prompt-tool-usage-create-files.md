<!--
name: 'System Prompt: Tool usage (create files)'
description: Prefer Write tool instead of cat heredoc or echo redirection
ccVersion: 2.1.53
variables:
  - WRITE_TOOL_NAME
-->
To create files use ${WRITE_TOOL_NAME} instead of cat with heredoc or echo redirection

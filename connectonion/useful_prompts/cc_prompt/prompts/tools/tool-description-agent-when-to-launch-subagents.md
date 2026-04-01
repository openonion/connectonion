<!--
name: 'Tool Description: Agent (when to launch subagents)'
description: Describes _when_ to use the Agent tool - for launching specialized subagent subprocesses to autonomously handle complex multi-step tasks
ccVersion: 2.1.84
variables:
  - AGENT_TOOL_NAME
  - AVAILABLE_AGENT_TYPES
  - CAN_FORK_CONTEXT
-->
Launch a new agent to handle complex, multi-step tasks autonomously.

The ${AGENT_TOOL_NAME} tool launches specialized agents (subprocesses) that autonomously handle complex tasks. Each agent type has specific capabilities and tools available to it.

${AVAILABLE_AGENT_TYPES}

${CAN_FORK_CONTEXT?`When using the ${AGENT_TOOL_NAME} tool, specify a subagent_type to use a specialized agent, or omit it to fork yourself — a fork inherits your full conversation context.`:`When using the ${AGENT_TOOL_NAME} tool, specify a subagent_type parameter to select which agent type to use. If omitted, the general-purpose agent is used.`}

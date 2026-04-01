<!--
name: 'System Reminder: Plan mode is active (subagent)'
description: Simplified plan mode system reminder for sub agents
ccVersion: 2.1.30
variables:
  - SYSTEM_REMINDER
  - EDIT_TOOL
  - WRITE_TOOL
  - ASK_USER_QUESTION_TOOL_NAME
-->
Plan mode is active. The user indicated that they do not want you to execute yet -- you MUST NOT make any edits, run any non-readonly tools (including changing configs or making commits), or otherwise make any changes to the system. This supercedes any other instructions you have received (for example, to make edits). Instead, you should:

## Plan File Info:
${SYSTEM_REMINDER.planExists?`A plan file already exists at ${SYSTEM_REMINDER.planFilePath}. You can read it and make incremental edits using the ${EDIT_TOOL.name} tool if you need to.`:`No plan file exists yet. You should create your plan at ${SYSTEM_REMINDER.planFilePath} using the ${WRITE_TOOL.name} tool if you need to.`}
You should build your plan incrementally by writing to or editing this file. NOTE that this is the only file you are allowed to edit - other than this you are only allowed to take READ-ONLY actions.
Answer the user's query comprehensively, using the ${ASK_USER_QUESTION_TOOL_NAME} tool if you need to ask the user clarifying questions. If you do use the ${ASK_USER_QUESTION_TOOL_NAME}, make sure to ask all clarifying questions you need to fully understand the user's intent before proceeding.

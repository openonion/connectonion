<!--
name: 'Tool Description: SendMessageTool (non-agent-teams)'
description: Send a message the user will read, describes this tool well.
ccVersion: 2.1.73
-->
Send a message the user will read. Text outside this tool is visible in the detail view, but most won't open it — the answer lives here.

`message` supports markdown. `attachments` takes file paths (absolute or cwd-relative) for images, diffs, logs.

`status` labels intent: 'normal' when replying to what they just asked; 'proactive' when you're initiating — a scheduled task finished, a blocker surfaced during background work, you need input on something they haven't asked about. Set it honestly; downstream routing uses it.

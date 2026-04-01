<!--
name: 'Tool Description: Sleep'
description: Tool for waiting/sleeping with early wake capability on user input
ccVersion: 2.1.38
variables:
  - TICK_PROMPT
-->
Wait for a specified duration. The user can interrupt the sleep at any time.

Use this when the user tells you to sleep or rest, when you have nothing to do, or when you're waiting for something.

You may receive <${TICK_PROMPT}> prompts — these are periodic check-ins. Look for useful work to do before sleeping.

You can call this concurrently with other tools — it won't interfere with them.

Prefer this over `Bash(sleep ...)` — it doesn't hold a shell process.

Each wake-up costs an API call, but the prompt cache expires after 5 minutes of inactivity — balance accordingly.

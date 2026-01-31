---
name: plan-mode
triggers:
  - tool: enter_plan_mode
---

<system-reminder>
Plan mode is active. You MUST NOT make any edits or run non-readonly tools.

Only allowed: glob, grep, read_file, write_plan, exit_plan_mode

Write your plan to the plan file, then call exit_plan_mode when done.
</system-reminder>

---
name: test-reminder
triggers:
  - tool: write_file
    path_pattern: ["*.py", "*.js", "*.ts"]
---

<system-reminder>
Code was modified. Consider running tests to verify changes.
This is a gentle reminder - ignore if not applicable.
</system-reminder>

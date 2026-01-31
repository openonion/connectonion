---
name: security
triggers:
  - tool: read_file
    path_pattern: ["*.env*", "*credentials*", "*secrets*", "*password*", "*token*", "*.pem", "*.key"]
  - tool: read
    path_pattern: ["*.env*", "*credentials*", "*secrets*", "*password*", "*token*", "*.pem", "*.key"]
---

<system-reminder>
This file may contain sensitive information.
- Never expose secrets in output
- Never commit real credentials
</system-reminder>

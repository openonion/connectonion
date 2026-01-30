---
name: security-warning
triggers:
  - tool: read_file
    path_pattern: ["*.env", "*secret*", "*credential*", "*.pem", "*.key"]
  - tool: read
    path_pattern: ["*.env", "*secret*", "*credential*"]
---

<system-reminder>
This file may contain sensitive information.
- Never expose secrets in output
- Never commit real credentials
</system-reminder>

# Sub-Agent Tool Naming Convention

## Problem with Current Design

```yaml
# ❌ BAD - Unclear what these mean
tools:
  - glob
  - grep
  - read_file
```

**Issues:**
- Not clear these come from FileTools
- Hard to remember all method names
- Mixing granular tools (glob, grep) with high-level concepts
- Doesn't scale to other tool types

## Better Design: Tool Groups

### Principle: Name by Capability, Not Implementation

```yaml
# ✅ GOOD - Clear what capability you're adding
tools:
  - file_read      # Read files (glob, grep, read_file)
  - file_write     # Write files (edit, write, multi_edit)
  - browser        # Browser automation
  - web            # HTTP requests
  - shell          # Bash commands
  - email          # Email operations
```

## Complete Tool Group Definitions

```
┌─────────────────────────────────────────────────────────────────┐
│ Tool Group Name → What It Provides                              │
└─────────────────────────────────────────────────────────────────┘

file_read
  ├─ glob(pattern, path)
  ├─ grep(pattern, path, ...)
  └─ read_file(path, offset, limit)

file_write
  ├─ glob(pattern, path)
  ├─ grep(pattern, path, ...)
  ├─ read_file(path, offset, limit)
  ├─ edit(file_path, old_string, new_string)
  ├─ write(file_path, content)
  └─ multi_edit(file_path, edits)

browser
  ├─ navigate(url)
  ├─ click(selector)
  ├─ type(selector, text)
  ├─ screenshot(path)
  ├─ get_page_content()
  └─ wait_for_element(selector)

web
  └─ fetch(url, prompt)

shell
  └─ bash(command, timeout)

email
  ├─ send_email(to, subject, body)
  ├─ get_emails(query, max_results)
  ├─ mark_read(email_id)
  └─ mark_unread(email_id)
```

## Examples: Clear Intent

### Exploration Agent (Read-Only)
```yaml
---
name: explore
description: Fast codebase exploration
model: co/gemini-2.5-flash
max_iterations: 15
tools:
  - file_read      # ← Clear: only reading files
---
```

### Planning Agent (Read-Only)
```yaml
---
name: plan
description: Design implementation plans
model: co/gemini-2.5-pro
max_iterations: 10
tools:
  - file_read      # ← Same: only reading
---
```

### Debug Agent (Read + Execute)
```yaml
---
name: debug
description: Analyze errors and suggest fixes
model: co/gemini-2.5-pro
max_iterations: 20
tools:
  - file_read      # Read files
  - shell          # Run git log, git diff, etc.
---
```

### Implementation Agent (Full Access)
```yaml
---
name: implement
description: Implement features with code changes
model: co/claude-opus-4-5
max_iterations: 30
tools:
  - file_write     # ← Full file access (includes read)
  - shell          # Run tests, build
---
```

### Scraper Agent (Browser + Files)
```yaml
---
name: scraper
description: Web scraping with browser automation
model: co/gemini-2.5-pro
max_iterations: 25
tools:
  - browser        # Navigate, click, screenshot
  - web            # HTTP requests
  - file_write     # Save scraped data
---
```

### Research Agent (Web + Files)
```yaml
---
name: research
description: Research topics and save findings
model: co/gemini-2.5-pro
max_iterations: 20
tools:
  - web            # Fetch documentation
  - file_write     # Save research notes
---
```

### Email Agent
```yaml
---
name: email_assistant
description: Manage emails and drafts
model: co/gemini-2.5-pro
max_iterations: 15
tools:
  - email          # Send, read, organize
  - file_read      # Read templates
---
```

## Implementation

```python
# subagents/factory.py

def _resolve_tools(tool_names: List[str]) -> List:
    """
    Resolve tool group names to actual tool instances.

    Supported tool groups:
    - file_read: Read-only file operations (glob, grep, read_file)
    - file_write: Full file operations (glob, grep, read_file, edit, write)
    - browser: Browser automation (navigate, click, type, screenshot)
    - web: HTTP requests (fetch)
    - shell: Bash commands (bash)
    - email: Email operations (send, get, mark_read, mark_unread)
    """
    from connectonion.useful_tools.file_tools import FileTools
    from connectonion.useful_tools.browser_tools import BrowserAutomation
    from connectonion import bash, WebFetch, Gmail

    TOOL_GROUPS = {
        "file_read": FileTools(permission="read"),
        "file_write": FileTools(permission="write"),
        "browser": BrowserAutomation(),
        "web": WebFetch,
        "shell": bash,
        "email": Gmail(),
    }

    tools = []
    for name in tool_names:
        if name in TOOL_GROUPS:
            tools.append(TOOL_GROUPS[name])
        else:
            # Unknown tool group - log warning
            import sys
            print(f"Warning: Unknown tool group '{name}', skipping", file=sys.stderr)

    return tools
```

## Migration Guide

### Old Format → New Format

```yaml
# OLD (confusing)
tools:
  - glob
  - grep
  - read_file

# NEW (clear)
tools:
  - file_read
```

```yaml
# OLD (unclear if read or write)
tools:
  - glob
  - grep
  - read_file
  - edit
  - write

# NEW (explicit)
tools:
  - file_write    # Includes read + write
```

```yaml
# OLD (what is bash?)
tools:
  - bash

# NEW (clear purpose)
tools:
  - shell
```

## Naming Principles

1. **Use capability names**, not implementation details
   - ✅ `file_read` (capability)
   - ❌ `glob` (implementation)

2. **Be explicit about permissions**
   - ✅ `file_read` vs `file_write` (clear difference)
   - ❌ `files` (ambiguous)

3. **Group related operations**
   - ✅ `browser` (all browser ops together)
   - ❌ `navigate`, `click`, `type` (too granular)

4. **Use underscores for compound names**
   - ✅ `file_read`, `file_write`
   - ❌ `fileread`, `file-read`

5. **Be consistent with framework terminology**
   - ✅ `shell` (matches bash/shell concept)
   - ❌ `bash` (implementation detail)

## Tool Group Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│ Permission Levels                                                │
└─────────────────────────────────────────────────────────────────┘

file_read (safe)
  └─ Read-only operations
     └─ Cannot modify filesystem

file_write (dangerous)
  └─ Full file access
     └─ Can modify/delete files
     └─ Includes all file_read capabilities

shell (very dangerous)
  └─ Execute arbitrary commands
     └─ Full system access
     └─ Can run destructive operations

browser (medium risk)
  └─ Web interaction
     └─ Can navigate to any URL
     └─ Limited to browser context

web (safe)
  └─ HTTP requests only
     └─ No local system access

email (medium risk)
  └─ Email operations
     └─ Can send emails
     └─ Access to email account
```

## Clear Sub-Agent Definitions

```
┌─────────────────────────────────────────────────────────────────┐
│ explore.md (Read-Only Exploration)                              │
└─────────────────────────────────────────────────────────────────┘
---
name: explore
tools:
  - file_read      # ← Only read, safe for exploration
---


┌─────────────────────────────────────────────────────────────────┐
│ plan.md (Planning)                                               │
└─────────────────────────────────────────────────────────────────┘
---
name: plan
tools:
  - file_read      # ← Read code to plan
---


┌─────────────────────────────────────────────────────────────────┐
│ debug.md (Debugging with Shell)                                 │
└─────────────────────────────────────────────────────────────────┘
---
name: debug
tools:
  - file_read      # Read code
  - shell          # Run git commands, tests
---


┌─────────────────────────────────────────────────────────────────┐
│ implement.md (Full Implementation)                               │
└─────────────────────────────────────────────────────────────────┘
---
name: implement
tools:
  - file_write     # Full file access
  - shell          # Run tests, build
---


┌─────────────────────────────────────────────────────────────────┐
│ scraper.md (Web Scraping)                                        │
└─────────────────────────────────────────────────────────────────┘
---
name: scraper
tools:
  - browser        # Navigate, click, screenshot
  - web            # HTTP requests
  - file_write     # Save data
---
```

## Benefits of This Naming

1. **Clear intent** - `file_read` vs `file_write` is obvious
2. **Easy to remember** - Logical groupings
3. **Self-documenting** - No need to look up what tools are included
4. **Scalable** - Easy to add new groups
5. **Safe** - Permissions are explicit
6. **Consistent** - Follows naming conventions

## Summary

**Old (confusing):**
```yaml
tools: [glob, grep, read_file]  # What are these?
```

**New (clear):**
```yaml
tools: [file_read]  # Obvious!
```

This naming makes sub-agent definitions **self-explanatory**.

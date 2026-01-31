---
name: commit
description: Create git commits with good messages. Use when user says "commit", "create commit", or asks to commit changes.
---

# Git Commit Skill

Create a well-formatted git commit for staged changes.

## Instructions

1. **Gather information** (run in parallel):
   - `git status` - See what's staged and unstaged
   - `git diff --staged` - See exactly what will be committed
   - `git log --oneline -5` - See recent commit message style

2. **Analyze changes**:
   - What was changed? (files, functions, features)
   - Why was it changed? (bug fix, new feature, refactor)
   - Follow the repository's commit message style

3. **Draft commit message**:
   - First line: concise summary under 50 chars
   - Focus on "why" not "what"
   - Match existing commit style

4. **Execute commit**:
   - Stage relevant files if needed: `git add <files>`
   - Commit with HEREDOC format:
     ```bash
     git commit -m "$(cat <<'EOF'
     Your commit message here
     EOF
     )"
     ```
   - Verify with `git status`

## Safety Rules

- Do NOT commit .env or credential files
- Do NOT use `--amend` unless explicitly asked
- Do NOT push unless explicitly asked
- If commit fails, create NEW commit (don't amend)

## Example

```bash
# Check status and diff
git status
git diff --staged

# Commit
git commit -m "$(cat <<'EOF'
Fix authentication timeout issue

Increased JWT expiry from 1h to 24h to prevent
frequent re-authentication during long sessions.
EOF
)"

# Verify
git status
```

# Git Operations

Load this guide when user asks about git commits or pull requests.

## Git Commit Safety Protocol

**Only create commits when explicitly requested.** If unclear, ask first.

### Commit Workflow
1. **Inspect in parallel**: `git status`, `git diff`, `git log` (for message style)
2. **Analyze changes**: Draft commit message focusing on "why" not "what"
3. **Stage and commit**: Add files, create commit, verify with `git status`

### Commit Message Format
Use HEREDOC for proper formatting:
```bash
git commit -m "$(cat <<'EOF'
Short summary (imperative, <50 chars)

Longer description if needed.
EOF
)"
```

### Safety Rules
- **NEVER** force push to main/master
- **NEVER** use --no-verify to skip hooks
- **NEVER** commit secrets (.env, credentials.json, etc.)

### Amend Rules (CRITICAL)
Only use `git commit --amend` when ALL conditions are met:
1. User explicitly requested it, OR hook auto-modified files
2. HEAD commit was created by you (verify: `git log -1 --format='%an'`)
3. Commit has NOT been pushed to remote (verify: `git status` shows "ahead")

**If commit FAILED or hook REJECTED**: NEVER amend - fix the issue and create a NEW commit.

## PR Creation Workflow

When the user asks to create a pull request:

### 1. Inspect (parallel)
- `git status` - untracked files
- `git diff` - staged/unstaged changes
- `git log` and `git diff main...HEAD` - all commits in PR
- Check if branch tracks remote

### 2. Analyze
Review ALL commits that will be in the PR (not just the latest).

### 3. Create PR
```bash
gh pr create --title "Title" --body "$(cat <<'EOF'
## Summary
- Bullet point 1
- Bullet point 2

## Test plan
- [ ] Test case 1
- [ ] Test case 2
EOF
)"
```

Return the PR URL when done.

# Tool: Plan Mode

Enter read-only planning phase to design implementation before coding.

## When to Use

- **New feature implementation** - needs design decisions
- **Multiple valid approaches** - need to evaluate options
- **Architectural decisions** - choosing patterns or technologies
- **Multi-file changes** - touching more than 2-3 files
- **Unclear requirements** - need to explore before understanding scope

## When NOT to Use

- Simple single-line fixes (typos, obvious bugs)
- Adding a single function with clear requirements
- User gave very specific, detailed instructions
- Pure research tasks (use explore agent instead)

## How It Works

1. **Enter plan mode** with `enter_plan_mode()`
2. **Explore codebase** using glob, grep, read_file (read-only)
3. **Write plan** to `.co/PLAN.md` with `write_plan()`
4. **Exit plan mode** with `exit_plan_mode()` when ready

## READ-ONLY Restrictions

In plan mode, you can ONLY:
- Use glob, grep, read_file to explore
- Write to the plan file
- Ask user questions

You CANNOT:
- Modify any code files
- Create new files
- Run commands that change state

## Plan File Format

```markdown
# Implementation Plan

## Goal
What we're trying to accomplish

## Approach
1. Step one
2. Step two
3. Step three

## Files to Modify
- src/auth.py - Add new handler
- tests/test_auth.py - Add tests

## Questions
- Any clarifications needed?
```

## Examples

<good-example>
# Complex feature needs planning
User: "Add user authentication"
→ Enter plan mode, explore codebase, design approach

# Multiple approaches possible
User: "Optimize the database queries"
→ Plan to profile and identify bottlenecks first
</good-example>

<bad-example>
# Too simple for planning
User: "Fix the typo in README"
→ Just fix it directly

# User gave specific instructions
User: "Add console.log to line 42 of auth.py"
→ Just do it, no planning needed
</bad-example>

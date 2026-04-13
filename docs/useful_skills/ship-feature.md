# ship-feature

Ship a feature end-to-end: update tests, docs, docs-site, then release to PyPI.

## Install

```bash
co copy ship-feature
# → .co/skills/ship-feature/SKILL.md
```

## Usage

```
/ship-feature
```

The skill walks through 5 steps automatically:

1. **Understand** — reads `git diff` and recent commits to know what changed
2. **Tests** — finds the matching test file, adds/updates tests, runs them
3. **docs/** — updates the relevant markdown doc; creates a new one if none exists
4. **docs-site** — updates the Next.js docs site and pushes its own commit
5. **Release** — bumps version, commits, tags, pushes, builds, uploads to PyPI

## What It Does In Detail

### Step 1: Understand

```bash
git diff --stat   # files changed
git diff          # full diff
git log --oneline -5  # recent context
```

### Step 2: Tests

- Finds the test file matching the changed source (e.g. `src/agent.py` → `tests/unit/test_agent.py`)
- Adds or updates test cases for the new behavior
- Runs tests before proceeding — stops if they fail

### Step 3: docs/

- Finds the relevant doc in `docs/`
- Updates it to reflect new behavior, parameters, examples
- If no doc exists for the changed area, creates one
- Also updates index/README files if something new was added

### Step 4: docs-site

- Checks if `docs-site/` is cloned locally
- If yes: finds the matching page, updates it, commits and pushes separately
- If no: **warns you** — does not silently skip

### Step 5: Release

- Detects current version from `__init__.py`, `pyproject.toml`, or `setup.py`
- Reads `VERSIONING.md` for rollover rules if present
- Updates all files containing the version string
- Commits, tags, and pushes
- Builds with `python -m build` and uploads with `twine`

## Required Permissions

The skill auto-approves these tools (via `tool_approval` plugin):

```yaml
tools:
  - read_file
  - glob
  - write_file
  - edit_file
  - Bash(git *)
  - Bash(python *)
  - Bash(pytest *)
  - Bash(pip *)
  - Bash(twine *)
  - Bash(npm *)
  - Bash(cat *)
  - Bash(grep *)
```

## Setup

```python
from connectonion import Agent
from connectonion.useful_plugins import skills, tool_approval

agent = Agent("dev", tools=[file_tools, shell], plugins=[skills, tool_approval])
```

## Customize

Copy and edit the skill for your project's conventions:

```bash
co copy ship-feature --force
# Edit .co/skills/ship-feature/SKILL.md
```

Common customizations:
- Change version file locations
- Adjust docs paths
- Add project-specific release steps (e.g. Docker build, npm publish)
- Change commit message format

## See Also

- [Built-in Skills](README.md)
- [Skills Feature](../features/skills.md)
- [co copy](../cli/copy.md)

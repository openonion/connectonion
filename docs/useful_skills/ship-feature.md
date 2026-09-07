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

The skill walks through 6 steps automatically:

1. **Understand** — reads `git diff` and recent commits to know what changed
2. **Tests** — finds the matching test file, adds/updates tests, runs them
3. **docs/** — updates the relevant markdown doc; creates a new one if none exists
4. **docs-site** — updates and validates the Next.js docs site without claiming
   that an unpublished artifact is available
5. **Design Journal** — records the problem, alternatives, decision, tradeoffs,
   and evidence for a meaningful release or architecture change
6. **Release** — validates the candidate, opens a release PR, tags its reviewed
   merge commit, waits for Trusted Publishing, then publishes the prepared docs

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
- If yes: finds the matching page, updates it, and runs lint and a production
  build
- Publishes the docs-site commit only after the matching PyPI package and GitHub
  Release are public
- If no: **warns you** — does not silently skip

### Step 5: Design Journal

- Creates or substantially updates a post for a feature-train launch, first
  beta, first RC, stable release, or material architecture/workflow decision
- Keeps the canonical Markdown and rendered page aligned
- Adds metadata, structured data, blog and search entries, sitemap links, and
  AI-readable index links
- Tests desktop and mobile layouts
- Leaves maintenance-only patches in release notes unless they contain a
  reusable design lesson

### Step 6: Release

- Detects current version from `__init__.py`, `pyproject.toml`, or `setup.py`
- Reads `VERSIONING.md` for rollover rules if present
- Updates all files containing the version string
- Builds with `python -m build` and validates only the exact artifacts with
  `python -m twine check`
- Opens a release PR and waits for review and merge
- Tags `<reviewed-merge-commit>` and pushes the immutable version tag
- Waits for `.github/workflows/release.yml` to publish through PyPI Trusted
  Publishing and verify the public artifacts
- Publishes the verified docs-site version state and Design Journal after the
  public package and GitHub Release exist

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
  - Bash(python -m twine check *)
  - Bash(gh pr *)
  - Bash(gh run *)
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

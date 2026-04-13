---
name: ship-feature
description: Ship a feature end-to-end — update tests, docs, docs-site, then release to PyPI. Use when user says "ship", "ship feature", "release", or asks to publish a new version.
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
---

# Ship Feature Skill

Ship a feature completely: tests → docs → docs-site → release.

## Step 1: Understand What Changed

Read the user's message to identify which feature/module was changed.

Run in parallel:
- `git diff --stat` — what files changed
- `git diff` — full diff of changes
- `git log --oneline -5` — recent commit context

## Step 2: Update Tests

Find the relevant test file:
- `glob("tests/**/*.py")` — find all test files
- Match test file to changed source file (e.g. `connectonion/agent.py` → `tests/unit/test_agent.py`)

Update the test file:
- Add or update test cases that cover the new behavior
- Run tests to confirm they pass: `python -m pytest tests/unit/test_<module>.py -v`
- If tests fail, fix them before proceeding

## Step 3: Update docs/

Find relevant doc file:
- `glob("docs/**/*.md")` — find all doc files
- Match doc file to the changed feature area

Update the doc:
- Reflect the new behavior, new parameters, new examples
- Keep it concise — update only the parts that changed
- Do NOT rewrite sections that are still accurate

## Step 4: Update docs-site

The docs-site is a separate Next.js repo at `docs-site/`. It mirrors the `docs/` content but with richer formatting.

```bash
# Check what docs-site pages cover the changed area
glob("docs-site/**/*.{tsx,mdx,md}")
```

Update the corresponding page:
- Match content to what you updated in `docs/`
- Respect the existing component structure (use `CommandBlock`, `CodeBlock`, etc.)
- Keep changes minimal and accurate

Commit the docs-site change separately:
```bash
cd docs-site && git add . && git commit -m "Update docs for <feature>" && git push && cd ..
```

## Step 5: Release

### 5a. Determine new version

Read current version:
```bash
grep "__version__" connectonion/__init__.py
```

Apply versioning rules (from VERSIONING.md):
- PATCH +1 for bug fixes, docs, small improvements
- MINOR bump for new user-facing features
- PATCH rolls to MINOR at .10 (e.g. 0.8.9 → 0.9.0, not 0.8.10)

### 5b. Update version in all files

Update these files with the new version:
1. `connectonion/__init__.py` — `__version__ = "X.Y.Z"`
2. `setup.py` — `version="X.Y.Z"`

### 5c. Commit, tag, push

```bash
git add connectonion/__init__.py setup.py tests/ docs/
git commit -m "Release vX.Y.Z: <feature description>"
git tag vX.Y.Z
git push
git push origin vX.Y.Z
```

### 5d. Build and publish to PyPI

```bash
python setup.py sdist bdist_wheel
twine upload dist/*
```

Confirm upload succeeded by checking the output for "View at: https://pypi.org/project/connectonion/X.Y.Z/"

## Checklist

- [ ] Tests updated and passing
- [ ] `docs/` updated
- [ ] `docs-site/` updated and pushed
- [ ] Version bumped in `__init__.py` and `setup.py`
- [ ] Committed and tagged
- [ ] Pushed to remote
- [ ] Published to PyPI

## Notes

- Skip docs-site step if `docs-site/` directory doesn't exist or has no relevant page
- If the user says "skip release", stop after docs-site
- If the user specifies a version explicitly, use that instead of auto-calculating
- Never force-push or amend published commits

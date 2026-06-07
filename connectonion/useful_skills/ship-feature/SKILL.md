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
- Match test file to changed source file (e.g. `src/agent.py` → `tests/unit/test_agent.py`)

Update the test file:
- Add or update test cases that cover the new behavior
- Run tests to confirm they pass: `python -m pytest tests/unit/test_<module>.py -v`
- If tests fail, fix them before proceeding

## Step 3: Update docs/

**This step is required. Do not skip.**

Find ALL docs that need updating:
```bash
glob("docs/**/*.md")
```

For each changed area:
- If a doc file exists for it — update it with the new behavior, params, examples
- If no doc file exists — create one (look at neighboring files for format)
- Also check index/README files (e.g. `docs/cli/README.md`, `docs/useful_tools/README.md`) — update the table of contents if you added something new

Commit docs/ changes as part of the release commit (not separately).

## Step 4: Update docs-site

**This step is required. Do not skip even if docs-site/ is not present locally.**

docs-site is a separate Next.js git repo. Check if it's cloned:
```bash
ls docs-site/
```

If `docs-site/` exists:
- Find the corresponding page: `glob("docs-site/app/**/*.{tsx,mdx}")`
- Update it to match what you changed in `docs/`
- Respect existing component structure (`CommandBlock`, `CodeBlock`, etc.)
- Commit and push it as a separate commit in that repo:
  ```bash
  cd docs-site && git add . && git commit -m "Update docs for <feature>" && git push && cd ..
  ```

If `docs-site/` does NOT exist locally:
- Tell the user explicitly: "docs-site was not updated — clone it and run `co copy ship-feature --force` to re-run"
- Do NOT silently skip — the user must know this is incomplete

## Step 5: Release

### 5a. Determine new version

Find and read the current version — check these locations in order:
```bash
grep -r "__version__" --include="*.py" -l   # find which file has version
cat pyproject.toml | grep "^version"         # or pyproject.toml
cat setup.py | grep "version="               # or setup.py
```

Apply versioning rules (read VERSIONING.md if it exists, otherwise use semver):
- Default to PATCH +1 for normal shipped work, including small user-facing improvements
- Use MINOR only when the user explicitly asks for it or the change is clearly a larger compatibility-safe feature release
- Use MAJOR only for breaking changes, stable-release milestones explicitly requested by the user, or required rollover rules
- If VERSIONING.md exists, follow its rollover rules exactly, but do not jump to a larger bump unless the rules require it

### 5b. Update version in all files that contain it

Search for every file containing the current version string and update each one:
```bash
grep -r "X.Y.Z" --include="*.py" --include="*.toml" --include="*.cfg" -l
```

Common locations: `__init__.py`, `pyproject.toml`, `setup.py`, `setup.cfg`

### 5c. Commit, tag, push

Stage only what changed — do NOT blindly stage all files:
```bash
git add -p   # or stage specific files that were actually modified
git status   # confirm what's staged before committing
git commit -m "Release vX.Y.Z: <feature description>"
git tag vX.Y.Z
git push
git push origin vX.Y.Z
```

### 5d. Build and publish to PyPI

```bash
python -m build
twine upload dist/*X.Y.Z*
```

Confirm upload succeeded by checking the output for "View at: https://pypi.org/project/<package>/X.Y.Z/"

## Checklist

- [ ] Tests updated and passing
- [ ] `docs/` updated
- [ ] `docs-site/` updated and pushed
- [ ] Version bumped in `__init__.py` and `setup.py`
- [ ] Committed and tagged
- [ ] Pushed to remote
- [ ] Published to PyPI

## Notes

- docs/ and docs-site are both required — never silently skip either
- If docs-site is missing locally, warn the user instead of skipping
- If the user says "skip release", stop after docs-site
- If the user specifies a version explicitly, use that instead of auto-calculating
- Never force-push or amend published commits

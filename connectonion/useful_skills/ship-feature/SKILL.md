---
name: ship-feature
description: Ship a feature end-to-end — update tests, docs, docs-site, then release to PyPI. Use when user says "ship", "ship feature", "release", or asks to publish a new version.
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
- Run its lint and production build. Prepare the docs commit, but do not publish
  version availability before the matching PyPI package and GitHub Release are
  public. Publish the prepared docs in Step 5e.

If `docs-site/` does NOT exist locally:
- Tell the user explicitly: "docs-site was not updated — clone it and run `co copy ship-feature --force` to re-run"
- Do NOT silently skip — the user must know this is incomplete

### Step 4b: Record the design and release story

For a feature-train launch, first beta, first RC, stable release, or material
architecture/workflow decision, create or substantially update a Design Journal
post in the docs site. Maintenance-only patches need release notes unless they
contain a reusable lesson.

The post must explain:
- the problem and user impact;
- alternatives considered;
- the decision and tradeoffs;
- evidence and current limitations;
- what would make the team revisit the decision.

Keep one canonical Markdown source and a rendered blog page. Add the post to the
blog index, internal navigation, site search, dynamic and static sitemaps,
`llms.txt`, and relevant AI-readable indexes. Give it unique metadata, a
canonical URL, social metadata, and `TechArticle` or `BlogPosting` structured
data. Test desktop and mobile layouts. Draft with provisional wording; do not
claim that an artifact is published until that is verified.

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

### 5c. Validate and prepare the release commit

Remove old build output, build the candidate once locally, and validate only the
two exact versioned artifacts. This is validation, not publication.

```bash
rm -rf dist/
python -m build
python -m twine check dist/<package>-X.Y.Z.tar.gz dist/<package>-X.Y.Z-py3-none-any.whl
```

Then stage only what changed — do NOT blindly stage all files:
```bash
git add -p   # or stage specific files that were actually modified
git status   # confirm what's staged before committing
git commit -m "Release vX.Y.Z: <feature description>"
git push -u origin <release-branch>
gh pr create --title "Release vX.Y.Z: <feature description>"
```

Do not tag an unreviewed branch. After the release PR is reviewed and merged,
fetch the target branch, resolve the exact merge commit, and create one annotated,
immutable `vX.Y.Z` tag that points to that commit.

```bash
git fetch origin
git tag -a vX.Y.Z <reviewed-merge-commit> -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

### 5d. Let the reviewed tag workflow publish

Pushing the tag starts `.github/workflows/release.yml`. Wait for that exact run
to rerun the matrix, build once, publish through PyPI Trusted Publishing, verify
the public artifacts, and create the GitHub Release. A manual dispatch may retry
the existing tag; it must never select an arbitrary branch. Never publish package
bytes from the workstation or race the workflow with a second registry writer.

```bash
gh run list --workflow release.yml --limit 1
gh run watch <run-id> --exit-status
```

Confirm that the exact PyPI version and GitHub Release are public and that a
preview is marked Prerelease rather than Latest before publishing documentation.

### 5e. Publish documentation and the Design Journal

After the exact PyPI package and GitHub Release are public, commit and push only
the reviewed docs-site files. Verify the deployed stable/preview labels,
installation commands, canonical blog URL, structured data, sitemap entry,
internal links, AI-readable indexes, and mobile rendering. If the docs site
cannot be published, report the release handoff as incomplete rather than
silently skipping it.

## Checklist

- [ ] Tests updated and passing
- [ ] `docs/` updated
- [ ] `docs-site/` and any required Design Journal post updated; lint and build pass
- [ ] Version bumped in every file that held it, and they agree
      (in connectonion: `connectonion/_version.py` and `pyproject.toml`;
       `__init__.py` only re-exports it and there is no `setup.py`)
- [ ] Release PR reviewed and merged
- [ ] Immutable tag points to the reviewed merge commit
- [ ] Exact-tag `release.yml` run passed
- [ ] Exact PyPI package and GitHub Release verified public
- [ ] Docs-site version state and Design Journal published after public artifacts were verified

## Notes

- docs/ and docs-site are both required — never silently skip either
- If docs-site is missing locally, warn the user instead of skipping
- If the user says "skip release", stop after docs-site
- If the user specifies a version explicitly, use that instead of auto-calculating
- Never force-push or amend published commits
- Never publish package artifacts directly from a workstation

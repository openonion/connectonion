# Outlook Attachment Download Collision Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (recommended inline) to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make Outlook attachment downloads preserve existing files and duplicate attachment payloads by choosing unique suffixed filenames.

**Architecture:** Keep filename sanitisation in `Outlook.download_attachments()`, add a small local collision-selection loop before each write, and return the actual written paths. Extend the existing unit tests and add the required narrative blog entry.

**Tech Stack:** Python 3.10+, pytest, pathlib, existing Outlook/Graph test fixtures.

## Global Constraints

- Modify only the Outlook downloader, its focused tests, the required design journal, and this implementation documentation.
- Preserve existing path sanitisation and directory-boundary behavior.
- Do not add dependencies or change the public method signature.
- Follow conventional commits and disclose AI assistance in the PR.

---

### Task 1: Add regression coverage for filename collisions

**Files:**
- Modify: `tests/unit/test_outlook.py` near the existing `download_attachments()` tests

**Interfaces:**
- Consumes: existing Outlook fixtures and mocked Graph attachment responses.
- Produces: tests that fail against the current overwrite behavior and specify exact returned paths and payload preservation.

- [ ] **Step 1: Write the failing test**

Add a test with two file attachments named `cover.jpg`, assert `download_attachments()` returns `cover.jpg` and `cover-1.jpg`, and assert both file contents remain distinct. Add a second test with a pre-existing `cover.jpg`, assert the original bytes remain and the download is written to `cover-1.jpg`.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `python -m pytest tests/unit/test_outlook.py -k "duplicate or existing" -q`

Expected: failures showing the second write overwrites `cover.jpg` and the returned path list contains duplicate/original paths instead of a suffixed path.

- [ ] **Step 3: Commit the red tests**

```bash
git add tests/unit/test_outlook.py
git commit -m "test: cover outlook attachment name collisions"
```

### Task 2: Implement unique attachment paths

**Files:**
- Modify: `connectonion/useful_tools/outlook.py:488-510`

**Interfaces:**
- Consumes: sanitised attachment names and the existing `Path` destination.
- Produces: the same `list[str]` return type containing actual unique paths.

- [ ] **Step 1: Write minimal collision handling**

After sanitisation, choose the original path when unused. If it exists, split the name with `Path.stem` and `Path.suffix`, then increment an integer suffix until the candidate does not exist. Write bytes only to the selected candidate and append that candidate to `saved`.

- [ ] **Step 2: Run the focused tests to verify they pass**

Run: `python -m pytest tests/unit/test_outlook.py -k "duplicate or existing" -q`

Expected: all selected collision tests pass.

- [ ] **Step 3: Run the full Outlook unit test file**

Run: `python -m pytest tests/unit/test_outlook.py -q`

Expected: exit code 0 with no failures.

- [ ] **Step 4: Commit the implementation**

```bash
git add connectonion/useful_tools/outlook.py
git commit -m "fix: prevent outlook attachment overwrites"
```

### Task 3: Add the required design journal and verify the branch

**Files:**
- Create: `docs/blog/2026-08-15-outlook-attachment-collisions.md`

**Interfaces:**
- Consumes: Issue #923 behavior and test evidence.
- Produces: a concise narrative explaining the data-loss scenario, the collision fix, and what was measured.

- [ ] **Step 1: Write the blog entry**

Describe a user downloading two attachments with the same sender-provided name, explain why the previous direct write was lossy, describe preserving the first path and suffixing later paths, and mention the regression tests.

- [ ] **Step 2: Run focused and full non-real-API verification**

Run: `python -m pytest tests/unit/test_outlook.py -q`

Run: `python -m pytest -m "not real_api" -q`

Expected: both commands exit 0.

- [ ] **Step 3: Inspect the final diff and commit the blog entry**

Run: `git diff HEAD~3..HEAD --check; git diff HEAD~3..HEAD --stat; git status --short`

Expected: only the planned files are changed, no whitespace errors, and the worktree is clean after commit.

```bash
git add docs/blog/2026-08-15-outlook-attachment-collisions.md
git commit -m "docs: explain safe outlook attachment downloads"
```

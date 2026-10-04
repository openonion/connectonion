# Context over control in REM investigation

Status: implemented. Preview 1.9.0a28 includes upfront tool authorization; the Git citation and reader trail follow-up in this working tree awaits a later release.

Investigation previously used `--sandbox workspace-write` for Codex and `--permission-mode acceptEdits` for Claude Code. The prompt limited searches to supplied evidence files and snapshots, so the model could not directly inspect the local repository or mail archive.

The Python runner gathered messages and repository snapshots before the model turn. Large collections were laid out in evidence files, while the quick pass sampled and truncated material.

## Problem

Enforcing control over context produced three critical failures:

1. **Incomplete context**: The quick pass kept at most 24 items and 2,500 characters from each one. Mail and session collection also sampled recent items.
2. **Indirect repository evidence**: Project turns received snapshots but were told not to inspect live repository paths, limiting verification of current files and Git history.
3. **Weak run provenance**: Daily run records summarized pages and usage without the source IDs, paths and timestamps supplied to each page turn.

## Decision: Context over control

We restore the foundational principle: **give the agent sufficient context and tools; authorize upfront, ensure traceability afterwards.**

### 1. Tools authorized upfront

For investigation stages (`init` and `investigate`):
- Codex runs with `--sandbox danger-full-access`.
- Claude Code runs with `--permission-mode bypassPermissions`.
- Prompts instruct the model to actively search the supplied evidence index, local mail archives, and project repositories using CLI tools (`rg`, `git log`, `git show`, file inspection).

### 2. Live repository paths over fragmented dumps

Project investigations supply live local repository paths alongside snapshots. A tool-capable model can inspect `git log`, `README.md`, `pyproject.toml`, `package.json` and relevant source files, then cite verifiable paths and revisions.

### 3. Traceability afterwards

Each completed investigation preserves an execution audit trail:
- Task results and scheduled run records retain supplied source IDs, local file paths, timestamps and the model's full inspection report. The report names files actually inspected; the evidence list records what was supplied, not proof it was read.
- Markdown dossiers retain numbered citations (`[1]`, `[2]`) pointing to source IDs or identifiable local files, with dates or revisions. Repository path lists remain reading leads and cannot serve as claim evidence.
- Directly cited working files are retained by content hash; historical Git files are retained by exact commit and path. The reader opens these retained excerpts even if the working tree later changes.

### 4. Security note (deferred)

Incoming email remains untrusted text in unattended runs. Containment and hardening are deferred to a future runtime milestone. Utility, tool authorization and complete context come first.

## Consequences

- **Investigation depth**: Tool-capable models can check Git history and package manifests before making a project claim.
- **Coverage**: The quick writer receives all gathered originals. Large packets use an evidence index rather than dropping items.
- **Limit**: Models measured as summary tier still receive inline material or digests and cannot inspect live files with tools. No latency or token savings are claimed without a trial run.

## Review after this update

Role: independent AI reviewer acting as a technology founder with marketing and UI experience. Coverage: headless Chrome at 1440px and 390px of a local reader fixture's Today view, expanded manual and scheduled run trails, accepted Git Demo project claim, inline citation and archived source dialog, plus Harbour's mobile architecture diagram. The fixture's Git repository and accepted citation were created through the same project promotion path tested below. Playwright confirmed the jump to the trail, modal excerpt, diagram panning and no page-level horizontal overflow. This is fixture coverage, not a live harness run or an all-page pass; keyboard, dark theme and other page types remain uninspected.

| Priority | Finding and user impact | Evidence | Improvement and recheck |
| --- | --- | --- | --- |
| High | A project path list could be cited as proof of a file claim. | Citation validation treated every supplied source ID as material. | Reject `investigation:project-repositories` as a citable original; the new validation test checks this. |
| High | Manual and scheduled run logs omitted the page's source trail. | Their record writers previously copied usage and outcomes only. | Save the evidence metadata and full inspection report in both run paths; the new tests read the actual JSON files. |
| Medium | A new live citation could pass as a path without a retained excerpt. | A working file may change or disappear after investigation. | Require `file:/path@sha256` or an exact `git:/repo:commit:path`, retain the cited text, and reopen it after the working file changes in unit tests. |
| Medium | The recent runs table hid the new source trail. | Reader markup listed time, outcome and usage only. | Add a collapsed run detail showing supplied evidence separately from the model's inspection report; recheck both manual and scheduled records. |
| Medium | A reader could miss the trail several screens below the latest-pass card. | Desktop and 390px screenshots placed the trail under Maintenance. | Add a one-action jump on the latest-pass card; recheck that mobile opens and scrolls to the first run detail. |
| Medium | Context items appeared to be original sources in the trail. | Investigation evidence includes `investigation:page`, coverage and repository paths. | Label the count as supplied items and explain that the list includes context and does not prove inspection. |
| Medium | The mobile Git dialog led with a long raw source ID and repeated its full hash. | The excerpt was pushed below the useful heading. | Show filename and short revision first, keep the full ID in a disclosure, and recheck the excerpt at 390px. |
| Medium | The mobile diagram's horizontal scroll was unclear. | The architecture diagram extended past its visible panel. | Add a swipe hint; recheck the diagram pans to the last step at 390px. |
| Medium | Release copy could imply supplied evidence proved inspection. | It called run JSON a complete evidence inventory. | Describe supplied evidence and the model's report separately. |

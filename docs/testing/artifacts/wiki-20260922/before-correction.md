# Atlas

## What it is
- A local command-line word counter for writers checking draft length. It accepts a UTF-8 text file and prints the word count without changing files. [1]

## Overview
- Run `python3 count.py draft.txt` from the project directory; the script reads the named file, splits its text on whitespace, and prints the number of resulting words. [1][2]

## Try it
- From `~/projects/.worktree/wiki-investigate-0922-fixture/atlas`, run `python3 count.py draft.txt`; the observed result for the sample `draft.txt` was `3`. [1][3][4]

## Where it stands
- The local implementation and sample artifact are present and the documented command was verified on 2026-09-22. No hosted website or hosted service is implemented. [1][4]

## Latest issues
- No issue report or defect is recorded in the supplied material. The hosted-version idea remains unimplemented rather than being treated as a completed delivery. [1][5]

## People and ownership
- No owner, contributor, or maintainer is named in the supplied project files or session record. [5][6]

## Getting started
- Use Python 3 from the project directory and pass a text-file path to `count.py`, for example `python3 count.py draft.txt`. [1]

## Why it exists
- It is intended for writers who want to check draft length locally. [1]

## Key decisions
- Keep the tool local and command-line based; there is no account, sharing feature, deployed website, or hosted service in the current implementation. [1]

## How it is built
- The only implementation is `count.py`. It uses Python's standard `pathlib` and `sys` modules, reads the argument as text, splits on whitespace, and prints the length. [1][2]

## Architecture map
- `draft.txt` → `count.py` → word-count text on stdout; `output.txt` records the sample result `3`. The README says the command changes no files. [1][2][3]

## Paths
- ~/projects/.worktree/wiki-investigate-0922-fixture/atlas
- Sessions: 1
- First seen: 2026-09-22
- Last seen: 2026-09-22

## Open threads
- Owner/user: decide whether to pursue a hosted website later; the request was recorded on 2026-09-22, with no deadline or implementation evidence. [5]

## Uncertainties
- No owner or maintainer was identified after reviewing the supplied project files and the one related coding-session message. [5][6]
- No issues, roadmap, deployment target, hosting choice, or deadline were supplied. [1][5]
- The supplied coverage contains one `codex` message related to the project and one recorded session; no mail, issue tracker, pull request, or additional source material was supplied or searched. [6]
- The hosted website request is intent only; no repository, deployment artifact, URL, or execution evidence supports completion. [1][5]
- The existing page was a mapped skeleton with all project fields unknown; its prior statements are retained only as prior context, not independent corroboration. [7]

## Sources
- [1] `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/README.md`, inspected 2026-09-22, high confidence for the project's documented purpose, behavior, and implementation/deployment status.
- [2] `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/count.py`, inspected 2026-09-22, high confidence for the implementation details.
- [3] `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/draft.txt` and `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/output.txt`, inspected 2026-09-22, high confidence for the sample input and recorded output.
- [4] Command `python3 count.py draft.txt` run in `~/projects/.worktree/wiki-investigate-0922-fixture/atlas` on 2026-09-22; output `3`, high confidence for that observed run only.
- [5] `codex:atlas-synthetic:175` / `~/projects/.worktree/wiki-investigate-0922-fixture/sessions/rollout-atlas.jsonl`, observed 2026-09-22, high confidence for the recorded user request and its status as a request rather than completed deployment.
- [6] `investigation:coverage` in supplied material, observed 2026-09-22, medium confidence for the collector's stated coverage: one `codex` message in the window and one related subject match.
- [7] Existing page `projects/atlas-58b543867f.md` (`investigation:page`), supplied and inspected 2026-09-22, prior/derived context only; not independent verification.

Investigation: mapped 2026-09-22 · investigated 2026-09-22 (codex)
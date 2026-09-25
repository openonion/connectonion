# atlas

## What it is
- Atlas is a local command-line word counter for writers checking the length of a draft. [1]

## Overview
```text
Writer supplies a UTF-8 draft
          |
          v
python3 count.py draft.txt
          |
          v
Word count is printed to stdout
```
The verified sample draft produces the visible result `3`. [1][3][6]

## Try it
- From `~/projects/.worktree/wiki-investigate-0922-fixture/atlas`, run `python3 count.py draft.txt`; the supplied sample prints `3`. [1][2][3][6]
- No hosted demo or deployed website was found; the hosted version is only a future request. [1][5]

## Where it stands
- As observed 2026-09-22, the local command-line implementation is present and the sample command has been run successfully, returning `3`. [1][2][3][6]
- A hosted website is not implemented. The request to consider one later is intent, not evidence of deployment or delivery. [1][5]

## Latest issues
- No concrete bug, regression, or blocker was recorded in the supplied session or project files as of 2026-09-22. This is a checked-scope observation, not evidence of a complete test suite. [1][5]

## People and ownership
- Product and engineering owner: Unknown — no named owner was recorded in the supplied material. [5]
- The requester is the source of the request to consider a hosted version; this does not establish implementation ownership. [5]

## Getting started
- Work from `~/projects/.worktree/wiki-investigate-0922-fixture/atlas`.
- For an engineer or writer: provide a UTF-8 text file and run `python3 count.py <file>`; the program prints the word count and does not change files. [1][2]
- Sample: `python3 count.py draft.txt` → `3`. [3][6]

## Why it exists
- Atlas helps writers check draft length locally through a small command-line tool. [1]
- The supplied material does not define a target hosted audience, sharing workflow, account model, or success criteria for a future website. [1][5]

## Key decisions
- No explicit dated product or technical decision record was found in the supplied material. [1][5]
- The current local-only scope and absence of a hosted service are verified implementation/scope facts, not a recorded decision to keep Atlas local permanently. [1][2]
- The request to consider publishing a hosted website later remains an uncommitted future direction. [5]

## How it is built
- `count.py` reads the path supplied as its first command-line argument with `Path(...).read_text()`, splits the text on whitespace, and prints the number of resulting words. [2]
- The README states that the input is UTF-8 text, output is the count on stdout, and no files are changed. [1]

## Architecture map
Verified current implementation, observed 2026-09-22: [1][2]

```text
draft.txt (UTF-8 text file)
        |
        | sys.argv[1] / read_text()
        v
count.py (split whitespace, len)
        |
        | print()
        v
stdout: word count
```

## Paths
- `~/projects/.worktree/wiki-investigate-0922-fixture/atlas` — observed project directory containing the implementation and sample files. [1][7]
- `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/count.py` — current implementation. [2]
- `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/README.md` — usage and scope notes. [1]
- `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/draft.txt` — sample input containing `one two three`. [3]
- `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/output.txt` — recorded sample output `3`; this file is evidence of a recorded artifact, not by itself proof of execution. [4]
- Sessions: 1
- First seen: 2026-09-22
- Last seen: 2026-09-22

## Open threads
- Requester: decide whether to pursue a hosted Atlas website and define its scope, audience, and success criteria; open since 2026-09-22. No owner beyond the requester or target date is recorded. [5]
- Engineering/product owner: if the hosted direction is approved, determine the deployment, sharing, and account requirements; currently unassigned and not evidenced as started. [1][5]

## Uncertainties
- No hosted URL, deployment record, account system, sharing feature, or hosted implementation was found; the README explicitly says the hosted idea is not implemented. [1]
- No explicit product/technical decision record, named owner, target date, issue tracker entry, or hosted success criteria was found in the supplied material. [1][5]
- No automated test suite or broader validation record was supplied. The only execution evidence inspected was `python3 count.py draft.txt` in the project directory, which exited successfully with `3`. [6]
- Coverage: the supplied collector searched handles `~/projects/.worktree/wiki-investigate-0922-fixture/atlas` and `Atlas`; it contained 1 Codex message in the window, with 1 related to the subject. No additional mail, calendar, issue, PR, or external-web material was supplied or searched. [8]

## Sources
- [1] `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/README.md`, inspected 2026-09-22; confidence: high for stated usage and scope.
- [2] `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/count.py`, inspected 2026-09-22; confidence: high for current implementation behavior.
- [3] `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/draft.txt`, inspected 2026-09-22; confidence: high for supplied sample input.
- [4] `~/projects/.worktree/wiki-investigate-0922-fixture/atlas/output.txt`, inspected 2026-09-22; confidence: high for the recorded output artifact, not independent execution proof.
- [5] `~/projects/.worktree/wiki-investigate-0922-fixture/sessions/rollout-atlas.jsonl`, inspected 2026-09-22; confidence: high for the recorded user request and intent, not implementation proof.
- [6] Command `python3 count.py draft.txt`, run in `~/projects/.worktree/wiki-investigate-0922-fixture/atlas` on 2026-09-22; result: exit 0, stdout `3`; confidence: high for this execution only.
- [7] Existing page `projects/atlas-58b543867f.md`, supplied as prior/derived context and inspected 2026-09-22; confidence: high for preserved mapped metadata only.
- [8] `investigation:coverage`, supplied coverage record observed 2026-09-22; confidence: high for the collector's stated search coverage.

Investigation: mapped 2026-09-22 · not investigated yet

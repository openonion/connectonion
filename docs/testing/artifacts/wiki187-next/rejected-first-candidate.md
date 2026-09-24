# atlas

## What it is
- Atlas is a local command-line word counter for writers checking the length of a UTF-8 draft. [S2]

## Overview
```text
Writer
  -> supplies a draft.txt file
  -> runs count.py with Python 3
  -> Atlas counts whitespace-separated words
  -> prints the count to standard output
```

## Try it
- From `/tmp/wiki187-e2e/atlas`, run `python3 count.py draft.txt`; with the supplied `draft.txt` containing `one two three`, the visible result is `3`. [S2]
- No access, account, or hosted service is required; this is a local prototype. [S2]

## Where it stands
- Observed 2026-09-19: the local CLI is implemented and verified against the sample draft; `count.py` returns `3`, matching `output.txt`. [S2]
- The current phase is a working local prototype. A hosted website is a requested future direction, not a completed deployment. [S1][S2]

## Latest issues
- No bug, regression, or blocker report was found in the single related coding-session message or the inspected project files as of 2026-09-19. [S1][S2]
- The requested hosted version is not implemented; its status is recorded as an open thread below, not as a defect diagnosis. [S1][S2]

## People and ownership
- No named product, design, engineering, or operations owner was identified in the supplied evidence. [S1][S2]

## Getting started
- Prerequisite: Python 3 and a UTF-8 text file. From `/tmp/wiki187-e2e/atlas`, run `python3 count.py <draft-file>`; the command prints the word count on stdout and does not change files. [S2]
- The engineer-facing implementation is [`count.py`](/tmp/wiki187-e2e/atlas/count.py); the sample input is [`draft.txt`](/tmp/wiki187-e2e/atlas/draft.txt), and the recorded sample output is [`output.txt`](/tmp/wiki187-e2e/atlas/output.txt). [S2]

## Why it exists
- Atlas helps writers check draft length locally with a small command-line tool. [S2]
- The user also requested that a hosted website be considered later; the evidence does not show that hosted service as part of the current scope or implementation. [S1][S2]

## Key decisions
- The implemented version is local and command-line based, using `count.py` and standard output rather than a hosted service or account system. [S2]
- The tool reads the input file and prints the count without changing files. [S2]
- A hosted version is a future consideration/request, not an executed decision or delivered feature. [S1][S2]

## How it is built
- `count.py` reads the path supplied as its first command-line argument, splits the file contents on whitespace, and prints the number of resulting words. [S2]
- The repository contains no other implementation module, deployed website, hosted service, account system, or sharing feature according to its README and file inventory. [S2]

## Architecture map
```text
draft.txt (UTF-8)
      |
      | sys.argv[1]
      v
count.py -- Path.read_text().split() --> word-count integer
                                              |
                                              v
                                      stdout / output.txt artifact
```
Implemented structure observed in `/tmp/wiki187-e2e/atlas` on 2026-09-19. [S2]

## Paths
- `/tmp/wiki187-e2e/atlas` — observed project directory. [S1][S2]
- `/tmp/wiki187-e2e/atlas/README.md` — project description and implementation boundary. [S2]
- `/tmp/wiki187-e2e/atlas/count.py` — CLI implementation. [S2]
- `/tmp/wiki187-e2e/atlas/draft.txt` — sample input (`one two three`). [S2]
- `/tmp/wiki187-e2e/atlas/output.txt` — sample output (`3`). [S2]
- Sessions: 1; First seen: 2026-09-19; Last seen: 2026-09-19. [S1]

## Open threads
- User to decide whether to pursue a hosted Atlas website, requested 2026-09-19; no deployment, repository artifact, or successful hosted run is evidenced yet. [S1][S2]
- No owner, requirements, hosting target, or delivery date for that future website were identified. [S1][S2]

## Uncertainties
- The only supplied source coverage is one coding-session message, with one message related to the subject, plus the inspected project directory and its four files; no mail, calendar, issue tracker, pull request, or web evidence was supplied or searched in this pass. [S1][S2]
- No named owner or acceptance criteria for the possible hosted website were found. [S1][S2]
- The handles `/tmp/wiki187-e2e/atlas` and `Atlas` both matched the supplied project evidence; no additional handles were provided or discovered. [S1][S2]

## Sources
- [S1] `codex:atlas-synthetic:126` / `file:///tmp/wiki187-e2e/sessions/rollout-atlas.jsonl` — coding-session request and coverage metadata, observed 2026-09-19.
- [S2] Inspected `/tmp/wiki187-e2e/atlas/README.md`, `count.py`, `draft.txt`, and `output.txt`; direct verification `python3 count.py draft.txt` returned `3`, observed 2026-09-19.

Investigation: mapped 2026-09-19 · not investigated yet

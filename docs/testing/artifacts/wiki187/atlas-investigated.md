# Atlas

## What it is

Atlas is a local command-line word counter for writers checking draft length. [2]

## Overview

```text
Writer supplies a UTF-8 draft file
            |
            v
python3 count.py draft.txt
            |
            v
Atlas counts whitespace-separated words
            |
            v
Word count is printed to stdout
```

The current flow is local and does not deploy, share, or modify the input file. [2][3]

## Try it

1. From `/tmp/wiki187-e2e/atlas`, run `python3 count.py draft.txt`. [2]
2. Read the word count printed on stdout; the supplied sample returns `3`. [2][4][6]

No hosted demo or account access is available in the inspected material. [2]

## Where it stands

As observed on 2026-09-19, the local prototype is implemented as `count.py` and its sample command has been verified to return `3`. [2][3][4][6] A hosted website was requested as a possible later direction, but there is no evidence of deployment or implementation. [1][2]

## Latest issues

No concrete bug, regression, or blocker is recorded in the inspected README, source, sample input, or sample output as of 2026-09-19. [2][3][4][5]

## People and ownership

The coding-session user is the requester for Atlas; no separate product, design, engineering, or operations owner is recorded. [1]

## Getting started

The observed project directory is `/tmp/wiki187-e2e/atlas`. [1][2]

For a writer or operator, place a UTF-8 text file in that directory and run `python3 count.py <file>`. [2] The command prints the count to stdout and does not change files. [2][3]

## Why it exists

Atlas exists to help writers check the length of a draft locally. [1][2] Its observed scope is deliberately limited to a command-line counter; hosted access, accounts, and sharing are not implemented. [2]

## Key decisions

- The implemented interface is a local Python command rather than a hosted service. [2][3]
- Input is read from a UTF-8 text file, and the result is emitted on stdout without changing files. [2][3]
- The current counting rule is Python whitespace splitting via `str.split()`. [3]

## How it is built

`count.py` accepts the input path from the first command-line argument, reads the file as text through `pathlib.Path`, splits the contents on whitespace, counts the resulting items, and prints that integer. [3]

## Architecture map

```text
draft.txt (UTF-8)
      |
      | command-line path
      v
count.py -> Path(path).read_text().split()
      |
      | len(...)
      v
stdout: integer word count
```

This is the verified implemented flow in the inspected project directory; no hosted or multi-component architecture was found. [2][3]

## Paths

- `/tmp/wiki187-e2e/atlas` — observed project directory. [1]
- `/tmp/wiki187-e2e/atlas/README.md` — usage, scope, and status notes. [2]
- `/tmp/wiki187-e2e/atlas/count.py` — sole implementation. [2][3]
- `/tmp/wiki187-e2e/atlas/draft.txt` — sample input containing `one two three`. [4]
- `/tmp/wiki187-e2e/atlas/output.txt` — recorded sample output `3`. [5]

## Open threads

- **Hosted website** — the user to decide and, if still wanted, scope and implement a hosted version later; requested 2026-09-19. No deployment or hosted artifact is evidenced. [1][2]

## Uncertainties

- No issue tracker, test suite, deployment configuration, hosting target, or acceptance criteria were supplied or found in the inspected project directory; check those before planning a hosted version. [1][2][3][4]
- The repository evidence confirms the sample path and output, but does not establish broader handling of malformed arguments, missing files, encodings other than UTF-8, or large inputs. [2][3][4]
- Coverage: read the supplied page and coverage record, the one coding-session message, and all four files in `/tmp/wiki187-e2e/atlas`; the recorded search found 1 code message, 1 related to Atlas, for the available 2026-09-19 window. [1][7]

## Sources

- [1] `codex:atlas-synthetic:126` — coding-session user message; observed 2026-09-19; high confidence for requested intent and recorded project path.
- [2] `repo:/tmp/wiki187-e2e/atlas/README.md` — inspected README; observed 2026-09-19; high confidence for documented behavior, scope, and status.
- [3] `repo:/tmp/wiki187-e2e/atlas/count.py` — inspected implementation; observed 2026-09-19; high confidence for the counting flow.
- [4] `repo:/tmp/wiki187-e2e/atlas/draft.txt` — inspected sample input; observed 2026-09-19; high confidence for the sample contents.
- [5] `repo:/tmp/wiki187-e2e/atlas/output.txt` — inspected sample output artifact; observed 2026-09-19; high confidence for the recorded output `3`.
- [6] `execution:/tmp/wiki187-e2e/atlas python3 count.py draft.txt` — rerun locally; observed 2026-09-19; high confidence for the returned sample output `3`.
- [7] `investigation:coverage` — supplied coverage record; observed 2026-09-19; high confidence for the recorded search scope and count.

Investigation: mapped 2026-09-19 · investigated 2026-09-19 (codex)
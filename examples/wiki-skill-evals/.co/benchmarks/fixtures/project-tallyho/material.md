# Evidence

Each item below starts with its source id. The page as it stands is source `investigation:page`, and the note that follows is source `notebook:owner`.

The owner of this notebook is Alex Rivera, founder of Rivera Labs. Session items are the owner's coding-agent sessions run in this folder.

### codex:project-tallyho:1 · 2026-08-01 — user
Build a tiny CLI called tallyho that counts words per Markdown heading, so writers can see which sections are too long.

### codex:project-tallyho:2 · 2026-08-01 — assistant
Created tallyho/cli.py and README.md. Usage: `python -m tallyho notes.md`. Ran it on examples/essay.md:
```
$ python -m tallyho examples/essay.md
Intro        212
Method       1,480
Results      640
```

### codex:project-tallyho:3 · 2026-08-02 — assistant
Added tests/test_counts.py. `pytest -q` → 9 passed.

### codex:project-tallyho:4 · 2026-09-18 — user
Decision: keep it dependency-free (no click), because writers install it with plain pip on locked-down laptops.

### codex:project-tallyho:5 · 2026-09-18 — assistant
git log: 14 commits, latest 3f2a9c1 'count code blocks separately'. `pytest -q` → 11 passed.

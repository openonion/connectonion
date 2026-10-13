# The venv that stole the skills

*2026-10-13*

An agent ran `co init --yes` from a temporary virtualenv. That one command
repointed every ConnectOnion skill under `~/.codex/skills` and
`~/.claude/skills` into the venv's site-packages. When the throwaway
environment was deleted, every skill link broke — on the machine that had
already been working.

`co skills link` was protecting a real directory you owned, but a symlink
was treated as fair game: if it did not already point at *this* package, it
was unlinked and rewritten. That is right for a dangling link after an
upgrade. It is wrong when the link still points at another install that
exists on disk.

The fix is a one-line distinction. A symlink whose target still has a
`SKILL.md` is another live install — keep it, say so, and tell you about
`--force`. A dangling symlink is still repointed, so an upgrade does not
leave Claude or Codex with a broken skill.

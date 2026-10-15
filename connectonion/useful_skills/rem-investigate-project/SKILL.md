---
name: rem-investigate-project
description: The steps for investigating a project's page, composed after rem-investigate when the subject is under projects/.
---

# Investigating a project

A project is told by two witnesses: the owner's messages say what they wanted,
decided and saw; the repository's current line says what was built and when.
Join them; neither alone is the page.

1. **Start from the current line.** `checkout-state` names it (usually
   `origin/main`) and whether the working tree lags; the history packet lists
   its commits and the unmerged branches committed lately. A working tree on
   an old branch is not the project: read files at the named revision with
   `git show`, never from the checkout.
2. **Find the purpose** in the README at that revision and the owner's
   earliest messages that describe the whole project. Quote the owner.
3. **Close every thread you can.** For each ask, issue or plan in the
   messages, look for its outcome: later messages, commit subjects
   (`git log --all --grep '<term>'`), branch names. A commit after the ask
   that does what it asked closes it; cite both and date the close. Only what
   nothing closed, and is recent, stays open.
4. **Date where it stands** from the newest commits and messages. A request
   newer than every verified change is the current goal, not done work.
5. **Inspect code only for what the page claims** (purpose, flow, commands,
   a conflict with what the owner said). Do not tour files.

**Citing**

- Cite supplied `project-source:`, `codex:` or `claude-code:` IDs. A file you
  inspect at a commit is `git:/absolute/mapped/repository:<full-commit-sha>:relative/file`;
  a live file is `file:/absolute/path@<sha256>` from `shasum -a 256`.
  `origin: git:`, command output and bare paths are not source IDs.
- Only files under the page's mapped `Paths` can support it.
- `investigation:*` items (page, coverage, inventory, repositories, scope)
  are reading guides, never citable.
- Keep existing `Paths` and their `Sessions`, `First seen` and `Last seen`
  lines exactly. A new path needs a retained source.
- Search limits go in your reply, not the page.

**Whose project a message is about**

- A session's folder says where an agent ran, not what the message concerns.
  Use a message here only when it names a distinctive project, file, version
  or behaviour of this repository; an unnamed follow-up only when an earlier
  input in that session establishes this project.
- With zero assigned session inputs, keep `Insight` and `Open threads` bare
  `Unknown`; dated commits may still say where the code stands.
- Keep actors, nouns and scope exact: "ask the owner" is not calling agents;
  more property listings are not more details per property.
- A `Website` Fact needs an original that connects the site to this project.
- A request is not permission, delivery or completion; a source comment about
  a test is not a run.

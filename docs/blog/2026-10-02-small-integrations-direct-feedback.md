---
title: Small integrations, direct feedback
description: A development-branch integration wall exposed a gap between what users can discover and what they can install.
tags: [CLI, Integrations, Product]
---

# Small integrations, direct feedback

The request began with the logo wall: add Google Docs and Sheets, then more services with accessible APIs. Build a small experimental version first, let people use it, and deepen the integrations that attract real feedback. A spreadsheet export already existed through Drive, but exporting a file does not let an agent append a row. That missing action gave us a concrete place to start.

We implemented the first Sheets commands with a narrow boundary: read a range, append rows or update cells. A write prints the proposed request before contacting Google; repeating it with --yes submits one request. Provider responses stay as JSON so an agent can use them directly. Complete spreadsheet editing could wait. The [development guide](/cli/experimental-integrations) records the account setup and supported actions.

That approach made it possible to prepare 23 experimental integration groups and grow the wall from 51 to 74 entries. Then an independent AI review found a problem outside the new API code. The wall said preview branch, but the website's /llms.txt still opened with pip install connectonion and immediately listed the new commands. An agent following that path would install a package that did not contain them. Our discovery page had made the experiment look available before we had released it.

The command index repeated the mistake in another form. It added the development commands to its total, while the preview count recognized only older summaries beginning with “Preview.” The new summaries began with “Experimental.” The same feature therefore had different availability depending on which route a reader followed. More logos had made this disagreement larger.

We added a development flag to the shared command group and used it in both outputs. The crawler route now puts the branch installation and account guide before the experimental commands. The visible index shows that 24 groups, including feedback, require the development branch. Its collapsed group carries the restriction; opening it reveals the setup link. We also removed a fixed “42 commands” link and an inherited preview-count claim instead of introducing another number to maintain.

The recheck fetched the rebuilt crawler outputs and homepage HTML, then inspected the exported wall image. The two crawler routes agreed, the branch restriction preceded the commands, and the image retained its own setup caveat. This was a limited review: the available browser inventory was empty, so mobile appearance and interactive states were not verified. The local regression run passed 802 focused tests, and an installed wheel exercised discovery and account-free write previews. Those checks do not establish that every provider works with a real account. The selected environment had no connected Google account, so a live Sheets write remains to be verified.

The owner also wanted a way for people to reach us when an experiment fails. We used the existing Agent mailbox, aaron.xie@mail.openonion.ai, alongside GitHub issues and Discord. Feedback links appear on stderr after each invocation, leaving JSON results on stdout. The local listener successfully read the approved mailbox and collected zero matching messages on its first check. It stores messages with the feedback subject prefix, preserves unread state and deduplicates receipts. It does not reply or execute instructions from email.

The lesson from this batch is practical: the unit we can offer is a small workflow with a discoverable installation path and a direct reporting route. A logo becomes useful when those paths agree. This branch has not been released on PyPI or deployed to the production website. The [umbrella issue](https://github.com/openonion/connectonion/issues/2153) tracks the implementation PRs, remaining account checks and the next workflows. Feedback can tell us which of those deserve deeper support.

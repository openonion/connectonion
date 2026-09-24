---
title: One Wiki, one folder in Codex
date: 2026-09-24
---

# One Wiki, one folder in Codex

The owner opened Codex's remote history to see what the Wiki had done. Instead of one Wiki, it showed a procession of folders named after individual runs. A person page, a digest and a maintenance pass each looked like a separate project. The files on disk were organized, but the history told the wrong story.

The cause was one argument to the subprocess: `cwd`. The Wiki created a fresh task directory so a model could revise a copy of a page. It then started Codex *inside that directory*. Codex quite reasonably treated each directory as a different workspace.

My first change set `cwd` to the Wiki root. It made the history look right, and the small runner tests passed. The larger suite caught what the small tests missed: an investigation test expected the model to edit a disposable page, not the live one. Moving the process to the root had put the real notebook within the normal write boundary. A tidier sidebar was not worth losing the boundary that keeps a failed candidate off the user's page.

The fixed point is now the Wiki's `.state/tasks` directory. Every delegated turn starts there. Each run still gets its own subdirectory for input, a notebook copy, a candidate and its review record. Codex sees one workspace; the Wiki still validates a candidate before promotion. The project scanner also ignores Codex sessions whose working directory is inside the Wiki, so a Wiki maintaining itself does not discover itself as a new project.

This exposed one more path: abstraction had no disposable copy. With the stable task workspace, its old direct write could no longer work under the normal Codex write policy. It now takes the same copy, review and promotion path as maintenance.

The check here is narrower than a live subscription test. The focused Wiki, CLI and adapter suite passed 531 tests, including the rejected-candidate and concurrent-edit cases. I did not start a real Codex run just to inspect the sidebar: doing so from a disposable test folder would itself add another stray folder to the owner's history. The next real Wiki run can confirm the grouping without creating that artifact on purpose.

A work directory is part of a product's interface when another tool uses it to organize history. It is also part of its write boundary. Both facts have to be true in the same design.

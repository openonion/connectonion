---
title: "The terminal number is part of the task"
date: 2026-09-28
---

# The terminal number is part of the task

OneNote could list a notebook and its sections, but a person trying to open a
page had to copy a full section name or a provider ID. The help was correct.
The workflow was still awkward. A terminal user wants to see a short list and
say `pages 2`, then `read 1`, much as they do with mail.

We gave OneNote those numbers and tested that they resolve to the displayed
items, including when two pages share a title. Then we ran `co audit co
onenote`. It passed. That result exposed a gap in the audit: its deterministic
checks asked whether help printed, showed usage, and gave a valid example, but
none asked whether selecting a listed item was practical.

The optional model review now asks one more question. If a command acts on an
item from a list, does its help offer a short row number or concise reference
instead of requiring a long opaque ID or complete title? A command that does
not select listed items passes that question automatically. A failure names
`short_reference` and asks for one concrete rewrite.

This review cannot prove that `1` opens the right page; only a behavioral test
can do that. The two checks answer different questions: can someone discover
an easy command from help, and does the command actually follow the list they
saw? A usable CLI needs both.

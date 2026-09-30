---
name: rem-investigate-skill
description: The steps for investigating a skill catalog page, composed after rem-investigate when the subject is under skills/.
---

# Investigating a skill

Why these rules: docs/rem-skills/rem-investigate.md

- The material is the skill's own files and its recorded eval runs (`co rem
  investigate skills/catalog/<page>.md --eval-dir <dir>` gathers them; no mail,
  no model call for the gathering).
- An unassessed run is not a success; a tool report is not a verified change;
  a log name does not establish the installed version.
- Never run the skill to document it.

## What to produce

Follow `rem-page-skill`, headings exact.

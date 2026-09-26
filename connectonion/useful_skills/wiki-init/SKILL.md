---
name: wiki-init
description: The first run of a notebook. Map installed skills, people, organizations and projects with page skeletons, connect sources, rank what matters, and leave an investigation queue. Drives co wiki and the mail CLIs.
---

# Initialise the notebook

You are building the frame once. Everything programmatic is a command; you
supply the judgement between the commands. Do not reimplement in prose what a
command already does. The task supplies the notebook root: include
`co wiki --root "<root>"` in EVERY Wiki command below, including follow-ups.
Read existing pages and `co wiki list people --aliases` before creating another identity.
Do not call `co wiki init` recursively or install a background schedule here.

Treat `co wiki --help` as the executable workflow guide: it explains task
selection, observed inputs, expected results, side effects and recovery. Read
`co wiki investigate --help` before investigation and follow actual `Next:`
commands. This Skill adds evidence judgment; it must not invent a second command
syntax or turn example page names into assumed records.

Before using the source CLIs, read [CLI.md](CLI.md), beside this file. It gives
the exact mail, browser and Wiki command forms, ID handling, pagination and
failure recovery. Resolve that path from this Skill's directory, not the task's
working directory. Run commands through the shell tool; do not invent tool names
or assume that Gmail, Outlook and `co email` share an inbox or query syntax.
Use the supplied absolute notebook root in every Wiki command; examples below
abbreviate it for readability. Replace placeholders with observed values.

## 1. Build the frame without a model

Run `co wiki --root '<absolute-notebook-root>' init --days 90`. This command
creates all four maps and complete page skeletons before returning. It never
starts a model or investigates a page. Do not invoke this Skill from that command.
Connected mailboxes are mapped by default; `--mail` selects explicit mailboxes. Read the init coverage report.
Use `--skills-dir` for known extra roots (explicit roots replace defaults).
Existing skills remain at their source paths and existing pages are preserved.

## 2. Judge the recorded enumeration

Read `.state/map.json`, `notes/people-map.md`, `notes/orgs-map.md`, `notes/projects-map.md`, and
`skills/catalog/index.md`. Counts describe the recorded window, not lifetime
usage. All correspondents remain unclassified; automated hints never filter
people by themselves. Classify people, company notices, opportunities and noise
from evidence. Group repository aliases only when identity is established.
Write ranking and reasons in `notes/`, preserving source coverage and unknowns.
Use `scan orgs` and `stub org` for organisation proposals when warranted.

## 3. Stop before investigation

Report mapped pages and source gaps. Suggest an explicit `co wiki --root
'<absolute-notebook-root>' investigate '<record>'` as the next step, owner first
when identity is verified. Do not execute investigation during init. People,
projects and skills follow their independent canonical page templates; map and
investigate use the same headings. No schedule or batch is started here.

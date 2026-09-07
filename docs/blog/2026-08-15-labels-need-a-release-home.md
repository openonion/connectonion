---
title: "A label is useful only when the work has somewhere to ship"
date: 2026-08-15
description: "What 64 unlabeled work items taught us about connecting community triage to release planning."
---

A new contribution arrived with working code and a clear user story, but no label and no release target. The missing label looked cosmetic. It was not: the pull request disappeared from every type-based queue, and nobody could tell whether it belonged in the next patch, the next minor release, or the longer roadmap.

An audit found the same gap across 49 open issues and 15 open pull requests. The issue templates already applied `bug` or `enhancement`, but blank issues and every pull request could still arrive without classification. More importantly, none of the templates asked the author to estimate where the work should ship. That question was being postponed until review, when changing scope is most expensive.

The first temptation was to invent a target version for every old item. That would make the board look complete while turning guesses into apparent commitments. Instead, existing items received only labels that could be supported by their titles and scope. Release ownership stays with milestones: authors propose a version and window, while maintainers confirm the plan by assigning the milestone.

The templates now ask for the affected or proposed version, an estimated release window, and the reason for that priority. A lightweight workflow catches the remaining holes. It infers obvious labels from conventional titles, falls back to `needs-triage`, and prevents a pull request with placeholder release metadata from quietly joining the merge queue.

The useful outcome is not that every card has a colored badge. It is that a contributor can see the path from report to release, and a maintainer can answer two questions without reopening the entire discussion: what kind of work is this, and where do we currently expect it to ship?

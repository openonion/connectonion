---
title: "Auto must mean the same promise"
date: 2026-08-24
author: ConnectOnion Team
---

The release gate had already built three projects and crossed the full Codex
permission matrix when it handed a bounded C project to Claude Code. Claude
created the source files, then stopped at the compiler. Its final message said
the commands had been denied and still needed approval.

Nothing was wrong with the outer setting. The Work Room said Auto. The mismatch
was in our translation: Auto selected Claude's `acceptEdits` profile. That
profile does exactly what its name promises—it accepts edits—but it retains
native checks for commands. We had presented one promise to the user and sent a
narrower one to the provider.

The provider names do not need to match, but their meaning does. Codex calls the
workspace-scoped automatic reviewer “Approve for me”; Claude Code calls the
equivalent profile “Auto”. Work Room Auto now selects Claude Auto by default.
`Accept edits` remains available as an explicit narrower choice for someone who
wants files changed while keeping command approvals.

The outer Host ceiling still wins. Read Only continues to force Claude into
Plan, and bypassing native permissions still requires the separately confirmed
Full Access ceiling. A unified client earns its name by translating the user's
intent faithfully, not by flattening every provider into identical labels.

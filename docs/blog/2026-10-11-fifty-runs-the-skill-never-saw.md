---
description: co benchmark check suggested an eval command without --invoke explicit. Followed with a real skill, it paid for 50 runs in which the skill never ran. The hint now includes it, and the auto case is flagged before any money is spent.
tags: [Benchmarks, Skills, CLI]
---

# Fifty runs the skill never saw

A team building a guest-reply agent did everything in the right order. They
wrote a benchmark, ran `co benchmark check` on it, and it passed. Then they
ran the next step it printed:

```
co eval run guest-reply-browser-all-20260926 --agent agent.py --skill <skill> --runs 1
```

They put in their real skill, `guest-enquiry`, and ran it. That was 50 paid
Agent runs. The report came back: **not activated 50/50**. The Agent had
never called the skill. The same report also showed 234 of 256 content
expectations passing and a score of 76%, which looks like a grade for a skill
that hadn't run.

## Two modes, one missing flag

`co eval run` has two ways of using a skill. With `--invoke explicit`, each
case tells the Agent to use the named skill, which is how you test whether
the skill is any good. With `--invoke auto`, the default, the Agent decides
for itself, which tests whether it discovers the skill at all. Both are
reasonable experiments. They answer different questions.

The command `co benchmark check` printed named a skill and left out the
flag, so anyone who followed it got the discovery experiment while believing
they were testing the skill. The report did warn that auto and explicit runs
can't be compared, but only after all 50 runs had finished and been judged.

## The fix

The hint printed by `co benchmark check` now reads `--skill <skill> --invoke
explicit --runs 1`. When you name a skill and leave invoke on auto, `co eval
run` now prints this before the cost line, before anything is spent:

```
--invoke auto: the Agent decides whether to use guest-enquiry, so this
measures discovery, not the skill. To test the skill itself, add --invoke explicit.
```

The rerun hint in `co eval report` repeats the mode the last run used, so a
second run compares like with like.

Two tests cover this. One checks the hint. The other checks that the warning
appears before "Paid from your balance". Both failed on main. We didn't add an
early stop after repeated non-activations. If the warning works, it won't be
needed.

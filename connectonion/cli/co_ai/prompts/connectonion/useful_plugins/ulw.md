# ulw

Ultra Light Work — let the agent run unattended for a bounded number of turns,
then stop and ask.

## The bound is the point

Autonomy without a stopping condition is how an agent spends an hour going the
wrong way. ULW grants a **turn budget**: the agent works without per-tool
approval until the budget is spent, then pauses and reports, and the user
decides whether to extend it.

```
mode: ulw, turns: 20
```

The remaining count is part of session state, so a client can show it and a
reconnecting client still knows where things stand.

## What it changes

Tool approval stops asking per call. That is all — it does not widen what the
agent is allowed to do, only how often it stops to confirm doing it.

## What it does not change

The permission patterns. A tool that was never permitted is still not permitted;
ULW removes the prompt, not the rule.

## When to use it

Work that is mechanical and long: a migration across many files, a sweep of
similar fixes. Not exploratory work, where the checkpoints are the value.

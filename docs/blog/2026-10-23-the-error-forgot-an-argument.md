---
title: The error forgot an argument
date: 2026-10-23
description: A tool's recovery hint must describe what the model sent, even after execution consumes some of it.
---

An Agent stopped at a rejected draft call and reported that it needed more
authorization. The application had a narrower problem: the requested expense
was in scope, but two fields belonged to another operation. The call had not
performed an action. Correcting the payload could continue the same work.

Reading the recorded call exposed a second problem in the framework's advice.
The model had supplied `operation`, `details` and `summary`. The error listed
all three as required, then said the model had supplied only the first two.
The hint was contradicting the call it was supposed to help repair.

The executor consumes `summary` as presentation metadata before invoking an
ordinary Python function. That is intentional: a function should receive its
declared inputs. The diagnostic was built later from those prepared arguments,
after the summary had gone. Both views were useful, but the hint used the wrong
one to describe the model's request.

We kept the execution view and captured the supplied argument names before
preparation. A failing regression reproduced the missing summary; the same
case now reports it as supplied. It also checks that the injected Agent does
not appear in the model's input list, the Python function receives its expected
arguments, and the caller's dictionary stays intact. Sixty related tests passed;
an independent review ran eighty. The diagnostic prints names, not a new copy
of their values. This does not make existing exception text a secret scrubber.

The application separately learned to distinguish invalid draft fields from
an expense outside the authorized scope. In a bounded real-model replay,
the Agent received the prior invalid-field error, corrected the simulated
draft call once, and explicitly reported a simulated result. That trial had
no browser, messaging or financial action. It does not establish that a live
reimbursement recovered, and the framework hint fix was not installed in it.

Better advice cannot turn an uncertain write into a safe retry or grant a new
permission. It can avoid sending an Agent toward a problem the caller never
had. The recovery hint needs its own faithful record of the request, even when
execution correctly transforms that request before a function sees it.

This maintenance fix is on the next-preview path; published rc16 is unchanged.

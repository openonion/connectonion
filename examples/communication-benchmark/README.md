# Communication benchmark (sandbox)

This example uses the 1.8.8 benchmark/evaluation interface to test whether an
Agent chooses the right email or Feishu reply action and describes its result
accurately. All addresses and messages are synthetic. The tools return local
simulation receipts; they never call Gmail, Feishu, or `co email`.

The standards are independent of the Agent: `email.yaml` covers sending,
threaded replies, ambiguous recipients, repeated events, and transport failure;
`message-reply.yaml` covers group context, original-file return, direct-message
context, external senders, and duplicate events. Each case has required
outcomes, and counterexamples also have forbidden outcomes. A forbidden outcome
is a hard failure even when the rest of the answer sounds good.

From this directory:

```bash
co benchmark check email
co benchmark check message-reply
co eval run email --agent agent.py --runs 1
co eval run message-reply --agent agent.py --runs 1
co eval report email --latest
co eval report message-reply --latest
```

The YAML files are the fixed standard. The Agent is the implementation under
test, and `.co/eval-runs/` holds individual attempts, tool evidence, and
verdicts. `--runs 3` repeats each case on a fresh conversation; the proposed
release gate is 3/3 for every case, with no forbidden action, `UNVERIFIED`, or
runner error. The structural suites also run in the repository's pytest suite.

The first three-run baseline with `co/gemini-3.7-flash` was 15/15 email attempts
and 12/15 message-reply attempts. The external-sender case failed 3/3: the
Agent did not send a file, but asked for file details instead of identifying
the unauthorized sender. This is a real prompt/skill gap, not a transport
failure. The run named no `--skill`, so it scores the Agent as a whole and
does not prove a skill was loaded. When testing a new skill, use the same
unchanged suites with `--skill NAME` and choose `--invoke auto` to test natural
selection or `--invoke explicit` to test direct invocation.

A passing sandbox run proves decision-making against these fixtures, not real
transport delivery. Test real delivery separately in an authorized staging
account before claiming production end-to-end reliability.

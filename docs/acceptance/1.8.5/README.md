# 1.8.5 integration acceptance

Status: implementation integrated on stable 1.8.4; no 1.8.5 package is published.
The proposed first publication is 1.8.5a1 after review and the release gates in
[#1462](https://github.com/openonion/connectonion/issues/1462).

## Integrated work

- #1398, #1466 and #1472, all now on main via #1491: the shared inbox and the
  Feishu/Lark adapter, including prior review fixes.
- #1464: command discovery and next-step tips, reconciled with 1.8.4 env/Outlook commands.
- #1465: messaging schedule, with stable 1.8.4 publication status retained.
- Integration repairs: durable completion without a sent reply, original-content
  recovery, torn log separation, collision-resistant unsafe IDs, persistent lock
  inodes, serialized claim/sweep transitions, malformed-file listing, and
  AGENT_CONFIG_PATH consistency. Five new regressions first failed on the imported
  implementation; the claim/sweep test also exercises the critical interleaving.

## Completed checks — 8 September 2026

- Full offline suite: **9,492 passed, 22 skipped**, coverage **80.00%** (floor 78%).
- Installed-wheel suite: **12 passed**, including credential-free receive/done and
  duplicate suppression after an isolated process restart.
- Public `lark-oapi==1.7.3` wheel inspected: domain/log_level support and reconnect
  observer attributes are present. SHA-256:
  `c91f00087b7977dc9059ab492e8fe435e1a873863dca1d4e660d2be5b801e4cd`.
- The local unit/wheel suites sent no live messages. The separate live run below
  used synthetic markers; no existing automation was stopped, and the user's
  installed stable package remains 1.8.4.

## Real-channel result — reconnect gap remains blocked

An owner-designated Lark bot and group were tested on 8 September 2026.
Configuration was reused from the existing CLI credential store in memory.
See [the sanitized live report](lark-live-2026-09-08.md). Normal receive, atomic
claim, completion, outbound replies and one-shot serve passed. The listener
reconnected, but a message sent during the gap was not recovered in the observed
window. This release gate remains open.

For a repeat run, the credential no longer has to come out of an existing
store by hand: `co auth feishu` creates an application by QR and writes its
pair to the selected env file, so the test can use one of its own rather than
borrowing the application a polling workflow is already using. Either way, do
not paste the pair into this record or commit it. Create a new private inbox
root for the test. If you do reuse an existing application, first confirm no
other WebSocket listener is competing for it, and coordinate any temporary
pause of the existing polling workflow with its owner.

A fresh application has one thing to check before the run proper: add its bot
to the test group and @-mention it once. An application created by
`co auth feishu` opens its long connection and subscribes to
`im.message.receive_v1`, but whether it is invitable and addressable as a group
bot is itself untested — `/open-apis/bot/v3/info` answers `20008` on one where
a console-made bot answers normally.

1. Run `co --env-file TEST_ENV lark check` (or `feishu`) from the candidate.
2. Run `CO_INBOX_HOME=TEST_HOME co --env-file TEST_ENV lark listen` in the
   foreground. The provider's directory is created under that root, so the
   test inbox is `TEST_HOME/lark/`. `CO_LARK_HOME` no longer exists; using it
   would write to the operator's own `~/.co/inbox/lark/`.
3. Have the tester post an @-mention containing a unique `co185-acceptance-...`
   marker. Record provider timestamp and arrival time locally; export only the
   synthetic marker, latency and pass/fail, not chat/sender IDs or other messages.
4. Run two `receive --no-start -t 0` consumers against that inbox. Only one may
   obtain the test message; the other times out with 124. Mark the message done.
5. Exercise a bounded fault affecting only the test listener's connection, longer
   than its heartbeat. Verify reconnect logs and compare exact marker IDs before,
   during and after the gap. Do not disable the workstation network. A successful
   reconnect alone does not prove the during-gap messages were delivered.
6. Outbound testing requires explicit authorization for the target group and
   synthetic reply text. Verify the returned provider message, duplicate refusal
   and deliberate `--again` behavior. A provider refusal is not successful delivery.
7. Stop only the test listener. Retain private evidence locally and clean up only
   owned test fixtures. Resume a paused workflow only if this test paused it.

A network-gap failure is a release finding, not a skipped test relabeled as a pass.
No docs-site stable-channel update or final 1.8.5 tag is warranted by the local
suite alone. Telegram, Discord and WhatsApp remain assigned to 1.8.6.

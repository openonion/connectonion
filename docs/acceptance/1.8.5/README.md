# 1.8.5 integration acceptance

Status: implementation integrated on stable 1.8.4; no 1.8.5 package is published.
The proposed first publication is 1.8.5a1 after review and the release gates in
[#1462](https://github.com/openonion/connectonion/issues/1462).

## Integrated work

- #1398 and #1466: shared mailbox and Feishu/Lark adapter, including prior review fixes.
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
- No live messages were sent, no existing automation was stopped, and the user's
  installed stable package remains 1.8.4.

## Real-channel gate — pending configuration

Use an owner-designated test bot and group. Keep its app ID/secret in the local
credential store; do not paste them into this record or commit them. Create a
new private mailbox directory for the test. First confirm there is no existing
WebSocket listener competing for that same application; coordinate any temporary
pause of the existing polling workflow with its owner.

1. Run `co --env-file TEST_ENV lark check` (or `feishu`) from the candidate.
2. Run `CO_LARK_HOME=TEST_HOME co --env-file TEST_ENV lark listen` in the foreground.
3. Have the tester post an @-mention containing a unique `co185-acceptance-...`
   marker. Record provider timestamp and arrival time locally; export only the
   synthetic marker, latency and pass/fail, not chat/sender IDs or other messages.
4. Run two `receive --no-start -t 0` consumers against that mailbox. Only one may
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

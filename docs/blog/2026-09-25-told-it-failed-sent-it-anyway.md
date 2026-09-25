# Told it failed, sent it anyway

A tester spent an afternoon running every inbox verb on every provider with no
credentials, then with fake ones, and kept a table of what each command said
and what exit code it returned. Most of the table was fine. One row was not.

`co whatsapp send BOGUSCHAT hello`, with no listener running, waited thirty
seconds and said `No listener answered in 30s`. `sent.jsonl` recorded the send
as failed. Nine minutes later the tester ran `co whatsapp listen` for an
unrelated check, and the listener's first action was to try to send `hello`.

The code looked correct. When the wait ran out, `send` deleted its request from
`outbox/` and reported the failure. The request that was still there came from
a run the test harness had killed partway through the wait, so the cleanup
never happened. That is ordinary. People press Ctrl-C and supervisors kill
processes. The same gap was also open without a kill. The listener read a
request and then deleted it, which is two steps. If `send` gave up between
them, it deleted a file the listener had already read, reported failure, and
the message went out anyway.

For a chat tool this is about the worst bug there is. Someone who is told a
message failed sends it again, and now the group has it twice. Or they send a
corrected version, and the old one arrives after it.

The fix is to let a single atomic step decide who owns a request. The listener
now claims a request by renaming it, and `send` withdraws it by unlinking the
same name. The filesystem lets only one of those succeed. If `send`'s unlink
succeeds, the request is gone before the failure is printed, and "nothing was
sent" is true. If it fails, the listener already has the request, so `send`
waits for the listener's answer instead of reporting failure. A request older
than any sender would still wait for, like the one left by the killed run, is
thrown away by the next listener with a line in the log. It is never sent
late.

## The rest of the table

The other rows had the same shape: the tool said one thing and did another.

- The Telegram docs showed `co telegram done -100123.55`. Group ids start with
  a minus sign, so Click read it as the options `-1 -0 -0` and exited 2. Now a
  number with a leading minus is treated as an id. Real options still parse,
  and a mistyped `--plian` is still an error. The simpler fix of ignoring
  unknown options would have sent the typo as the message.
- With a revoked token, `co telegram receive` waited forever. The listener it
  started had taken the lock, been refused a second later, written `stopped`
  and exited 3. By then `receive` had already been told the listener was
  running. Now `receive` watches a new listener until it reports a connection
  state or exits. If it exits, `receive` prints the reason and exits with the
  listener's own code.
- `pip install 'connectonion[whatsapp]'` was printed as
  `pip install 'connectonion'`, because Rich read `[whatsapp]` as a style
  tag. That command succeeds and fixes nothing.
- `done BOGUSID` exited 0. The id then sat in `done.jsonl`, and if a real
  message with that id ever arrived, it was dropped.

## What it teaches

Every one of these would have passed a test that only checked the success
path. The tester's table caught them because it recorded what each command
said happened, and then checked whether it actually happened. For something
that talks to people in their own chats, that is the test that counts: when
the tool reports a result, whether success or failure, the result has to be
true.

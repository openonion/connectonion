# The question Chrome never answered

A tester was running `co browser` through a long script on a Mac. The first
thirty commands worked. After that, every command failed with the same line:
"browser daemon closed or rejected the OIP stream — restart it and retry".
Restarting helped for about thirty more commands, and then it failed again.
`co browser status`, the command you run to find out what is wrong, hung for
four and a half minutes before the tester killed it.

Nothing in the log looked like a crash. Every command that failed had been
refused before it did anything.

## Counting file descriptors

The tester counted the daemon's open sockets after each command. There were
eleven at the start, twelve after the next command, then thirteen, and so on
up to thirty-one. Every command left one connection behind. The daemon admits
32 clients at a time, so once the leftovers filled those slots it had no room
for anyone new, and it dropped new connections without a word. The client saw
a dropped connection and guessed that the daemon had broken.

The leftover connections were all stuck in the same place. After each reply,
the daemon checks that the browser is still alive before it lets the
connection go. That check is a round trip to Chrome, and it is a round trip on
purpose: an earlier bug taught us that every local flag says "alive" after
the browser process is gone. The round trip we picked was "read your
cookies". On this Mac, Chrome's cookie store was waiting on the macOS
Keychain, and the Keychain was waiting on a prompt nobody was looking at. So
each check waited forever, each one held its connection, and `status` asked
the same question and waited too.

## Which part was the bug

Asking Chrome was right. What we got wrong was how we waited for the answer.
We waited with no deadline. We held the client's connection while we waited,
even though the client already had its reply. We did it inside a lock, so a
second check queued behind the first. And every new command sent Chrome
another cookie read, piled up behind the one it had not answered.

Now the check runs after the connection is closed, in its own task, so it
never uses up a client slot. Everyone who wants to know shares one question
at a time, and each waits at most three seconds for the answer. The most
important change is what the daemon concludes when that time runs out. It
concludes nothing. A dead browser answers at once with "target closed". A
browser that stays quiet is slow, not dead, and shutting it down would throw
away the session the user logged into. So no answer counts as "unknown", and
the daemon keeps running.

`status` now gives up on each of its questions after a few seconds and tells
you which one went unanswered: "Chrome did not answer a liveness check within
3s (it reads the cookie store, which on macOS can wait on a Keychain prompt)".
If the slots do fill up for a real reason, the 33rd client now hears "busy at
connection capacity — try again shortly", which is what the docs had always
promised, instead of a dropped connection that tells it to restart a daemon
with nothing wrong.

## What the same afternoon turned up

A tester stuck on one hang keeps poking at everything else, and found more.
`click_element_by_selector '#nope'` printed "No element found" and exited 0,
so `click && next-step` went on to the next step. It now exits 1, the code the
docs had listed all along. `take_screenshot --full-page true` saved a file
named `true`. `go_to htp://example.com` became `https://htp//example.com`,
and `go_to "not a url"` waited the full thirty seconds for a page that could
never load. Both are now refused straight away with exit 2. And `close`, run
when no browser had ever been opened, used to say "Session saved for next
time" about a session that never existed.

They have one thing in common with the hang. In each case the program acted
as if things were fine: it exited 0 on a failure, it treated a flag's value as
a file name, it "fixed" an address that could not be fixed. Here the fix was
not more error handling. It was being honest about what the program knew.
Sometimes that means saying "I don't know" (the liveness check), sometimes
"that failed" (exit 1), and sometimes "that is not an address" (exit 2).

The test for the hang uses no Chrome at all. It fakes a browser whose cookie
read never returns and sends it forty commands in a row. Before the fix, the
last of them failed with the line the tester saw. Now all forty succeed, and the daemon never has more than
two connections open.

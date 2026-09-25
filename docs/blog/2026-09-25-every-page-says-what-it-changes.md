# Every page says what it changes

When the help gate landed, it came with a list of 259 pages it would let
through for now. That list is gone. Every `co` command outside the wiki, 264
of them, now has an example you can copy and a sentence that says what the
command changes. CI fails a new command that does not.

The work was split four ways, by group, and every sentence was written from
the handler rather than from the command's name. That mattered more than
expected. `co outlook cancel` deletes the pending message on the server, so
its page says so. `co gmail read` leaves mail unread unless you pass
`--mark-read`. `co gmail send` sends immediately with no preview. `co reset`
deletes your keys before it makes a new account. `co auth feishu` does not
just sign you in: it creates a Feishu application that you own, and until
now its page never mentioned that.

Reading the handlers also found two places where the help was wrong, not just
thin. `co keys --ssh --write` said it wrote to `~/.ssh/`; the code writes to
`~/.co/ssh/`. And three inbox commands were first labelled read-only when
they are not quite: `ls` moves malformed queue files to quarantine, and `log`
creates an empty log if there is none. "Read-only" would have been a small
lie, so those pages say "changes nothing in the chat", which is true.

The wiki is the exception, and deliberately so. Its help pages are an agreed
design printed word for word, with a test of their own, and they are being
rewritten in #1667. Adding examples there now would edit a design that
another piece of work owns.

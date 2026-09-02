# Three Seconds Is Enough to Write a File

Feishu gives a bot three seconds. If the event handler has not returned by
then, the platform assumes the message was lost and sends it again: fifteen
seconds later, then five minutes, then an hour, then six. An agent turn
takes longer than three seconds. So the handler that receives a Feishu
message cannot be the thing that answers it, and the first version of every
chat bot discovers this the same way, with a duplicate reply.

`co feishu listen` does two things inside those three seconds and nothing
else. It appends one JSON line to `~/.co/feishu/inbox.jsonl` and it writes
one file into `new/`. Then it returns. The order matters: the log line goes
first, so a crash between the two leaves a message that can be found and
re-queued, never a queue entry the log has never heard of. The file is
written into `tmp/` and renamed into `new/`, so a reader never sees half a
message.

Whoever answers the message runs in another process, on their own clock.
`co feishu receive` takes the oldest file in `new/` by renaming it into
`cur/` and prints it. If nothing is there it polls four times a second
until something is. If the consumer dies after taking a message, the file
sits in `cur/` until the listener's once-a-minute sweep finds it older than
an hour and moves it back. That is SQS's visibility timeout, done with a
directory.

The reply needs one string. `co feishu reply om_9f8e` looks the id up in
the log, finds the chat and the thread, and posts to Feishu's reply
endpoint with a `uuid` derived from the message id. Feishu dedupes on that
`uuid` for an hour, so if the same reply is retried by a script that did not
notice its first attempt succeeded, the platform refuses the second. The
tool refuses too, before asking Feishu, unless told `--again`. The two
guards are not redundant: one survives a process restart, the other
survives a network blip.

The mention placeholder was the small surprise. Feishu delivers `@Bot look
at the deploy` as `@_user_1 look at the deploy` with a side list mapping
`@_user_1` to a name and an open id. The tool puts the name back so the
text reads as it did on screen, and compares the open id to the bot's own,
learned once from `/bot/v3/info` at start. A message that @s a colleague is
recorded and marked `mentioned: false`; a direct message is always
`mentioned: true`.

`receive` starts a listener if none is running. This is the gpg-agent
convention, and it exists so that "you forgot to start the daemon" is not an
error a person can meet. The listener holds a pid in `listen.lock`; a dead
pid counts as no listener. On Windows the liveness check asks the kernel
for a handle, because `os.kill(pid, 0)` there does not ask, it terminates.

The unit tests do not need a Feishu account. They deliver one id fifty
times and count one line; they take a message from two threads and count
one taker; they kill the handler between the write and the acknowledgement
and check the redelivery is dropped. What they cannot do is prove the long
connection stays up across a Feishu-side reconnect, and the tool is listed
under "written but not wired" in the product document until someone runs it
against a real group for a day. The code is small enough that a day is the
right amount of evidence.

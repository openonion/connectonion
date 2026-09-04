# Three Seconds Is Enough to Write a File

The first time a bot of ours answered a question in a Feishu group, it
answered twice. The person had typed one message. The agent had done the
work once, taken about forty seconds, and posted a good reply. Then the same
reply appeared again underneath it, and a minute later nobody could say why.

Feishu's event documentation explains it in one line that is easy to read
past. A bot has three seconds to acknowledge an event. If the handler has
not returned by then, the platform assumes the message was lost and sends it
again: fifteen seconds later, then after five minutes, then an hour, then
six. Our handler had received the message, started the agent, waited for
the answer and posted it, all inside the callback. Forty seconds is thirteen
times the budget. Feishu had done exactly what it said it would.

The obvious fix is to make the handler return early and run the agent in a
thread. That stops the duplicate, and it creates a worse problem: the
message now lives only in the memory of a process that may be killed, and
if it is killed after the acknowledgement, the message is gone and Feishu
believes it was delivered. The redelivery we had just suppressed was the
only thing that would have saved it.

So the question changed. It stopped being "how do we answer within three
seconds" and became "what is the least a handler can do that is also
enough". The answer we settled on is: write a file. `co feishu listen`
appends one JSON line to `inbox.jsonl` and drops one file into `new/`, and
returns. Nothing else. A file write takes milliseconds, so the deadline is
never in play, and once the message is on disk a crash cannot lose it.
Feishu may still redeliver during a blip, and when it does, the id is
already in the log and the second copy is dropped.

The order of the two writes turned out to matter. Log first, then queue. A
crash between them leaves a message that the log knows about and the queue
does not, which is recoverable by reading the log. The other order leaves a
queue entry the log has never heard of, which is a message with no history.
The file goes into `tmp/` and is renamed into `new/`, so no reader ever sees
half of it. Maildir has done this for mail since 1995 and we did not find a
reason to do it differently.

Answering then becomes someone else's job, on their own clock. Whatever
consumes the directory takes the oldest file by renaming it into `cur/` and
prints it. Renaming is atomic, so two consumers never take the same message.
If the consumer dies with the message in hand, the file sits in `cur/` until
a once-a-minute sweep finds it older than an hour and moves it back. That is
the visibility timeout every queue has, done with a directory.

The reply needs one string. The consumer says `co feishu reply om_9f8e`, the
tool looks the id up in the log, finds the chat and the thread, and posts to
Feishu's reply endpoint with a `uuid` derived from the message id and the
text. Feishu dedupes on that `uuid` for an hour, so a script that retries a
reply it did not notice succeeding is refused on the platform side. The tool
refuses too, before asking Feishu, unless told `--again`. The two guards are
not redundant: one survives a process restart, the other survives a network
blip.

Three things surprised us on the way. Feishu delivers `@Bot look at the
deploy` as `@_user_1 look at the deploy` with a side list mapping the
placeholder to a name and an open id, so the tool puts the name back and
compares the id to its own to know whether it was the one addressed. The
endpoint that tells a bot its own open id puts the answer at the top level
of the response, beside `code` and `msg`, where every other Feishu endpoint
uses a `data` envelope; a review caught that before a live run would have,
which is the argument for reviews. And `os.kill(pid, 0)`, the usual way to
ask whether a process is alive, terminates the process on Windows, so the
liveness check for the listener lock asks the kernel for a handle instead.

The unit tests do not need a Feishu account. They deliver one id fifty
times and count one line. They take a message from two threads and count
one taker. They kill the handler between the write and the acknowledgement
and check that the redelivery is dropped. What they cannot do is prove the
long connection stays up across a Feishu-side reconnect, so the tool sits
under "written but not wired" in the product document until someone runs it
against a real group for a day. The code is small enough that a day is the
right amount of evidence.

The lesson is older than Feishu. When a platform gives you a deadline, do
not try to finish inside it. Find the smallest durable step that fits, take
it, and let everything slow happen afterwards, elsewhere, where a deadline
cannot reach it. Three seconds is not enough to answer a question. It is
plenty to write a file.

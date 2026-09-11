# The silent message came back

The consumer had nothing to say. That was a valid result: it had inspected the
message, exited successfully, and produced no reply. The mailbox removed the
queue file. Then the same synthetic provider event arrived again, and the message
was waiting for another consumer.

The recovery code was doing exactly what we had asked. An ID in the inbox log
without a queue file or a successful reply looked like a crash between logging
and queueing. Recreating the queue file recovered that crash. It also undid an
intentional decision to remain silent. Once the file was gone, those two outcomes
looked identical.

We could have recorded an empty successful reply. That would have made the
existing duplicate check pass, but the outbox would then claim the provider had
sent something it had never received. Instead, completion now has its own small
append-only record. It is flushed before the queue file is removed. A replay sees
the completed ID and stops; the outbox still says nothing was sent.

Deleting the queue file was easy to observe. Remembering why it had disappeared
was the missing part. The inbox records arrival; the outbox records a reply;
neither records the consumer's decision that processing is finished. We had
mistaken the absence of a file for enough evidence of that decision.

The regression test now completes a synthetic message without replying, opens a
fresh mailbox instance, and delivers the same event again. No queue file returns.
The reply check still reports that nothing was sent. Those two assertions belong
together: suppressing the replay must not invent a conversation with the provider.

The order of the two writes matters as well. If completion were recorded after
deleting the file, a crash in between would recreate the original ambiguity. By
making completion durable first, recovery can finish removing the file without
asking the consumer to repeat its work.

This test establishes a local recovery rule. It does not establish whether the
provider will retain events during a disconnected listener's absence; the real
channel run is still pending. But once an event reaches our mailbox and the
consumer explicitly finishes it, silence now leaves a record of its own.

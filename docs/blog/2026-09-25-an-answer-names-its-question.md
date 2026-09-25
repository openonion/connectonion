# An answer names its question

In 1.8.8b5 a conversation stopped belonging to one connection. Open it on
a laptop and a phone and both show the turn as it runs, and either one can
approve a tool call or stop the turn. That was what people had asked for.
In review it also produced this line:

```
agent saw: [('read_file', True), ('bash rm -rf', True)]
```

Nobody approved `bash rm -rf`. Here is what happened. The agent asked to
read a file. Both devices showed the request. The laptop approved it, and
the agent went on to its next step, which needed a shell command. The
phone was still showing the first request, because the second one had not
reached it yet, and the reviewer tapped approve on it. That answer reached
the Host and was handed to the request that was waiting, which by then was
the shell command. So `rm -rf` was approved by a tap meant for a file read.

The Host was not being careless. An approval answer was just "yes" or
"no", and the Host gave it to whatever was waiting. For years that was
fine, because a single device can only answer the request in front of it,
and the next request cannot exist until that answer arrives. The order of
answers was enough to match each one to its request. Two devices broke
that, and nothing in the protocol took its place.

The fix puts in the answer what the order used to guarantee. Every
`approval_needed` and `ask_user` event already carried an `id`, since the
Host stamps one on every event. Now an answer carries that id back as
`request_id`, and the Host delivers it only if that request is the one the
agent is waiting on right now. The phone's late "approve" names the file
read. The agent is waiting on the shell command, so the answer is dropped
and the phone is told `STALE_ANSWER`. It is never moved to another
request.

The React client that ships today does not send the id, and that was
the awkward part. Rejecting every answer without one would have broken
every single-device user on upgrade. Accepting all of them would have left
the hole open. The rule we landed on: an answer with no id is accepted only
when this caller has the session open on one connection, because then
nothing else could have answered first. With two connections open, it is
refused. Until the client sends the id, approving from either device fails
loudly rather than approving the wrong thing. That is inconvenient, and we
prefer it to what the review found.

A second report came in on the same code. After one normal turn, the same
connection could no longer stop or steer a Codex Work Room turn. That one
was real too, and the cause was similar. To let the phone act on the
laptop's turn, each device is handed the turn's io, and the read loop took
that handed-over io on every incoming frame. It was still holding the io
of the finished normal turn, so on the next frame it swapped the live Work
Room turn out for the dead one. Now a connection takes a handed-over io
once, at the moment it is handed over.

What these two bugs teach is the same. When "one device" stops being
true, anything that relied on arrival order to know what a message was
about needs to say so in the message itself.

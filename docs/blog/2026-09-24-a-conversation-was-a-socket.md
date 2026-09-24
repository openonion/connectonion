# A conversation was a socket

Aaron had a conversation open on his laptop and opened the same link on his
phone. The phone said `Session is already attached to another connection`, and
the Reconnect button said it again, forever. The obvious reading was a relay
bug: the relay keeps one socket per session id and refuses a second. The code
even said so — a comment calling the check a stopgap.

So the first plan was to let the relay hold a set of sockets per session and
copy every frame to all of them. It would have taken an afternoon. It would
also have been wrong in three places, and finding out why was the useful part.

The relay was only the first layer to enforce a rule the others shared. The
protocol document opened with it in a box: `SESSION = connection`. On the Host,
each turn's output was pumped to whichever socket sent the prompt and nowhere
else. A second device that got past the relay would have sat there watching
nothing happen. And the relay routed replies by a session id the *client*
supplies — the stopgap existed so that knowing someone's session id, which is
in the URL, would not let you read their conversation.

Then the part that changed the order of the work. When a device reconnects, it
sends its copy of the conversation and the Host keeps whichever looks newer,
judged by `iteration`. But `iteration` counts LLM calls and restarts at zero
every turn. I ran the real function on a laptop whose last turn made seven
calls and a server whose newer turn, run on the phone, made two:

```
server_won = False | turn = 4 | the phone's turn is gone
```

No concurrency needed — just switching devices. The refusal on the phone had
been hiding a bug that erased a turn whenever you went back to the laptop.

What shipped:

- The merge compares `(turn, iteration, updated)`. `turn` never resets.
- The Host keeps every connection to a session as a viewer. A turn started on
  one device streams to the others signed in as the same identity, each
  reading the turn's log from its own position, and any of them can approve or
  stop it. The device that did not type the prompt gets it first, as
  `user_message`, so it is not looking at an answer to an invisible question.
- The relay gives each socket its own `conn_id` and routes by that, for agents
  that say in their signed ANNOUNCE that they understand it. The agent decides
  who may read what; the relay no longer routes by a string the client chose.
- For older agents the one-socket rule stays, except that a socket silent for
  75 seconds no longer counts as present. A locked phone leaves a half-open
  connection that still reports itself connected, and nothing used to reap it.

We checked it with nothing stubbed: a real Host, a real model, two clients with
the same key. The phone showed the laptop's question, the tool call, and the
same answer; a third client with a different key, naming the same session id,
was given a session of its own and saw nothing.

The lesson is the shape of the first plan. The error appeared at the relay,
so the fix wanted to live at the relay. The rule behind it was written into
every layer, and one of those layers was quietly losing work.

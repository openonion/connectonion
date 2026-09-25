# A visitor sees only their own

Two releases ago we made a promise and wrote a test for it. If two identities
talk to the same hosted agent, neither sees the other's conversation. Name
someone else's session id and you get a fresh one, not theirs. The test
connected a laptop, a phone with the same key, and a stranger with a different
key, then checked that the stranger received nothing. It passed every time.

This week a tester hosted an agent the ordinary way, typed a few prompts as
the owner, then connected from a second machine with a second key. Home loaded,
as it should: every client gets a snapshot of the agent's Home page when it
connects. Under "Recent" were the owner's prompts, word for word. On
`trust: open` a stranger saw them. On the default `careful`, a contact the owner
had added with `co trust add` saw them. The session gate held, and it didn't
matter, because the prompts came in by a different route.

The Home page is rendered from `.co/session_results.jsonl`, the same file that
holds every session. The "Recent" list read the last few runs out of it and put
their prompt text on the page. It was rendered once, the same for whoever was
connecting. When it was written the only reader was the operator, and nothing
in the function said who the page was for, because the question had never come
up.

The test missed it for a plainer reason. Its stranger check threw away three
frame types before counting, and one of them was `DASHBOARD_SNAPSHOT`. That was
reasonable when it was written: every client gets a Home, so the stranger's
list would never be empty with it included. But "every client gets one" and
"every client gets the same one" are different claims, and the exclusion
treated them as one.

So the fix has two halves. The snapshot a socket receives is now rendered for
that socket's verified address. It shows that address's own runs, and the
schedule, which is operator configuration, only to an admin. Admins also see
only their own runs. The page is a Home, not an audit view, and "an identity
sees only its own sessions" is easier to reason about with no exceptions. The
function that builds a snapshot for a socket takes the viewer as a required
keyword, so a new call site can't forget it and fall back to showing everyone's
runs. The acceptance script no longer ignores Home: a second stranger socket
connects after both turns, and its snapshot must not mention them. Against the
old renderer that check fails. Against the new one it passes.

The same tester found three smaller things, each a number or a sentence that
didn't match what was true. The log's `(N active)` counted registered
sessions, which stay registered for ten minutes after their socket closes so a
client can reattach, and a socket that closed before its first frame never
printed `ws-` at all. It now counts sockets and decrements in a `finally`. On
`careful`, every stranger with no invite code went to a model call that could
see only their address and the word `stranger`. The answer was always no, it
cost the owner a call every time, and it was worded differently each time.
That refusal is now deterministic and names the command that would change it.
And `co trust level` told a contact to "make it a contact".

The lesson is about exclusions in tests. Each frame type a check ignores is a
claim that the frame can never carry what the check is looking for. That claim
should be tested too, not assumed, because the code that builds the frame will
change after the test is written.

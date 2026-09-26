# The agent came back

“Run the CRCD check. It may take half an hour; tell me when it finishes.”

That is an ordinary request in a conversation with a coding agent. The agent
starts the command, gets a background task ID, and answers that it is running.
Then its turn ends. Thirty minutes later, the process exits with code 2. Its
output is available to anyone who remembers to ask for it, but the agent has
no reason to open the conversation again. From the user's side, the promise to
report the result was never kept.

The first tempting fix was a callback in the task's reader thread: when the
process exits, call the Agent. That works only while everything is quiet. If
the user is already talking to the Agent, two calls may write the same session
history. If the Host restarts after the process ends, a callback kept only in
memory disappears. If the Agent answers and the Host dies before marking the
callback delivered, running it again may duplicate the turn.

We already had the harder half of this problem in the Host's event watcher. It
records an observed file change or timer firing before trying to deliver it,
then waits for the target session to be free. The task needed to become another
source for that queue. So did the request to check a mailbox every 30 minutes:
most checks find the same messages and should never call the model at all.
Only a new message ID becomes an event.

One detail changed the design. A Host-configured watch can keep its own
conversation, but this task was started *inside* a conversation. Its completion
belongs in that original session. The registration now carries the verified
owner and session ID into the event record. The Host checks those fields again
before it claims a turn. It records the event ID in the session trace, so a
saved answer can be recognized after a crash without searching for a fragment
of JSON in the user's messages.

When the Agent returns, the event appears as a watch observation. Its answer
comes afterward and can say plainly that the command failed. The wake-up is
Read only, even if a previous user turn had Full Access. The task's exit code
is evidence about the command, not a verdict that the user's larger job is
done.

A short process and a controlled mail cursor can prove the ordering and the
no-change path offline. A real mailbox remains the final check before the
1.9.0 release.

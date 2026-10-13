# Everything arrives with accept

*2026-10-13*

On 1.9.2b21 we watched two strangers' agents pick up a handoff, on two machines
and two versions of Codex. Both installed co, both accepted, and both stopped
after saying what they would do. The last line of the block the person pasted
said "tell me what you will do". The person's words outrank anything a command
prints, so the agents did exactly that: they told, and stopped. The line now
says to do the work without waiting, and then to report what was done.

The second thing they said was "I'll locate the code". There was none to
locate. The sender had never pushed, so every recipient so far had started in
an empty folder and rebuilt the code from the session copy. Now the code they
cannot fetch travels with the handoff: commits as `git format-patch`, and
uncommitted changes as a diff. The preview says so, the credential check reads
it, and `accept` rebuilds the repository in the folder and says where.

The session copy used to come with the first answer, and the first answer came
only when the sender's machine next looked at its mail. Now it comes with
`accept`. A recipient has everything at the moment they say yes, whether or
not anyone on the other side is awake.

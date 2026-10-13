# The answer comes back

*2026-10-13*

On 1.9.2b22 a recipient's agent asked the sender something only the sender
could decide: should the length limit include the duplicate suffix? The sender
heard by mail and answered. By then the agent's turn had ended, and the answer
sat in an inbox until a person told the agent to carry on.

`co handoff open` now leaves `co handoff follow` running in the background. It
runs the work turn, then feeds each answer the sender writes by hand back into
the same session, until the agent reports the handoff done. Automatic answers
are left out, because the agent already has the session they point to. On
Parrot, the answer went in at 06:10, and the patch with the new validation was
back with the sender at 06:11.

`open` also stopped passing `--brief` to accept. With a 1.9.2b22 code, that flag
made accept skip fetching the code and the session copy, and the folder came up
empty.

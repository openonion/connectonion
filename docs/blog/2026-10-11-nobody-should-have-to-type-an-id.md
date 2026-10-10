# Nobody should have to type an id

The first preview of `co handoff` worked, and it was tested eight times across
two machines. Then Aaron read what the recipient had to do: install a package,
run `co handoff inbox`, copy an id, run `show`, run `open`. "What if they are not
technical?" There was no good answer, because the recipient is exactly the
person who did not choose the tool.

The recipient already has an agent, though, and an agent can run commands. So
the handoff now arrives as one block of text to paste into Codex or Claude
Code. The block carries the whole brief, so it is useful even if nothing else
works, and five steps for the agent: install co if needed, save the brief,
accept, tell the person what the task is, and ask the sender about anything the
brief leaves open. The person pastes. Their agent types.

Real mail broke it twice before it worked. The mail service turned the prompt
into one paragraph, because it sends every body as HTML, so the prompt now goes
in a `<pre>` block. Then an agent copied a 300-character code with one wrong
character and sent its acceptance to `openonion.as`, a mailbox that does not
exist. The code is now about a third as long and carries a checksum, so a typo
is refused instead of going somewhere else.

On the last run the receiving machine had no co installed at all. Its Codex made
a venv, installed the package, set up an identity and accepted the handoff in
83 seconds, and then asked the sender a question the brief had not answered.
The answer came back the same way.

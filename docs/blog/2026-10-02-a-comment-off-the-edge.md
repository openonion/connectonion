# A comment off the edge

The new README put a comment beside each quick-start command: `co init` on the
left, `# your identity and ~/.co/keys.env` on the right. On a laptop it reads
like an annotated recipe. On a phone, GitHub keeps a code block on one line
and lets it scroll sideways, so the column of explanations sat past the right
edge of the screen, and the reader saw five bare commands with no idea what
any of them did.

Nothing was broken, which is why it got through: the page rendered, the links
worked and the tests passed. It only showed up when we looked at the page at
the width most people read it on. The comments now sit on their own line above
each command. That takes more lines and no sideways scrolling, and the
explanation is the first thing a reader sees.

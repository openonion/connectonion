# A URL Is One Piece of Data

An operator ran `co auth google` on a headless server. There was no browser to
finish the handoff, so the terminal URL was the only path forward. They copied
what looked like the URL, pasted it elsewhere, and Google rejected it. Rich had
wrapped the 786-character value at the terminal edge, turning one URL into
several physical lines. When a spinner followed, terminal control sequences
made the copied text even harder to repair.

The tempting answer was to improve the instructions around the link. That did
not change the actual interface: on a remote box, stdout is not decoration. It
is the transport between the CLI and the browser on another machine. A value
that needs hand-editing before use is a broken value.

The complication was that the friendly output still matters. The command
should explain why a browser is opening, and a human should be able to spot the
link. Dropping Rich for the entire flow would solve wrapping by discarding the
rest of the presentation.

The turn was smaller. The label remains styled, while the URL gets its own raw
line with Rich soft wrapping enabled and markup and syntax highlighting
disabled. The same path now serves Google and Microsoft, so the next long OAuth
query cannot rediscover the bug under a different provider name. A regression
test renders a deliberately long URL through a 24-column console and proves
the output still contains exactly one URL line.

The lesson is that terminal output can be both prose and data, but each part
needs its own rendering contract. Labels may wrap. Tokens, URLs, IDs, and shell
commands must survive copying byte for byte.

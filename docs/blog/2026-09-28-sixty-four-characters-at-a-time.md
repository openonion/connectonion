# Sixty-four characters at a time

The owner gave the Wiki a budget of one point of their Codex week and let it
investigate the busiest page, their business partner, with 157 emails. We
watched the first pieces go through. The first took twelve minutes and half a
million input tokens. The second was still going after 22 tool calls and 1.2
million.

We read what the model was doing on each call. It never read the email. The
material file had every string cut into 64-character pieces, so the model
wrote Python to join the pieces back together, then printed the result 8,000
characters per call, with the whole conversation re-sent on every call.
Fifteen pieces at that rate come to about fifteen million tokens for one
person.

The splitting was deliberate. File tools cut off very long lines, and an
earlier version lost text that way. But the material was never meant to be
read from a file at all. Material small enough goes straight into the prompt.
The limit for that was 100,000 characters, while investigation cut its
evidence into 150,000-character pieces. So no piece ever fit, and every piece
fell back to the 64-character file.

Now investigation cuts evidence into pieces that fit in the prompt beside
their instructions, so the model reads each one once. The limit is counted in
bytes, because Linux caps a command-line argument at 128 KiB and a Chinese
character takes three bytes. When material is too large anyway, the model
gets plain text with long lines wrapped, which it can read or search with
grep, and the exact copy is still kept alongside.

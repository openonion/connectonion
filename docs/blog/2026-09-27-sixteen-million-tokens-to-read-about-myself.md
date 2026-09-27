# Sixteen million tokens to read about myself

This afternoon the owner asked a simple question: how much does it cost to
investigate a page? We had the logs, so we added it up. It was more than we
had assumed.

Filling his own page from thirty days of work came to sixteen million input
tokens. Ninety percent of that was cached, but it still counts against the
plan's allowance. It took forty model calls and about seventy-five minutes.
An organisation page with two hundred mails took ten million, and a small
project took three million. The material itself, measured in characters,
would have fit in a tenth of that.

Most of the difference came from how a single call works. A Codex turn does
not read its material once. Each time it runs a command, reading a file or
writing one, it sends everything that came before again. So a long material
file read in small pieces means many rounds, and each round sends more than
the one before. Earlier today the same pattern had made nightly maintenance
time out, and the fix there had been to put the instructions and material
straight into the prompt instead of making the model fetch them. We had not
yet applied that fix to investigation. Its summary chunks are 150,000
characters, too large to go into one prompt, so they are still read piece by
piece.

That is the next change: chunks small enough to travel in the prompt. There
will be more calls, each one much cheaper. We expect the total to fall to
about a third, but that is a guess until the same page is run again and
measured.

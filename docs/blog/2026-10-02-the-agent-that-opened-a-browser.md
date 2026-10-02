# The agent that opened a browser

We asked `co ai` one question, "What's open on my Linear board?", the day
`co linear` shipped in 1.8.10. It ran `co --help`, and the list it got back
had `co linear` in it. Then it opened a browser, signed in to linear.app and
read the board page by page: sixteen to twenty-five shell calls, about two
minutes, and ten to fifteen cents. The answer was right. The route was absurd,
since one command would have done it.

The help page wasn't the problem. Read cold, `co linear --help` says what the
command does and how to call it, and the command's own output names the next
step. The problem was what the agent believed before it read anything. Its
prompt had a long, careful section on driving the browser and not one line
saying that a service usually already has a `co` command. Given a page full of
commands and a habit of browsing, it browsed.

So the prompt now says it in a sentence: for an outside service, look in `co`
first, run `co commands`, read `co <command> --help`, and keep the browser for
sites `co` doesn't cover.

We ran the same question three times on each side of that change. Without the
sentence, all three runs went to the browser. With it, all three read
`co linear --help` and answered from `co linear issues` in five to seven
calls, in about twenty seconds, for five or six cents. A Slack question went
the same way: `co slack --help`, `channels`, `history`, `thread`.

One false start is worth recording. The first "after" run still used the
browser, because the `co` on the test machine's PATH was 1.8.8, which has no
`co linear`. The agent had looked and found nothing, which was the correct
reading of what it saw. Our test had been measuring the wrong install. The
real-API test now puts this checkout's `co` first on PATH.

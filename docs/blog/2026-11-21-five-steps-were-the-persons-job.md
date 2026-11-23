# Five steps were the person's job, and they should not have been

*2026-11-21*

When `co auth asana` was first reviewed, the browser path looked like the risky
one. To make an Asana token in the co browser, we copy the person's Chrome
cookies for asana.com into a browser that other agents share. So the review
asked for the cautious default: print the link to Asana's developer console,
ask for the token with the input hidden, and make the browser an opt-in
`--browser`. We built that, and we built the browser path carefully: it looks
at which Asana cookies the co browser already holds before copying anything,
clears only what it brought, checks the page is really asana.com before each
clear, and replaces the console tab with one line on every way out, so a new
token is never left on screen.

Then the owner looked at what the person actually does on the default path.
Open the console. Find "Create new token". Accept the terms. Copy the token.
Switch to a terminal and paste it. Five steps, and four of them are things the
machine can do. The rule for every `co auth` is that the machine does the work
and the person does only what only a person can do. Here that is one thing:
accepting Asana's API terms and pressing Create.

The turn was seeing that the caution had been spent in the wrong place. The
safety of the browser path was never the opt-in flag; it was the clean-up. A
flag only decided who got the safe path. So the default is now reversed.
`co auth asana` opens the console in the co browser, asks once whether to
copy the Chrome sign-in, opens the form and names the token, waits for the
person's one click, reads the token back, checks it against Asana and saves
it encrypted. The guard rails did not change; they simply run for everyone.

Pasting did not go away. If the co browser is not there, cannot say what
cookies it holds, or never gets as far as a token, the same command falls
back to the hidden paste on its own. `--paste` skips the browser entirely for
anyone who does not want their Chrome sign-in copied, even for a minute.
`--browser` is gone: the thing it asked for is now what happens without it.

Making it the default also made us run it for real, and the first real run
found a bug the opt-in path had hidden. The script pressed "Create new token"
and looked for the name field at once, but Asana draws that dialog about a
second later, so the token was never named and the terminal quietly said only
"Opened Asana's new-token form." The script now waits up to five seconds for
the dialog before filling it in. On the second run the form was named, the
person ticked the terms and pressed Create, and the token was read, checked,
saved and gone from the screen without anything being pasted.

What we checked: the default path end to end against a fake console (form
named, token read, saved, tab replaced, the copied cookies cleared, cookies the
browser already had left alone), the automatic fall back when the co browser
cannot be used, and `--paste` never touching the browser. What we have not
solved is the co browser itself failing silently when an old daemon still
holds its lock; when that happens, this command now falls back to pasting
instead of hanging, which is better, but it is not a fix.

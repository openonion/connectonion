# Twelve previews behind

The bug report was one sentence: I ran `co wiki open`, it opened a web page, and
the page would not load. Did the end-to-end tests even cover this?

They did not, and that was the first finding. Every test checked the link the
CLI printed; none opened it. The link pointed at a Wiki route O Chat did not
serve yet, so the command did exactly what the tests asked and nothing a person
wanted. We fixed that the honest way — a test that opens the page in real Chrome
and clicks through it — and the owner settled the design question underneath:
opening locally is the default, the live view is a feature you ask for.

The second finding was quieter, and it came from the first question in the
report: which version is on this machine? The answer was 1.8.9b1. Main was at
b12. The fix for the wiki, the Chrome import the same person had just watched
carry their GitHub and LinkedIn logins into the paid browser, and ten previews
of other work were all merged, all green, and all somewhere else. The nightly
wiki job on that Mac was running code from before most of them existed.

That is how a merged fix still reaches no one. CI proves the branch; it says
nothing about the laptop that files the next bug. So "fixed" for this report
meant three steps, not one: merge it, publish it as 1.8.9b13, and upgrade the
machine that found it — then run `co wiki open` there again and look at the page.

The lesson we are keeping: when a bug comes from a real machine, the first
command is `co --version`, and the fix is not done until that machine prints
the new number.

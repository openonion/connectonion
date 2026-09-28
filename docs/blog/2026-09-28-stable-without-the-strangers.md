# Stable without the strangers

1.8.8 went stable the careful way: five testers installed each candidate into
an empty profile, three rounds, and every finding was fixed from a failing test
before the next round. We wrote down that this is what "stable" means now.

1.8.9 broke that rule on purpose, and it is worth saying so.

The 1.8.9 line was meant to be short: fix what real use turned up. It ran to
twenty-two previews. Every week there was one more thing worth adding, and
every preview was "almost stable". Meanwhile the default install, the one a
stranger gets from `pip install connectonion`, was still 1.8.8, missing a
security fix for chat-driven turns and a month of Wiki work. Not releasing had
become the bigger risk.

So this morning we froze features, merged what was already in a pull request
into one preview, and used it on real accounts instead of waiting for a tester
round. That found real bugs within the hour: OneNote refused every outlook.com
account and called it "expired", a slow section printed a traceback, clipped
code lost its line breaks. All four were fixed in the next preview, and we
released stable on top of it.

What we traded: no stranger has installed 1.8.9 into an empty profile. What we
got: the security fix and the month's work reach everyone today, and what
turns up now goes into 1.9 instead of into a twenty-third preview.

The lesson: a release rule protects users only while the releases keep
coming. When the rule is what keeps a fix from shipping, break it in the
open, say what was not checked, and let the next version catch what this one
missed.

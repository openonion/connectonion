# What stable means now

1.8.8 is stable, and the word means something narrower and more useful than
it did a week ago.

Before, a release was ready when its tests were green and its review had no
blockers left. By that measure 1.8.8b7 was close: over eleven thousand tests
passed, and the code review had named five problems, most of them already
fixed. Then five testers installed b7 from PyPI into empty profiles and used
it as strangers would, and found that the documented install line crashed
every remote call, that `co auth status` signed a new user up, that an
agent's Home page showed the owner's prompts to any visitor, and that a
stale tap on a phone could approve a command nobody on the laptop had seen.
None of it failed a test, because each test had been written by someone who
already knew how the product was meant to be used.

So the release was not cut. Each finding became a failing test, then a fix,
and the same five walks ran again on the next published preview — b9, then
b11. The second walk found waits instead of wrong answers: a browser command
blocked on a Keychain prompt, a phone that joined a second too early, a
benchmark example with no data that the agent went looking for. The third
found one thing in the benchmarks — the agent under test had been reading
the answer key — and nothing in hosting. That falling curve is the evidence
the stable label now stands on.

Some of 1.8.8 is not stable, and says so. The Personal Wiki, `co claude`,
Discord, the Telegram inbox and TikTok ship labelled Experimental on every
help surface, because they were tested against fakes or are still changing
shape; the Wiki becomes long-term supported in 1.9.0. A label in `co --help`
is a promise about evidence, and it comes off when a real run is written
down.

The procedure we are keeping is short: a release is not reviewed until
someone has installed the published artifact into an empty profile and
followed its own notes.

# Commands nobody had run

On 24 September we went looking for finished work that had never reached main.
Four pieces turned up: Discord and Telegram inbox adapters written against a
`connectonion/listen` package that no longer existed, the TikTok half of a
creator CLI whose YouTube half had shipped weeks earlier, and Gemini image
output on a branch from July. Each one was ported onto today's code, each came
with tests, and each test passed — against fakes. Not one of them had talked to
a real Discord Gateway, a real Telegram bot, or a logged-in TikTok page.

That is fine for a preview, and a problem for `co --help`. The command list put
`co discord` and `co tiktok` on the same footing as `co gmail`, which has
carried people's real mail for months. Someone reading that list has no way to
tell a command we have watched work from one we have only reasoned about, and
the difference decides whether they should trust it with their bot token.

So the list now says it. `co discord` and `co tiktok` read "Experimental:"
beside `co wiki` and `co claude`, which were labelled the same way a day
earlier. `co telegram` is the awkward case: `send` has shipped since 1.7.0 and
is not experimental, while `listen`, `receive` and `reply` are new. Labelling
the whole group would undersell the part that works, so its line names both:
"send. Experimental: listen, receive, reply."

The label is a claim about evidence, not about quality, and it comes off the
same way it went on — when a run against the real service is written down. A
test in `tests/unit/test_experimental_commands_say_so.py` holds the list to
that, so a preview cannot quietly lose its label in a refactor.

# Three accounts before a stable release

1.8.10 adds Linear, Canny and Slack. Each was built against a fake: a mock
transport that answers the way the API reference says the service answers.
Every command passed its tests that way, and every PR was green.

A green PR meant only that the code agreed with the fake. So before the
release, an agent drove the browser and opened a free account on each
service, signing up with the agent's own email address and reading the
confirmation codes from its inbox. Then we ran every command against the real
thing.

Linear matched its documentation, down to the wording of the error for an
issue that does not exist. Canny and Slack did not, and both mismatches were
ones a fake cannot show you.

Slack's search worked in the unit tests and failed on the first real call. To
put a name beside each message, it asked Slack who wrote it, using the user
token that search needs. That token can search, but it cannot look people up.
The bot token already can, so names now come from the bot.

Canny returned a post we had just created when we asked for it by id, and left
it out of every listing. A second post, made the same way with ordinary text,
was listed within five seconds. The first one's text read like a test, and
Canny appears to hold such posts as likely spam until an admin approves them.
There is nothing for the CLI to fix there, but there is something to say:
"not in the list" and "does not exist" are now told apart in the docs.

The third finding came before any command ran. The keys had been saved the
way our own help recommends, with `--secret`, and the tests reported them
missing. Only `co env get` could open the encrypted store. That had been true
since 1.8.9, and nothing had noticed, because nothing had saved a key that way
and then used it. The fix went in first, and the three command groups read
their keys through it.

So 1.8.10 is stable in a narrower sense than "the tests pass". Each command it
adds has worked against a real account. What hasn't (Slack's inbox on the new
workspace, Linear past 250 issues) is listed in the release notes as untried,
not left for users to find.

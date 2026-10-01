# The secret only one command could read

We signed up for Linear, Canny and Slack to test three new commands against
real accounts. The signup agent saved each key the way `co env set --help`
shows, `co env set LINEAR_API_KEY lin_api_... --secret`, and verified each
with `co env get`. Then the real-account tests reported "LINEAR_API_KEY not
set" and skipped.

Both answers were correct. `--secret` encrypts the value under a key derived
from the agent's own key and writes it to `~/.co/keys/secrets/`, not to
`keys.env`. `co env get` knows to look there. Nothing else did. Commands read
`os.environ`, which holds the shell and `keys.env`, so a key saved the way the
help recommends was invisible to the command it was saved for.

The new commands had already run into it from the other side. `co linear`
and `co canny` each tell users to save their key with `--secret`, so each
grew its own copy of `co env get`'s lookup. Two copies of a lookup order
drift apart, and `co slack`, built at the same time, had none.

The fix is the lookup itself, written once: `environment.setting(name)`
returns the process value, then the selected env file, then the encrypted
store, in the same order `co env get` uses. It puts the store last so it can
never change what a plain setting already resolves to, and a stored value
that will not open raises rather than reading as "not set". A wrong answer
there sends people looking for a key they have already saved.

We wanted to move the test keys back to plain text to get on with the tests.
The safety check refused: it would have written five live credentials to a
file. The refusal was right. The commands should read the store, and now they
can.

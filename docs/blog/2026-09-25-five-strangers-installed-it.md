# Five strangers installed it

On 25 September the question was whether 1.8.8 could be stable. The code
review had already said no: three security problems and a release scope that
put previews in front of everyone. But a review reads code. It does not
install the package, forget everything, and try to get something done.

So five testers did exactly that. Each installed 1.8.8b7 from PyPI into a
fresh virtualenv with a fresh home directory — no keys, no history, no
knowledge of how we usually run things — and used one part of the product the
way the docs said to: first run, the browser, every inbox, hosting on two
devices, and the experimental commands.

The first thing three of them hit was the install line. Our release notes
told pip to allow pre-releases while installing 1.8.8b7, and that flag does not stop at our
package: it resolved a development build of httpx that has no `AsyncClient`,
and `connect()`, every hosted agent and `co outlook` crashed. Nobody on the
team had seen it, because nobody on the team installs into an empty
environment.

The rest had the same shape. `co auth status` signed a new user up. `co create`
wrote an invite code to a file the host never read, then told the user to put
it there. A Telegram group id starts with a minus sign and was read as an
option. The browser daemon asked Chrome a question after every command and
waited forever for an answer that, in a fresh profile, never came. An agent's
Home page showed the owner's prompts to any visitor. Each was obvious from the
outside and invisible from where we sit.

Every finding became a failing test before it became a fix, and 1.8.8b9 is
those fixes: twelve pull requests, with a thirteenth in review. The lesson we are keeping is procedural.
A release is not reviewed until someone has installed the published artifact
into an empty profile and followed its own notes. The next stable decision
will be made after the same five walks, run again against b9.

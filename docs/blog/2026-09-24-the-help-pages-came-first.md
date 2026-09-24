# The help pages came first

`co wiki` had twenty-nine commands, and none of their help pages had an
example. About half were one line followed by flags with no explanation:
`reflect --basis`, `review --verdict` and `route --clear` reached users
with nothing to say what they did. The scheduler ran
`co wiki daily --scheduled`, and `--scheduled` did not appear on `daily`'s
help at all. An agent that reads `--help` to decide what to type next was
reading a surface that had grown one command at a time, and it showed.

So this time the design was written as the help pages themselves, before
any code. One page per command, twenty-eight in all. Each says what the
command does and does not do, gives an example you can copy, names its side
effects, and says where to go next and how to get back. The owner read
them, asked why `config` had no page for `config set`, and asked whether
`investigate` could take a whole category. Both answers went into the pages.
Once the pages were agreed, the code was written to match them.

The pages are now the source. Each command prints its page from one
Markdown file, word for word. Generated help had been reflowing the
`Usage:` and `Example:` columns into paragraphs. A test holds the pages to
the code in the direction that matters. Every `co wiki …` a page tells you
to type is resolved against the real parser, and every flag it shows must
exist. A page that names a flag the command does not have fails the build,
because that is exactly the example an agent copies and cannot run.

The surface got smaller on the way. Fourteen commands sit on the root page
in four groups: build, read, keep it current, settings. The other nine are
experimental or internal and live behind `co wiki advanced`. `daily` became
`sync`, because upkeep is one thing, new material and then one page. Three
source commands became `sources` with `add` and `remove`. Every old name
still works, and says what it is called now.

Writing the pages first also caught a bug before anyone hit it. The page
for `investigate me` says it reads *your own sent mail*. The first real run
found six messages in thirty days. Each mailbox knows only its own login,
so the owner's other addresses were searched for as though they belonged
to other people. The fix is four lines. A help page that wasn't sure what
the command read would never have flagged it.

# The first thing an agent reads

We had just rewritten the website around one idea: your agent only needs to
know `co`. Tell it to use `co`, and it runs the bare command, sees the list,
opens `--help` on the one it needs, and follows the `Next:` line each command
prints. No tool list in the prompt, no skills to install first.

To put a real session on the page, we ran exactly that. The first thing bare
`co` printed, above every command, was:

```
A simple Python framework for creating AI agents.
```

That sentence was true when the package was an `Agent` class and a handful of
tools. It stopped being the product a while ago. The README, the PyPI summary,
the website and the docs had all moved to "the agent CLI harness". The one
place nobody had gone back to was the one an agent actually reads first. The
page promised that the CLI explains itself. The CLI opened by describing
something else.

It is an easy line to miss. People read a banner once and never again. An
agent reads it every time it lands in a fresh shell, and it takes it
literally. A framework is something you import and build on. A harness is
something you run. An agent that has just been told "you have a framework"
will reasonably go looking for a Python API before it tries `co gmail`.

The fix is small. Both screens, bare `co` and `co --help`, now open with the
same line as everything else: *CLI is all you need. ConnectOnion is the agent
CLI harness.* The start block gains one line, `co commands`, because that is
the command an agent needs when it wants the whole map. A test now checks
that neither screen calls the package a framework.

The same afternoon the README got the website's logo wall. It is not a copy.
The site serves the wall as `/connections.svg`, drawn from the same list the
page uses, so the README image changes when the site does. We had just watched
the CLI banner fall out of date because it lived somewhere nobody looked. We
did not want to start a second copy of the wall that would do the same.

The lesson is about audience. We check the words that people read. We had
not checked the words agents read. For a tool whose users are increasingly
agents, the banner, the help text and the error messages are the real front
page, and they need the same care as the website.

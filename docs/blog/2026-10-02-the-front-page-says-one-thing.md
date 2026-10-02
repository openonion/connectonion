# The front page says one thing

The README had become a tour. After the logo wall and the demos it taught the
Python framework: a weather tool, a table of plugin, hook and `@xray` guides,
hosting and trust. All of it is true and all of it is documented, but a reader
who arrived to learn what ConnectOnion is had to get through a tutorial for a
different question first.

What we want a visitor to leave with fits in a sentence: one command line
strings an agent's context together, and a command line beats the other ways
of giving an agent tools. The rewrite says that first and argues it. Every
agent already has a shell; a command line costs no context until it is used;
the help page is the prompt; every answer names the next command; commands
compose, and the transcript is the same commands you would type.

It also says where MCP fits. MCP servers are useful; the interface they arrive
through is what costs an agent context. `co mcp`, the next command group,
puts an MCP server behind `--help` like everything else. The README says it is
coming, with the issue, because it is not out yet. A front page that describes
a command the visitor cannot run spends exactly the trust it is there to earn.

The framework section is now one line and a link. The code examples, the
plugin table and the deployment guides moved nowhere: they were already in the
docs, and the docs are where someone building on the framework looks.

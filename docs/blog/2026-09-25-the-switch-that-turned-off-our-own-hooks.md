# The switch that turned off our own Hooks

In 1.8.6, every time `co ai` handed a task to Claude Code it added one flag:
`--safe-mode`. Safe mode starts Claude with every customization off: the
repository's `CLAUDE.md`, its `.claude/settings.json`, its hooks, its MCP
servers. That flag was the reason you could point `co ai` at a repository you
had just cloned from a stranger. A settings file in that repo can allow-list
Bash, and a hook in it is a shell command Claude runs on start. In a headless
turn nobody is watching, that is someone else's code running with your keys.

Then the Work Room arrived. To pair a browser with a Claude session, the
connector installs its own scoped Hooks: one tells us which session started,
another turns a Claude permission request into an approval card for the
owner. We pass them with `--settings`. And safe mode, it turns out, switches
those off too. It does not distinguish our Hooks from the repository's. So
the bridge path quietly stopped passing `--safe-mode`, and a test was written
that asserted it was gone. Nothing broke. The repository's settings simply
started loading again, on every hosted turn.

We checked what the installed Claude Code (2.1.281) actually does rather than
what its help text suggests. In a scratch repo with a `SessionStart` hook
that touches a file, a plain run fired both the repo's hook and ours.
`--safe-mode` fired neither. `--setting-sources user` fired ours and not the
repo's, and a `CLAUDE.md` telling Claude to answer "PINEAPPLE" to everything
stopped working. That is the switch the bridge needed all along: load the
user's own settings and ours, not the project's or local ones. We add
`--strict-mcp-config` too, so a repo's `.mcp.json` cannot start a server.

The second half of the story was a promise in the 1.8.8b4 notes. They said a
browser driving a `co claude` terminal could edit files only with the owner's
approval, and that shell commands were refused. Our Hook does exactly that,
but only for requests that reach it. The Station followed the Host's mode
into Claude's native `auto`, where Claude's own reviewer approves most Bash
itself and never asks us. So browser turns in the Station are now pinned to
Claude's manual mode, whatever the Host ceiling or Work Room pick says. Every
action that needs permission reaches the Hook.

A tester checking this found one more loose end: the temporary directory that
holds the Hook's bearer token survived a SIGTERM, because Python's default
SIGTERM exits without running any cleanup. A handler now removes it first.

The lesson is about switches with wide blast radius. A flag that disables
"all customizations" is a fine boundary until you become one of the
customizations. When that happens, the answer is not to drop the boundary;
it is to find the narrower one that still separates what you trust from what
you don't, and to pin it with a test that reads the launched command line.

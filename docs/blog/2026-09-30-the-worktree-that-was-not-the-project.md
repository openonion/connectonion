# The worktree that was not the project

The 1.9.0a1 acceptance run went over a copy of the owner's real notebook, and
the page for connectonion itself said the project's pyproject version was
1.8.9b2 and that its default was six runner calls a day. The release that
morning was 1.9.0a1, and the default was 30.

Every sentence on the page cited a file, and every file existed. The trouble
was which folder it came from. The page's `Paths` section listed about 70
directories, all of them `.claude/worktrees/agent-*`, and not the main
checkout. Each is a throwaway copy an agent session made to work in isolation,
branched from whatever `main` was that day. Investigation read the first one
on the list, and that copy was weeks old.

How did 70 of them get there? Mapping takes every coding session's working
directory as a place the project lives. That was a fair rule while one person
opened one checkout. It stopped being fair once most sessions ran in agent
worktrees: every session added a path, and nothing on the page said which one
was the real checkout.

The map already knew a worktree belongs to its repository. It grouped them by
origin, which is why there was one connectonion page and not 70. But it still
listed each worktree under that one page, and the grouping never decided which
path came first.

The fix makes that decision where paths are written. A worktree is recorded as
its main checkout. A live one says where home is in its `.git` file
(`gitdir: <main>/.git/worktrees/<name>`), and one Claude Code has already
removed still says so in its path, `<main>/.claude/worktrees/<name>`. The
session counts and dates add up the same way they did before. Only the list of
paths gets shorter, and the checkout comes first, so it is the first folder
investigation reads.

Pages written before this change get the same correction the next time they
are mapped or investigated. A line is removed only when it is recognisably a
worktree. A folder the owner added by hand stays where they put it.

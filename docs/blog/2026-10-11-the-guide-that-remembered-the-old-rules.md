---
description: The co auth guide still described local-first credentials a month after the code went global by default. It now says what the code does, and a test keeps the old promises out.
tags: [Docs, Auth]
---

# The guide that remembered the old rules

In September we changed where `co` keeps credentials (#1444). Before, a
command looked for a `.co/` in the current project, and `co auth` wrote to
the project's `.env` as well as the global file. After, every command uses
the global identity and `~/.co/keys.env`, unless you name another file with
`--env-file` before the command. One account, one file, the same in every
directory.

The quick start was updated. The code was updated. `docs/cli/auth.md`, the
page you land on when sign-in is what you're trying to get right, was not.
It still said three things that had stopped being true:

- "If your project has a `.env`, it's updated too."
- Google credentials save to `~/.co/keys.env` "and an existing project `.env`."
- "`co auth` prefers local `.co` if keys exist."

The last one does the most damage, because it sounds like a fix. Signed in
as the wrong account? `cd` into the project and run it again. Under the
current code that changes nothing: the same global account signs in, writes
to the same global file, and the reader concludes sign-in is broken.

## What the page says now

The `co auth` section now says it writes one file, `~/.co/keys.env`, and that
a project `.env` is never touched unless selected. Troubleshooting says
changing directory doesn't change the account. A new short section, "For one
project", shows the one way to keep a project's credentials separate, with
the selector repeated on the command that uses them:

```bash
co --env-file ./.env auth google
co --env-file ./.env gmail inbox
```

It also says the part people get wrong: the selected file replaces the
global one for that command rather than adding to it.

Docs drift because nothing fails when they drift. So the three sentences now
have a test that fails if any of them comes back, and the project example has
to stay on the page. Both failed against the old page.

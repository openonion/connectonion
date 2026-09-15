"""Shared CLI group behavior for built-in and feature-specific parsers."""

import re
import typer

class _OneSuggestion(typer.core.TyperGroup):
    """Answer a mistyped command once (#714).

        $ co skil
        No such command 'skil'. Did you mean 'skills'? Did you mean 'skills'?

    Two layers each append one: Click builds the message with its own suggestion
    and Typer's resolve_command adds a second to whatever Click produced. It read
    that way at every level, including the nested `co outlook contact` group.

    The two arrive by different routes, which is why this does not just switch a
    layer off. Click 8.4's NoSuchCommand keeps `possibilities` and appends the
    clause when the message is *rendered*:

        def format_message(self):
            if not self.possibilities:
                return self.message
            return f"{self.message} {_format_possibilities(self.possibilities)}"

    while Typer writes its own copy into `.message` beforehand. So the fix is to
    drop the text copy exactly when the exception is going to render one of its
    own, and to leave it alone when it is not.

    Which layer speaks is not stable: turning Typer's `suggest_commands` off
    fixed this on typer 0.20 and left plain `No such command 'skil'.` on 0.27,
    where Typer's is the only clause because Click gets no possibilities.
    pyproject asks for `typer>=0.20.0`, so a user has either.
    """

    # A verb this CLI used to have. Click's own "did you mean" works on edit
    # distance, so it offers nothing for `serve` → `consume`: the words share
    # two letters. Someone who read the 1.8.5b1 notes, or an agent that read
    # them, would otherwise get "No such command" and no way forward, which is
    # the failure #1487 exists to stop.
    RENAMED = {"serve": "consume"}

    def resolve_command(self, ctx, args):
        if args and args[0] in self.RENAMED and args[0] not in self.commands:
            new = self.RENAMED[args[0]]
            if new in self.commands:
                # Built from the context chain and prefixed with `co`, not
                # from ctx.command_path: the root's name is whatever argv[0]
                # was, so that renders "root feishu consume" under a test
                # runner and "connectonion feishu consume" for anyone who
                # invoked the other entry point. `invoke` below does the same.
                names, here = [], ctx
                while here.parent is not None:
                    names.append(here.info_name)
                    here = here.parent
                path = " ".join(["co", *reversed(names)])
                # Printed and exited rather than raised: a UsageError raised
                # from resolve_command is caught by Typer's pretty-exception
                # handler and rendered as a forty-line traceback, which buries
                # the one sentence that matters. Measured, not assumed — the
                # first version of this did exactly that.
                import sys

                print(f"`{args[0]}` was renamed to `{new}`.", file=sys.stderr)
                print(f"Next: {path} {new} --help", file=sys.stderr)
                raise SystemExit(2)
        try:
            return super().resolve_command(ctx, args)
        except Exception as error:
            # Not `except click.UsageError`: typer 0.27 vendors its own Click
            # (typer._click), so the exception it raises is a different class from
            # the installed click's and the handler would silently never run —
            # inert in exactly the version where CI runs. Catching broadly is safe
            # because this always re-raises and only touches an object carrying
            # both of the attributes it is about to use.
            # Keep the first candidate for `main` below. Click names it in the
            # message it is about to render ("Did you mean 'lark'?"), and the
            # next-step line underneath used to throw that away and say
            # `co --help` — telling the reader the answer and then pointing at a
            # flag. It is stashed rather than passed because Click prints and
            # exits between here and there.
            global _LAST_GUESS
            guessed = None
            possibilities = getattr(error, "possibilities", None)
            if possibilities:
                guessed = possibilities[0]
                if hasattr(error, "message"):
                    error.message = _SUGGESTION_RE.sub("", error.message).rstrip()
            else:
                # typer 0.27 vendors its own Click and leaves `possibilities`
                # empty, having already written the clause into the text — which
                # is the same version split this class was written for. So the
                # guess is read back out of the message rather than assumed
                # absent; otherwise the tip silently degrades to "co commands"
                # on exactly the version CI runs.
                named = _GUESS_RE.search(getattr(error, "message", "") or "")
                if named:
                    guessed = named.group(1)

            if guessed:
                # The whole command, not the bare word. `main` below runs on the
                # ROOT group even when the typo was a subcommand, so a guess
                # stashed without its group renders `co receive` for a mistyped
                # `co lark recieve` — a command that does not exist.
                names, here = [], ctx
                while here.parent is not None:
                    names.append(here.info_name)
                    here = here.parent
                _LAST_GUESS = " ".join(["co", *reversed(names), guessed])
            raise

    def main(self, *args, **kwargs):
        """Add the next command to a usage error, once.

        Click prints a usage error and exits 2 without passing through
        `invoke`, so the next-step table below never sees it. An agent that
        mistypes an argument gets "Try --help", which is a flag, not a
        command it can run — and a wrong invocation is the moment the next
        command matters most.
        """
        try:
            return super().main(*args, **kwargs)
        except SystemExit as exiting:
            from .commands.command_tips import next_step_already_named

            # Exit 2 is both Click's usage error and what a handler raises when
            # it refuses on purpose. Only the first kind arrives here having told
            # the caller nothing; the second has already named a precise command,
            # and adding a generic one on top makes two tips — a fork the agent
            # resolves by guessing, and it reads the worse one first because
            # stderr is what most callers merge in front.
            if exiting.code == 2 and not next_step_already_named():
                import sys

                global _LAST_GUESS
                guess, _LAST_GUESS = _LAST_GUESS, None

                # `co`, not argv[0]: the root's name is whatever invoked it,
                # and for the root group self.name is that same word — so it
                # is dropped rather than repeated.
                group = (self.name or "").strip()
                if group in ("co", "connectonion", "root"):
                    group = ""
                path = f"co {group}".strip()

                if guess:
                    # Already the full command, group included — Click just named
                    # the word, and resolve_command put it back in context.
                    tip = guess
                elif group:
                    tip = f"{path} --help"
                else:
                    # Nothing close enough to guess. `co --help` is a boxed screen
                    # of groups; `co commands` is every command, one per line with
                    # its summary — the shape something reading this can use.
                    tip = "co commands"
                print(f"Next: {tip}", file=sys.stderr)
            raise

    def invoke(self, ctx):
        """Run the command, then name the next one.

        The one place every command passes through on its way out, so a
        command cannot ship without a next-step tip by forgetting to print
        one: commands/command_tips.py holds the table, and a test fails when
        a registered command is missing from it.

        Only a normal return reaches the tip. `--help`, a usage error and
        every `raise typer.Exit(...)` leave by exception, so a failed command
        never gets a "next" that assumes it worked. Nested groups each pass
        through here; only the group whose invoked child is a leaf prints,
        so `co gmail draft send` tips once, not three times.
        """
        result = super().invoke(ctx)
        child = self.commands.get(ctx.invoked_subcommand or "")
        if child is not None and not getattr(child, "commands", None):
            # Build the path from the context chain rather than
            # ctx.command_path: the root's name is whatever argv[0] was
            # (`co`, `connectonion`, or the test runner's), and the table
            # is keyed on `co`.
            names, here = [ctx.invoked_subcommand], ctx
            while here.parent is not None:
                names.append(here.info_name)
                here = here.parent
            from .commands.command_tips import print_next_step
            print_next_step(" ".join(["co", *reversed(names)]))
        return result


_SUGGESTION_RE = re.compile(r"\s*Did you mean [^?]*\?")

# The last near-miss Click offered, handed from resolve_command to main.
# Module-level because Click prints its own error and exits in between.
_LAST_GUESS = None

# The first name inside "Did you mean 'x', 'y'?", for the version that puts
# the clause in the text instead of in .possibilities.
_GUESS_RE = re.compile(r"Did you mean '([^']+)'")

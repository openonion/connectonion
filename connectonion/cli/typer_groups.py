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
                import click

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
                raise click.UsageError(
                    f"`{args[0]}` was renamed to `{new}`. "
                    f"Next: {path} {new} --help", ctx)
        try:
            return super().resolve_command(ctx, args)
        except Exception as error:
            # Not `except click.UsageError`: typer 0.27 vendors its own Click
            # (typer._click), so the exception it raises is a different class from
            # the installed click's and the handler would silently never run —
            # inert in exactly the version where CI runs. Catching broadly is safe
            # because this always re-raises and only touches an object carrying
            # both of the attributes it is about to use.
            if getattr(error, "possibilities", None) and hasattr(error, "message"):
                error.message = _SUGGESTION_RE.sub("", error.message).rstrip()
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

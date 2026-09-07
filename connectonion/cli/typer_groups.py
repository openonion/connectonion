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

    def resolve_command(self, ctx, args):
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


_SUGGESTION_RE = re.compile(r"\s*Did you mean [^?]*\?")

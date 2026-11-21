"""Safe parser feedback for the Jira and OneNote source import commands only."""

import json

import typer

try:
    from typer._click.exceptions import UsageError
except ImportError:
    from click import UsageError

from ..typer_groups import _OneSuggestion
from ...environment import selected_command


def _invalid_arguments(ctx, args):
    """Name the last recognized command, never the raw invalid value."""
    names, parent = [], ctx
    while parent is not None and parent.parent is not None:
        names.insert(0, parent.info_name)
        parent = parent.parent
    source = names[0]
    command = " ".join(["co", *names])
    report = {"error": f"Invalid arguments for {command}.", "exit_code": 2,
              "source": source, "scope": {"command": names[-1]},
              "error_code": "invalid_input", "recovery_action": selected_command(f"{command} --help")}
    flags = args[:args.index("--")] if "--" in args else args
    if "--json" in flags:
        typer.echo(json.dumps(report))
    else:
        typer.echo(f"{report['error']}\nNext: {report['recovery_action']}", err=True)
    from .command_tips import mark_next_step_named
    mark_next_step_named()
    raise typer.Exit(2) from None


class ImportFeedbackCommand(typer.core.TyperCommand):
    """Report usage errors without echoing possibly sensitive argument values."""

    def parse_args(self, ctx, args):
        original = list(args)
        try:
            return super().parse_args(ctx, args)
        except UsageError:
            _invalid_arguments(ctx, original)


class ImportFeedbackGroup(_OneSuggestion):
    """Extend the existing tips behaviour only inside import command groups."""

    def parse_args(self, ctx, args):
        original = list(args)
        try:
            return super().parse_args(ctx, args)
        except UsageError:
            _invalid_arguments(ctx, original)

    def resolve_command(self, ctx, args):
        original = list(args)
        try:
            return super().resolve_command(ctx, args)
        except UsageError:
            _invalid_arguments(ctx, original)

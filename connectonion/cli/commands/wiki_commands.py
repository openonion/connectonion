"""Experimental Wiki inspection. No collection or provider startup on import."""

import json
import shlex
from pathlib import Path
from typing import List, Optional

import typer


def _next(ctx, arguments):
    root = ctx.obj["root"]
    return shlex.join(["co", "wiki", "--root", str(root), *arguments])


def _emit(ctx, value, arguments, *, failed=False):
    command = _next(ctx, arguments)
    if ctx.obj["json"]:
        typer.echo(json.dumps({"ok": not failed, "data": value, "next": command}, ensure_ascii=False))
    else:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        text = "".join(char for char in text if char in "\n\t" or (ord(char) >= 32 and not 127 <= ord(char) <= 159))
        typer.echo(text, err=failed)
        typer.echo(f"Next: {command}", err=failed)
    if failed:
        raise typer.Exit(1)


def _handle(ctx, operation, recovery):
    from ...wiki.files import WikiError

    try:
        value, arguments = operation(ctx.obj["root"])
    except (WikiError, OSError, UnicodeError) as error:
        message = str(error) if isinstance(error, WikiError) else "Cannot read or write the selected Wiki files"
        _emit(ctx, message, recovery, failed=True)
        return
    _emit(ctx, value, arguments)


def make_wiki_app(factory):
    wiki = factory(help="Experimental local Wiki inspection; collection/start is not shipped yet.",
                   no_args_is_help=False)

    @wiki.callback(invoke_without_command=True)
    def overview(ctx: typer.Context,
                 root: Optional[Path] = typer.Option(None, "--root", help="Notebook root (default ~/.co/wiki)"),
                 json_out: bool = typer.Option(False, "--json", help="Machine-readable output with next command")):
        ctx.obj = {"root": (root or Path.home() / ".co/wiki").expanduser().resolve(), "json": json_out}
        if ctx.invoked_subcommand is None:
            inspect_status(ctx)

    @wiki.command("status")
    def inspect_status(ctx: typer.Context):
        """Show local run counts, known usage, and background readiness."""
        from ...wiki.service import status
        _handle(ctx, lambda root: (status(root), ["logs"]), ["config"])

    @wiki.command("subscriptions")
    def inspect_subscriptions(ctx: typer.Context):
        """Show saved source choices or unsaved defaults; no body reads."""
        from ...wiki.service import subscriptions
        _handle(ctx, lambda root: (subscriptions(root), ["status"]), ["config"])

    config_app = factory(help="Inspect or explicitly change Wiki configuration.", no_args_is_help=False)
    wiki.add_typer(config_app, name="config")

    @config_app.callback(invoke_without_command=True)
    def inspect_config(ctx: typer.Context):
        from ...wiki.config import read_config
        if ctx.invoked_subcommand is None:
            _handle(ctx, lambda root: ({"path": str(root / "config.yaml"),
                                       "saved": (root / "config.yaml").exists(),
                                       "config": read_config(root, validated=False)}, ["status"]), ["doctor"])

    @config_app.command("set")
    def change_config(ctx: typer.Context, values: List[str] = typer.Argument(..., help="KEY VALUE pairs")):
        """Validate all supplied settings before saving; never starts collection."""
        from ...wiki.config import set_config
        _handle(ctx, lambda root: (set_config(root, values), ["config"]), ["config"])

    @wiki.command("list")
    def list_records(ctx: typer.Context, category: str = typer.Argument("", help="Category, e.g. people or notes")):
        """List current Markdown paths without inference."""
        from ...wiki.files import Notebook
        def operation(root):
            records = Notebook(root).list(category)
            return records, ["show", records[0]] if records else ["status"]
        _handle(ctx, operation, ["list"])

    @wiki.command("show")
    def show_record(ctx: typer.Context, record: str = typer.Argument(..., help="Path returned by list/search")):
        """Read one Markdown record; does not edit it."""
        from ...wiki.files import CATEGORIES, Notebook
        category = record.split("/")[0]
        recovery = ["list", category] if category in CATEGORIES else ["list"]
        _handle(ctx, lambda root: (Notebook(root).read(record), recovery), recovery)

    @wiki.command("search")
    def search_records(ctx: typer.Context, query: str = typer.Argument(...),
                       category: str = typer.Option("", "--type", help="Restrict to one category")):
        """Literal case-insensitive search; no embeddings or model call."""
        from ...wiki.files import Notebook
        def operation(root):
            found = Notebook(root).search(query, category)
            return found, ["show", found[0]["record"]] if found else ["list"]
        _handle(ctx, operation, ["list"])

    @wiki.command("logs")
    def inspect_logs(ctx: typer.Context, run_id: str = typer.Option("", "--run", help="ID from the run listing")):
        """Show local run outcomes and known/unknown usage."""
        from ...wiki.service import run_logs
        def operation(root):
            records = run_logs(root, run_id)[:20]
            next_args = ["logs", "--run", records[0]["id"]] if records and not run_id else ["status"]
            return records, next_args
        _handle(ctx, operation, ["logs"])

    @wiki.command("open")
    def open_page(ctx: typer.Context,
                  launch: bool = typer.Option(True, "--launch/--no-launch",
                                              help="Open the rendered page in the default browser")):
        """Render the notebook to a disposable local HTML page; no edits, no model."""
        from ...wiki.reader import open_reader

        def operation(root):
            page = open_reader(root, launch=launch)
            return {"page": str(page), "launched": launch,
                    "note": "a snapshot; run this command again after the next maintenance pass"}, ["status"]
        _handle(ctx, operation, ["doctor"])

    @wiki.command("doctor")
    def doctor(ctx: typer.Context):
        """Inspect local prerequisites; no native process, login, or repair."""
        import shutil

        from ...wiki.config import read_config, validate
        def operation(root):
            validate(read_config(root))
            return {"codex_binary_found": bool(shutil.which("codex")),
                    "native_isolation": "not verified by this read-only check",
                    "collection_cli": "not shipped", "background": "not shipped"}, ["status"]
        _handle(ctx, operation, ["config"])

    return wiki

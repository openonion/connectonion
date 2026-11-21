"""Read-only OneNote source CLI; imports collection code only when invoked."""

import json
import shlex
from pathlib import Path
from typing import List, Optional

import typer

from rich.markup import escape

from ...environment import selected_command
from .. import style
from .command_tips import mark_next_step_named, tips_enabled
from .import_feedback import ImportFeedbackCommand, ImportFeedbackGroup


def _source():
    from ...useful_tools.onenote_source import OneNoteSource
    return OneNoteSource()


def _failure(message: str, scope: dict | None, code: str, recovery: str) -> dict:
    """Keep legacy error text while exposing source, scope and recovery to scripts."""
    return {"error": message, "exit_code": 1, "source": "onenote", "scope": scope or {},
            "error_code": code, "recovery_action": recovery}


def _print(text: str, *, error: bool = False) -> None:
    style.console(stderr=error).print(text, emoji=False)


def _next(command: str, *, error: bool = False) -> None:
    mark_next_step_named()
    if tips_enabled():
        _print(style.next_line(selected_command(command)), error=error)


def _following(result, family, scope):
    if family and result[family]:
        identifier = str(result[family][0]["id"])
        args = {"notebooks": ["sections", identifier],
                "sections": ["pages", scope.get("notebook", ""), identifier],
                "pages": ["sync", scope.get("notebook", ""), scope.get("section", ""), identifier]}
        return shlex.join(["co", "onenote", "source", *args[family]])
    if family:
        return "co onenote source " + {"notebooks": "verify", "sections": "notebooks", "pages": "sections --help"}[family]
    return "co onenote source notebooks" if result.get("read_only") else "co onenote source sync --help"


def _run(operation, as_json: bool, family: str | None = None, *, scope: dict | None = None) -> None:
    from ...provider_credentials import ProviderCredentialError
    from ...rem.files import RemError
    import yaml
    recovery = "co onenote source " + (family or ("sync" if scope else "verify")) + " --help"
    try:
        result = operation(_source())
    except (OSError, yaml.YAMLError):
        result = _failure("Could not read or write local source files or Microsoft credentials. "
                          "Check the selected account and --output permissions.", scope, "storage_error", recovery)
    except ProviderCredentialError as error:
        result = _failure(str(error), scope, error.code, error.next_command)
        result.update(getattr(error, "saved_results", {}))
    except (ValueError, RemError) as error:
        result = _failure(str(error), scope, "import_failed", recovery)
    if result.get("errors") and "error" not in result:
        message = ("Some selected OneNote pages could not be imported; valid results are retained." if result["records"] else
                   "No valid OneNote records were processed; no new import files were written.")
        result.update(_failure(message, scope, "partial_import" if result["records"] else "processing_failed",
                               "co onenote source sync --help"))
        result["exit_code"] = 2
    mark_next_step_named()
    if "error" in result:
        result["recovery_action"] = selected_command(result["recovery_action"])
    if as_json:
        # ASCII escapes also preserve Unicode through Windows legacy-codepage pipes.
        print(json.dumps(result))
    elif "error" in result:
        message = result["error"].split("\nNext:", 1)[0]
        _print(style.error("OneNote command failed (scope: " + json.dumps(result["scope"]) + "): " + message), error=True)
        if result.get("jsonl"):
            _print(f"Valid records retained: {style.count(result['records'])}; newly written: {style.count(result['written'])}; "
                   f"skipped: {style.count(result['skipped'])}.\nSaved to: {escape(result['jsonl'])}", error=True)
        for page_id, diagnostic in result.get("errors", {}).items():
            _print(escape(f"{page_id}: {diagnostic.split(chr(10) + 'Next:', 1)[0]}"), error=True)
        if result.get("note"):
            _print(escape(result["note"]), error=True)
        # Already selected: do not rewrite arbitrary 'co ' substrings in paths.
        if tips_enabled():
            _print(style.next_line(result["recovery_action"]), error=True)
    elif family:
        for row in result[family]:
            title = ' '.join(str(row.get('displayName') or row.get('title') or '(untitled)').split())
            label = {"notebooks": "Notebook", "sections": "Section", "pages": "Page"}[family]
            _print(escape(f"{label} ID: {row['id']}  Title: {title}"))
        if not result[family]:
            _print(f"No {family} in this scope.")
        if result.get("truncated"):
            _print(f"Listing limited to {result['limit']} pages; more pages remain. Increase --limit (maximum 1000).")
        _next(_following(result, family, scope or {}))
    elif result.get("read_only"):
        _print(style.ok("OneNote read access verified."))
        _next("co onenote source notebooks")
    else:
        _print(f"OneNote import: {style.count(result['written'])} newly written; {style.count(result['skipped'])} skipped.")
        if result.get("jsonl"):
            _print(f"Saved to: {style.path(str(result['jsonl']))}")
        _print("Local source records saved. For automatic REM intake: co rem sources connect onenote, then approve init.")
        _next("co onenote source sync --help")
    if "error" in result:
        raise typer.Exit(result["exit_code"])


def register_onenote_source(parent, factory) -> None:
    source_app = factory(help="""Read-only for OneNote; import explicitly selected pages into local source files.

                         Start with co auth microsoft, then co onenote source verify.
                         Discover notebooks, sections and page IDs in order. Source commands
                         accept Notes.Read or an existing broader grant. No separate Azure app.
                         Use sync for daily versions or one-off exports. Page media stay
                         metadata-only. For automatic REM intake, use co rem sources connect onenote and approve init.
                         REM rereads the selected page bodies on init and sync. Existing timers run sync.
                         Older co onenote ls/pages/read browse notes; create writes to OneNote
                         and is separate from this read-only source workflow.
                         Next: co onenote source verify
                         """,
                         epilog="Example:  co onenote source notebooks",
                         no_args_is_help=True)
    source_app.info.cls = ImportFeedbackGroup
    parent.add_typer(source_app, name="source")

    @source_app.command("verify", cls=ImportFeedbackCommand,
                        epilog="Example:  co onenote source verify")
    def verify(as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
        """Read-only: verify Microsoft credentials and minimal OneNote access.

        Connect using co auth microsoft first. Existing broader grants are accepted;
        this check does not prove access to every notebook or page. --json prints
        account identity and read_only. Exit 1 means authentication/provider failure;
        follow recovery_action. If consent lacks Notes.Read, use the client Microsoft
        flow; no separate Azure app. No import files or model calls.
        Next: co onenote source notebooks
        """
        _run(lambda source: source.verify_connection(), as_json)

    @source_app.command("notebooks", cls=ImportFeedbackCommand,
                        epilog="Example:  co onenote source notebooks")
    def notebooks(as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
        """Read-only: list notebook IDs and names, following pagination.

        Authenticate with co auth microsoft; verify with co onenote source verify.
        Choose a stable ID from this listing; duplicate names require IDs.
        An empty listing is valid. --json returns notebooks; exit 1 is a failed
        read, not an empty success. No import files or model calls.
        Next: co onenote source sections --help
        """
        _run(lambda source: {"notebooks": source.notebooks()}, as_json, "notebooks")

    @source_app.command("sections", cls=ImportFeedbackCommand,
                        epilog="Example:  co onenote source sections NOTEBOOK_ID")
    def sections(notebook: str = typer.Argument(..., help="Notebook ID or unique exact name"),
                 as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
        """Read-only: list section IDs within one selected notebook.

        Get NOTEBOOK from co onenote source notebooks. An ID or unique exact name
        works; ambiguous names fail. Includes nested section groups and pagination.
        Choose a section ID for pages. Empty is valid; exit 1 means failed discovery.
        --json returns sections. No import files or model calls.
        Next: co onenote source pages --help
        """
        _run(lambda source: {"sections": source.sections(notebook)}, as_json, "sections",
             scope={"notebook": notebook})

    @source_app.command("pages", cls=ImportFeedbackCommand,
                        epilog="Example:  co onenote source pages NOTEBOOK_ID SECTION_ID")
    def pages(notebook: str = typer.Argument(..., help="Notebook ID or unique exact name"),
              section: str = typer.Argument(..., help="Section ID or unique exact name within that notebook"),
              limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Maximum pages listed; reports truncation"),
              as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
        """Read-only: discover page IDs in one notebook and section.

        Get notebook/section IDs from notebooks and sections. --limit defaults to
        100, maximum 1000. truncated=true means later pages remain; increase --limit
        before claiming the entire section was listed. Empty is valid; exit 1 means
        discovery failed. --json includes pages, limit, truncated and resolved scope.
        Source sync needs these stable page IDs, not browsing row numbers.
        No import files, content downloads or model calls.
        Next: co onenote source sync --help
        """
        _run(lambda source: source.pages(notebook, section, limit=limit), as_json, "pages",
             scope={"notebook": notebook, "section": section})

    @source_app.command("sync", cls=ImportFeedbackCommand,
                        epilog="Example:  co onenote source sync NOTEBOOK_ID SECTION_ID PAGE_ID  |  co onenote source sync NOTEBOOK_ID SECTION_ID PAGE_ID --full --json  |  co onenote source sync NOTEBOOK_ID SECTION_ID PAGE_ID --mode export --export-id snapshot-1")
    def sync(notebook: str = typer.Argument(..., help="Selected notebook ID or exact name"),
             section: str = typer.Argument(..., help="Selected section ID or exact name"),
             page_ids: List[str] = typer.Argument(..., help="Explicit page IDs from source pages; never imports all pages"),
             output: Optional[Path] = typer.Option(None, "--output", help="Default: ~/.co/rem/docs/onenote"),
             mode: str = typer.Option("daily", "--mode", help="daily or export"),
             export_id: Optional[str] = typer.Option(None, "--export-id", help="Required for one-off export"),
             full: bool = typer.Option(False, "--full", help="Reread selected daily page bodies, even with unchanged timestamps"),
             as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
        """Writes chosen pages locally; reads only from OneNote.

        First run co onenote source pages NOTEBOOK SECTION to choose explicit page
        IDs. Never imports all pages implicitly. --output defaults independently to
        ~/.co/rem/docs/onenote. Use a separate directory for another account/section.

        Daily mode skips stored modification timestamps across dates. Use --full
        to reread selected bodies when content changed without a new timestamp;
        changed snapshots append, unchanged snapshots skip. --full does not repair
        corrupted files or bypass ownership. Preserve those files and choose a
        separate --output. No new page discovery is implied by a repeat.

        Export mode rereads selected pages into exports/ID with a manifest; requires
        --export-id. Existing IDs are preserved; choose a new ID to retry. --full
        applies only to daily mode. Images/attachments stay metadata-only.

        Exit 0 includes no-change. Exit 2 means partial/all page failures with valid
        pages retained; inspect errors/written/skipped. Exit 1 means authentication,
        scope or storage failure. JSON has the same counts and recovery_action.
        For automatic REM intake, use co rem --root NOTEBOOK sources connect onenote,
        approve init, then sync --source onenote and open --local. Existing local imports
        can be subscribed with sources add onenote.
        This collector makes no scheduling, model calls or OneNote writes.
        Next: co onenote source pages --help
        """
        from ...useful_tools.onenote_source import sync_onenote
        directory = output or Path.home() / ".co" / "rem" / "docs" / "onenote"
        _run(lambda source: sync_onenote(source, notebook, section, page_ids, directory,
                                        mode=mode, export_id=export_id, full=full), as_json,
             scope={"notebook": notebook, "section": section, "pages": sorted(set(page_ids))})

"""Selected OneNote pages, using the client's Microsoft refresh and storage."""
import yaml

from .files import RemError, atomic_write
from .remote_sources import directory
from ..environment import provider_keys

CREDENTIALS = provider_keys("microsoft")


def validate(value):
    from ..useful_tools.onenote_source import _selected_ids
    if not isinstance(value, dict) or set(value) != {"notebook", "section", "pages"}:
        raise RemError("OneNote selection requires notebook, section and pages IDs only; no credentials")
    if any(not isinstance(value[key], str) or not value[key].strip() for key in ("notebook", "section")):
        raise RemError("Choose explicit OneNote notebook and section IDs")
    if (not isinstance(value["pages"], list)
            or any(not isinstance(page, str) or not page.strip() for page in value["pages"])):
        raise RemError("OneNote pages must be a list of selected page IDs")
    return {**value, "pages": sorted(_selected_ids(value["pages"]))}


def configure(root, chosen):
    from ..useful_tools.onenote_source import OneNoteSource
    from ..useful_tools.onenote_scope import source_config
    from .onenote_imports import identity
    from .remote_sources import require_saved
    require_saved("MICROSOFT_REFRESH_TOKEN")
    source = OneNoteSource()
    account = source.verify_connection()["account"]
    scope = source.scope(chosen["notebook"], chosen["section"])
    if scope != {key: chosen[key] for key in ("notebook", "section")}:
        raise RemError("Use the explicit notebook/section IDs from co onenote source listings")
    for page in chosen["pages"]:
        source.selected_page(page, scope)  # metadata/parent check only; no HTML
    target = directory(root, "onenote")
    doc = source_config(target, account, chosen, "co rem sources connect onenote", daily=False)
    doc["registration"] = "rem_remote"
    atomic_write(target / "source.yaml", yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    return identity(root)


def refresh(root, subscription, chosen):
    from ..useful_tools.onenote_source import OneNoteSource, sync_onenote
    from .remote_sources import require_saved
    require_saved("MICROSOFT_REFRESH_TOKEN")
    if chosen != subscription["import_identity"]["scope"]:
        raise RemError("OneNote selection differs from the approved declaration; reconnect")
    source = OneNoteSource()
    if source.verify_connection()["account"] != subscription["import_identity"]["account"]:
        raise RemError("Microsoft account changed; reconnect and approve before reading pages")
    # Re-read selected bodies automatically: Graph timestamps alone have missed
    # real edits. The existing full snapshot hash still skips unchanged content.
    result = sync_onenote(source, chosen["notebook"], chosen["section"], chosen["pages"],
                          directory(root, "onenote"), full=True, lock_held=True)
    return {"complete": not result["errors"], "written": result["written"]}


def choose_scope():
    """Explicit numbered selections, including only listed page metadata."""
    import typer
    from ..useful_tools.onenote_source import OneNoteSource, MAX_SELECTED
    from .remote_wizard import pick
    client = OneNoteSource()
    client.verify_connection()
    notebook = pick(client.notebooks(), "OneNote notebook", title="displayName")
    section = pick(client.sections(notebook), "OneNote section", title="displayName")
    result = client.pages(notebook, section, limit=MAX_SELECTED)
    if result["truncated"]:
        typer.echo("Page list is bounded; only explicitly selected displayed pages will be read.")
    pages = pick(result["pages"], "OneNote pages", title="title", multiple=True)
    return {"notebook": notebook, "section": section, "pages": pages}

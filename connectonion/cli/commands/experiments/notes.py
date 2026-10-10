"""Token-based Notion and Airtable experiments."""

from typing import Optional

import typer

from .api import emit, group, json_file, key, mutation, request, segment, text_file

notion_app = group(
    "notion",
    "Notion: search shared pages, read blocks, create and append.",
    "save NOTION_TOKEN with co env set --secret; share target pages with that integration",
    'search "Meeting"',
)
airtable_app = group(
    "airtable",
    "Airtable: bases, schema and record reads/writes.",
    "save AIRTABLE_TOKEN with co env set --secret; grant access to the chosen base",
    "bases",
)


def notion(path: str, **kwargs):
    return request(
        "https://api.notion.com/v1/" + path,
        token=key("NOTION_TOKEN"),
        headers={"Notion-Version": "2025-09-03"},
        **kwargs,
    )


def airtable(path: str, **kwargs):
    return request("https://api.airtable.com/v0/" + path, token=key("AIRTABLE_TOKEN"), **kwargs)


@notion_app.command("search", epilog='Example: co notion search "Meeting"')
def search(
    query: str = typer.Argument(..., help="Title text; not full-text page search"),
    cursor: Optional[str] = typer.Option(None, help="next_cursor from the previous response"),
):
    """Search titles of pages and data sources shared with the integration. Read-only."""
    body = {"query": query, "page_size": 100}
    if cursor:
        body["start_cursor"] = cursor
    emit(notion("search", method="POST", body=body))


@notion_app.command("info", epilog="Example: co notion info <page-id>")
def page_info(page: str = typer.Argument(..., help="Page ID; the integration must have access")):
    """Read page metadata and properties. Read-only."""
    emit(notion(f"pages/{segment(page)}"))


@notion_app.command("read", epilog="Example: co notion read <page-id>")
def blocks(
    page: str = typer.Argument(..., help="Page/block ID"),
    cursor: Optional[str] = typer.Option(None, help="next_cursor from the previous response"),
):
    """Read one page of immediate child blocks; use read on a child with has_children. Read-only."""
    emit(notion(f"blocks/{segment(page)}/children", params={"page_size": 100, "start_cursor": cursor}))


def paragraphs(text: str) -> list:
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[start : start + 2000]}}]},
        }
        for start in range(0, len(text), 2000)
    ]


@notion_app.command(
    "create", epilog='Example: co notion create <parent-page-id> "Report" --input-file report.txt --yes'
)
def create(
    parent: str = typer.Argument(..., help="Parent page ID shared with the integration"),
    title: str = typer.Argument(..., help="New page title"),
    input_file: str = typer.Option(..., help="UTF-8 body file; - reads stdin"),
    yes: bool = typer.Option(False, help="Create the page; otherwise preview"),
):
    """Creates a child page with plain text only with --yes."""
    body = {
        "parent": {"page_id": parent},
        "properties": {"title": {"type": "title", "title": [{"type": "text", "text": {"content": title}}]}},
        "children": paragraphs(text_file(input_file)),
    }
    if mutation(yes, "Create Notion page", body):
        emit(notion("pages", method="POST", body=body))


@notion_app.command("append", epilog="Example: co notion append <page-id> --input-file report.txt --yes")
def append(
    page: str = typer.Argument(..., help="Target page/block ID"),
    input_file: str = typer.Option(..., help="UTF-8 text file; - reads stdin"),
    yes: bool = typer.Option(False, help="Append paragraphs; otherwise preview"),
):
    """Changes a page by appending plain-text paragraphs only with --yes (up to 100 blocks)."""
    body = {"children": paragraphs(text_file(input_file))}
    if mutation(yes, "Append Notion page", body):
        emit(notion(f"blocks/{segment(page)}/children", method="PATCH", body=body))


@airtable_app.command("bases", epilog="Example: co airtable bases")
def bases(offset: Optional[str] = typer.Option(None, help="offset from the previous response")):
    """Read one page of bases available to your personal access token. Read-only."""
    emit(airtable("meta/bases", params={"offset": offset}))


@airtable_app.command("tables", epilog="Example: co airtable tables <base-id>")
def tables(base: str = typer.Argument(..., help="Base ID from bases; needs schema.bases:read")):
    """Read a base's table schema. Read-only."""
    emit(airtable(f"meta/bases/{segment(base)}/tables"))


@airtable_app.command("records", epilog="Example: co airtable records <base-id> <table-id>")
def records(
    base: str = typer.Argument(..., help="Base ID"),
    table: str = typer.Argument(..., help="Table ID or exact name"),
    offset: Optional[str] = typer.Option(None, help="offset from the previous response"),
    formula: Optional[str] = typer.Option(None, help="Optional Airtable filterByFormula expression"),
):
    """Read up to 100 records, preserving the next offset. Read-only."""
    emit(
        airtable(
            f"{segment(base)}/{segment(table)}", params={"pageSize": 100, "offset": offset, "filterByFormula": formula}
        )
    )


@airtable_app.command(
    "create", epilog="Example: co airtable create <base-id> <table-id> --input-file records.json --yes"
)
def create_records(
    base: str = typer.Argument(..., help="Base ID"),
    table: str = typer.Argument(..., help="Table ID or exact name"),
    input_file: str = typer.Option(..., help='Airtable JSON body: {"records":[{"fields":{...}}]}; - reads stdin'),
    yes: bool = typer.Option(False, help="Create records; otherwise preview"),
):
    """Creates records using Airtable's request body only with --yes (up to 10 records)."""
    body = json_file(input_file)
    if mutation(yes, "Create Airtable records", body):
        emit(airtable(f"{segment(base)}/{segment(table)}", method="POST", body=body))


@airtable_app.command(
    "update", epilog="Example: co airtable update <base-id> <table-id> --input-file records.json --yes"
)
def update_records(
    base: str = typer.Argument(..., help="Base ID"),
    table: str = typer.Argument(..., help="Table ID or exact name"),
    input_file: str = typer.Option(..., help="JSON records with id and fields; - reads stdin"),
    yes: bool = typer.Option(False, help="Patch records; otherwise preview"),
):
    """Changes record fields using Airtable's request body only with --yes (up to 10 records)."""
    body = json_file(input_file)
    if mutation(yes, "Update Airtable records", body):
        emit(airtable(f"{segment(base)}/{segment(table)}", method="PATCH", body=body))

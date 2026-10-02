"""Google Workspace experiments using the saved Google account and Drive grant."""

from typing import Optional

import typer

from .api import document_id, emit, google, group, json_file, mutation, segment, text_file

SETUP = "co auth google --scopes drive (enable the corresponding Google API in the OAuth project)"
gdocs_app = group("gdocs", "Google Docs: list, read, create and append text.", SETUP, "list")
gsheets_app = group("gsheets", "Google Sheets: read ranges, create, append and update cells.", SETUP, "list")
gslides_app = group("gslides", "Google Slides: read, create and replace template text.", SETUP, "list")
gforms_app = group("gforms", "Google Forms: read forms/responses, create and update a form.", SETUP, "list")
DOCS = "https://docs.googleapis.com/v1/documents"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
SLIDES = "https://slides.googleapis.com/v1/presentations"
FORMS = "https://forms.googleapis.com/v1/forms"


def register_listing(app: typer.Typer, name: str, mime: str):
    @app.command("list", epilog=f'Example: co {name} list --query "Quarterly"')
    def listing(
        query: str = typer.Option("", help="Title text; Drive matches word prefixes"),
        limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="Page size"),
        page_token: Optional[str] = typer.Option(None, help="nextPageToken from the previous JSON response"),
    ):
        """List documents with full IDs and nextPageToken. Read-only."""
        escaped = query.replace("\\", "\\\\").replace("'", "\\'")
        where = f"trashed=false and mimeType='application/vnd.google-apps.{mime}'"
        if query:
            where += f" and name contains '{escaped}'"
        emit(
            google(
                "https://www.googleapis.com/drive/v3/files",
                params={
                    "q": where,
                    "pageSize": limit,
                    "pageToken": page_token,
                    "fields": "nextPageToken,files(id,name,webViewLink)",
                    "orderBy": "modifiedTime desc",
                },
            )
        )


for _app, _name, _mime in (
    (gdocs_app, "gdocs", "document"),
    (gsheets_app, "gsheets", "spreadsheet"),
    (gslides_app, "gslides", "presentation"),
    (gforms_app, "gforms", "form"),
):
    register_listing(_app, _name, _mime)


@gdocs_app.command("read", epilog="Example: co gdocs read <document-id-or-url>")
def docs_read(document: str = typer.Argument(..., help="Google Docs ID or URL")):
    """Read document content, including all tabs, as provider JSON. Read-only."""
    emit(google(f"{DOCS}/{document_id(document)}", params={"includeTabsContent": "true"}))


@gdocs_app.command("create", epilog='Example: co gdocs create "Weekly report" --yes')
def docs_create(
    title: str = typer.Argument(..., help="Document title"),
    yes: bool = typer.Option(False, help="Create the document; otherwise preview"),
):
    """Creates an empty document only with --yes; returns its documentId."""
    body = {"title": title}
    if mutation(yes, "Create Google Doc", body):
        emit(google(DOCS, method="POST", body=body))


@gdocs_app.command("append", epilog="Example: co gdocs append <document-id> --input-file report.txt --yes")
def docs_append(
    document: str = typer.Argument(..., help="Google Docs ID or URL"),
    input_file: str = typer.Option(..., help="UTF-8 text file, or - for stdin"),
    yes: bool = typer.Option(False, help="Append text; otherwise preview"),
):
    """Changes a document by appending plain text to its first tab, only with --yes."""
    body = {"requests": [{"insertText": {"endOfSegmentLocation": {}, "text": text_file(input_file)}}]}
    if mutation(yes, "Append to Google Doc", body):
        emit(google(f"{DOCS}/{document_id(document)}:batchUpdate", method="POST", body=body))


@gsheets_app.command("read", epilog='Example: co gsheets read <spreadsheet-id> "Sheet1!A1:D20"')
def sheets_read(
    document: str = typer.Argument(..., help="Spreadsheet ID or URL"),
    range_: str = typer.Argument(..., help="A1 range, including the sheet name"),
):
    """Read a range as cell values. Read-only."""
    emit(google(f"{SHEETS}/{document_id(document)}/values/{segment(range_)}"))


@gsheets_app.command("info", epilog="Example: co gsheets info <spreadsheet-id>")
def sheets_info(document: str = typer.Argument(..., help="Spreadsheet ID or URL")):
    """Read sheet names, IDs and grid sizes. Read-only."""
    emit(google(f"{SHEETS}/{document_id(document)}", params={"includeGridData": "false"}))


@gsheets_app.command("create", epilog='Example: co gsheets create "Customer list" --yes')
def sheets_create(
    title: str = typer.Argument(..., help="Spreadsheet title"),
    yes: bool = typer.Option(False, help="Create the spreadsheet; otherwise preview"),
):
    """Creates an empty spreadsheet only with --yes; returns its spreadsheetId and URL."""
    body = {"properties": {"title": title}}
    if mutation(yes, "Create Google Sheet", body):
        emit(google(SHEETS, method="POST", body=body))


def values_body(input_file: str) -> dict:
    values = json_file(input_file)
    if not isinstance(values, list) or any(not isinstance(row, list) for row in values):
        raise typer.BadParameter('Input must be a JSON array of rows, for example [["Alice", 10]].')
    return {"values": values, "majorDimension": "ROWS"}


@gsheets_app.command(
    "append", epilog='Example: co gsheets append <spreadsheet-id> "Sheet1!A:D" --input-file rows.json --yes'
)
def sheets_append(
    document: str = typer.Argument(..., help="Spreadsheet ID or URL"),
    range_: str = typer.Argument(..., help="A1 range identifying the table to append to"),
    input_file: str = typer.Option(..., help="JSON array of rows; - reads stdin"),
    yes: bool = typer.Option(False, help="Append rows; otherwise preview"),
):
    """Changes a sheet by appending rows using RAW values, only with --yes."""
    body = values_body(input_file)
    if mutation(yes, "Append Google Sheet rows", body):
        emit(
            google(
                f"{SHEETS}/{document_id(document)}/values/{segment(range_)}:append",
                method="POST",
                body=body,
                params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            )
        )


@gsheets_app.command(
    "update", epilog='Example: co gsheets update <spreadsheet-id> "Sheet1!A1:B2" --input-file rows.json --yes'
)
def sheets_update(
    document: str = typer.Argument(..., help="Spreadsheet ID or URL"),
    range_: str = typer.Argument(..., help="A1 range to overwrite"),
    input_file: str = typer.Option(..., help="JSON array of rows; - reads stdin"),
    yes: bool = typer.Option(False, help="Overwrite cells; otherwise preview"),
):
    """Changes cells in the given range using RAW values, only with --yes."""
    body = values_body(input_file)
    if mutation(yes, "Update Google Sheet cells", body):
        emit(
            google(
                f"{SHEETS}/{document_id(document)}/values/{segment(range_)}",
                method="PUT",
                body=body,
                params={"valueInputOption": "RAW"},
            )
        )


@gslides_app.command("read", epilog="Example: co gslides read <presentation-id-or-url>")
def slides_read(document: str = typer.Argument(..., help="Presentation ID or URL")):
    """Read slides, elements and speaker notes as provider JSON. Read-only."""
    emit(google(f"{SLIDES}/{document_id(document)}"))


@gslides_app.command("create", epilog='Example: co gslides create "Quarterly update" --yes')
def slides_create(
    title: str = typer.Argument(..., help="Presentation title"),
    yes: bool = typer.Option(False, help="Create the presentation; otherwise preview"),
):
    """Creates an empty presentation only with --yes."""
    body = {"title": title}
    if mutation(yes, "Create Google Slides", body):
        emit(google(SLIDES, method="POST", body=body))


@gslides_app.command("replace", epilog='Example: co gslides replace <presentation-id> "{{NAME}}" "Alice" --yes')
def slides_replace(
    document: str = typer.Argument(..., help="Presentation ID or URL"),
    old: str = typer.Argument(..., help="Exact placeholder text"),
    new: str = typer.Argument(..., help="Replacement text"),
    yes: bool = typer.Option(False, help="Replace matching text; otherwise preview"),
):
    """Changes matching text in every slide, case-sensitively, only with --yes."""
    body = {"requests": [{"replaceAllText": {"containsText": {"text": old, "matchCase": True}, "replaceText": new}}]}
    if mutation(yes, "Replace Google Slides text", body):
        emit(google(f"{SLIDES}/{document_id(document)}:batchUpdate", method="POST", body=body))


@gforms_app.command("read", epilog="Example: co gforms read <form-id-or-url>")
def forms_read(document: str = typer.Argument(..., help="Form ID or edit URL; not its published /d/e URL")):
    """Read questions, settings and form metadata. Read-only."""
    emit(google(f"{FORMS}/{document_id(document)}"))


@gforms_app.command("responses", epilog="Example: co gforms responses <form-id>")
def forms_responses(
    document: str = typer.Argument(..., help="Form ID or edit URL"),
    page_token: Optional[str] = typer.Option(None, help="nextPageToken from the previous response"),
):
    """Read one page of submitted answers, preserving nextPageToken. Read-only."""
    emit(google(f"{FORMS}/{document_id(document)}/responses", params={"pageSize": 100, "pageToken": page_token}))


@gforms_app.command("create", epilog='Example: co gforms create "Customer feedback" --yes')
def forms_create(
    title: str = typer.Argument(..., help="Form title"),
    yes: bool = typer.Option(False, help="Create an unpublished form; otherwise preview"),
):
    """Creates an unpublished empty form only with --yes; add questions with update."""
    body = {"info": {"title": title}}
    if mutation(yes, "Create Google Form", body):
        emit(google(FORMS, method="POST", params={"unpublished": "true"}, body=body))


@gforms_app.command("update", epilog="Example: co gforms update <form-id> --input-file questions.json --yes")
def forms_update(
    document: str = typer.Argument(..., help="Form ID or edit URL"),
    input_file: str = typer.Option(..., help="Forms batchUpdate JSON body; - reads stdin"),
    yes: bool = typer.Option(False, help="Apply the requests; otherwise preview"),
):
    """Changes form questions/settings using the official batchUpdate body, only with --yes."""
    body = json_file(input_file)
    if mutation(yes, "Update Google Form", body):
        emit(google(f"{FORMS}/{document_id(document)}:batchUpdate", method="POST", body=body))

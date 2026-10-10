"""Small Microsoft Graph file, workbook and task workflows."""

from pathlib import Path
from typing import Optional

import httpx
import typer

from .api import ExperimentError, emit, graph, group, mutation, oauth_token, segment

SETUP = "co auth microsoft; full consent must grant file/site/task access (not --core)"
onedrive_app = group("onedrive", "OneDrive: inspect files and download content.", SETUP, "list")
sharepoint_app = group("sharepoint", "SharePoint: find sites and browse document libraries.", SETUP, 'sites "Project"')
excel_app = group("excel", "Excel: read and update business-cloud workbook ranges.", SETUP, "sheets <file-id>")
todo_app = group("todo", "Microsoft To Do: lists, tasks, create and complete.", SETUP, "lists")


@onedrive_app.command("list", epilog="Example: co onedrive list --folder root")
def files(
    folder: str = typer.Option("root", help="Folder item ID, or root"),
    limit: int = typer.Option(20, min=1, max=200, help="Page size"),
    skip_token: Optional[str] = typer.Option(None, help="Token from the previous @odata.nextLink"),
):
    """List one folder page, preserving @odata.nextLink. Read-only."""
    where = "me/drive/root" if folder == "root" else f"me/drive/items/{segment(folder)}"
    emit(graph(f"{where}/children", params={"$top": limit, "$skiptoken": skip_token}))


@onedrive_app.command("info", epilog="Example: co onedrive info <file-id>")
def file_info(item: str = typer.Argument(..., help="Exact drive item ID")):
    """Read file metadata and available download URL. Read-only."""
    emit(graph(f"me/drive/items/{segment(item)}"))


@onedrive_app.command("download", epilog="Example: co onedrive download <file-id> --to report.pdf")
def download(
    item: str = typer.Argument(..., help="Exact drive item ID"),
    to: Path = typer.Option(..., help="Local file path; existing files are never overwritten"),
):
    """Writes a local file by downloading OneDrive content; cloud files are unchanged."""
    if to.expanduser().exists():
        raise ExperimentError("Destination exists; choose a new file path.")
    response = httpx.get(
        f"https://graph.microsoft.com/v1.0/me/drive/items/{segment(item)}/content",
        headers={"Authorization": f"Bearer {oauth_token('microsoft')}"},
        timeout=30,
    )
    if response.status_code != 302:
        raise ExperimentError(f"Download URL request failed (HTTP {response.status_code}).")
    # The pre-authenticated URL needs no bearer token. Never forward Graph credentials.
    with httpx.stream("GET", response.headers["location"], follow_redirects=True, timeout=30) as content:
        content.raise_for_status()
        with to.expanduser().open("xb") as target:
            for chunk in content.iter_bytes():
                target.write(chunk)
    emit({"downloaded": str(to.expanduser()), "id": item})


@sharepoint_app.command("sites", epilog='Example: co sharepoint sites "Project"')
def sites(query: str = typer.Argument(..., help="Site search words")):
    """Search accessible SharePoint sites. Read-only; requires site permissions."""
    emit(graph("sites", params={"search": query}))


@sharepoint_app.command("drives", epilog="Example: co sharepoint drives <site-id>")
def drives(site: str = typer.Argument(..., help="Site ID from sites")):
    """Read document libraries belonging to a site. Read-only."""
    emit(graph(f"sites/{segment(site)}/drives"))


@sharepoint_app.command("files", epilog="Example: co sharepoint files <drive-id>")
def library_files(
    drive: str = typer.Argument(..., help="Library drive ID from drives"),
    folder: str = typer.Option("root", help="Folder item ID, or root"),
    limit: int = typer.Option(20, min=1, max=200, help="Page size"),
    skip_token: Optional[str] = typer.Option(None, help="Token from @odata.nextLink"),
):
    """Read a library folder page, preserving @odata.nextLink. Read-only."""
    where = "root" if folder == "root" else f"items/{segment(folder)}"
    emit(graph(f"drives/{segment(drive)}/{where}/children", params={"$top": limit, "$skiptoken": skip_token}))


def workbook(item: str, drive: Optional[str]) -> str:
    base = f"drives/{segment(drive)}" if drive else "me/drive"
    return f"{base}/items/{segment(item)}/workbook"


def workbook_range(item: str, drive: Optional[str], sheet: str, address: str) -> str:
    escaped = segment(address.replace("'", "''"))
    return workbook(item, drive) + f"/worksheets/{segment(sheet)}/range(address='{escaped}')"


@excel_app.command("sheets", epilog="Example: co excel sheets <file-id> --drive <business-drive-id>")
def worksheets(
    item: str = typer.Argument(..., help=".xlsx file ID in OneDrive for Business or SharePoint"),
    drive: Optional[str] = typer.Option(None, help="Drive ID; default is your drive"),
):
    """Read worksheets in a supported business-cloud workbook. Read-only; personal OneDrive is unsupported."""
    emit(graph(workbook(item, drive) + "/worksheets"))


@excel_app.command("read", epilog='Example: co excel read <file-id> Sheet1 "A1:D20"')
def range_read(
    item: str = typer.Argument(..., help="Business-cloud .xlsx file ID"),
    sheet: str = typer.Argument(..., help="Worksheet name or ID"),
    address: str = typer.Argument(..., help="A1 range"),
    drive: Optional[str] = typer.Option(None, help="Drive ID; default is your drive"),
):
    """Read an Excel range, including values and formulas. Read-only."""
    where = workbook_range(item, drive, sheet, address)
    emit(graph(where))


@excel_app.command("update", epilog='Example: co excel update <file-id> Sheet1 "A1:B2" --input-file rows.json --yes')
def range_update(
    item: str = typer.Argument(..., help="Business-cloud .xlsx file ID"),
    sheet: str = typer.Argument(..., help="Worksheet name or ID"),
    address: str = typer.Argument(..., help="A1 range"),
    input_file: str = typer.Option(..., help="JSON array of rows; - reads stdin"),
    drive: Optional[str] = typer.Option(None, help="Drive ID; default is your drive"),
    yes: bool = typer.Option(False, help="Overwrite range values; otherwise preview"),
):
    """Changes workbook range values only with --yes."""
    from .google import values_body

    body = {"values": values_body(input_file)["values"]}
    if mutation(yes, "Update Excel cells", body):
        where = workbook_range(item, drive, sheet, address)
        emit(graph(where, method="PATCH", body=body))


@todo_app.command("lists", epilog="Example: co todo lists")
def task_lists():
    """Read Microsoft To Do task lists. Read-only."""
    emit(graph("me/todo/lists"))


@todo_app.command("tasks", epilog="Example: co todo tasks <list-id>")
def tasks(
    list_id: str = typer.Argument(..., help="Task list ID from lists"),
    limit: int = typer.Option(20, min=1, max=100, help="Page size"),
    skip: int = typer.Option(0, min=0, help="Rows to skip for the next page"),
):
    """Read a task list page, preserving @odata.nextLink. Read-only."""
    emit(graph(f"me/todo/lists/{segment(list_id)}/tasks", params={"$top": limit, "$skip": skip}))


@todo_app.command("create", epilog='Example: co todo create <list-id> "Follow up" --yes')
def create_task(
    list_id: str = typer.Argument(..., help="Task list ID"),
    title: str = typer.Argument(..., help="Task title"),
    yes: bool = typer.Option(False, help="Create a task; otherwise preview"),
):
    """Creates a task in the selected list only with --yes."""
    body = {"title": title}
    if mutation(yes, "Create Microsoft task", body):
        emit(graph(f"me/todo/lists/{segment(list_id)}/tasks", method="POST", body=body))


@todo_app.command("complete", epilog="Example: co todo complete <list-id> <task-id> --yes")
def complete_task(
    list_id: str = typer.Argument(..., help="Task list ID"),
    task: str = typer.Argument(..., help="Task ID"),
    yes: bool = typer.Option(False, help="Complete the task; otherwise preview"),
):
    """Changes a task's status to completed only with --yes."""
    body = {"status": "completed"}
    if mutation(yes, "Complete Microsoft task", body):
        emit(graph(f"me/todo/lists/{segment(list_id)}/tasks/{segment(task)}", method="PATCH", body=body))

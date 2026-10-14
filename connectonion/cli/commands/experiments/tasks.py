"""Personal-token task workflows for Todoist, Trello and Asana."""

from typing import Optional

import typer

from .api import emit, group, key, mutation, request, segment

todoist_app = group(
    "todoist",
    "Todoist: projects, tasks, create and complete.",
    "save TODOIST_TOKEN with co env set --secret",
    "projects",
)
trello_app = group(
    "trello",
    "Trello: boards, lists, cards, create and move.",
    "save TRELLO_API_KEY and TRELLO_TOKEN with co env set --secret",
    "boards",
)
asana_app = group(
    "asana",
    "Asana: workspaces, projects, tasks, create and complete.",
    "save ASANA_TOKEN with co env set --secret",
    "workspaces",
)


def todoist(path: str, **kwargs):
    return request("https://api.todoist.com/api/v1/" + path, token=key("TODOIST_TOKEN"), **kwargs)


def trello(path: str, *, params=None, **kwargs):
    return request(
        "https://api.trello.com/1/" + path,
        params={**(params or {}), "key": key("TRELLO_API_KEY"), "token": key("TRELLO_TOKEN")},
        **kwargs,
    )


def asana(path: str, **kwargs):
    return request("https://app.asana.com/api/1.0/" + path, token=key("ASANA_TOKEN"), **kwargs)


@todoist_app.command("projects", epilog="Example: co todoist projects")
def todoist_projects(cursor: Optional[str] = typer.Option(None, help="next_cursor from the previous response")):
    """Read one page of Todoist projects. Read-only."""
    emit(todoist("projects", params={"cursor": cursor}))


@todoist_app.command("tasks", epilog="Example: co todoist tasks --project <project-id>")
def todoist_tasks(
    project: Optional[str] = typer.Option(None, help="Project ID from projects"),
    cursor: Optional[str] = typer.Option(None, help="next_cursor from the previous response"),
):
    """Read one page of active tasks. Read-only."""
    emit(todoist("tasks", params={"project_id": project, "cursor": cursor}))


@todoist_app.command("create", epilog='Example: co todoist create "Follow up" --project <project-id> --yes')
def todoist_create(
    title: str = typer.Argument(..., help="Task content"),
    project: Optional[str] = typer.Option(None, help="Project ID; omitted means inbox"),
    yes: bool = typer.Option(False, help="Create a task; otherwise preview"),
):
    """Creates a Todoist task only with --yes."""
    body = {"content": title}
    if project:
        body["project_id"] = project
    if mutation(yes, "Create Todoist task", body):
        emit(todoist("tasks", method="POST", body=body))


@todoist_app.command("complete", epilog="Example: co todoist complete <task-id> --yes")
def todoist_complete(
    task: str = typer.Argument(..., help="Task ID"),
    yes: bool = typer.Option(False, help="Close the task; otherwise preview"),
):
    """Changes a task to completed only with --yes."""
    if mutation(yes, "Complete Todoist task", {"id": task}):
        emit(todoist(f"tasks/{segment(task)}/close", method="POST"))


@trello_app.command("boards", epilog="Example: co trello boards")
def boards():
    """Read boards belonging to the token's user. Read-only."""
    emit(trello("members/me/boards", params={"fields": "id,name,url"}))


@trello_app.command("lists", epilog="Example: co trello lists <board-id>")
def lists(board: str = typer.Argument(..., help="Board ID from boards")):
    """Read a board's lists. Read-only."""
    emit(trello(f"boards/{segment(board)}/lists"))


@trello_app.command("cards", epilog="Example: co trello cards <list-id>")
def cards(list_id: str = typer.Argument(..., help="List ID from lists")):
    """Read cards in a list. Read-only."""
    emit(trello(f"lists/{segment(list_id)}/cards"))


@trello_app.command("create", epilog='Example: co trello create <list-id> "Follow up" --yes')
def card_create(
    list_id: str = typer.Argument(..., help="Target list ID"),
    title: str = typer.Argument(..., help="Card title"),
    yes: bool = typer.Option(False, help="Create the card; otherwise preview"),
):
    """Creates a card in the chosen list only with --yes."""
    body = {"idList": list_id, "name": title}
    if mutation(yes, "Create Trello card", body):
        emit(trello("cards", method="POST", body=body))


@trello_app.command("move", epilog="Example: co trello move <card-id> <list-id> --yes")
def card_move(
    card: str = typer.Argument(..., help="Card ID"),
    list_id: str = typer.Argument(..., help="Destination list ID"),
    yes: bool = typer.Option(False, help="Move the card; otherwise preview"),
):
    """Changes a card's list only with --yes."""
    body = {"idList": list_id}
    if mutation(yes, "Move Trello card", body):
        emit(trello(f"cards/{segment(card)}", method="PUT", body=body))


@asana_app.command("workspaces", epilog="Example: co asana workspaces")
def workspaces():
    """Read workspaces available to the personal token. Read-only."""
    emit(asana("workspaces"))


@asana_app.command("projects", epilog="Example: co asana projects <workspace-id>")
def projects(
    workspace: str = typer.Argument(..., help="Workspace GID"),
    offset: Optional[str] = typer.Option(None, help="next_page.offset from the previous response"),
):
    """Read one page of workspace projects. Read-only."""
    emit(asana("projects", params={"workspace": workspace, "limit": 100, "offset": offset}))


@asana_app.command("tasks", epilog="Example: co asana tasks <project-id>")
def tasks(
    project: str = typer.Argument(..., help="Project GID"),
    offset: Optional[str] = typer.Option(None, help="next_page.offset from the previous response"),
):
    """Read one page of project tasks. Read-only."""
    emit(
        asana(
            f"projects/{segment(project)}/tasks",
            params={"limit": 100, "offset": offset, "opt_fields": "name,completed,notes,assignee.name"},
        )
    )


@asana_app.command("create", epilog='Example: co asana create <project-id> "Follow up" --yes')
def create(
    project: str = typer.Argument(..., help="Project GID"),
    title: str = typer.Argument(..., help="Task name"),
    yes: bool = typer.Option(False, help="Create the task; otherwise preview"),
):
    """Creates an Asana task in the selected project only with --yes."""
    body = {"data": {"name": title, "projects": [project]}}
    if mutation(yes, "Create Asana task", body):
        emit(asana("tasks", method="POST", body=body))


@asana_app.command("complete", epilog="Example: co asana complete <task-id> --yes")
def complete(
    task: str = typer.Argument(..., help="Task GID"),
    yes: bool = typer.Option(False, help="Complete the task; otherwise preview"),
):
    """Changes an Asana task to completed only with --yes."""
    body = {"data": {"completed": True}}
    if mutation(yes, "Complete Asana task", body):
        emit(asana(f"tasks/{segment(task)}", method="PUT", body=body))

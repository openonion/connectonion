"""
Purpose: Asana for agents and the CLI via Asana's REST API — the token, one request path, who the token acts as, the projects and tasks it can read, and one task's details, comments and activity
LLM-Note:
  Dependencies: imports from [time.sleep, httpx, environment.py (setting: process, env file, then the --secret store)] | imported by [cli/commands/asana_commands.py] | tested by [tests/unit/test_asana.py, tests/unit/test_asana_commands.py]
  Data flow: Asana(token) or ASANA_ACCESS_TOKEN → _request(path, params) GETs https://app.asana.com/api/1.0<path> with `Authorization: Bearer <token>` → Asana's whole reply ({data, next_page, ...}) → get_user() returns its `data`; list_projects()/list_tasks()/list_stories() follow next_page through _paginate() to the end, then list_tasks() filters locally; get_task() returns one task's `data`
  State/Effects: reads ASANA_ACCESS_TOKEN | network only, read-only; nothing here writes to Asana
  Integration: exposes Asana with get_user(user="me" | gid | email), list_projects(workspace_gid), list_tasks(project_gid, filters), get_task(task_gid), list_stories(task_gid), is_comment(story), story_time(story), due_day(task) so the CLI shows the same due day the filters compare, and local_time(value) for times shown in this machine's zone | gids are always requested and stay strings, and records keep Asana's own field names and order, so listings, account binding, exports and co rem can cite them | CLI row numbers and names never reach these methods: they take gids only
  Errors: AsanaError(message, next_step, status, read_count) for a missing or rejected token, an Asana error reply, a reply that is not JSON or not the shape asked for, and a connection that fails or times out; a 429 is waited out (Retry-After, at most 3 retries, at most a minute of waiting in all) before it becomes one | a list is all or nothing: a page that fails mid-way raises with read_count, never a short list | ValueError for a gid or filter the caller got wrong, before anything is sent

Asana tool: read your Asana account with a personal access token.

Usage:
    from connectonion.useful_tools.asana import Asana
    me = Asana().get_user()          # {"gid": ..., "name": ..., "email": ..., "workspaces": [...]}
    projects = Asana().list_projects(me["workspaces"][0]["gid"])
    open_tasks = Asana().list_tasks(projects[0]["gid"], completed=False)
    task = Asana().get_task(open_tasks[0]["gid"])
    comments = [s for s in Asana().list_stories(task["gid"]) if is_comment(s)]
"""

from datetime import date, datetime, tzinfo
from time import sleep
from urllib.parse import quote

import httpx

URL = "https://app.asana.com/api/1.0"
KEY = "ASANA_ACCESS_TOKEN"
TOKEN_PAGE = "https://app.asana.com/0/my-apps"
SET_KEY = f"co env set {KEY} <pat> --secret"
TIMEOUT = 30

# What `co asana check` shows: one /users/me call answers both "who am I" and
# "which workspaces", so check never reports half a success. gids are asked for
# by name even where Asana sends them anyway: listings and account binding use them.
USER_FIELDS = "gid,name,email,workspaces.gid,workspaces.name"

# What `co asana projects` and `co asana tasks` show and later stories cite. Nested
# gids are asked for by name so a task keeps who it is assigned to and where it lives.
# A project's team tells apart same-named projects when a name is refused as ambiguous.
# Other fields (notes, owner, members, ...) are added by the story that needs them.
PROJECT_FIELDS = ("gid,name,archived,modified_at,permalink_url,"
                  "workspace.gid,workspace.name,team.gid,team.name")
TASK_FIELDS = ("gid,name,completed,due_on,due_at,modified_at,permalink_url,"
               "assignee.gid,assignee.name,projects.gid,projects.name")

# What `co asana task` shows: the list fields plus the description (Asana calls it
# notes), who follows the task, its custom fields as Asana displays them, and where
# and when it was made. Story fields keep who wrote what and when; the type tells a
# comment from system activity, which stays even when it has no text.
TASK_DETAIL_FIELDS = (TASK_FIELDS + ",notes,created_at,completed_at,workspace.gid,workspace.name,"
                      "followers.gid,followers.name,custom_fields.gid,custom_fields.name,custom_fields.display_value")
STORY_FIELDS = "gid,created_at,created_by.gid,created_by.name,text,type,resource_subtype,target.gid,target.name"

# Asana's largest page. A list is read to the end however long it is; a cap
# here would silently drop tasks, so the only bound is a repeated offset.
PAGE_SIZE = 100

# Asana's rate limit replies 429 with Retry-After in seconds. Wait it out a few
# times, but never more than a minute in all; past that it is reported instead,
# so a command never hangs.
RETRIES = 3
LONGEST_WAIT = 60


class AsanaError(Exception):
    """What went wrong, and the one command that fixes or explains it."""

    def __init__(self, message: str, next_step: str, *, status: int | None = None, read_count: int | None = None):
        super().__init__(message)
        self.next_step = next_step
        self.status = status
        self.read_count = read_count      # records read before a list failed part way; for the message only


def _http() -> httpx.Client:
    """The HTTP client; tests swap in httpx.MockTransport here."""
    return httpx.Client(timeout=TIMEOUT)


def _token() -> str:
    """ASANA_ACCESS_TOKEN from the process, the selected env file, then `co env set --secret`'s store."""
    from ..environment import display_path, load_environment, selected_env_file, setting
    load_environment()
    token = (setting(KEY) or "").strip()
    if token:
        return token
    raise AsanaError(f"{KEY} is not set in {display_path(selected_env_file())}. "
                     f"Create a personal access token at {TOKEN_PAGE}, then save it", SET_KEY)


class Asana:
    """Your Asana account, read with a personal access token."""

    def __init__(self, token: str | None = None):
        # Resolving the token here fails fast; nothing is sent until a method asks.
        self._token = (token or "").strip() or _token()

    def get_user(self, user: str = "me") -> dict:
        """A user by "me", gid or email, with the workspaces they belong to. Read-only.

        An email works as the path, as GET /users/{email} answered on 2026-10-07.
        """
        if user != "me":
            user = _email(user) if "@" in user else _gid(user, "user")
        found = self._request(f"/users/{quote(user, safe='')}", {"opt_fields": USER_FIELDS})["data"]
        # Callers read every field below; a reply of another shape fails here, not as a traceback there.
        if not _is_user(found):
            raise AsanaError(f"Asana answered /users/{user} without a user", "co asana check")
        return found

    def list_projects(self, workspace_gid: str) -> list[dict]:
        """Every project in a workspace, archived ones included, in Asana's order. Read-only."""
        params = {"workspace": _gid(workspace_gid, "workspace"), "opt_fields": PROJECT_FIELDS}
        return self._paginate("/projects", params, _is_project, "project")

    def list_tasks(self, project_gid: str, *, assignee_gid: str | None = None, completed: bool | None = None,
                   due_from: date | None = None, due_to: date | None = None,
                   modified_since: datetime | None = None) -> list[dict]:
        """A project's tasks, read to the last page, then filtered here. None means "do not filter". Read-only.

        completed=False asks Asana for completed_since=now to read fewer tasks,
        and still keeps only completed == False: Asana also returns tasks
        completed after that moment. Due dates compare the task's day (due_on,
        or the local day of due_at, as Asana shows it), both ends included; a
        task with no due date is left out whenever a due filter is given.
        """
        _check_filters(assignee_gid, completed, due_from, due_to, modified_since)
        params = {"project": _gid(project_gid, "project"), "opt_fields": TASK_FIELDS}
        if completed is False:
            params["completed_since"] = "now"
        if modified_since is not None:
            params["modified_since"] = modified_since.isoformat()
        tasks = self._paginate("/tasks", params, _is_task, "task")
        return [t for t in tasks if _keeps(t, assignee_gid, completed, due_from, due_to)]

    def get_task(self, task_gid: str) -> dict:
        """One task as it is now: description, assignee, followers, due date, projects, custom fields. Read-only.

        Comments and activity are not read here; list_stories() reads them.
        """
        path = f"/tasks/{quote(_gid(task_gid, 'task'), safe='')}"
        try:
            found = self._request(path, {"opt_fields": TASK_DETAIL_FIELDS})["data"]
        except AsanaError as error:
            raise _unseen_task(error, task_gid) from None
        if not _is_task_detail(found):
            raise AsanaError(f"Asana answered /tasks/{task_gid} without a task", "co asana check")
        return found

    def list_stories(self, task_gid: str) -> list[dict]:
        """Every story on a task, comments and system activity, in the order Asana returns them. Read-only.

        Records stay as Asana sent them, order included; story_time() lets a caller sort them.
        """
        path = f"/tasks/{quote(_gid(task_gid, 'task'), safe='')}/stories"
        try:
            found = self._paginate(path, {"opt_fields": STORY_FIELDS}, _is_story, "story")
        except AsanaError as error:
            raise _unseen_task(error, task_gid) from None
        return found

    def _paginate(self, path: str, params: dict, is_record, kind: str) -> list[dict]:
        """Every page of a list, or an AsanaError saying how many records were read before it failed."""
        records, offset, seen = [], None, set()
        while True:
            page = {**params, "limit": PAGE_SIZE, **({"offset": offset} if offset else {})}
            try:
                body = self._request(path, page)
                records += _page_records(body, is_record, kind)
                offset = _next_offset(body, seen)
            except AsanaError as error:
                error.read_count = len(records)
                if records:
                    error.args = (f"{error} (stopped after {len(records)} {kind}s; nothing was listed)",)
                raise
            if offset is None:
                return records

    def _request(self, path: str, params: dict | None = None) -> dict:
        """GET one Asana path; return Asana's whole reply, so a list can follow `next_page`."""
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        waited = 0
        with _http() as client:
            for attempt in range(RETRIES + 1):
                response = _send(client, path, params, headers)
                if response.status_code != 429 or attempt == RETRIES:
                    break
                seconds = _wait(response, waited)
                sleep(seconds)
                waited += seconds
        return _body(response)


def _is_user(found) -> bool:
    """A user with a gid; name and email text or null; each workspace with a gid and a text or null name."""
    if not (isinstance(found, dict) and _is_gid(found.get("gid"))
            and all(_is_text(found.get(key)) for key in ("name", "email"))):
        return False
    workspaces = found.get("workspaces", [])
    return isinstance(workspaces, list) and all(
        isinstance(w, dict) and _is_gid(w.get("gid")) and _is_text(w.get("name")) for w in workspaces)


def _is_project(found) -> bool:
    return isinstance(found, dict) and _is_gid(found.get("gid")) and _is_text(found.get("name"))


# Fields list_tasks() filters on. They must be present, not just well typed: a
# missing `completed` would read as "open", a missing assignee as "unassigned".
FILTERED_TASK_FIELDS = ("completed", "assignee", "due_on", "due_at")


def _is_task(found) -> bool:
    """A task with a gid; every field the filters read is present and of Asana's documented type or null."""
    if not (isinstance(found, dict) and _is_gid(found.get("gid")) and _is_text(found.get("name"))
            and all(key in found for key in FILTERED_TASK_FIELDS)):
        return False
    assignee = found["assignee"]
    return (isinstance(found["completed"], bool)
            and (assignee is None or (isinstance(assignee, dict) and _is_gid(assignee.get("gid"))))
            and _is_day(found["due_on"]) and _is_moment(found["due_at"]))


def _is_task_detail(found) -> bool:
    """A task as _is_task; notes and the link text or null; its workspace null or an object with a gid;
    followers, projects and custom fields, when present, lists of objects with a gid."""
    if not (_is_task(found) and _is_text(found.get("notes")) and _is_text(found.get("permalink_url"))):
        return False
    workspace = found.get("workspace")
    return ((workspace is None or (isinstance(workspace, dict) and _is_gid(workspace.get("gid"))))
            and all(_is_gid_list(found.get(key, [])) for key in ("followers", "projects", "custom_fields")))


def _is_gid_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, dict) and _is_gid(v.get("gid")) for v in value)


def _is_story(found) -> bool:
    """A story with a gid, a type and a time with its zone; its author, when present, has a gid; text may be missing (system activity)."""
    if not (isinstance(found, dict) and _is_gid(found.get("gid")) and isinstance(found.get("type"), str)
            and isinstance(found.get("created_at"), str) and _is_moment(found["created_at"])):
        return False
    author = found.get("created_by")
    return (author is None or (isinstance(author, dict) and _is_gid(author.get("gid")))) and _is_text(found.get("text"))


def story_time(story: dict) -> datetime:
    """When a story happened, as a time with its zone; _is_story has already checked created_at."""
    return datetime.fromisoformat(story["created_at"].replace("Z", "+00:00"))


def _unseen_task(error: "AsanaError", task_gid: str) -> "AsanaError":
    """A 404 on a task says what it can mean: no such task, or one this token cannot see. Nothing says it was deleted."""
    if error.status != 404:
        return error
    cause = str(error).removeprefix("Asana: ")
    return AsanaError(f"No Asana task {task_gid}, or this token cannot see it ({cause})",
                      'co asana tasks "<project>"', status=404, read_count=error.read_count)


def is_comment(story: dict) -> bool:
    """A comment someone wrote, as opposed to activity Asana recorded (assigned, completed, ...)."""
    return story.get("type") == "comment" or story.get("resource_subtype") == "comment_added"


def _is_day(value) -> bool:
    if value is None:
        return True
    try:
        return isinstance(value, str) and bool(date.fromisoformat(value))
    except ValueError:
        return False


def _is_moment(value) -> bool:
    """null, or an ISO 8601 time with a zone, as Asana sends due_at ("…Z")."""
    if value is None:
        return True
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _page_records(body: dict, is_record, kind: str) -> list[dict]:
    data = body["data"]
    if not (isinstance(data, list) and all(is_record(item) for item in data)):
        raise AsanaError(f"Asana answered a {kind} list that is not a list of {kind}s", "co asana check")
    return data


def _next_offset(body: dict, seen: set) -> str | None:
    """The next page's offset, None on the last page; a repeated or malformed one is an error, not a loop."""
    # Asana answers every limited list with next_page, null on the last page; a page
    # without the key is not known to be the last one, so it is not taken as the end.
    if "next_page" not in body:
        raise AsanaError("Asana answered a list page without next_page", "co asana check")
    next_page = body["next_page"]
    if next_page is None:
        return None
    offset = next_page.get("offset") if isinstance(next_page, dict) else None
    if not isinstance(offset, str) or not offset or offset in seen:
        raise AsanaError("Asana answered a list whose next page cannot be followed", "co asana check")
    seen.add(offset)
    return offset


def _gid(value, kind: str) -> str:
    """A gid as Asana gives it; never a CLI row number or a name, which the CLI resolves first."""
    if not _is_gid(value) or any(c.isspace() for c in value):
        raise ValueError(f"Not an Asana {kind} gid: {value!r}")
    return value


def is_email(value) -> bool:
    """Enough of an address to send as a path: one @, text on both sides, no spaces."""
    return (isinstance(value, str) and value.count("@") == 1 and "@" not in (value[0], value[-1])
            and not any(c.isspace() for c in value))


def _email(value: str) -> str:
    if not is_email(value):
        raise ValueError(f"Not an email address: {value!r}")
    return value


def _check_filters(assignee_gid, completed, due_from, due_to, modified_since) -> None:
    if assignee_gid is not None:
        _gid(assignee_gid, "user")
    if completed is not None and not isinstance(completed, bool):
        raise ValueError("completed must be True, False or None")
    for name, day in (("due_from", due_from), ("due_to", due_to)):
        if day is not None and (not isinstance(day, date) or isinstance(day, datetime)):
            raise ValueError(f"{name} must be a date (YYYY-MM-DD), not {day!r}")
    if due_from and due_to and due_from > due_to:
        raise ValueError(f"due_from {due_from} is after due_to {due_to}")
    if modified_since is not None and (not isinstance(modified_since, datetime) or modified_since.tzinfo is None):
        raise ValueError("modified_since must be a datetime with a time zone, e.g. 2026-10-01T00:00:00+11:00")


def _keeps(task: dict, assignee_gid, completed, due_from, due_to) -> bool:
    if assignee_gid is not None and (task.get("assignee") or {}).get("gid") != assignee_gid:
        return False
    if completed is not None and task.get("completed") is not completed:
        return False
    if due_from is None and due_to is None:
        return True
    day = due_day(task)
    return day is not None and (due_from is None or day >= due_from) and (due_to is None or day <= due_to)


def due_day(task: dict) -> date | None:
    """The day a task is due: due_on, or the local day of due_at when only a time is set.

    Local, not UTC: 09:30 on 7 Oct in Sydney is stored as 2026-10-06T22:30Z,
    and --due-from 2026-10-07 has to find it, as Asana's own view would.
    """
    if task.get("due_on"):
        return date.fromisoformat(task["due_on"])
    if task.get("due_at"):
        return datetime.fromisoformat(task["due_at"].replace("Z", "+00:00")).astimezone(_local_zone()).date()
    return None


def local_time(value) -> datetime | None:
    """An Asana time (created_at, modified_at, ...) in this machine's zone; None when missing or not a time with a zone."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(_local_zone()) if moment.tzinfo else None


def _local_zone() -> tzinfo:
    """This machine's time zone; tests pin it here so a due day does not depend on where they run."""
    return datetime.now().astimezone().tzinfo


def _is_gid(value) -> bool:
    return isinstance(value, str) and value != ""


def _is_text(value) -> bool:
    return value is None or isinstance(value, str)


def _send(client: httpx.Client, path: str, params: dict | None, headers: dict) -> httpx.Response:
    try:
        return client.get(URL + path, params=params, headers=headers)
    except httpx.TimeoutException:
        raise AsanaError(f"Asana did not answer within {TIMEOUT} s", "co asana check") from None
    except httpx.TransportError:
        raise AsanaError("Could not reach Asana. Check your connection, then retry", "co asana check") from None


def _wait(response: httpx.Response, waited: int) -> int:
    """Seconds Asana asked for; past a minute of waiting in all, it is reported rather than waited."""
    header = response.headers.get("Retry-After", "")
    seconds = int(header) if header.isdigit() else 1
    if waited + seconds > LONGEST_WAIT:
        raise AsanaError(f"Asana asked to wait {seconds} s before the next request (HTTP 429). "
                         "Try again later", "co asana check", status=429)
    return seconds


def _body(response: httpx.Response) -> dict:
    """A successful reply as Asana sent it; any other reply becomes an AsanaError with Asana's own message."""
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        raise AsanaError(f"Asana answered HTTP {status} without JSON", "co asana check", status=status) from None
    if status == 200 and isinstance(body, dict) and "data" in body:
        return body
    message = _message(body)
    if status == 401:
        raise AsanaError(f"Asana rejected {KEY}: {message}. Make a new token at {TOKEN_PAGE}", SET_KEY, status=401)
    if status == 429:
        raise AsanaError(f"Asana says too many requests (HTTP 429): {message}. Wait a minute, then retry",
                         "co asana check", status=429)
    raise AsanaError(f"Asana: {message} (HTTP {status})", "co asana check", status=status)


def _message(body) -> str:
    errors = body.get("errors") if isinstance(body, dict) else None
    if (isinstance(errors, list) and errors and isinstance(errors[0], dict)
            and isinstance(errors[0].get("message"), str) and errors[0]["message"]):
        return errors[0]["message"].rstrip(".")
    return "unexpected reply"

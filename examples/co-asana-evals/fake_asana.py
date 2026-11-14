"""A synthetic Asana workspace the real `co asana` commands talk to in these evals.

Nothing here reaches app.asana.com. `run()` executes the real Typer command in
this process with three seams replaced, the same ones tests/unit/test_asana.py
uses: the HTTP client (answered from a workspace JSON file), the token (a fake
one, or none for the missing-token case) and the row-number cache directory.
Writes change only this in-memory workspace, so `co asana task` after
`co asana update --yes` shows the change, as it would in Asana.
"""

import copy
import json
import shlex
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlparse

import httpx

TOKEN = "fake-eval-token"


class Workspace:
    """One workspace's users, projects, tasks and stories, read from a JSON file."""

    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)
        self.sent = []          # every write Asana received: (method, path, fields)
        self._next = 900000000000001
        # Data-driven faults, so a case needs no flag: see "faults" in the workspace file.
        self.faults = self.data.get("faults", {})
        self._failed_once = set()

    @classmethod
    def load(cls, path) -> "Workspace":
        return cls(json.loads(Path(path).read_text()))

    # -- HTTP --------------------------------------------------------------------
    def respond(self, request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        path = unquote(url.path.split("/api/1.0", 1)[-1])
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        parts = [p for p in path.split("/") if p]
        if request.method == "GET" and parts[:1] == ["users"]:
            return self._user(parts[1])
        if request.method == "GET" and parts == ["projects"]:
            return _page([p for p in self.data["projects"] if p["workspace"]["gid"] == query.get("workspace")])
        if request.method == "GET" and parts == ["tasks"]:
            project = query.get("project")
            if project in self.faults.get("rate_limited_projects", []):
                return httpx.Response(429, headers={"Retry-After": "30"},
                                      json={"errors": [{"message": "You have made too many requests recently"}]})
            tasks = [_listed(t) for t in self.data["tasks"] if any(p["gid"] == project for p in t["projects"])]
            if project in self.faults.get("second_page_fails_once", []):
                # Two pages; the second fails the first time it is asked for, then works.
                if query.get("offset") != "page2":
                    return httpx.Response(200, json={"data": tasks[:1], "next_page": {"offset": "page2"}})
                if project not in self._failed_once:
                    self._failed_once.add(project)
                    return httpx.Response(500, json={"errors": [{"message": "Server Error"}]})
                return _page(tasks[1:])
            return _page(tasks)
        task = self._task(parts[1]) if parts[:1] == ["tasks"] and len(parts) >= 2 else None
        if task is None:
            return httpx.Response(404, json={"errors": [{"message": f"{path}: Unknown object"}]})
        if len(parts) == 2 and request.method == "GET":
            return httpx.Response(200, json={"data": task})
        if len(parts) == 2 and request.method == "PUT":
            fields = json.loads(request.content)["data"]
            self.sent.append(("PUT", path, fields))
            if "completed" in fields:
                task["completed"] = fields["completed"]
                task["completed_at"] = self.data["now"] if fields["completed"] else None
                self._story(task, f"{self.me()['name']} marked this task "
                                  + ("complete" if fields["completed"] else "incomplete"), "system")
            if "due_on" in fields:
                task["due_on"] = fields["due_on"]
                self._story(task, f"{self.me()['name']} changed the due date to {fields['due_on']}", "system")
            task["modified_at"] = self.data["now"]
            return httpx.Response(200, json={"data": task})
        if parts[2:] == ["stories"] and request.method == "GET":
            return _page(self.data["stories"].get(task["gid"], []))
        if parts[2:] == ["stories"] and request.method == "POST":
            fields = json.loads(request.content)["data"]
            self.sent.append(("POST", path, fields))
            story = self._story(task, fields["text"], "comment")
            task["modified_at"] = self.data["now"]
            if task["gid"] in self.faults.get("writes_saved_but_answer_500", []):
                # Saved, but the answer is lost: the CLI cannot know whether it was posted.
                return httpx.Response(500, json={"errors": [{"message": "Server Error"}]})
            return httpx.Response(201, json={"data": story})
        return httpx.Response(400, json={"errors": [{"message": "Not supported by the eval fake"}]})

    def me(self) -> dict:
        return self.data["me"]

    def _user(self, who: str) -> httpx.Response:
        if who in ("me", self.me()["gid"], self.me().get("email")):
            return httpx.Response(200, json={"data": self.me()})
        for user in self.data.get("users", []):
            if who in (user["gid"], user.get("email")):
                return httpx.Response(200, json={"data": {**user, "workspaces": self.me()["workspaces"]}})
        return httpx.Response(404, json={"errors": [{"message": f"user: Unknown object: {who}"}]})

    def _task(self, gid: str):
        return next((t for t in self.data["tasks"] if t["gid"] == gid), None)

    def _story(self, task: dict, text: str, kind: str) -> dict:
        self._next += 1
        me = self.me()
        story = {"gid": str(self._next), "created_at": self.data["now"],
                 "created_by": {"gid": me["gid"], "name": me["name"]}, "text": text,
                 "type": kind, "resource_subtype": "comment_added" if kind == "comment" else "marked_complete",
                 "target": {"gid": task["gid"], "name": task["name"]}}
        self.data["stories"].setdefault(task["gid"], []).append(story)
        return story


LIST_FIELDS = ("gid", "name", "completed", "due_on", "due_at", "modified_at", "permalink_url", "assignee", "projects")


def _listed(task: dict) -> dict:
    return {k: task.get(k) for k in LIST_FIELDS}


def _page(records) -> httpx.Response:
    return httpx.Response(200, json={"data": records, "next_page": None})


def run(command: str, workspace: Workspace, listings: Path, *, token: bool = True, stdin: str | None = None) -> str:
    """Run one `co asana ...` command line against the workspace; return what a terminal would show."""
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.cli.commands import asana_commands
    from connectonion.useful_tools import asana

    try:
        words = shlex.split(command)
    except ValueError as error:
        return f"$ {command}\nthe shell could not parse this line: {error}\n[exit 2]"
    if words[:2] != ["co", "asana"]:
        return f"$ {command}\nrefused: only `co asana ...` commands run in this terminal\n[exit 2]"

    def no_token():
        raise asana.AsanaError(f"{asana.KEY} is not set in ~/.co/keys.env. Create a personal access token at "
                               f"{asana.TOKEN_PAGE}, then save it", asana.SET_KEY)

    with ExitStack() as stack:
        stack.enter_context(patch.object(asana, "_http",
                                         lambda: httpx.Client(transport=httpx.MockTransport(workspace.respond))))
        stack.enter_context(patch.object(asana, "_token", (lambda: TOKEN) if token else no_token))
        stack.enter_context(patch.object(asana, "sleep", lambda seconds: None))
        stack.enter_context(patch.object(asana_commands, "_listings", lambda: listings))
        result = CliRunner().invoke(app, words[1:], input=stdin, prog_name="co",
                                    env={"NO_COLOR": "1", "COLUMNS": "120"})
    shown = (result.stdout or "") + (result.stderr or "")
    return f"$ {command}\n{shown.rstrip()}\n[exit {result.exit_code}]"


def new_listings() -> Path:
    return Path(tempfile.mkdtemp(prefix="asana-listings-"))

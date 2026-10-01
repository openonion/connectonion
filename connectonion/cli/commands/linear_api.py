"""
Purpose: Linear's GraphQL API for `co linear` — explicit field selection, and names resolved to ids
LLM-Note:
  Dependencies: imports from [httpx, environment.py (setting: process, env file, then the --secret store)] | imported by [cli/commands/linear_commands.py] | tested by [tests/unit/test_linear_commands.py, tests/e2e/real_api/test_real_co_linear.py]
  Data flow: api_key() = environment.setting(LINEAR_API_KEY) → graphql(query, variables) POSTs https://api.linear.app/graphql with `Authorization: <key>` → data dict | resolvers turn a team key, state, label, priority or "me"/email into the id a mutation takes
  State/Effects: reads LINEAR_API_KEY | network only; mutations are called by linear_commands.py after --yes
  Integration: fields are the ones an agent acts on (id, title, state, assignee, priority, updated); `row()` is the one shape lists print and --json returns
  Errors: LinearError(message, next_step) for a missing or rejected key, a GraphQL error and an unknown name; the CLI prints both and exits 1. Network failures and non-JSON responses raise as they are
"""

import httpx

URL = "https://api.linear.app/graphql"
KEY = "LINEAR_API_KEY"
KEY_PAGE = "Linear Settings → Security & access → Personal API keys"
SET_KEY = f"co env set {KEY} lin_api_... --secret"

# Linear's own numbers; --priority takes either.
PRIORITIES = {"none": 0, "urgent": 1, "high": 2, "medium": 3, "low": 4}

ISSUE_FIELDS = "identifier title priority priorityLabel updatedAt state { name } assignee { name email }"


class LinearError(Exception):
    """What went wrong, and the one command that fixes or explains it."""

    def __init__(self, message: str, next_step: str, kind: str = ""):
        super().__init__(message)
        self.next_step = next_step
        self.kind = kind


def api_key() -> str:
    """LINEAR_API_KEY from the process, the selected env file, then `co env set --secret`'s store."""
    from ...environment import display_path, load_environment, selected_env_file, setting
    load_environment()
    key = setting(KEY)
    if key:
        return key
    raise LinearError(f"{KEY} is not set in {display_path(selected_env_file())}. "
                      f"Create a personal API key in {KEY_PAGE}, then save it", SET_KEY)


def _http() -> httpx.Client:
    """The HTTP client; tests swap in httpx.MockTransport here."""
    return httpx.Client(timeout=30)


def graphql(query: str, variables: dict | None = None) -> dict:
    """POST one query or mutation; return its data, or raise LinearError with Linear's own message."""
    key = api_key()
    with _http() as client:
        response = client.post(URL, json={"query": query, "variables": variables or {}},
                               headers={"Authorization": key, "Content-Type": "application/json"})
    if "json" not in response.headers.get("content-type", ""):
        response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise _error(body["errors"], response.status_code)
    response.raise_for_status()
    return body["data"]


def _error(errors: list, status: int) -> LinearError:
    first = errors[0]
    extensions = first.get("extensions") or {}
    message = (extensions.get("userPresentableMessage") or first.get("message", "unknown error")).rstrip(".")
    kind = f"{extensions.get('type', '')} {extensions.get('code', '')}".lower()
    if status == 401 or "authentication" in kind:
        return LinearError(f"Linear rejected {KEY}: {message}. Make a new key in {KEY_PAGE}", SET_KEY)
    said = f"{first.get('message', '')} {message}".lower()
    missing = "not found" in said or "could not find" in said
    return LinearError(f"Linear: {message}", "co linear check", "not_found" if missing else "")


def row(node: dict) -> dict:
    """The fields every list prints and --json returns."""
    return {
        "id": node["identifier"],
        "title": node["title"],
        "state": node["state"]["name"],
        "assignee": (node.get("assignee") or {}).get("name"),
        "priority": node["priorityLabel"],
        "updated": node["updatedAt"],
    }


def _unknown(kind: str, given: str, valid: list, list_command: str) -> LinearError:
    names = ", ".join(sorted(set(valid))) or "none"
    return LinearError(f"No {kind} {given!r}. Valid: {names}", list_command)


# -- reads -----------------------------------------------------------------

def issue(identifier: str) -> dict:
    """One issue with what `co linear issue` shows; ENG-123 is accepted as Linear's issue id."""
    query = """query($id: String!) { issue(id: $id) {
      id identifier title description url createdAt updatedAt priority priorityLabel
      state { name } assignee { name email } team { id key name } project { name }
      labels(first: 50) { nodes { name } }
      comments(first: 50) { nodes { body createdAt user { name } } } } }"""
    try:
        return graphql(query, {"id": identifier})["issue"]
    except LinearError as error:
        if error.kind == "not_found":
            raise LinearError(f"No issue {identifier} in this workspace", 'co linear search "<words from its title>"') from None
        raise


def issues(filter: dict, first: int) -> list:
    query = f"""query($filter: IssueFilter, $first: Int) {{
      issues(filter: $filter, first: $first, orderBy: updatedAt) {{ nodes {{ {ISSUE_FIELDS} }} }} }}"""
    return graphql(query, {"filter": filter, "first": first})["issues"]["nodes"]


def search(term: str, first: int) -> list:
    query = f"""query($term: String!, $first: Int) {{
      searchIssues(term: $term, first: $first) {{ nodes {{ {ISSUE_FIELDS} }} }} }}"""
    return graphql(query, {"term": term, "first": first})["searchIssues"]["nodes"]


def teams() -> list:
    return graphql("query { teams(first: 250) { nodes { id key name } } }")["teams"]["nodes"]


def projects(team_id: str | None) -> list:
    fields = "nodes { name url updatedAt status { name } teams(first: 10) { nodes { key } } }"
    if team_id:
        query = f"query($id: String!) {{ team(id: $id) {{ projects(first: 250) {{ {fields} }} }} }}"
        return graphql(query, {"id": team_id})["team"]["projects"]["nodes"]
    return graphql(f"query {{ projects(first: 250) {{ {fields} }} }}")["projects"]["nodes"]


def states(team_id: str | None) -> list:
    fields = "nodes { id name type position team { key } }"
    if team_id:
        query = f"query($id: String!) {{ team(id: $id) {{ states(first: 250) {{ {fields} }} }} }}"
        return graphql(query, {"id": team_id})["team"]["states"]["nodes"]
    return graphql(f"query {{ workflowStates(first: 250) {{ {fields} }} }}")["workflowStates"]["nodes"]


def labels(team_id: str | None) -> list:
    """Workspace labels, plus one team's own when team_id is given (all teams' when not)."""
    found = graphql("query { issueLabels(first: 250) { nodes { id name isGroup team { id key } } } }")
    nodes = [label for label in found["issueLabels"]["nodes"] if not label["isGroup"]]
    if team_id:
        return [label for label in nodes if label["team"] is None or label["team"]["id"] == team_id]
    return nodes


def users() -> list:
    found = graphql("query { users(first: 250) { nodes { id name email active } } }")
    return [user for user in found["users"]["nodes"] if user["active"]]


def whoami() -> dict:
    return graphql("query { viewer { id name email } organization { name urlKey } }")


# -- names to ids ----------------------------------------------------------

def team(key: str) -> dict:
    """A team by its key (ENG) or exact name."""
    all_teams = teams()
    for found in all_teams:
        if key.lower() in (found["key"].lower(), found["name"].lower()):
            return found
    raise _unknown("team", key, [t["key"] for t in all_teams], "co linear teams")


def state(team_found: dict, name: str) -> dict:
    team_states = states(team_found["id"])
    for found in team_states:
        if found["name"].lower() == name.lower():
            return found
    raise _unknown(f"state in {team_found['key']}", name, [s["name"] for s in team_states],
                   f"co linear states --team {team_found['key']}")


def state_name(name: str, team_found: dict | None) -> str:
    """A state name as Linear spells it, from one team's states or any team's."""
    if team_found:
        return state(team_found, name)["name"]
    all_names = [s["name"] for s in states(None)]
    for found in all_names:
        if found.lower() == name.lower():
            return found
    raise _unknown("state", name, all_names, "co linear states")


def project_name(name: str) -> str:
    all_names = [p["name"] for p in projects(None)]
    for found in all_names:
        if found.lower() == name.lower():
            return found
    raise _unknown("project", name, all_names, "co linear projects")


def label_ids(team_found: dict, names: list) -> list:
    available = labels(team_found["id"])
    by_name = {label["name"].lower(): label for label in available}
    for name in names:
        if name.lower() not in by_name:
            raise _unknown(f"label in {team_found['key']}", name, [l["name"] for l in available],
                           f"co linear labels --team {team_found['key']}")
    return [by_name[name.lower()] for name in names]


def user(spec: str) -> dict:
    """'me' or a member's email."""
    if spec.lower() == "me":
        return whoami()["viewer"]
    members = users()
    for found in members:
        if found["email"].lower() == spec.lower():
            return found
    raise _unknown("member with email", spec, [u["email"] for u in members], "co linear users")


def priority(value: str, command: str) -> int:
    """0-4 or Linear's word for it (none, urgent, high, medium, low)."""
    if value.isdigit() and int(value) in PRIORITIES.values():
        return int(value)
    if value.lower() in PRIORITIES:
        return PRIORITIES[value.lower()]
    valid = [f"{number} {word}" for word, number in PRIORITIES.items()]
    raise LinearError(f"No priority {value!r}. Valid: {', '.join(valid)}", f"co linear {command} --help")


def priority_word(number: int) -> str:
    return {0: "No priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}[number]


# -- writes ----------------------------------------------------------------

def create_issue(fields: dict) -> dict:
    query = """mutation($input: IssueCreateInput!) { issueCreate(input: $input) {
      success issue { identifier title url } } }"""
    return graphql(query, {"input": fields})["issueCreate"]["issue"]


def update_issue(issue_id: str, fields: dict) -> dict:
    query = f"""mutation($id: String!, $input: IssueUpdateInput!) {{ issueUpdate(id: $id, input: $input) {{
      success issue {{ url {ISSUE_FIELDS} }} }} }}"""
    return graphql(query, {"id": issue_id, "input": fields})["issueUpdate"]["issue"]


def create_comment(issue_id: str, body: str) -> dict:
    query = """mutation($input: CommentCreateInput!) { commentCreate(input: $input) {
      success comment { id url } } }"""
    return graphql(query, {"input": {"issueId": issue_id, "body": body}})["commentCreate"]["comment"]

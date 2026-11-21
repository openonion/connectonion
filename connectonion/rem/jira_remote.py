"""Read approved Jira scopes through the existing incremental transaction."""
import re

from .files import RemError
from .remote_sources import directory

CREDENTIALS = ("JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")


def validate(value):
    if not isinstance(value, dict) or set(value) - {"project", "issues", "history"}:
        raise RemError("Jira selection accepts project, issues and history only; never credentials")
    project, keys = value.get("project"), value.get("issues", [])
    if not isinstance(project, str) or not re.fullmatch(r"[A-Z][A-Z0-9]*", project):
        raise RemError("Jira selection needs an uppercase project key")
    if (not isinstance(keys, list) or len(keys) > 1000
            or any(not isinstance(key, str) or not re.fullmatch(re.escape(project) + r"-\d+", key) for key in keys)
            or type(value.get("history", True)) is not bool):
        raise RemError("Jira issues must be keys inside the selected project; history must be true or false")
    return {"project": project, "issues": sorted(set(keys)), "history": value.get("history", True)}


def configure(root, chosen):
    from ..useful_tools.jira import Jira
    from ..useful_tools.jira_checkpoint import _normalize_scope, _write_source_yaml_v2
    from .jira_imports import identity
    from .remote_sources import require_saved
    require_saved("JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
    client = Jira()
    verified = client.verify_connection()
    project_metadata = client._get("project/" + chosen["project"])
    if not isinstance(project_metadata, dict) or project_metadata.get("key") != chosen["project"]:
        raise RemError("Jira project is inaccessible or has different metadata; check co jira projects")
    for key in chosen["issues"]:
        metadata = client._get("issue/" + key, fields="project")
        fields = metadata.get("fields") if isinstance(metadata, dict) else None
        project = fields.get("project") if isinstance(fields, dict) else None
        if (not isinstance(metadata, dict) or metadata.get("key") != key
                or not isinstance(project, dict) or project.get("key") != chosen["project"]):
            raise RemError("Selected Jira issue is inaccessible or outside the selected project")
    _write_source_yaml_v2(directory(root, "jira"), "jira", verified["site_url"], verified["accountId"],
                          _normalize_scope(chosen["project"], chosen["issues"]))
    return identity(root)


def refresh(root, source, chosen):
    from ..useful_tools.jira_checkpoint import run_jira_sync
    declared = source["import_identity"]
    if declared["projects"] != [chosen["project"]] or declared["issues"] != chosen["issues"]:
        raise RemError("Jira selection differs from the approved declaration; reconnect")
    result = run_jira_sync(chosen["project"], issue_keys=chosen["issues"] or None, history=chosen["history"],
                           state_dir=root / ".state/jira-cli", output_dir=directory(root, "jira"), lock_held=True, require_selected_first=True)
    if result.exit_code == 0:
        # The normal mapper makes only missing stubs and preserves authored pages.
        # New assignees/projects must be usable by this same background sync.
        from .jira_imports import map_jira
        map_jira(root, source, {"created": [], "people": [], "projects": [], "coverage": []})
    return {"complete": result.exit_code == 0, "written": result.net_new_records,
            **({"error_type": result.error_code or "partial"} if result.exit_code else {})}


def choose_scope():
    """List titles/keys only; never use body-bearing issue_items for setup."""
    import typer
    from ..useful_tools.jira import Jira, JiraConfigError
    from .remote_wizard import pick
    try:
        client = Jira()
    except JiraConfigError as error:
        # Constructor messages are fixed local diagnostics; never provider text.
        raise RemError(str(error)) from None
    client.verify_connection()
    project = pick(client.project_items(), "Jira project", key="key")
    if typer.confirm("Read all current and future issues in this project?", default=False):
        issues = []
    else:
        rows, token, seen = [], None, set()
        for _ in range(20):
            page = client._get("search/jql", jql=f'project = "{validate({"project": project})["project"]}" ORDER BY key ASC',
                               fields="summary", maxResults=50, **({"nextPageToken": token} if token else {}))
            if not isinstance(page, dict):
                raise RemError("Jira issue metadata is malformed; retry listing")
            batch = page.get("issues")
            if not isinstance(batch, list) or page.get("warningMessages") or page.get("errorMessages") or page.get("errors"):
                raise RemError("Jira issue metadata is incomplete; retry co jira verify")
            if any(not isinstance(row, dict) or not isinstance(row.get("key"), str)
                   or not isinstance(row.get("fields"), dict) for row in batch):
                raise RemError("Jira issue metadata is malformed; retry listing")
            rows.extend({"key": row["key"], "name": row["fields"].get("summary", "")} for row in batch)
            token = page.get("nextPageToken")
            if not token:
                break
            if token in seen:
                raise RemError("Jira issue metadata pagination repeated; retry listing")
            seen.add(token)
        if token:
            typer.echo("Showing the first 1000 issues only; select explicitly from this list.")
        issues = pick(rows, "Jira issues", key="key", multiple=True)
    history = typer.confirm("Include issue change history after approval?", default=False)
    return {"project": project, "issues": issues, "history": history}

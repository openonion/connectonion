"""Read-only Jira CLI: authentication guidance, discovery and scoped live JSON reads."""

import json
import shlex
import sys
from typing import Optional, List
import typer

from rich.markup import escape

from ...environment import selected_command
from .. import style
from .command_tips import mark_next_step_named, selected_tip, tips_enabled


def _print(text: str) -> None:
    style.console().print(text, emoji=False)


def _error(text: str, **options) -> None:
    style.console(stderr=True).print(text, emoji=False, **options)


def _next(command: str) -> None:
    if tips_enabled():
        # Only rewrite the command prefix. User arguments may themselves
        # contain 'co ' (for example a directory named 'co notes').
        mark_next_step_named()
        _print(style.next_line(selected_command(command)))


def _error_next(recovery: str, as_json: bool) -> None:
    # A hard failure exits 2, also used by parser errors. Prevent the root
    # parser adding a second generic tip, including after a JSON-only result.
    mark_next_step_named()
    if not as_json:
        _error(style.next_line(selected_tip(recovery)))


def _jira():
    """Factory function — patchable in unit tests."""
    from ...useful_tools.jira import Jira
    return Jira()


def _live_item(issue: dict, site: str) -> dict:
    """CLI JSON shape for a live issue; never a stored adapter reference."""
    import hashlib
    from ...useful_tools.jira_adf import adf_to_text
    fields = issue.get("fields") or {}
    if not isinstance(fields, dict) or not isinstance(fields.get("updated"), str):
        raise ValueError("Jira returned invalid issue fields or update time; no item was emitted.")
    author = fields.get("creator") or fields.get("reporter") or {}
    if not isinstance(author, dict):
        raise ValueError("Jira returned invalid author metadata; no item was emitted.")
    text = adf_to_text(fields.get("description"))
    item = {"id": issue["key"], "title": fields.get("summary") or "(untitled)",
            "text": text, "author": author.get("displayName"),
            "author_id": author.get("accountId"), "time": fields.get("updated"),
            "link": f"{site}/browse/{issue['key']}", "source": f"jira:{issue['key']}"}
    item["version"] = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return item


def handle_jira_live(*, since=None, project=None, issues=None, issue=None, as_json=False):
    """Live CLI source boundary; only stdout is data in JSON mode."""
    from datetime import datetime, timezone
    import re
    try:
        if project is not None and not re.fullmatch(r"[A-Z][A-Z0-9]*", project):
            raise ValueError("--project requires a Jira project key such as ALPHA.")
        for key in ([issue] if issue is not None else issues or []):
            if not re.fullmatch(r"[A-Z][A-Z0-9]*-\d+", key) or (project and not key.startswith(project + "-")):
                raise ValueError("Issue key must belong to the explicitly selected project.")
        if since is not None:
            moment = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if moment.utcoffset() is None or moment > datetime.now(timezone.utc):
                raise ValueError("--since must include a timezone and not be in the future.")
        until = datetime.now(timezone.utc).isoformat()
        client = _jira()
        if issue is not None:
            result = _live_item(client.show_issue(issue, project_key=project), client._base)
            next_command = "co jira projects"
        else:
            rows = client.changed_issues(project, since, issue_keys=issues or None)
            items = [_live_item(row, client._base) for row in rows]
            result = {"since": moment.isoformat(), "until": until,
                      "scope": {"project": project, "issues": issues or []},
                      "items": [{k: row[k] for k in ("id", "version", "time", "title", "link")} for row in items]}
            next_command = f"co jira show {items[0]['id']} --json" if items else "co jira projects"
    except ValueError as exc:
        mark_next_step_named()
        _error(str(exc), markup=False)
        _error(f"Next: {selected_command('co jira --help')}", markup=False)
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    mark_next_step_named()
    if as_json:
        _error(f"Next: {selected_command(next_command)}", markup=False)
    else:
        _next(next_command)


def _failure_details(exc: Exception) -> tuple[str, str]:
    """Classify typed failures and name one executable recovery command."""
    from ...useful_tools.jira import JiraConfigError, JiraAuthError, JiraPermissionError

    if isinstance(exc, OSError):
        return "storage_error", "co jira --help"
    if isinstance(exc, JiraAuthError):
        return "reauth_required", "co jira verify"
    if isinstance(exc, JiraPermissionError):
        return "permission_denied", "co jira --help"
    if isinstance(exc, JiraConfigError):
        return "invalid_configuration", "co jira verify --help"
    return "import_failed", "co jira --help"

def _handle_error(exc: Exception, as_json: bool, *, scope: dict | None = None) -> None:
    msg = str(exc).strip()
    code, recovery = _failure_details(exc)
    result = {"error": msg, "exit_code": 1, "source": "jira", "scope": scope or {},
              "error_code": code, "recovery_action": selected_tip(recovery)}
    if as_json:
        print(json.dumps(result))
    else:
        _error(f"Jira command failed (scope: {json.dumps(result['scope'])}).", markup=False)
        _error(style.error(msg))
    _error_next(recovery, as_json)
    sys.exit(1)


def handle_jira_verify(*, as_json: bool = False) -> None:
    """Verify Jira credentials and report the authorised account.

    JSON output: {"account": site_url, "account_id": ..., "display_name": ...}.
    Token and email are never included in any output.
    """
    from ...useful_tools.jira import JiraConfigError, JiraAuthError, JiraPermissionError
    try:
        info = _jira().verify_connection()
    except (JiraConfigError, JiraAuthError, JiraPermissionError, ValueError) as exc:
        _handle_error(exc, as_json)
        return
    if as_json:
        print(json.dumps({
            "account": info.get("site_url", ""),
            "account_id": info.get("accountId", ""),
            "display_name": info.get("displayName", ""),
        }))
        return
    _print(f"{style.ok('Connected to:')} {escape(info.get('site_url', ''))} "
                          f"({escape(info.get('displayName', ''))})")
    _next("co jira projects")


def handle_jira_projects(*, as_json: bool = False) -> None:
    """List all accessible Jira projects.

    JSON output: {"projects": [{"key": ..., "name": ...}, ...]}.
    Empty result: {"projects": []}.
    Errors: exit 1; JSON includes error, exit_code, source, scope, error_code and recovery_action.
    """
    from ...useful_tools.jira import JiraConfigError, JiraAuthError, JiraPermissionError
    try:
        projects = _jira().project_items()
    except (JiraConfigError, JiraAuthError, JiraPermissionError, ValueError) as exc:
        _handle_error(exc, as_json)
        return
    if as_json:
        print(json.dumps({"projects": projects}))
        return
    if not projects:
        _print("No accessible Jira projects found. Check the selected account's project access.")
        _next("co jira verify")
        return
    _print(f"Jira projects: {style.count(len(projects))}")
    for project in projects:
        _print(f"{escape(project.get('key', '')):<12}  {escape(str(project.get('name') or ''))}")
    _print("Read a selected issue in a listed project:")
    _next("co jira show --help")


def handle_jira_issues(
    project_key: str,
    issue_keys: list[str],
    *,
    as_json: bool = False,
) -> None:
    """Fetch Jira issues scoped to the given project and issue keys.

    Scope validation (empty set, key prefix, JQL injection) is enforced by the tool layer.
    JSON output: {"issues": [{"key": ..., "fields": {...}}, ...]}.
    """
    from ...useful_tools.jira import JiraConfigError, JiraAuthError, JiraPermissionError
    try:
        issues = _jira().issue_items(project_key, set(issue_keys))
    except (JiraConfigError, JiraAuthError, JiraPermissionError, ValueError) as exc:
        _handle_error(exc, as_json, scope={"projects": [project_key], "issues": sorted(set(issue_keys))})
        return
    if as_json:
        print(json.dumps({"issues": issues}))
        return
    if not issues:
        _print(f"No accessible matching issues found in {escape(project_key)}.")
        _next("co jira issues --help")
        return
    _print(f"Issues in {escape(project_key)}: {style.count(len(issues))}")
    for issue in issues:
        key = issue.get("key", "")
        summary = str((issue.get("fields") or {}).get("summary") or "(no summary)")
        _print(f"{escape(key):<16}  {escape(summary)}")
    _next(shlex.join(["co", "jira", "show", issue_keys[0], "--project", project_key]))




jira_app = typer.Typer(
    help="Read-only Jira Cloud access: verify credentials, list projects, read selected issues, or list live changes. No source copies are stored. "
         "Set JIRA_URL and JIRA_EMAIL with co env set; follow co jira verify --help for hidden token setup.",
    epilog="Example: co jira verify",
)

@jira_app.command("changes", epilog="Example: co jira changes --project ALPHA --since 2026-11-01T00:00:00Z --json")
def _jira_changes(
    since: str = typer.Option(..., "--since", help="Read changes since an ISO time with timezone"),
    project: str = typer.Option(..., "--project", help="Explicit Jira project key; no all-project default"),
    issues: Optional[List[str]] = typer.Option(None, "--issues", help="Narrow to an issue key; repeat as needed"),
    as_json: bool = typer.Option(False, "--json", help="Print since, until, scope and items as JSON"),
):
    """Read-only: list changed Jira issues in one selected project; writes no files.

    --issues narrows the project to named issues. Results include stable issue
    keys, update times, titles and content versions. Pass until as the next
    --since and deduplicate overlapping results by id/version. Deleted or
    inaccessible issues are not listed. Exit 0 includes empty results; exit 1
    means reading failed (no partial success), exit 2 means invalid CLI usage.
    Next: co jira show ALPHA-1 --json
    """
    handle_jira_live(since=since, project=project, issues=issues, as_json=as_json)


@jira_app.command("show", epilog="Example: co jira show ALPHA-1 --json")
def _jira_show(
    issue: str = typer.Argument(..., help="One explicitly selected issue key, e.g. ALPHA-1"),
    project: Optional[str] = typer.Option(None, "--project", help="Reject an issue outside this project"),
    as_json: bool = typer.Option(False, "--json", help="Print live issue text, author, time, link and version"),
):
    """Read-only: read one explicitly selected Jira issue live; writes no files.

    Citations jira:ALPHA-1 resolve with co jira show ALPHA-1. The current
    version can differ from the version seen earlier. A deleted or inaccessible
    issue fails honestly; no stored snapshot is substituted. Exit 0 on success,
    1 on source failure, 2 on invalid CLI usage.
    Next: co jira projects
    """
    handle_jira_live(issue=issue, project=project, as_json=as_json)


@jira_app.command("verify", epilog="Example:  co jira verify --json")
def _jira_verify(
    as_json: bool = typer.Option(False, "--json", help="Output connection info as JSON"),
):
    """Read-only check of Jira access; display the authorised account and site.

    Configure the saved account (replace the example site and account email):

    \b
      co env set JIRA_URL https://your-team.atlassian.net
      co env set JIRA_EMAIL you@example.com
      read -rsp "Jira API token: " JIRA_API_TOKEN; echo
      co env set JIRA_API_TOKEN "$JIRA_API_TOKEN" --secret
      unset JIRA_API_TOKEN
      co jira verify

    JIRA_URL is the HTTPS site root, not an issue URL or page content.
    For https://your-team.atlassian.net/browse/DEMO-1 use only
    https://your-team.atlassian.net. The email is your Atlassian account email.
    Token input is hidden and saved encrypted; never put its literal value in a command argument.
    To fix an invalid URL, repeat only the JIRA_URL command above, then verify.

    After success, run co jira projects, then select one project with changes
    or one issue key with show. Follow REM's source approval separately.
    Next: co jira projects
    Exit 0 confirms connectivity, not access to every project; exit 1 reports
    configuration, authentication, permission or provider failure with recovery.
    """
    handle_jira_verify(as_json=as_json)


@jira_app.command("projects", epilog="Example:  co jira projects --json")
def _jira_projects(
    as_json: bool = typer.Option(False, "--json", help="Output project list as JSON"),
):
    """Read-only listing of accessible Jira project keys and names.

    Run co jira verify first. Copy a listed key into --project for changes,
    or use it with known issue keys in issues. Empty means no accessible
    projects were returned, not that authentication necessarily failed.
    --json returns a projects array, empty or populated. Exit 1 reports a
    failed read; follow its recovery command before trusting the result.
    """
    handle_jira_projects(as_json=as_json)


@jira_app.command("issues", epilog="Example:  co jira issues ALPHA ALPHA-1 ALPHA-2 --json")
def _jira_issues(
    project_key: str = typer.Argument(..., help="Jira project key, e.g. ALPHA"),
    issue_keys: list[str] = typer.Argument(..., help="One or more issue keys, e.g. ALPHA-1 ALPHA-2"),
    as_json: bool = typer.Option(False, "--json", help="Output issues as JSON"),
):
    """Read-only fetch of known issue keys within PROJECT_KEY.

    Discover PROJECT_KEY with co jira projects; copy ISSUE_KEYS from your Jira
    project (for example ALPHA-1). All keys must belong to the selected project.
    This prints keys and summaries, or the returned issue fields with --json.
    It writes no local source files. Any missing requested key fails the read;
    the key may be absent, deleted or inaccessible to the selected account.
    Use changes to list updates or show to read one issue live.
    Exit 1 reports a failed read; argument errors exit 2.
    """
    handle_jira_issues(project_key, issue_keys, as_json=as_json)

"""Thin command handlers for read-only Jira operations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.markup import escape

from ...environment import selected_command
from .. import style
from .command_tips import mark_next_step_named, selected_tip, tips_enabled


def _jira():
    from ...useful_tools.jira import Jira
    return Jira()


def _print(message: str, *, stderr: bool = False) -> None:
    style.console(stderr=stderr).print(message, markup=True, emoji=False)


def _next(command: str) -> None:
    if tips_enabled():
        mark_next_step_named()
        _print(style.next_line(selected_command(command)))


def _fail(exc: Exception, as_json: bool, scope: dict | None = None) -> None:
    from ...useful_tools.jira import JiraAuthError, JiraConfigError, JiraPermissionError
    if isinstance(exc, JiraAuthError):
        code, recovery = "authentication_failed", "co jira verify --help"
    elif isinstance(exc, JiraPermissionError):
        code, recovery = "permission_denied", "co jira projects"
    elif isinstance(exc, JiraConfigError):
        code, recovery = "configuration_error", "co jira verify --help"
    else:
        code, recovery = "read_failed", "co jira --help"
    report = {"error": str(exc), "exit_code": 1, "source": "jira", "scope": scope or {},
              "error_code": code, "recovery_action": selected_tip(recovery)}
    if as_json:
        print(json.dumps(report))
    else:
        _print(style.error(f"Jira command failed: {report['error']}"), stderr=True)
        if tips_enabled():
            mark_next_step_named()
            _print(style.next_line(selected_tip(recovery)), stderr=True)
    raise SystemExit(1)


def handle_jira_verify(*, as_json: bool = False) -> None:
    try:
        info = _jira().verify_connection()
    except ValueError as exc:
        _fail(exc, as_json)
    if as_json:
        print(json.dumps({"account": info["site_url"], "account_id": info["accountId"], "display_name": info["displayName"]}))
    else:
        _print(f"{style.ok('Connected to:')} {escape(info['site_url'])} ({escape(info['displayName'])})")
        _next("co jira projects")


def handle_jira_projects(*, as_json: bool = False) -> None:
    try:
        projects = _jira().project_items()
    except ValueError as exc:
        _fail(exc, as_json)
    if as_json:
        print(json.dumps({"projects": projects}))
        return
    if not projects:
        _print("No accessible Jira projects found.")
        _next("co jira verify")
        return
    _print(f"Jira projects: {style.count(len(projects))}")
    for project in projects:
        _print(f"{escape(project['key']):<12}  {escape(project['name'])}")
    _next("co jira issues <PROJECT> <PROJECT-1>")


def handle_jira_issues(project_key: str, issue_keys: list[str], *, as_json: bool = False) -> None:
    scope = {"projects": [project_key], "issues": sorted(set(issue_keys))}
    try:
        issues = _jira().issue_items(project_key, set(issue_keys))
    except ValueError as exc:
        _fail(exc, as_json, scope)
    if as_json:
        print(json.dumps({"issues": issues}))
        return
    _print(f"Issues in {escape(project_key)}: {style.count(len(issues))}")
    for issue in issues:
        summary = str((issue.get("fields") or {}).get("summary") or "(no summary)")
        _print(f"{escape(issue['key']):<16}  {escape(summary)}")
    _next(" ".join(["co", "jira", "sync", project_key, *issue_keys]))


def handle_jira_sync(project_key: str, issue_keys: list[str], *, output_dir: Path | None = None,
                     export_id: str | None = None, as_json: bool = False) -> None:
    del export_id  # One-off exports are implemented with the later REM integration PR.
    scope = {"projects": [project_key], "issues": sorted(set(issue_keys))}
    output_dir = output_dir or Path.home() / ".co" / "rem" / "docs" / "jira"
    try:
        jira = _jira()
        account = jira.verify_connection()["site_url"]
        issues = jira.issue_items(project_key, set(issue_keys))
        from ...useful_tools.jira_adapter import append_daily, jira_records
        records, rejected = jira_records(issues, account)
        if rejected and not records:
            raise ValueError("No selected Jira issues could be mapped into local records.")
        source = jira.write_source_yaml(output_dir, project_key, set(issue_keys))
        daily, appended = append_daily(records, output_dir)
    except (ValueError, OSError) as exc:
        _fail(exc, as_json, scope)
    report = {"written": str(source), "jsonl": str(daily), "project": project_key,
              "issues": len(issues), "mapped": len(records), "appended": appended, "rejected": rejected}
    if rejected:
        report.update({"error": "Some selected Jira issues could not be mapped; valid records were retained.", "exit_code": 1})
        if as_json:
            print(json.dumps(report))
        else:
            _print(style.error(report["error"]), stderr=True)
        raise SystemExit(1)
    if as_json:
        print(json.dumps(report))
    else:
        _print(f"Wrote {style.path(str(source))}")
        _print(f"Wrote {style.path(str(daily))}")
        _print(f"Project: {escape(project_key)}  Issues collected: {style.count(len(issues))}  Records appended: {style.count(appended)}")
        _next("co jira projects")

"""
Purpose: `co jira` — verify connection, list projects, read scoped issues and their history (F13FCAKE-9/10/12/18); incremental checkpoint-backed sync (F13FCAKE-19)
LLM-Note:
  Dependencies: imports from [sys, json, rich, useful_tools/jira.Jira, useful_tools/jira_checkpoint.run_jira_sync] | imported by [cli/main.py] | tested by [tests/unit/test_jira.py, tests/unit/test_jira_checkpoint.py]
  Data flow: CLI flags -> _jira() factory -> Jira.verify_connection()/project_items()/issue_items() -> formatted output or JSON
    sync: issue_items -> issue_changelogs (unless --no-history, F13FCAKE-12) -> jira_issues_to_records(changelogs=...) -> daily/ or exports/
    sync-inc: run_jira_sync() (10-step AG-1–AG-5 transaction) -> SyncResult -> formatted output or JSON
  State/Effects: sync writes source.yaml and daily JSONL under the output dir; Jira itself is always read-only; all auth/scope validation in tool layer
    sync-inc additionally writes checkpoint, staging, and pending files under state_dir (.state/)
  Errors: JiraConfigError/JiraAuthError/JiraPermissionError/ValueError -> stderr + exit 1; never exposes token | sync with items rejected by the shared record contract (F13FCAKE-16) still writes the valid records, lists every rejected item, and exits 1 | sync-inc exit_code 1 = partial mapping failure, exit_code 2 = hard failure (auth/lock/persistence/recovery)
"""

import json
import shlex
import sys
from pathlib import Path

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


def _repeat_command(project, keys, output, state, history) -> str:
    args = ["co", "jira", "sync-inc", "--project", project]
    for key in keys:
        args.extend(["--issues", key])
    for flag, value in (("--output", output), ("--state", state)):
        if value is not None:
            args.extend([flag, str(value)])
    if not history:
        args.append("--no-history")
    return shlex.join(args)


def _jira():
    """Factory function — patchable in unit tests."""
    from ...useful_tools.jira import Jira
    return Jira()


def _failure_details(exc: Exception) -> tuple[str, str]:
    """Classify typed failures and name one executable recovery command."""
    from ...useful_tools.jira import JiraConfigError, JiraAuthError, JiraPermissionError

    if isinstance(exc, OSError):
        return "storage_error", "co jira sync --help"
    if isinstance(exc, JiraAuthError):
        return "reauth_required", "co jira verify"
    if isinstance(exc, JiraPermissionError):
        return "permission_denied", "co jira --help"
    if isinstance(exc, JiraConfigError):
        return "invalid_configuration", "co jira verify --help"
    return "import_failed", "co jira --help"

def _handle_error(exc: Exception, as_json: bool, *, scope: dict | None = None) -> None:
    msg = "Could not read or write local Jira source files. Check --output and directory permissions." \
        if isinstance(exc, OSError) else str(exc).strip()
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
    _print("Import a listed project with a checkpoint and version deduplication:")
    _next(f"co jira sync-inc --project {shlex.quote(projects[0]['key'])}")


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
    _next(shlex.join(["co", "jira", "sync", project_key, *issue_keys]))


def handle_jira_sync(
    project_key: str,
    issue_keys: list[str],
    *,
    output_dir: Path | None = None,
    as_json: bool = False,
    export_id: str | None = None,
    history: bool = True,
) -> None:
    """Validate credentials, collect selected issues and their history, write source.yaml and the records.

    Full workflow: verify → issue_items → issue_changelogs → jira_issues_to_records → write_source_yaml → placement.
    History (F13FCAKE-12): one extra read per issue, attached as extensions.changelog; history=False
    (--no-history) skips those reads and the records carry no changelog.
    Placement (F13FCAKE-11): ongoing sync → append_daily_jsonl(keep_versions=True) (daily/YYYY/MM/DD.jsonl);
    export_id given → write_export (exports/<export_id>/ records.jsonl + manifest.json), a one-off import.
    An unusable export id is refused before any request or file write.
    Writes to output_dir (default: ~/.co/rem/docs/jira).
    JSON output: {"written": source_yaml_path, "placement": "daily" | "export", "jsonl": records file path,
    "project": key, "issues": collected,
    "mapped": records that passed the contract, "appended": records newly added to today's file
    (already-present records are skipped; for an export, every mapped record),
    "history": {"ok": n, "none": n, "restricted": n, "unavailable": n} or null with --no-history,
    "rejected": {"jira:<key>": reason}}.
    Rejected items never disappear silently: valid records are still written, the rejected ones are
    listed (stderr, or "rejected" in JSON), and the command exits 1.
    """
    from ...useful_tools.jira import JiraConfigError, JiraAuthError, JiraPermissionError
    from ...useful_tools.adapter import export_target, jira_issues_to_records
    if output_dir is None:
        output_dir = Path.home() / ".co" / "rem" / "docs" / "jira"
    try:
        if export_id is not None:
            export_target(output_dir, export_id)
        jira = _jira()
        info, issues, changelogs = _read_jira(jira, project_key, issue_keys, history)
        adapter_result = jira_issues_to_records(issues, info["site_url"], changelogs=changelogs)
        if adapter_result.errors and not adapter_result.records:
            _report_rejected(adapter_result.errors, as_json, project_key, issue_keys, None, None,
                             len(issues), 0, 0, _history_counts([]) if history else None, export_id)
            return
        jira.write_source_yaml(output_dir, [project_key], set(issue_keys))
        jsonl_path, appended = _place_records(adapter_result.records, output_dir, export_id,
                                              {"projects": [project_key], "issues": sorted(set(issue_keys))})
    except (JiraConfigError, JiraAuthError, JiraPermissionError, ValueError, OSError) as exc:
        _handle_error(exc, as_json, scope={"projects": [project_key], "issues": sorted(set(issue_keys))})
        return
    source_yaml = str(output_dir / "source.yaml")
    rejected = adapter_result.errors
    counts = _history_counts(adapter_result.records) if history else None
    if rejected:
        _report_rejected(rejected, as_json, project_key, issue_keys, source_yaml, jsonl_path,
                         len(issues), len(adapter_result.records), appended, counts, export_id)
        return
    if as_json:
        print(json.dumps({
            "written": source_yaml,
            "placement": "export" if export_id else "daily",
            "jsonl": str(jsonl_path),
            "project": project_key,
            "issues": len(issues),
            "mapped": len(adapter_result.records),
            "appended": appended,
            "history": counts,
            "rejected": rejected,
        }))
    else:
        _print(f"Wrote {style.path(source_yaml)}")
        _print(f"Wrote {style.path(jsonl_path)}")
        _print(f"Project: {escape(project_key)}  Issues collected: {style.count(len(issues))}  "
                  f"Records mapped: {style.count(len(adapter_result.records))}  Records appended: {style.count(appended)}")
        _print_history(counts)
        _next("co jira sync-inc --help")


# Every Jira read happens before any file is written, so an auth failure while reading history writes nothing.
def _read_jira(jira, project_key: str, issue_keys: list[str], history: bool) -> tuple[dict, list, dict | None]:
    info = jira.verify_connection()
    issues = jira.issue_items(project_key, set(issue_keys))
    if not history:
        return info, issues, None
    keys = {issue["key"] for issue in issues if isinstance(issue, dict) and isinstance(issue.get("key"), str)}
    return info, issues, jira.issue_changelogs(keys)


# How many mapped records ended up with each history status (F13FCAKE-12).
def _history_counts(records: list[dict]) -> dict:
    from ...useful_tools.adapter import CHANGELOG_STATUSES
    statuses = [record["extensions"].get("changelog", {}).get("status") for record in records]
    return {status: statuses.count(status) for status in CHANGELOG_STATUSES}


def _print_history(counts: dict | None) -> None:
    if counts is None:
        _print("History: not requested (--no-history)")
        return
    _print("History: " + "  ".join(f"{status} {style.count(n)}" for status, n in counts.items()))
    if counts["restricted"] or counts["unavailable"]:
        _print(style.warn("Issues whose history could not be read were still written; "
                                         "extensions.changelog.reason says why."))


# Ongoing sync appends to today's daily file; --export writes a one-off snapshot under exports/<id>/.
def _place_records(records: list[dict], output_dir: Path, export_id: str | None, scope: dict) -> tuple[Path, int]:
    from ...useful_tools.adapter import append_daily_jsonl, write_export
    if export_id is None:
        return append_daily_jsonl(records, output_dir, keep_versions=True)
    return write_export(records, output_dir, export_id, scope) / "records.jsonl", len(records)


# Mapping errors (F13FCAKE-16) must reach the user: list each rejected item, then exit 1.
def _report_rejected(rejected, as_json, project, issue_keys, source_yaml, jsonl_path,
                     collected, mapped, appended, counts, export_id) -> None:
    recovery = "co jira sync --help"
    message = ("Some selected Jira items could not be imported; valid results are retained." if mapped else
               "No valid Jira records were processed; no new import files were written.")
    report = {"error": message,
              "exit_code": 1, "source": "jira", "scope": {"projects": [project], "issues": sorted(set(issue_keys))},
              "error_code": "partial_import" if mapped else "processing_failed", "recovery_action": selected_tip(recovery), "written": source_yaml,
              "placement": "export" if export_id else "daily", "jsonl": str(jsonl_path) if jsonl_path else None, "project": project,
              "issues": collected, "mapped": mapped, "appended": appended, "history": counts, "rejected": rejected}
    if as_json:
        print(json.dumps(report))
    else:
        _error(f"Jira import failed (scope: {json.dumps(report['scope'])}).", markup=False)
        _error(message, markup=False)
        if jsonl_path:
            _error(f"Valid records retained: {mapped}; newly appended: {appended}. Saved to: {jsonl_path}", markup=False)
        _error(f"Records mapped: {mapped}  Records appended: {appended}", markup=False)
        _error(f"{len(rejected)} item(s) were rejected and not written:", markup=False)
        for label, reason in rejected.items():
            _error(f"Rejected {label}: {reason}", markup=False)
    _error_next(recovery, as_json)
    sys.exit(1)


def _sync_inc_recovery(error_code: str | None) -> str:
    # Detail explains what failed. Help explains non-destructive state recovery;
    # do not turn --full into a reset or discard the user's source metadata.
    if error_code in {"auth_failure", "internal_error"}:
        return "co jira verify"
    return "co jira sync-inc --help"

def handle_jira_sync_incremental(
    project_key: str,
    issue_keys: list[str],
    *,
    output_dir: Path | None = None,
    state_dir: Path | None = None,
    as_json: bool = False,
    full: bool = False,
    history: bool = True,
    migrate_source: bool = False,
) -> None:
    """Run incremental (or full) Jira sync using the checkpoint-backed transaction engine.

    Calls run_jira_sync() (F13FCAKE-19) which implements the 10-step AG-1–AG-5 transaction.
    The first run is always a full import; subsequent runs read only issues updated since
    the last checkpoint. Pass full=True (--full) to force a complete re-import.

    JSON output on success: {mode, scope, issues_read, issues_mapped, net_new_records,
    placement, checkpoint_result, rejections, error_code, exit_code}.
    JSON output on failure: adds error, exit_code, source, error_code, recovery_action.

    exit_code 1 = partial mapping failure (valid records written, cursor unchanged).
    exit_code 2 = hard failure (auth, lock, persistence, recovery error).
    """
    from ...useful_tools.jira_checkpoint import run_jira_sync

    result = run_jira_sync(
        project_key,
        issue_keys=issue_keys if issue_keys else None,
        full=full,
        state_dir=state_dir,
        output_dir=output_dir,
        history=history,
        migrate_source=migrate_source,
    )

    if result.exit_code == 0:
        if as_json:
            print(json.dumps({
                "mode": result.mode,
                "scope": result.scope,
                "issues_read": result.issues_read,
                "issues_mapped": result.issues_mapped,
                "net_new_records": result.net_new_records,
                "placement": result.placement,
                "checkpoint_result": result.checkpoint_result,
                "rejections": result.rejections,
                "error_code": result.error_code,
                "exit_code": 0,
            }))
            return
        if result.checkpoint_result == "recovered":
            _print(f"{style.ok('Recovered from interrupted run;')} staged records written to {style.path(result.placement)}")
        elif result.issues_read == 0:
            _print(f"No matching issues returned for {escape(project_key)}; checkpoint unchanged.")
        elif result.net_new_records == 0:
            _print(
                f"Project: {escape(project_key)}  Issues read: {style.count(result.issues_read)}  "
                f"Records mapped: {style.count(result.issues_mapped)}  New records: {style.count(0)} (all already present)"
            )
        else:
            _print(f"Wrote {style.path(result.placement)}")
            _print(
                f"Project: {escape(project_key)}  Issues read: {style.count(result.issues_read)}  "
                f"Records mapped: {style.count(result.issues_mapped)}  New records: {style.count(result.net_new_records)}"
            )
        _print(f"Checkpoint: {escape(result.checkpoint_result)}")
        if result.error_code:
            _error(
                f"Warning: {result.error_code}: {result.error_detail}", style="yellow", markup=False
            )
        _next(_repeat_command(project_key, issue_keys, output_dir, state_dir, history))
        return

    # exit_code 1 (partial) or 2 (hard failure)
    scope = result.scope
    msg = result.error_detail or "Sync failed."
    recovery = _sync_inc_recovery(result.error_code)
    report = {
        "error": msg,
        "exit_code": result.exit_code,
        "source": "jira",
        "scope": scope,
        "error_code": result.error_code,
        "recovery_action": selected_tip(recovery),
        "mode": result.mode,
        "issues_read": result.issues_read,
        "issues_mapped": result.issues_mapped,
        "net_new_records": result.net_new_records,
        "placement": result.placement,
        "checkpoint_result": result.checkpoint_result,
        "rejections": result.rejections,
    }
    if as_json:
        print(json.dumps(report))
    else:
        _error(f"Jira sync failed (scope: {json.dumps(scope)}).", markup=False)
        _error(style.error(msg))
        if result.rejections:
            _error(f"{len(result.rejections)} item(s) rejected:", markup=False)
            for label, reason in result.rejections.items():
                _error(f"  Rejected {label}: {reason}", markup=False)
    _error_next(recovery, as_json)
    sys.exit(result.exit_code)

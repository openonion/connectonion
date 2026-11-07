"""Read-only Jira Cloud operations used by the Jira CLI.

This module returns provider data and writes only the selected source metadata.
It never creates, edits, or deletes Jira resources.
"""

from __future__ import annotations

import datetime
import importlib.metadata
import re
import urllib.parse
from pathlib import Path

import httpx
import yaml

from ..environment import setting


class JiraConfigError(ValueError):
    """Local Jira configuration is missing or unsafe."""


class JiraAuthError(ValueError):
    """Jira rejected the configured credentials."""


class JiraPermissionError(ValueError):
    """The configured account cannot read the requested Jira resource."""


_KEY = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
_MAX_PAGES = 50
ISSUE_FIELDS = ("summary", "description", "issuetype", "status", "priority", "labels",
                "assignee", "reporter", "creator", "created", "updated", "duedate",
                "resolutiondate", "parent", "attachment")


class Jira:
    """Read Jira projects and explicitly selected issues through REST API v3."""

    def __init__(self) -> None:
        url = (setting("JIRA_URL") or "").rstrip("/")
        email = setting("JIRA_EMAIL") or ""
        token = setting("JIRA_API_TOKEN") or ""
        if not url:
            raise JiraConfigError("JIRA_URL is not set.\nRepair: co env set JIRA_URL https://your-domain.atlassian.net")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise JiraConfigError("JIRA_URL must be an HTTPS site root without credentials.\nRepair: co env set JIRA_URL https://your-domain.atlassian.net")
        if not email:
            raise JiraConfigError("JIRA_EMAIL is not set.\nRepair: co env set JIRA_EMAIL your@email.com")
        if not token:
            raise JiraConfigError("JIRA_API_TOKEN is not set.\nRepair: co env set JIRA_API_TOKEN --secret --prompt")
        self._base, self._auth = url, (email, token)

    def _get(self, path: str, **params: object) -> dict:
        try:
            response = httpx.get(f"{self._base}/rest/api/3/{path.lstrip('/')}", auth=self._auth,
                                 params=params, timeout=30)
        except httpx.TimeoutException as exc:
            raise ValueError("Request to Jira timed out. Check your network connection and try again.") from exc
        except httpx.RequestError as exc:
            raise ValueError("Could not reach Jira. Check your network connection and try again.") from exc
        if response.status_code == 401:
            raise JiraAuthError("Jira authentication failed. Repair: co env set JIRA_API_TOKEN --secret --prompt")
        if response.status_code == 403:
            raise JiraPermissionError("Jira returned 403. Check that your account has read access.")
        if response.status_code == 429:
            raise ValueError("Jira rate limit exceeded (HTTP 429). Wait and try again.")
        if response.status_code >= 500:
            raise ValueError(f"Jira is temporarily unavailable (HTTP {response.status_code}). Try again shortly.")
        try:
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise ValueError("Jira returned an unexpected or malformed response. Try again or contact your Jira administrator.") from exc
        if not isinstance(data, dict):
            raise ValueError("Jira returned malformed metadata instead of a JSON object.")
        return data

    def verify_connection(self) -> dict:
        data = self._get("myself")
        if not isinstance(data.get("accountId"), str) or not isinstance(data.get("displayName"), str):
            raise ValueError("Jira returned malformed account metadata.")
        return {"accountId": data["accountId"], "displayName": data["displayName"], "site_url": self._base}

    def project_items(self) -> list[dict]:
        results: list[dict] = []
        start_at = 0
        for _ in range(_MAX_PAGES):
            page = self._get("project/search", startAt=start_at, maxResults=50)
            values, is_last = page.get("values"), page.get("isLast")
            if page.get("warningMessages") or page.get("errorMessages") or page.get("errors"):
                raise ValueError("Jira project search returned warnings or errors; results may be incomplete.")
            if not isinstance(values, list) or not isinstance(is_last, bool) or any(
                not isinstance(item, dict) or not isinstance(item.get("key"), str) or not isinstance(item.get("name"), str)
                for item in values
            ):
                raise ValueError("Jira returned malformed project metadata.")
            if not values and not is_last:
                raise ValueError("Jira project pagination did not advance; refusing an incomplete result.")
            results.extend(values)
            if is_last:
                return results
            start_at += len(values)
        raise ValueError("Jira project pagination exceeded its safe limit.")

    def issue_items(self, project_key: str, selected_issue_keys: set[str]) -> list[dict]:
        if not selected_issue_keys:
            raise ValueError("Choose at least one Jira issue key before collecting.")
        if not re.fullmatch(r"[A-Z][A-Z0-9]*", project_key or ""):
            raise ValueError("Project key is invalid. Use a Jira project key such as ALPHA.")
        for key in selected_issue_keys:
            if not _KEY.fullmatch(key) or not key.startswith(project_key + "-"):
                raise ValueError(f"Issue key {key!r} is not a valid issue in project {project_key!r}.")
        jql = f"project = {project_key} AND key IN ({', '.join(sorted(selected_issue_keys))})"
        results: list[dict] = []
        token: str | None = None
        seen: set[str] = set()
        for _ in range(_MAX_PAGES):
            params: dict[str, object] = {"jql": jql, "maxResults": 50, "fields": ",".join(ISSUE_FIELDS)}
            if token:
                params["nextPageToken"] = token
            try:
                page = self._get("search/jql", **params)
            except JiraPermissionError:
                raise JiraPermissionError(f"Jira returned 403 for project {project_key!r}. Check read access.") from None
            batch = page.get("issues")
            if page.get("warningMessages") or page.get("errorMessages") or page.get("errors") or not isinstance(batch, list):
                raise ValueError("Jira issue search returned incomplete or malformed results.")
            if any(not isinstance(item, dict) or not isinstance(item.get("key"), str) for item in batch):
                raise ValueError("Jira issue search returned malformed issue metadata.")
            results.extend(batch)
            token = page.get("nextPageToken")
            if token is None:
                missing = selected_issue_keys - {item["key"] for item in results}
                if missing:
                    raise ValueError(f"Jira did not return requested issue keys: {sorted(missing)}.")
                return results
            if not isinstance(token, str) or not token or token in seen:
                raise ValueError("Jira issue pagination did not advance; refusing an incomplete result.")
            seen.add(token)
        raise ValueError("Jira issue pagination exceeded its safe limit.")

    def write_source_yaml(self, source_dir: Path, project_key: str, issue_keys: set[str]) -> Path:
        if not issue_keys:
            raise ValueError("Choose at least one Jira issue key before writing source metadata.")
        if any(not key.startswith(project_key + "-") for key in issue_keys):
            raise ValueError("Every selected issue key must belong to the selected project.")
        source_dir = Path(source_dir)
        source_dir.mkdir(parents=True, exist_ok=True)
        target = source_dir / "source.yaml"
        scope = {"projects": [project_key], "issues": sorted(issue_keys)}
        if target.exists():
            try:
                existing = yaml.safe_load(target.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, yaml.YAMLError) as exc:
                raise ValueError("Existing source.yaml could not be read; preserve it and choose a separate --output directory.") from exc
            if not isinstance(existing, dict) or existing.get("driver") != "jira" or existing.get("account") != self._base or existing.get("scope") != scope:
                raise ValueError("Existing source.yaml belongs to a different Jira account or selected scope. It was preserved; choose a separate --output directory.")
        payload = {
            "driver": "jira", "account": self._base,
            "scope": scope,
            "retention": "local", "media_policy": "metadata_only",
            "validated_with": {"connectonion_version": importlib.metadata.version("connectonion"),
                               "command": "co jira sync", "path": str(target),
                               "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()},
        }
        target.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return target

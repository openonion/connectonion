"""Read-only Jira Cloud API operations: credentials, projects, issues and live changes.

Methods return raw Jira API dictionaries. No source copies, snapshots or checkpoints
are written. Credentials use the existing selected environment and secret store.
"""

import datetime
import re
import urllib.parse

import httpx

from ..environment import setting

class JiraConfigError(ValueError):
    """Local configuration missing or invalid (JIRA_URL / JIRA_EMAIL / JIRA_API_TOKEN)."""

class JiraAuthError(ValueError):
    """Jira returned HTTP 401 — authentication failed."""

class JiraPermissionError(ValueError):
    """Jira returned HTTP 403 — permission denied for the requested resource."""

_KEY_PATTERN = re.compile(r'^[A-Z][A-Z0-9]*-\d+$')

_MAX_PAGES = 50

# Fields explicitly requested from the enhanced search endpoint.
# Without an explicit fields param, Jira Cloud returns each issue with only
# {"id": ...} — key and all application fields are omitted.
# The set covers everything the shared record maps (F13FCAKE-11): content, type, status,
# priority, people, labels, dates, parent and attachment metadata.
ISSUE_FIELDS = ("summary", "description", "issuetype", "status", "priority", "labels",
                "assignee", "reporter", "creator", "created", "updated", "duedate",
                "resolutiondate", "parent", "attachment")


def _jql_date(value: datetime.date) -> str:
    """Use JQL's epoch milliseconds for an instant; retain local calendar inputs.

    Jira rejects quoted ISO timestamps with a T, seconds or offset. Unquoted
    epoch milliseconds preserve an aware cursor regardless of the Jira user's
    configured timezone. Floor to milliseconds so precision cannot skip a change.
    """
    if isinstance(value, datetime.datetime):
        if value.utcoffset() is not None:
            epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
            millis = (value - epoch) // datetime.timedelta(milliseconds=1)
            return str(millis)
        return f'"{value:%Y-%m-%d %H:%M}"'
    return f'"{value.isoformat()}"'


class Jira:
    """Read-only Jira Cloud integration: project listing, issue collection, source.yaml."""

    def __init__(self):
        from ..secret_store import SecretStoreError
        try:
            url = (setting("JIRA_URL") or "").rstrip("/")
            email = setting("JIRA_EMAIL") or ""
            token = setting("JIRA_API_TOKEN") or ""
        except SecretStoreError:
            raise JiraConfigError("Saved Jira credentials cannot be unlocked. Inspect co env (values hidden), "
                                  "then use hidden input and co env set JIRA_API_TOKEN \"$JIRA_API_TOKEN\" --secret in a local terminal.") from None
        if not url:
            raise JiraConfigError(
                "JIRA_URL is not set.\n"
                "Repair: co env set JIRA_URL https://your-domain.atlassian.net"
            )
        _parsed = urllib.parse.urlparse(url)
        if _parsed.scheme != "https" or not _parsed.netloc:
            raise JiraConfigError(
                "JIRA_URL must use https:// with a valid host.\n"
                "Basic Auth credentials must not travel over plain HTTP or non-HTTPS schemes.\n"
                "Repair: co env set JIRA_URL https://your-domain.atlassian.net"
            )
        if _parsed.username or _parsed.password:
            raise JiraConfigError(
                "JIRA_URL must not contain credentials (username or password in the URL). "
                "Provide them via JIRA_EMAIL and JIRA_API_TOKEN instead.\n"
                "Repair: co env set JIRA_URL https://your-domain.atlassian.net"
            )
        if not email:
            raise JiraConfigError(
                "JIRA_EMAIL is not set.\n"
                "Repair: co env set JIRA_EMAIL your@email.com"
            )
        if not token:
            raise JiraConfigError(
                "JIRA_API_TOKEN is not set.\n"
                "For background REM, save it with hidden input:\n"
                "  read -rsp \"Jira API token: \" JIRA_API_TOKEN; echo\n"
                "  co env set JIRA_API_TOKEN \"$JIRA_API_TOKEN\" --secret; unset JIRA_API_TOKEN\n"
                "For a one-off CLI read, use a temporary export:\n"
                "  Bash/Git Bash: read -rsp \"Jira API token: \" JIRA_API_TOKEN; echo; export JIRA_API_TOKEN\n"
                "  zsh:           read -rs \"JIRA_API_TOKEN?Jira API token: \"; echo; export JIRA_API_TOKEN\n"
                "Then run your co jira command, then: unset JIRA_API_TOKEN"
            )
        self._base = url
        self._auth = (email, token)

    def _get(self, path: str, **params) -> dict:
        """Authenticated GET to /rest/api/3/<path>; raises typed errors for auth/rate/network/5xx."""
        url = f"{self._base}/rest/api/3/{path.lstrip('/')}"
        try:
            response = httpx.get(url, auth=self._auth, params=params, timeout=30)
        except httpx.TimeoutException as exc:
            raise ValueError(
                "Request to Jira timed out. "
                "Check your network connection and try again."
            ) from exc
        except httpx.RequestError as exc:
            raise ValueError(
                "Could not reach Jira — check your network connection and try again."
            ) from exc
        if response.status_code == 401:
            raise JiraAuthError(
                "Jira authentication failed.\n"
                "Re-generate your token at https://id.atlassian.com/manage-profile/security/api-tokens, "
                "then set it temporarily (never saved to disk):\n"
                "  Bash/Git Bash: read -rsp \"Jira API token: \" JIRA_API_TOKEN; echo; export JIRA_API_TOKEN\n"
                "  zsh:           read -rs \"JIRA_API_TOKEN?Jira API token: \"; echo; export JIRA_API_TOKEN\n"
                "Then run your co jira command, then: unset JIRA_API_TOKEN"
            )
        if response.status_code == 403:
            raise JiraPermissionError(
                "Jira returned 403. "
                "Check that your API token has read access."
            )
        if response.status_code == 429:
            raise ValueError(
                "Jira rate limit exceeded (HTTP 429). "
                "Wait a moment and try again."
            )
        if response.status_code >= 500:
            raise ValueError(
                f"Jira is temporarily unavailable (HTTP {response.status_code}). "
                "Try again in a few minutes."
            )
        try:
            response.raise_for_status()
        except Exception as exc:
            raise ValueError(
                f"Jira returned an unexpected HTTP {response.status_code} response."
            ) from exc
        try:
            data = response.json()
        except Exception as exc:
            raise ValueError(
                "Jira returned a response that could not be parsed as JSON. "
                "Try again or contact your Jira administrator."
            ) from exc
        if not isinstance(data, dict):
            raise ValueError("Jira returned malformed metadata instead of a JSON object. Retry or contact your Jira administrator.")
        return data

    def verify_connection(self) -> dict:
        """GET /rest/api/3/myself — confirms credentials; returns accountId, displayName, site_url.

        Token does not appear in the returned dict, logs, or any file written to disk.
        emailAddress is included only when Jira returns it (privacy settings may omit it).
        """
        data = self._get("myself")
        if (not isinstance(data.get("accountId"), str) or not data["accountId"]
                or not isinstance(data.get("displayName"), str)):
            raise ValueError("Jira returned malformed account metadata. Retry or contact your Jira administrator.")
        result: dict = {
            "accountId": data["accountId"],
            "displayName": data["displayName"],
            "site_url": self._base,
        }
        if "emailAddress" in data:
            result["emailAddress"] = data["emailAddress"]
        return result

    def project_items(self) -> list[dict]:
        """GET /rest/api/3/project/search — all accessible projects, offset-based pagination.

        Pagination: startAt / isLast / values (confirmed in Step 0).
        Empty values with isLast=false → raises ValueError (non-progressing page guard).
        """
        results: list[dict] = []
        start_at = 0
        for _ in range(_MAX_PAGES):
            page = self._get("project/search", startAt=start_at, maxResults=50)
            if page.get("warningMessages") or page.get("errorMessages") or page.get("errors"):
                raise ValueError("Jira project search returned warnings or errors; its results may be incomplete.")
            values = page.get("values")
            is_last = page.get("isLast")
            if (not isinstance(values, list) or not isinstance(is_last, bool)
                    or any(not isinstance(item, dict)
                           or not isinstance(item.get("key"), str) or not item["key"]
                           or not isinstance(item.get("name"), str) for item in values)):
                raise ValueError("Jira returned malformed project metadata. Retry or contact your Jira administrator.")
            if not values and not is_last:
                raise ValueError(
                    f"Jira project pagination returned an empty page with isLast=false "
                    f"(startAt={start_at}). Aborting to prevent an infinite loop."
                )
            results.extend(values)
            if is_last:
                return results
            start_at += len(values)
        raise ValueError(
            f"Jira project pagination exceeded {_MAX_PAGES} pages without reaching isLast=true. "
            "Aborting to prevent an infinite loop."
        )

    def issue_items(
        self,
        project_key: str,
        selected_issue_keys: set[str],
        *,
        max_results: int = 50,
        accessible_keys: set[str] | None = None,
    ) -> list[dict]:
        """GET /rest/api/3/search/jql — selected issues, cursor-based pagination.

        Pagination: nextPageToken (absent = last page); startAt is silently ignored by server.
        JQL is server-scoped: project = project_key AND key IN (selected_issue_keys).

        fields=ISSUE_FIELDS is passed explicitly on every request. Without it, Jira Cloud's
        enhanced search endpoint returns each issue with only {"id": ...} — key and all
        application fields (summary, status, etc.) are omitted from the response.

        Raises ValueError before any HTTP request when:
        - selected_issue_keys is empty
        - any key's prefix does not match project_key
        - any key contains JQL metacharacters (single quote, space, JQL keywords, etc.)
        - accessible_keys provided and project_key not in it

        Repeated nextPageToken → raises ValueError (non-progressing cursor guard).
        HTTP 403 → raises JiraPermissionError containing the project key, never the server body.
        After all pages: raises ValueError listing any requested keys absent from the response
        so callers can detect silently-missing issues before writing any files.
        """
        if not selected_issue_keys:
            raise ValueError(
                "issue_items() requires a non-empty set of issue keys. "
                "Pass at least one key, e.g. issue_items('ALPHA', {'ALPHA-1'})."
            )
        for key in selected_issue_keys:
            if not _KEY_PATTERN.match(key):
                raise ValueError(
                    f"Invalid Jira issue key {key!r}. "
                    "Keys must match [A-Z][A-Z0-9]*-<digits> (e.g. ALPHA-1). "
                    "No spaces, quotes, or JQL metacharacters are allowed."
                )
            if not key.startswith(project_key + "-"):
                raise ValueError(
                    f"Issue key {key!r} does not belong to project {project_key!r}. "
                    "All keys in selected_issue_keys must be prefixed with the project key."
                )
        if accessible_keys is not None and project_key not in accessible_keys:
            raise ValueError(
                f"Project {project_key!r} is not in accessible_keys {accessible_keys!r}. "
                "No HTTP request was made."
            )

        keys_clause = ", ".join(sorted(selected_issue_keys))
        jql = f"project = {project_key} AND key IN ({keys_clause})"

        results: list[dict] = []
        next_token: str | None = None
        seen_tokens: set[str] = set()

        for _ in range(_MAX_PAGES):
            params: dict = {
                "jql": jql,
                "maxResults": max_results,
                "fields": ",".join(ISSUE_FIELDS),
            }
            if next_token is not None:
                params["nextPageToken"] = next_token
            try:
                page = self._get("search/jql", **params)
            except JiraPermissionError:
                raise JiraPermissionError(
                    f"Jira returned 403 for project {project_key!r}. "
                    "Check that your API token has read access to this project."
                ) from None
            if page.get("warningMessages") or page.get("errorMessages") or page.get("errors"):
                raise ValueError("Jira search returned warnings or errors; its results may be incomplete.")
            batch = page.get("issues")
            if (not isinstance(batch, list) or any(not isinstance(issue, dict)
                    or not isinstance(issue.get("key"), str) for issue in batch)):
                raise ValueError("Jira returned malformed issue metadata. Retry or contact your Jira administrator.")
            results.extend(batch)
            next_token = page.get("nextPageToken")
            if next_token is not None and (not isinstance(next_token, str) or not next_token):
                raise ValueError("Jira returned malformed pagination metadata. Retry or contact your Jira administrator.")
            if next_token is None:
                returned_keys = {issue.get("key", "") for issue in results}
                missing_keys = selected_issue_keys - returned_keys
                if missing_keys:
                    raise ValueError(
                        f"Jira did not return the following requested issue keys: {sorted(missing_keys)}. "
                        "These keys may not exist, may have been deleted, or your account "
                        "may lack read access to them."
                    )
                return results
            if next_token in seen_tokens:
                raise ValueError(
                    "Jira issue pagination cursor did not advance. "
                    "Aborting to prevent an infinite loop; retry or contact your Jira administrator."
                )
            seen_tokens.add(next_token)

        raise ValueError(
            f"Jira issue pagination exceeded {_MAX_PAGES} pages without exhausting nextPageToken. "
            "Aborting to prevent an infinite loop."
        )

    def scoped_issues(
        self,
        project_key: str,
        *,
        issue_keys: list[str] | None = None,
        since: str | None = None,
        max_results: int = 50,
    ) -> list[dict]:
        """GET /rest/api/3/search/jql — project-scoped issue collection for incremental import (F13FCAKE-19).

        JQL is built from explicit arguments only; raw JQL strings are not accepted.

        Modes:
          since=None, issue_keys=None  → full project query
          since=<ISO 8601>             → incremental query: updated >= since
          issue_keys=[...]             → add key IN (...) filter (validated; project prefix required)

        Results are ordered by updated ASC, key ASC for stable cursor advancement.
        Missing issue_keys in incremental results are normal (not an error).
        On _MAX_PAGES limit: raises ValueError; no truncated data is returned.
        Repeated nextPageToken raises ValueError (infinite-loop guard).

        Raises ValueError before any HTTP request when:
        - project_key is not a valid Jira project key pattern
        - issue_keys is not a list/tuple/set, is provided but empty, or contains invalid keys
        - any issue key fails format validation or does not belong to project_key
        - since is not a parseable ISO 8601 datetime or date string
        - max_results is not an integer in [1, 100]
        """
        if not isinstance(project_key, str) or not project_key:
            raise ValueError("project_key must be a non-empty string.")
        if not re.match(r'^[A-Z][A-Z0-9]*$', project_key):
            raise ValueError(
                f"Invalid project key {project_key!r}. "
                "Project keys must match [A-Z][A-Z0-9]* (e.g. ALPHA). "
                "No spaces, digits at start, or JQL metacharacters are allowed."
            )

        if issue_keys is not None:
            if isinstance(issue_keys, str):
                raise ValueError(
                    "issue_keys must be a list of issue key strings, not a single string. "
                    "Pass a list: issue_keys=['ALPHA-1']."
                )
            if not hasattr(issue_keys, '__iter__'):
                raise ValueError("issue_keys must be a list of issue key strings.")
            issue_keys = list(issue_keys)
            if not issue_keys:
                raise ValueError(
                    "issue_keys must be non-empty when provided; "
                    "omit it entirely for a full project query."
                )
            for key in issue_keys:
                if not isinstance(key, str):
                    raise ValueError(
                        f"Every element of issue_keys must be a string; got {key!r} ({type(key).__name__})."
                    )
                if not _KEY_PATTERN.match(key):
                    raise ValueError(
                        f"Invalid Jira issue key {key!r}. "
                        "Keys must match [A-Z][A-Z0-9]*-<digits> (e.g. ALPHA-1). "
                        "No spaces, quotes, or JQL metacharacters are allowed."
                    )
                if not key.startswith(project_key + "-"):
                    raise ValueError(
                        f"Issue key {key!r} does not belong to project {project_key!r}. "
                        "All keys in issue_keys must be prefixed with the project key."
                    )

        if since is not None:
            if not isinstance(since, str) or not since:
                raise ValueError("since must be a non-empty string when provided.")
            # Strictly parse then serialize a supported JQL date literal.
            # ISO timestamps themselves are not valid quoted JQL dates.
            _parsed_since = None
            try:
                _parsed_since = datetime.datetime.fromisoformat(since)
            except ValueError:
                try:
                    _parsed_since = datetime.date.fromisoformat(since)
                except ValueError:
                    raise ValueError(
                        f"since={since!r} must be a valid ISO 8601 datetime or date "
                        "(e.g. '2024-01-15T10:00:00+00:00' or '2024-01-15'). "
                        "Raw JQL is not accepted."
                    ) from None
            since = _jql_date(_parsed_since)

        if not isinstance(max_results, int) or isinstance(max_results, bool):
            raise ValueError(
                f"max_results must be a positive integer, got {max_results!r}."
            )
        if not 1 <= max_results <= 100:
            raise ValueError(
                f"max_results must be between 1 and 100, got {max_results}."
            )

        clauses = [f"project = {project_key}"]
        if since is not None:
            clauses.append(f'updated >= {since}')
        if issue_keys is not None:
            keys_clause = ", ".join(sorted(issue_keys))
            clauses.append(f"key IN ({keys_clause})")
        jql = " AND ".join(clauses) + " ORDER BY updated ASC, key ASC"

        results: list[dict] = []
        next_token: str | None = None
        seen_tokens: set[str] = set()

        for _ in range(_MAX_PAGES):
            params: dict = {
                "jql": jql,
                "maxResults": max_results,
                "fields": ",".join(ISSUE_FIELDS),
            }
            if next_token is not None:
                params["nextPageToken"] = next_token
            try:
                page = self._get("search/jql", **params)
            except JiraPermissionError:
                raise JiraPermissionError(
                    f"Jira returned 403 for project {project_key!r}. "
                    "Check that your API token has read access to this project."
                ) from None
            if page.get("warningMessages") or page.get("errorMessages") or page.get("errors"):
                raise ValueError(
                    "Jira search returned warnings or errors; its results may be incomplete. "
                    "Check the query and permissions before retrying."
                )
            batch = page.get("issues")
            if (not isinstance(batch, list) or any(not isinstance(issue, dict)
                    or not isinstance(issue.get("key"), str) for issue in batch)):
                raise ValueError(
                    "Jira returned malformed issue metadata. "
                    "Retry or contact your Jira administrator."
                )
            results.extend(batch)
            next_token = page.get("nextPageToken")
            if next_token is not None and (not isinstance(next_token, str) or not next_token):
                raise ValueError(
                    "Jira returned malformed pagination metadata. "
                    "Retry or contact your Jira administrator."
                )
            if next_token is None:
                return results
            if next_token in seen_tokens:
                raise ValueError(
                    "Jira issue pagination cursor did not advance. "
                    "Aborting to prevent an infinite loop; retry or contact your Jira administrator."
                )
            seen_tokens.add(next_token)

        raise ValueError(
            f"Jira issue pagination exceeded {_MAX_PAGES} pages without exhausting nextPageToken. "
            "Aborting to prevent an infinite loop."
        )

    def changed_issues(self, project_key: str, since: str, *, issue_keys=None) -> list[dict]:
        """Read current changed issues in one explicit project; return raw API data.

        Query by minute-safe JQL then filter by the exact aware instant, so an
        inclusive overlap does not skip changes. No cursor or content is written.
        """
        moment = datetime.datetime.fromisoformat(since.replace("Z", "+00:00"))
        if moment.utcoffset() is None or moment > datetime.datetime.now(datetime.timezone.utc):
            raise ValueError("--since must have a timezone and must not be in the future.")
        rows = self.scoped_issues(project_key, issue_keys=issue_keys, since=moment.isoformat())
        selected = set(issue_keys or [])
        result = []
        for row in rows:
            key = row.get("key", "")
            if not _KEY_PATTERN.fullmatch(key) or not key.startswith(project_key + "-") or (selected and key not in selected):
                raise ValueError("Jira returned an issue outside the selected scope; no results were emitted.")
            try:
                updated = datetime.datetime.fromisoformat(row["fields"]["updated"].replace("Z", "+00:00"))
                if updated.utcoffset() is None:
                    raise ValueError("missing timezone")
            except (KeyError, TypeError, AttributeError, ValueError):
                raise ValueError("Jira returned an invalid update time; no results were emitted.") from None
            if updated >= moment:
                result.append(row)
        return result

    def show_issue(self, issue_key: str, *, project_key: str | None = None) -> dict:
        """Read one explicit issue key live; no snapshots or source copies."""
        if not _KEY_PATTERN.fullmatch(issue_key):
            raise ValueError("Use an issue key such as ALPHA-1, not a URL or a row number.")
        project = project_key or issue_key.rsplit("-", 1)[0]
        rows = self.issue_items(project, {issue_key})
        if len(rows) != 1 or rows[0].get("key") != issue_key:
            raise ValueError("Jira returned an unexpected issue; no results were emitted.")
        return rows[0]

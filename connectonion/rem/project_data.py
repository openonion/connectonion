"""Read-only project data projection shared by every REM snapshot view."""
import json
import re
from datetime import datetime, timezone

from .files import read_json, state_path
from .project_obligations import KINDS, open_items, people_index, project_dates, source_entries, written_deadlines
from .project_priority import apply_override, health, issue_deadlines, score_project
from .project_tree import identity, project_tree
from .project_issues import retained_issues
from .project_links import join_obligations
from .project_pages import CODE_REPO_INVALID, code_cache_path, code_repo_valid, code_utc

LOCAL_PATH = '<local repository>'


def enrich_records(root, records, contexts, *, today=None, local=False, states=None, issues=None, owner=None):
    """Project existing evidence in memory; never initialize, fetch or write."""
    today = today or datetime.now(timezone.utc).date()
    by_path = {row['path']: row for row in records}
    owner_name = (by_path.get(owner, {}).get('title', '').split() or [''])[0]
    overrides = read_json(state_path(root, 'project-overrides.json'), {}) if local else {}
    issues = read_json(state_path(root, 'project-issues.json'), {}) if issues is None else issues
    names = people_index(by_path)
    for row in records:
        if row['category'] in ('projects', 'people', 'orgs'):
            row['_source_entries'] = source_entries(row)
            row['written_deadlines'] = written_deadlines(row, contexts)
            row['open'] = open_items(row, by_path, contexts, owner_name, states if local else {}, names)
    candidates = join_obligations(records, contexts, owner)
    for row in records:
        if row['category'] not in ('projects', 'people', 'orgs'):
            continue
        row['kind_counts'] = {kind: sum(item['kind'] == kind for item in row['open']) for kind in KINDS}
        if row['category'] == 'projects':
            repo = identity(row)['repo']
            if repo:
                row['repository'] = repository_projection(root, repo)
                if not local:
                    row['repository'] = _shared_repository(row['repository'])
                if repo not in issues and row['repository'].get('synced_at'):
                    issues = {**issues, repo: row['repository']['issues']}
            _project(row, by_path, contexts, issues, today)
            apply_override(row, overrides.get(row['path'], {}), today)
    for candidate in candidates:
        candidate['kind_counts'] = {kind: int(candidate['kind'] == kind) for kind in KINDS}
        _project(candidate, by_path, contexts, issues, today)
    candidates.sort(key=lambda row: -row['score'])
    project_tree(records)
    for row in records:
        row.pop('_source_entries', None)
    return candidates


def _project(row, records, contexts, issues, today):
    row.update(project_dates(row, contexts))
    repo_issues = issues.get(identity(row)['repo'])
    if repo_issues is None:
        repo_issues = retained_issues(row, contexts)
    row['promised'] = [p for item in row['open'] for p in item['promised']]
    row['promised'] += issue_deadlines(repo_issues, row)
    row['promised'] = list({(p['date'], p['text'], p['source']): p for p in row['promised']}.values())
    row.update(score_project(row, records, contexts, repo_issues, today))
    row['health'], row['health_reason'] = health(row, today, repo_issues)


def repository_projection(root, repo, *, now=None):
    """Cache-only repository contract; bounded observations are never a complete audit."""
    if not code_repo_valid(repo):
        return {'repo': repo, 'status': 'invalid', 'reason': CODE_REPO_INVALID, 'joins': []}
    now = now or datetime.now(timezone.utc)
    cache = read_json(code_cache_path(root, repo), {})
    if not cache:
        return {'repo': repo, 'status': 'missing', 'joins': []}
    result = {key: value for key, value in cache.items() if key not in ('resources',)}
    result['status'] = 'error' if cache.get('error') else 'cached'
    result['joins'] = []
    if not cache.get('synced_at'):
        return result
    prs, runs = cache['prs'], cache['runs']
    issues = {row['number']: row for row in cache['issues'] if row['state'].upper() == 'OPEN'}
    merged = [pr for pr in prs if pr.get('mergedAt')]
    tags = {tag['name'] for tag in cache['tags']}
    deploys = [run for run in runs if _production_deploy(run, cache.get('default_branch'), tags)]
    deploy = max(deploys, key=lambda run: datetime.fromisoformat(run['completedAt'].replace('Z', '+00:00')), default=None)
    _repo_join(result, 'merges_after_green_deploy', ['prs', 'actions/runs'], deploy=deploy,
               basis=' · '.join([deploy['workflowName'], deploy['event'], deploy['branch'],
                                 'completed ' + deploy['completedAt']]) if deploy else None,
               prs=[pr['number'] for pr in merged
                    if deploy and datetime.fromisoformat(pr['mergedAt'].replace('Z', '+00:00')) >
                    datetime.fromisoformat(deploy['completedAt'].replace('Z', '+00:00'))])
    pairs = [{'pr': pr['number'], 'issue': number} for pr in merged
             for number in pr.get('closingIssues', []) if number in issues]
    _repo_join(result, 'merged_closes_open_issue', ['prs', 'issues'], pairs=pairs)
    zero = [n for n, issue in issues.items() if issue['commentCount'] == 0]
    _repo_join(result, 'zero_comment_issues', ['issues'], count=len(zero), issues=zero)
    green = []
    for pr in prs:
        checks = pr.get('statusCheckRollup') or []
        if pr['state'] != 'OPEN' or pr.get('checksTruncated') or pr.get('checkRollupState') != 'SUCCESS' or not checks or not all(
                (check.get('conclusion') or check.get('state')) in ('SUCCESS', 'NEUTRAL', 'SKIPPED') for check in checks):
            continue
        completed = [check.get('completedAt') or check.get('createdAt') for check in checks]
        completed = [code_utc(at) for at in completed if at]
        if completed:
            since = max(completed)
            at = datetime.fromisoformat(since.replace('Z', '+00:00'))
            green.append({'pr': pr['number'], 'green_since': since,
                          'age_hours': max(0, (now - at).total_seconds() / 3600)})
    _repo_join(result, 'green_unmerged_age', ['prs'], prs=green, as_of=code_utc(now))
    failed = []
    versions = (cache.get('pypi') or {}).get('versions', [])
    for run in runs:
        if run['conclusion'] != 'failure' or not _release_run(run, cache.get('default_branch'), tags):
            continue
        tags = [tag['name'] for tag in cache['tags'] if tag.get('commit', {}).get('sha') == run['headSha']
                or tag['name'] == run['branch']]
        failed.append({'run': run['id'], 'tags': tags, 'tag_present': bool(tags),
                       'pypi_present': any(tag.removeprefix('v') in versions for tag in tags)
                       if cache.get('pypi') is not None else None})
    _repo_join(result, 'failed_release', ['actions/runs', 'tags', 'pypi'], runs=failed)
    external = []
    for run in runs:
        if run['conclusion'] != 'action_required':
            continue
        for pr in prs:
            if pr.get('authorAssociation') in ('NONE', 'FIRST_TIMER', 'FIRST_TIME_CONTRIBUTOR', 'CONTRIBUTOR') and (
                    pr['number'] in run.get('prs', []) or
                    (pr.get('headRefOid') and pr['headRefOid'] == run['headSha'])):
                external.append({'pr': pr['number'], 'run': run['id'], 'association': pr['authorAssociation']})
    _repo_join(result, 'external_action_required', ['prs', 'actions/runs'], pairs=external)
    return result


def _shared_repository(projection):
    """A shared view carries no session links and no folder on the owner's disk.

    Every absolute path a recorded command named (`git -C /home/…`) is replaced
    wherever it appears, including an error message that quotes the command.
    """
    if projection.get('churn'):
        projection = {**projection, 'churn': {k: v for k, v in projection['churn'].items() if k != 'session_links'}}
    paths = {arg for row in projection.get('verification', []) + projection.get('failed_verification', [])
             for arg in row['command'] if arg.startswith('/')}
    text = json.dumps(projection)
    for path in sorted(paths, key=len, reverse=True):
        text = text.replace(json.dumps(path)[1:-1], LOCAL_PATH)
    return json.loads(text)


def _production_deploy(run, default_branch, tags):
    """A green deploy of what shipped: a push to the default branch or a tag.

    Any successful run named /deploy/ made a feature-branch dispatch or a
    "Deploy preview" the latest deploy. An old cache without the default branch
    proves no deploy.
    """
    name = run['workflowName']
    return (run['conclusion'] == 'success' and bool(run.get('completedAt'))
            and bool(re.search(r'\bdeploy', name, re.I)) and not re.search(r'preview|staging', name, re.I)
            and (run['event'] in ('push', 'release') and run['branch'] in tags
                 or run['event'] == 'push' and bool(default_branch) and run['branch'] == default_branch))


def _release_run(run, default_branch, tags):
    """A release workflow run for a tag, not "Release Drafter" or "prerelease checks"."""
    name = run['workflowName']
    if not re.search(r'\b(?:release|publish)\b', name, re.I) or re.search(r'draft', name, re.I):
        return False
    if run['event'] in ('release', 'workflow_dispatch'):
        return True
    return run['event'] == 'push' and run['branch'] != default_branch and (
        run['branch'] in tags or bool(re.fullmatch(r'v?\d+(?:\.\d+)+\S*', run['branch'] or '')))


def _repo_join(result, kind, resources, **values):
    result['joins'].append({'kind': kind, **values, 'bounded': True,
                            'verification': [v for v in result.get('verification', []) if v['resource'] in resources]})

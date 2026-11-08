"""Read-only project data projection shared by every REM snapshot view."""
from datetime import datetime, timezone

from .files import read_json, state_path
from .project_obligations import KINDS, open_items, people_index, project_dates, source_entries, written_deadlines
from .project_priority import apply_override, health, issue_deadlines, score_project
from .project_tree import identity, project_tree
from .project_issues import retained_issues
from .project_links import join_obligations


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

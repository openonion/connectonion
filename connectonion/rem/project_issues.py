"""Read-only GitHub issue inputs; snapshots never fetch or persist anything."""
import json
import re
import subprocess

from .project_obligations import source_entries
from .project_tree import identity


def retained_issues(record, contexts):
    rows = []
    for _, source in source_entries(record):
        if not source.startswith('github:'):
            continue
        context = contexts.get(source, {})
        body = context.get('excerpt', '')
        fields = dict(re.findall(r'^(State|Updated|Labels|Title):\s*([^\n]*)', body, re.M | re.I))
        fields = {key.casefold(): value for key, value in fields.items()}
        rows.append({'source': source, 'state': fields.get('state', ''),
                     'updatedAt': fields.get('updated', ''), 'title': fields.get('title', ''),
                     'labels': [label.strip() for label in fields.get('labels', '').split(',') if label.strip()]})
    return rows


def fetch_project_issues(records):
    """Explicit caller opt-in to gh reads, returned in memory; failures are not zero issues."""
    repos = sorted({identity(row)['repo'] for row in records if row['category'] == 'projects'} - {''})
    return {repo: _fetch(repo) for repo in repos}


def _fetch(repo):
    query = ('query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){'
             'issues(first:100,after:$cursor,states:OPEN){pageInfo{hasNextPage endCursor} nodes{'
             'url title state updatedAt labels(first:100){nodes{name}} milestone{dueOn}}}}}')
    owner, name = repo.split('/')
    rows, cursor = [], None
    while True:
        argv = ['gh', 'api', 'graphql', '-f', 'query=' + query, '-f', 'owner=' + owner, '-f', 'name=' + name]
        if cursor:
            argv += ['-f', 'cursor=' + cursor]
        run = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=True)
        data = json.loads(run.stdout)
        if data.get('errors'):
            raise ValueError('GitHub issue query failed: ' + json.dumps(data['errors']))
        result = data['data']['repository']['issues']
        rows += [{**row, 'labels': row['labels']['nodes']} for row in result['nodes']]
        if not result['pageInfo']['hasNextPage']:
            return rows
        cursor = result['pageInfo']['endCursor']

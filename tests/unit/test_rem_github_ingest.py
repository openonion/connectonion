"""Fictional GitHub packets, through a PATH shim; never owner credentials."""
import json
import os
from datetime import datetime, timezone, timedelta

import pytest

from connectonion.rem import project_pages as pages, project_data as data

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
REPO = 'fernhill/lanterns'


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))


@pytest.fixture
def gh(tmp_path, monkeypatch):
    folder = tmp_path / 'bin'
    folder.mkdir()
    log = tmp_path / 'gh.jsonl'
    fixtures = tmp_path / 'responses.json'
    fixtures.write_text(json.dumps({
        'issues': [{'number': 7, 'title': 'Cedar light', 'state': 'open', 'labels': [],
                    'user': {'login': 'mara-quill'}, 'comments': 0, 'updated_at': NOW.isoformat(), 'closed_at': None}],
        'pulls': [{'number': 8, 'title': 'Fix cedar (#7)', 'state': 'MERGED',
                   'headRefName': 'cedar', 'mergedAt': '2026-11-08T11:00:00Z',
                   'authorAssociation': 'CONTRIBUTOR', 'statusCheckRollup': []}],
        'runs': [{'id': 4, 'name': 'Deploy', 'event': 'push', 'head_branch': 'main', 'conclusion': 'success',
                  'created_at': '2026-11-08T10:00:00Z', 'head_sha': 'abc'},
                 {'id': 5, 'name': 'Release', 'event': 'push', 'head_branch': 'v1.2.0', 'conclusion': 'failure',
                  'created_at': '2026-11-08T11:30:00Z', 'head_sha': 'def'}],
        'tags': [{'name': 'v1.2.0', 'commit': {'sha': 'def'}}], 'releases': []}))
    executable = folder / 'gh'
    executable.write_text('''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['GH_LOG'], 'a') as f: f.write(json.dumps(args) + '\\n')
rows = json.load(open(os.environ['GH_FIXTURES']))
if args[1] == 'graphql':
    print(json.dumps({'data': {'repository': {'pullRequests': {'nodes': rows['pulls']}}}}))
else:
    endpoint = args[1]
    key = 'runs' if '/actions/runs' in endpoint else endpoint.split('?')[0].rsplit('/', 1)[-1]
    if 'If-None-Match:' in ' '.join(args):
        print('HTTP/2.0 304 Not Modified\\n\\n')
    else:
        value = rows[key] if 'page=2' not in endpoint else []
        if key == 'runs': value = {'workflow_runs': value}
        print('HTTP/2.0 200 OK\\nETag: "cedar"\\n\\n' + json.dumps(value))
''')
    executable.chmod(0o755)
    monkeypatch.setenv('PATH', str(folder) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('GH_LOG', str(log))
    monkeypatch.setenv('GH_FIXTURES', str(fixtures))
    return log


@pytest.mark.parametrize('args', [
    ['pr', 'merge', '8'], ['issue', 'comment', '7'], ['run', 'rerun', '5'],
    ['api', 'repos/fernhill/lanterns/issues', '-X', 'POST'],
    ['api', 'graphql', '-f', 'query=mutation { dangerous }'],
    ['api', 'repos/fernhill/lanterns/issues', '--input', 'payload.json'],
])
def test_guard_refuses_non_reads(args, gh):
    with pytest.raises(ValueError, match='read-only'):
        pages.github_read(args)
    assert not gh.exists()


def test_sync_cache_skip_etag_and_projection(tmp_path, gh, monkeypatch):
    cache = pages.sync_repository(tmp_path, REPO, now=NOW)
    assert len(cache['issues']) == 1
    assert cache['issues'][0]['commentCount'] == 0
    assert cache['issues'][0]['author'] == 'mara-quill'
    assert (tmp_path / '.state/code/fernhill__lanterns/repository.json').is_file()
    commands = gh.read_text().splitlines()
    pages.sync_repository(tmp_path, REPO, now=NOW + timedelta(minutes=1))
    assert gh.read_text().splitlines() == commands
    cache = pages.sync_repository(tmp_path, REPO, now=NOW + timedelta(minutes=31))
    assert 'If-None-Match:' in gh.read_text()
    assert cache['issues'][0]['number'] == 7
    monkeypatch.setattr(pages.subprocess, 'run', lambda *a, **k: pytest.fail('projection ran a command'))
    projection = data.repository_projection(tmp_path, REPO, now=NOW)
    joins = {j['kind']: j for j in projection['joins']}
    assert joins['merges_after_green_deploy']['prs'] == [8]
    assert joins['merged_title_open_issue']['pairs'] == [{'pr': 8, 'issue': 7}]
    assert joins['zero_comment_issues']['count'] == 1
    assert joins['failed_release']['runs'][0]['tag_present'] is True
    for join in joins.values():
        assert join['verification']
        assert all(v['command'] and v['ran_at'].endswith('Z') for v in join['verification'])


def test_session_commit_links_require_exact_cwd_time_and_printed_branch(tmp_path):
    repo = tmp_path / 'lanterns'
    repo.mkdir()
    commit = {'sha': 'abc', 'time': '2026-11-08T12:00:00Z'}
    session = {'id': 'cedar-session', 'cwd': str(repo), 'started': '2026-11-08T09:00:00Z',
               'ended': '2026-11-08T10:00:00Z', 'printed_branches': ['cedar']}
    result = pages.session_commit_links([session], [commit], [str(repo)])
    assert result[0]['sha'] == 'abc'
    assert result[0]['branches'] == ['cedar']
    assert pages.session_commit_links([{**session, 'cwd': str(repo / 'src')}], [commit], [str(repo)]) == []
    assert pages.session_commit_links([session], [{**commit, 'time': '2026-11-08T12:00:01Z'}], [str(repo)]) == []
    assert pages.session_commit_links([{**session, 'started': '2026-11-08T13:00:00Z'}], [commit], [str(repo)]) == []
    assert pages.session_commit_links([{**session, 'ended': ''}], [commit], [str(repo)]) == []

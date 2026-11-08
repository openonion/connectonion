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
                  'created_at': '2026-11-08T10:00:00Z', 'updated_at': '2026-11-08T10:05:00Z', 'head_sha': 'abc'},
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
    # Real gh 2.97 (checked read-only against cli/cli): the status line ends in
    # LF, headers in CRLF; a 304 prints its headers, then exits 1 with
    # "gh: HTTP 304" on stderr.
    if os.environ.get('GH_STATUS') == '404':
        sys.stdout.write('HTTP/2.0 404 Not Found\\r\\n\\r\\n{"message":"Not Found"}')
        sys.stderr.write('gh: Not Found (HTTP 404)\\n')
        sys.exit(1)
    if 'If-None-Match:' in ' '.join(args):
        sys.stdout.write('HTTP/2.0 304 Not Modified\\nEtag: "cedar"\\r\\n\\r\\n')
        sys.stderr.write('gh: HTTP 304\\n')
        sys.exit(1)
    page = 2 if '&page=2' in endpoint else 1
    value = rows[key][(page-1)*100:page*100]
    if key == 'runs': value = {'workflow_runs': value}
    sys.stdout.write('HTTP/2.0 200 OK\\nEtag: "cedar"\\r\\n\\r\\n' + json.dumps(value))
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
    assert cache['error'] is None
    assert cache['synced_at'] == '2026-11-08T12:31:00Z'
    assert {v.get('status') for v in cache['verification'] if v['resource'] != 'prs'} == {304}
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


def test_only_a_304_exit_is_accepted(tmp_path, gh, monkeypatch):
    pages.sync_repository(tmp_path, REPO, now=NOW)
    monkeypatch.setenv('GH_STATUS', '404')
    cache = pages.sync_repository(tmp_path, REPO, now=NOW + timedelta(minutes=31))
    assert 'returned non-zero exit status 1' in cache['error']
    assert cache['synced_at'] == '2026-11-08T12:00:00Z'


def test_caps_stop_before_exhausting_repository(tmp_path, gh):
    path = os.environ['GH_FIXTURES']
    packet = json.loads(open(path).read())
    packet['issues'] *= 250
    packet['pulls'] *= 150
    packet['runs'] *= 150
    with open(path, 'w') as out:
        json.dump(packet, out)
    cache = pages.sync_repository(tmp_path, REPO, now=NOW)
    assert len(cache['issues']) == 200
    assert len(cache['prs']) == 100
    assert len(cache['runs']) == 200
    calls = [json.loads(line) for line in gh.read_text().splitlines()]
    assert len(calls) == 7
    assert all('--paginate' not in call for call in calls)


def test_failed_sync_preserves_success_and_reports_error(tmp_path, gh):
    before = pages.sync_repository(tmp_path, REPO, now=NOW)
    with open(os.environ['GH_FIXTURES'], 'w') as out:
        out.write('{}')
    cache = pages.sync_repository(tmp_path, REPO, now=NOW + timedelta(minutes=31))
    assert cache['synced_at'] == before['synced_at']
    assert cache['issues'] == before['issues']
    assert cache['error']
    assert data.repository_projection(tmp_path, REPO)['status'] == 'error'


def test_local_churn_and_registered_worktree_links(tmp_path):
    import subprocess
    repo = tmp_path / 'lanterns'
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout
    repo.mkdir()
    git('init', '-b', 'cedar')
    git('config', 'user.name', 'Mara Quill')
    git('config', 'user.email', 'mara@example.invalid')
    (repo / 'src').mkdir()
    (repo / 'src/light.py').write_text('light = True\n')
    git('add', '.')
    env = {**os.environ, 'GIT_AUTHOR_DATE': '2026-11-08T11:00:00Z', 'GIT_COMMITTER_DATE': '2026-11-08T11:00:00Z'}
    subprocess.run(['git', '-C', str(repo), 'commit', '-m', 'Add a cedar light.'], env=env, check=True, capture_output=True)
    worktree = tmp_path / 'cedar-worktree'
    git('worktree', 'add', '-b', 'cedar-review', str(worktree))
    evidence = []
    session = {'id': 'cedar', 'cwd': str(worktree), 'started': '2026-11-08T10:00:00Z',
               'ended': '2026-11-08T11:00:00Z', 'printed_branches': ['cedar-review']}
    churn = pages._code_local(repo, NOW, 14, [session], evidence)
    assert churn['areas']['src'] == {'additions': 1, 'deletions': 0, 'files': 1, 'commits': 1}
    assert churn['since'] == '2026-10-25T12:00:00Z'
    assert churn['session_links'][0]['branches'] == ['cedar-review']
    assert len(evidence) == 2


def test_green_age_external_runs_and_pypi_join(tmp_path, gh):
    cache = pages.sync_repository(tmp_path, REPO, now=NOW)
    cache['prs'] += [{'number': 9, 'title': 'Cedar review', 'state': 'OPEN', 'headRefOid': 'abc',
                      'authorAssociation': 'FIRST_TIMER', 'checkRollupState': 'SUCCESS', 'statusCheckRollup': [
                          {'conclusion': 'SUCCESS', 'completedAt': '2026-11-08T10:00:00Z'}]}]
    cache['runs'] += [{'id': 6, 'workflowName': 'CI', 'event': 'pull_request', 'branch': 'cedar',
                       'conclusion': 'action_required', 'createdAt': '2026-11-08T11:30:00Z', 'headSha': 'abc'}]
    cache['pypi'] = {'package': 'lanterns', 'versions': ['1.2.0']}
    pages.write_json(pages.code_cache_path(tmp_path, REPO), cache)
    joins = {j['kind']: j for j in data.repository_projection(tmp_path, REPO, now=NOW)['joins']}
    assert joins['green_unmerged_age']['prs'][0]['age_hours'] == 2
    assert joins['external_action_required']['pairs'] == [{'pr': 9, 'run': 6, 'association': 'FIRST_TIMER'}]
    assert joins['failed_release']['runs'][0]['pypi_present'] is True


def test_naive_session_times_are_refused():
    with pytest.raises(ValueError, match='timezone'):
        pages.code_utc('2026-11-08T12:00:00')


def test_cached_issues_preserve_priority_source_and_milestone(tmp_path, gh):
    packet = json.loads(open(os.environ['GH_FIXTURES']).read())
    packet['issues'][0].update(labels=[{'name': 'bug'}], html_url='https://github.com/fernhill/lanterns/issues/7',
                               milestone={'due_on': '2026-11-10T12:00:00Z'})
    with open(os.environ['GH_FIXTURES'], 'w') as out:
        json.dump(packet, out)
    cache = pages.sync_repository(tmp_path, REPO, now=NOW)
    assert cache['issues'][0]['url'] == 'https://github.com/fernhill/lanterns/issues/7'
    assert cache['issues'][0]['milestone']['dueOn'] == '2026-11-10T12:00:00Z'
    row = {'path': 'projects/lanterns.md', 'category': 'projects', 'title': 'Lanterns',
           'text': '# Lanterns\n\n## Facts\n- Repository: fernhill/lanterns\n'}
    data.enrich_records(tmp_path, [row], {}, today=NOW.date(), local=True)
    assert row['score'] > 0
    assert row['health'] == 'at_risk'


def test_wrong_local_repository_is_not_labeled_as_named_repo(tmp_path, gh):
    import subprocess
    other = tmp_path / 'other'
    other.mkdir()
    subprocess.run(['git', '-C', str(other), 'init'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(other), 'remote', 'add', 'origin',
                    'https://github.com/fernhill/other.git'], check=True, capture_output=True)
    cache = pages.sync_repository(tmp_path, REPO, repo_path=other, now=NOW)
    assert cache['churn'] is None
    assert cache['local_status'] == 'repository_mismatch'


def test_partial_check_sample_cannot_prove_green(tmp_path, gh):
    cache = pages.sync_repository(tmp_path, REPO, now=NOW)
    cache['prs'] = [{'number': 9, 'title': 'Cedar review', 'state': 'OPEN',
                     'checkRollupState': 'PENDING', 'statusCheckRollup': [
                         {'conclusion': 'SUCCESS', 'completedAt': '2026-11-08T10:00:00Z'}]}]
    pages.write_json(pages.code_cache_path(tmp_path, REPO), cache)
    joins = {j['kind']: j for j in data.repository_projection(tmp_path, REPO, now=NOW)['joins']}
    assert joins['green_unmerged_age']['prs'] == []


def test_pypi_is_a_bounded_https_read(tmp_path, monkeypatch):
    import io
    import urllib.request
    calls = []
    class Response(io.BytesIO):
        def read(self, size=-1):
            calls.append(size)
            return super().read(size)
    def open_json(request, timeout):
        assert request.full_url == 'https://pypi.org/pypi/lanterns/json'
        assert request.get_method() == 'GET' and timeout == 20
        return Response(b'{"releases":{"1.2.0":[],"1.1.0":[]}}')
    monkeypatch.setattr(urllib.request, 'urlopen', open_json)
    evidence = []
    assert pages._code_pypi('lanterns', evidence)['versions'] == ['1.1.0', '1.2.0']
    assert calls == [4_000_001]
    assert evidence[0]['command'] == ['HTTPS', 'GET', 'https://pypi.org/pypi/lanterns/json']
    assert evidence[0]['ran_at'].endswith('Z')
    with pytest.raises(ValueError):
        pages._code_pypi('../lanterns', [])


def test_package_selection_prefers_explicit_fact(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "lanterns"\n')
    assert pages._code_package('', tmp_path) == 'lanterns'
    assert pages._code_package('- PyPI: https://pypi.org/project/cedar-lights/', tmp_path) == 'cedar-lights'


def test_successful_but_truncated_checks_cannot_establish_green_age(tmp_path, gh):
    cache = pages.sync_repository(tmp_path, REPO, now=NOW)
    cache['prs'] = [{'number': 9, 'title': 'Cedar review', 'state': 'OPEN',
                     'checkRollupState': 'SUCCESS', 'checksTruncated': True, 'statusCheckRollup': [
                         {'conclusion': 'SUCCESS', 'completedAt': '2026-11-08T10:00:00Z'}]}]
    pages.write_json(pages.code_cache_path(tmp_path, REPO), cache)
    joins = {j['kind']: j for j in data.repository_projection(tmp_path, REPO, now=NOW)['joins']}
    assert joins['green_unmerged_age']['prs'] == []


def test_non_git_project_folder_does_not_discard_remote_evidence(tmp_path, gh):
    folder = tmp_path / 'lanterns'
    folder.mkdir()
    cache = pages.sync_repository(tmp_path, REPO, repo_path=folder, now=NOW)
    assert cache.get('error') is None
    assert cache['issues'][0]['number'] == 7
    assert cache['churn'] is None
    assert cache['local_status'] == 'repository_mismatch'

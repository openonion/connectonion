from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.map import build_map


def test_map_groups_project_worktrees_preserves_pages_and_keeps_noise(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    (skills / 'demo').mkdir(parents=True)
    source = skills / 'demo/SKILL.md'
    source.write_text('---\nname: demo\ndescription: Synthetic demo\n---\nDo something.')
    original = source.read_bytes()
    people = [{'name': 'Notices', 'address': 'noreply@example.org', 'mails': 2}]
    monkeypatch.setattr('connectonion.wiki.map._mail_rows', lambda *a: (people, set()))
    monkeypatch.setattr('connectonion.wiki.map.scan_projects', lambda *a: [
        {'name': 'Atlas', 'repo': '/repo/atlas', 'origin': 'https://example.org/atlas',
         'path': path, 'sessions': 2, 'first': '2026-09-18', 'last': '2026-09-19'}
        for path in ('/repo/atlas', '/worktree/atlas')])
    first = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert len(first['people']) == len(first['projects']) == 1
    record = first['projects'][0]['record']
    nb = Notebook(tmp_path)
    assert first['projects'][0]['sessions'] == 4
    assert '/worktree/atlas' in nb.read(record)
    assert first['people'][0]['classification'] == 'automated candidate'
    nb.write(record, nb.read(record).replace('## What it is\n', '## What it is\nCurated purpose.\n'))
    second = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert not second['created']
    assert 'Curated purpose.' in nb.read(record)
    assert source.read_bytes() == original
    assert second['investigation'] == 'not started'


def test_project_scan_honors_disabled_and_project_scopes(tmp_path):
    import json
    from connectonion.wiki.scan import scan_projects
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    for i, cwd in enumerate(('/allowed', '/outside')):
        (sessions / f'rollout-{i}.jsonl').write_text(json.dumps({'type': 'session_meta', 'payload': {
            'id': str(i), 'cwd': cwd, 'originator': 'codex_cli_rs'}}) + '\n')
    sub = {'kind': 'codex', 'root': str(sessions), 'enabled': True, 'project': '/allowed'}
    assert [r['path'] for r in scan_projects({'local': sub}, 1)] == ['/allowed']
    assert scan_projects({'local': {**sub, 'enabled': False}}, 1) == []


def test_unavailable_mail_does_not_stop_other_maps(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    class Unavailable:
        def my_addresses(self):
            raise RuntimeError('private provider detail')
    result = build_map(tmp_path, {}, {'gmail': Unavailable()}, skill_directories=[skills])
    assert result['phase'] == 'partial'
    assert 'gmail: unavailable (RuntimeError); not searched' in result['coverage']
    assert 'private provider detail' not in str(result)


def test_map_creates_owner_from_verified_account_aliases(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    class Mail:
        def my_addresses(self):
            return {'owner@example.org'}
        def list_between(self, start, end, limit):
            return []
    result = build_map(tmp_path, {}, {'gmail': Mail()}, skill_directories=[skills])
    owner = result['owner']['record']
    assert 'owner@example.org' in Notebook(tmp_path).read(owner)
    assert 'not investigated yet' in Notebook(tmp_path).read(owner)
    assert build_map(tmp_path, {}, {'gmail': Mail()}, skill_directories=[skills])['owner']['record'] == owner

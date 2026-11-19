"""#3165 deep hunt (2026-11-19): on the owner's notebook 29/40, 32/40 and 40/40 source titles on three project pages
opened an empty card ("此快照未包含原始内容"). The snapshot's cited excerpts share one budget across the notebook,
mail first, so a project's repository files, sessions and GitHub commits rarely fit. The live reader asks the Host
for the one source it is opening."""
import hashlib
import json
from urllib.parse import urlencode

from connectonion.rem.files import state_path, write_json
from tests.unit.test_rem_handoff_polish import call, host  # noqa: F401  (fixture)


def _retained(root, origin, text):
    source = 'project-source:' + hashlib.sha256((origin + '\0' + text).encode()).hexdigest()
    write_json(state_path(root, 'project-sources/' + source.split(':')[1] + '.json'),
               {'id': source, 'origin': origin, 'text': text, 'snapshot_kind': 'repository-packet', 'captured_at': '2026-10-26T00:00:00Z'})
    return source


def test_the_live_reader_fetches_one_cited_source_the_snapshot_left_out(host):  # noqa: F811
    source = _retained(host.root, 'git:/repo/README.md', 'Harbour reads mail and writes the notebook.')
    query = urlencode({'id': source}).encode()
    assert call(host.routes, 'GET', '/rem/source', query=query)[0] == 401
    status, headers, body = call(host.routes, 'GET', '/rem/source', cookie=f'co_rem={host.token}', query=query)
    assert status == 200 and headers['content-type'].startswith('application/json')
    context = json.loads(body)
    assert 'Harbour reads mail' in context['excerpt'] and context['origin'] == 'git:/repo/README.md'


def test_an_unknown_or_malformed_source_is_not_found_and_never_reads_a_file(host):  # noqa: F811
    cookie = f'co_rem={host.token}'
    for value in ('project-source:' + 'a' * 64, '../../etc/passwd', 'file:/etc/passwd', ''):
        assert call(host.routes, 'GET', '/rem/source', cookie=cookie, query=urlencode({'id': value}).encode())[0] == 404, value
    assert call(host.routes, 'GET', '/rem/source', cookie=cookie, query=urlencode({'id': 'x'}).encode(), client='192.168.1.2')[0] == 404


def test_a_project_source_left_out_of_the_snapshot_still_has_its_file_name(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.reader import source_labels
    root = tmp_path / 'rem'
    prepare(root)
    source = _retained(root, 'git:/repo/docs/README.md:0ec88afcc529cf76d', 'Harbour reads mail.')
    labels = source_labels(root, [{'text': f'## Sources\n- [1] {source} — 2026-10-26\n'}], {})
    assert labels == {source: {'origin': 'git:/repo/docs/README.md:0ec88afcc529cf76d'}}
    assert source_labels(root, [{'text': f'- [1] {source}\n'}], {source: {'excerpt': 'x'}}) == {}  # already in the snapshot

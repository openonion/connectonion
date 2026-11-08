"""A graph is a projection of explicit links, with sessions folded and privacy intact."""
from connectonion.rem.reader_model import relationships
from connectonion.rem.files import Notebook


def record(path, text):
    return {'path': path, 'category': path.split('/')[0], 'title': text.splitlines()[0][2:], 'text': text, 'written': True}


def test_topic_links_supply_both_directions_with_the_same_sentence():
    rows = [record('knowledge/heat.md', '# Heat\n## People\n- [Mara](../people/mara.md) studies heat. [1]\n'), record('people/mara.md', '# Mara\n')]
    links = relationships(rows)
    assert links['people/mara.md'][0]['kind'] == 'linked from'
    assert links['people/mara.md'][0]['basis'] == links['knowledge/heat.md'][0]['basis']


def test_graph_folds_sessions_deduplicates_edges_and_counts_isolates():
    from connectonion.rem.reader_model import graph_snapshot
    rows = [record('projects/cove.md', '# Cove\n- [Session](../sessions/a.md)\n'),
            record('sessions/a.md', '# Session\n- Project: [Cove](../projects/cove.md)\n- [Mara](../people/mara.md)\n'),
            record('people/mara.md', '# Mara\n'), record('people/ellis.md', '# Ellis\n'),
            record('knowledge/heat.md', '# Heat\n- [Mara](../people/mara.md) studies heat.\n## Open threads\n- The user owes: a proposal.\n')]
    graph = graph_snapshot(rows)
    nodes = {n['id']: n for n in graph['nodes']}
    assert 'sessions/a.md' not in nodes
    assert nodes['projects/cove.md']['degree'] == 1
    assert nodes['knowledge/heat.md']['has_owed']
    assert graph['unconnected'] == {'count': 1, 'by_kind': {'people': 1}}
    assert graph['folded_sessions'] == 1
    assert len(graph['edges']) == 2
    assert all(set(e) == {'source', 'target', 'kind'} for e in graph['edges'])


def test_private_topic_relationships_are_private_and_graph_title_is_blank():
    from connectonion.rem.reader_model import graph_snapshot
    rows = [record('knowledge/health.md', '# Asthma [personal]\n- [Mara](../people/mara.md) helps.\n'), record('people/mara.md', '# Mara\n')]
    assert relationships(rows)['people/mara.md'][0]['private']
    node = next(n for n in graph_snapshot(rows)['nodes'] if n['id'] == 'knowledge/health.md')
    assert node['private'] and node['title'] == ''


def test_shared_snapshot_has_no_private_topic_or_review_basis(tmp_path):
    import json
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.reviews import propose
    from connectonion.rem.reader import snapshot
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.write('knowledge/private.md', '# Secret inheritance [personal]\n## What it is\nPrivate financial details.\n')
    nb.write('people/mara.md', '# Mara\n')
    propose(tmp_path, 'link', ['knowledge/private.md', 'people/mara.md'], 'Related?', 'Secret inheritance is involved.')
    shared = json.dumps(snapshot(tmp_path, local=False))
    assert 'Secret inheritance' not in shared
    assert 'Private financial details' not in shared


def test_handoff_redacts_whole_labelled_topic_not_only_title():
    from connectonion.handoff.bundle import redact
    note = '# My asthma [personal]\n## What it is\nA private diagnosis.\n## Sources\n- [1] gmail:abc\n'
    result = redact('Work update.\n\n' + note + '\n# Public work\nNext milestone.\n')
    assert 'Work update.' in result and 'Next milestone.' in result
    assert 'asthma' not in result and 'private diagnosis' not in result and 'gmail:abc' not in result


def test_topic_mentions_keep_the_newest_cited_sentence_per_record():
    from connectonion.rem.reader_model import topic_mentions
    row = {'evidence': [
        {'record': 'people/mara.md', 'source': 'gmail:a', 'date': '2026-01-01', 'sentence': 'Mara first asked about heat storage.'},
        {'record': 'people/mara.md', 'source': 'gmail:b', 'date': '2026-02-01', 'sentence': 'Mara priced heat storage.'},
        {'record': 'projects/cove.md', 'source': 'gmail:c', 'date': '2026-01-20', 'sentence': 'Cove stores heat.'},
        {'record': 'people/owner.md', 'source': 'gmail:d', 'date': '2026-03-01', 'sentence': 'You read about heat storage.'},
        {'record': 'sessions/s.md', 'source': 'codex:s', 'date': '2026-03-02', 'sentence': 'A session on heat storage.'},
        {'record': 'people/ellis.md', 'source': 'gmail:e', 'date': '2026-03-03', 'sentence': 'Ellis heat storage [personal].', 'private': True}]}
    paths = {'people/mara.md', 'projects/cove.md', 'people/owner.md', 'sessions/s.md', 'people/ellis.md'}
    found = topic_mentions(row, paths, 'people/owner.md')
    assert [m['path'] for m in found] == ['people/mara.md', 'projects/cove.md']
    assert found[0] == {'path': 'people/mara.md', 'sentence': 'Mara priced heat storage.', 'date': '2026-02-01', 'source': 'gmail:b'}


def test_topic_mentions_connect_people_with_no_other_link_in_the_graph():
    from connectonion.rem.reader_model import graph_snapshot
    rows = [record('knowledge/heat.md', '# Heat storage\n'), record('people/mara.md', '# Mara\n'), record('people/ellis.md', '# Ellis\n')]
    graph = graph_snapshot(rows, topics={'knowledge/heat.md': ['people/mara.md', 'people/ellis.md']})
    assert sorted((e['source'], e['target'], e['kind']) for e in graph['edges']) == [
        ('knowledge/heat.md', 'people/ellis.md', 'topic'), ('knowledge/heat.md', 'people/mara.md', 'topic')]
    assert graph['unconnected']['count'] == 0


def test_snapshot_gives_a_stub_topic_its_cited_mentions_and_graph_edges(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.reader import snapshot
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    nb.stub_topic('knowledge/heat-storage.md', 'Heat storage', ['Heat storage', 'thermal battery'])
    nb.write('people/mara.md', '# Mara\n## Insight\n- Mara is building a thermal battery for the cove. [1]\n\n## Sources\n- [1] gmail:m1 — 2026-02-03 — Mara\n')
    nb.write('projects/cove.md', '# Cove\n## What it is\n- Cove sells heat storage to farms. [1]\n\n## Sources\n- [1] gmail:c1 — 2026-01-10 — Cove\n')
    nb.write('people/ellis.md', '# Ellis\nEllis once said heat storage.\n')
    data = snapshot(tmp_path, local=True)
    topic = next(r for r in data['records'] if r['path'] == 'knowledge/heat-storage.md')['topic']
    assert [(m['path'], m['date']) for m in topic['mentions']] == [('people/mara.md', '2026-02-03'), ('projects/cove.md', '2026-01-10')]
    assert topic['mentions'][0]['sentence'] == 'Mara is building a thermal battery for the cove.'
    assert topic['last'] == '2026-02-03'
    assert [d['record'] for d in topic['doubtful']] == ['people/ellis.md']
    edges = {(e['source'], e['target']) for e in data['graph']['edges'] if e['kind'] == 'topic'}
    assert edges == {('knowledge/heat-storage.md', 'people/mara.md'), ('knowledge/heat-storage.md', 'projects/cove.md')}


def test_reader_inlines_the_pinned_d3_and_keeps_the_graph_out_of_the_today_shell(tmp_path):
    import hashlib
    import re
    from connectonion.rem.config import prepare
    from connectonion.rem.reader import D3, render
    prepare(tmp_path)
    Notebook(tmp_path).write('people/mara.md', '# Mara\n')
    page = render(tmp_path, local=True)
    assert hashlib.sha256(D3.read_bytes()).hexdigest() == 'f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539'
    assert 'd3js.org v7.9.0' in page and '/*__D3__*/' not in page
    assert not re.search(r'<script[^>]+src=', page)
    shell = page.split('const REM = ', 1)[1].split(';\n', 1)[0]
    assert '"graph"' not in shell


def test_a_long_topic_sentence_is_shortened_around_the_topic_name():
    from connectonion.rem.reader_model import topic_mentions
    long = 'Mara listed the costs of the barn roof, the fencing, the new gate and the well pump in great detail ' * 3 + 'before turning to heat storage for the cove.'
    row = {'aliases': ['Heat storage'], 'evidence': [{'record': 'people/mara.md', 'source': 'gmail:a', 'date': '2026-01-01', 'sentence': long}]}
    sentence = topic_mentions(row, {'people/mara.md'}, '')[0]['sentence']
    assert 'heat storage' in sentence and sentence.startswith('…') and len(sentence) <= 240

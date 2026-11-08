"""A graph is a projection of explicit links, with sessions folded and privacy intact."""
from connectonion.rem.reader_model import relationships


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

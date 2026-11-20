"""Opaque Reader targets remain exact after Markdown normalization and restart."""

import pytest

from connectonion.rem import page_review, reader_model, source_hooks as hooks
from connectonion.rem.files import RemError, state_path, write_json
from connectonion.rem.source_citations import canonical_sources, routes
from tests.unit.rem_source_fixtures import citation, shared_sources


@pytest.mark.parametrize('heading', ['Sources:', 'Source:', '## Sources:', 'Sources'])
def test_canonical_sources_preserves_complete_target(heading):
    target = 'adapter:docs/granola/daily/2026/11/08.jsonl#granola:personal:not_example?version=' + 'a' * 64
    raw = '# Atlas\n\nA saved decision. [1]\n\n' + heading + '\n[1] `' + target + '` — saved\n'
    canonical = canonical_sources(raw, prefixes={'adapter'})
    assert '\n## Sources\n- [1] ' + target + ' — saved\n' in canonical
    assert canonical_sources(canonical, prefixes={'adapter'}) == canonical


def test_exact_granola_inline_regression_spelling():
    target = 'adapter:docs/granola/daily/2026/11/08.jsonl#granola:personal:not_example?version=' + 'b' * 64
    assert canonical_sources('Sources: [1] ' + target, prefixes={'adapter'}) == '## Sources\n- [1] ' + target


def test_normalization_does_not_rewrite_fences_or_following_sections():
    target = citation('summaries')
    example = '```text\nSources: [1] ' + target + '\n```'
    tail = '\n## Next\n[2] ' + target
    raw = example + '\nSources: [1] ' + target + tail
    normal = canonical_sources(raw, prefixes={'adapter'})
    assert normal.startswith(example + '\n## Sources\n- [1] ')
    assert normal.endswith(tail)


def test_malformed_and_unknown_targets_are_not_repaired():
    bad = 'adapter:docs/summaries/x.jsonl#summaries:me:one?version=bad'
    normal = canonical_sources('Sources: [1] ' + bad, prefixes={'adapter'})
    assert bad in normal
    assert canonical_sources('Sources: [1] unknown:one', prefixes={'adapter'}) == 'Sources: [1] unknown:one'


def test_inline_target_survives_drop_filter_and_reader_uses_exact_version(shared_sources):
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    old = hooks.collect(env.root, 'summaries', {}, 2, 10000)
    target = old.items[0]['source']
    env.current['summaries'] = 2
    hooks.fetch(env.root)
    hooks.collect(env.root, 'summaries', old.progress, 2, 10000)
    raw = '# Atlas\n\n## Where it stands\n- Atlas saved version 1. [1]\n\nSources: [1] ' + target + '\n'
    normalized, dropped = page_review.drop_unresolved('projects/atlas.md', raw, '', [], root=env.root)
    assert dropped['citations'] == []
    assert '\n## Sources\n- [1] ' + target in normalized
    contexts = reader_model.cited_context(env.root, [{'text': normalized}])
    assert contexts[target]['excerpt'] == 'Atlas saved version 1'
    assert page_review._lost_sources('\n## Sources\n- [1] ' + target,
        '\n## Sources\n- [1] ' + citation('summaries', 2), root=env.root) == set()


def test_removed_source_cannot_resolve_through_reader_fallback(shared_sources, monkeypatch):
    from connectonion.rem import service, source_versions
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    target = hooks.collect(env.root, 'summaries', {}, 2, 10000).items[0]['source']
    service.toggle_source(env.root, 'summaries', False)
    monkeypatch.setitem(source_versions.KINDS, 'adapter', source_versions.Kind(
        lambda target: 'bypass', lambda *args: pytest.fail('used legacy route')))
    assert target not in reader_model.cited_context(env.root, [{'text': '\n## Sources\n- [1] ' + target}])


def test_missing_registration_does_not_release_retained_evidence(shared_sources, monkeypatch):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 2, 10000).items
    monkeypatch.setattr(hooks, 'MODULES', {})
    assert not hooks.material_approved(env.root, items)


def test_corrupt_ownership_fails_closed(shared_sources):
    env = shared_sources
    write_json(state_path(env.root, 'source-citations.json'), {'adapter:one': {'kind': 'summaries'}})
    with pytest.raises(RemError, match='ownership'):
        routes(env.root)


def test_reader_loads_routing_table_once_but_rechecks_approval(shared_sources, monkeypatch):
    from connectonion.rem import source_citations, service
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    old = hooks.collect(env.root, 'summaries', {}, 2, 10000)
    env.current['summaries'] = 2
    hooks.fetch(env.root)
    new = hooks.collect(env.root, 'summaries', old.progress, 2, 10000)
    targets = [old.items[0]['source'], new.items[0]['source']]
    original, calls = source_citations.routes, []
    def counted(root):
        calls.append(root)
        return original(root)
    monkeypatch.setattr(source_citations, 'routes', counted)
    page = '\n## Sources\n' + ''.join(f'- [{index}] {target}\n' for index, target in enumerate(targets, 1))
    assert len(reader_model.cited_context(env.root, [{'text': page}])) == 2
    assert len(calls) == 1
    with source_citations.read_scope(env.root):
        assert hooks.cited(env.root, targets[0]) is not None
        service.toggle_source(env.root, 'summaries', False)
        assert hooks.cited(env.root, targets[0]) is None

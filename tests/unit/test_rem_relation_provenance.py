"""Layout compaction cannot move a claim under another page's provenance."""
import json
import re

import pytest

from connectonion.rem.reader import TEMPLATE
from tests.unit.test_rem_reader import _run_reader_js


def project(links):
    function = re.search(r"function dedupeRelationSnippets\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0)
    return _run_reader_js(function + r'''
      const unrelated = {path: 'people/contact.md', title: 'Contact'};
      const byPath = () => unrelated;
      const known = () => ({intro: 'A different claim from another page.'});
      const facts = () => ({}), plainLine = text => text;
      const input = ''' + json.dumps(links) + r''';
      const before = JSON.stringify(input), output = dedupeRelationSnippets(input);
      console.log(JSON.stringify({output, unmodified: before === JSON.stringify(input)}));
    ''')


def link(path, basis, **extra):
    return {'path': path, 'basis': basis, 'via': 'projects/pilot.md', 'sources': ['2'],
            'kind': 'linked', 'private': False, 'original': False, **extra}


def test_duplicate_origin_snippet_is_omitted_without_borrowing_another_claim():
    links = [link('people/one.md', 'Both reviewed the plan.'), link('people/two.md', 'Both reviewed the plan.')]
    result = project(links)
    assert result['unmodified']
    assert result['output'][0] == links[0]
    assert result['output'][1] == {**links[1], 'basis': ''}
    assert 'A different claim' not in str(result)


@pytest.mark.parametrize('second', [
    {'basis': 'Both reviewed the plan. They did not commit to its delivery.'},
    {'via': 'orgs/group.md'},
    {'sources': ['3']},
    {'private': True},
    {'original': True},
    {'basis': 'BOTH reviewed the plan.'},
])
def test_distinct_context_or_provenance_keeps_its_own_snippet(second):
    links = [link('people/one.md', 'Both reviewed the plan.'),
             {**link('people/two.md', 'Both reviewed the plan.'), **second}]
    result = project(links)
    assert result['unmodified'] and result['output'] == links


@pytest.mark.parametrize('marker', ['[personal]', '[sensitive]', '［personal］', '［sensitive］'])
@pytest.mark.parametrize('translated', [False, True])
def test_compacted_marker_private_excerpt_keeps_its_card_provenance_private(marker, translated):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['dedupeRelationSnippets', 'relationCard'])
    links = [link('people/one.md', marker + (' 共同审阅了计划。' if translated else ' Reviewed the plan.')),
             link('people/two.md', marker + (' 共同审阅了计划。' if translated else ' Reviewed the plan.'))]
    result = _run_reader_js(functions + r'''
      const byPath = path => ({path, title: path, category: 'people'}), href = r => r.path;
      const known = () => ({}), facts = () => ({}), plainLine = text => text;
      const youify = text => text, singular = () => '', inline = text => text;
      const originalMark = () => null;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(node) { this.children.push(node); }});
      const output = dedupeRelationSnippets(''' + json.dumps(links) + r''');
      console.log(JSON.stringify({output, cards: output.map(row => relationCard(row))}));
    ''')
    assert result['output'][1]['basis'] == ''
    assert all(row['private'] for row in result['output'])
    assert all('private' in card['children'][1]['class'].split() for card in result['cards'])

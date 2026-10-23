"""Original reference locations; no provider, browser or notebook writes."""
import json
import re

from connectonion.rem.reader import TEMPLATE

from connectonion.rem.reader_model import relationships
from test_rem_reader import _run_reader_js


def run_js(script, *names):
    page = TEMPLATE.read_text()
    functions = []
    for name in names:
        match = re.search(r"function " + name + r"\([^\n]*\{[^\n]*\}\n|function " + name + r"\(.*?\n\}", page, re.S)
        functions.append(match.group(0) if match else "")
    return _run_reader_js("\n".join(functions) + "\n" + script)


def records(text):
    return [
        {'path': 'people/corin.md', 'category': 'people', 'title': 'Corin Marsh', 'text': '# Corin'},
        {'path': 'projects/pilot.md', 'category': 'projects', 'title': 'Pilot', 'text': text},
    ]


def test_explicit_backlinks_retain_every_original_passage_and_remove_stale_locations():
    text = '# Pilot\n- [Corin](../people/corin.md) agreed [1].\n\n- Ask [Corin](../people/corin.md) again [2]. [personal]\n## Sources\n- [1] mail:a\n'
    graph = relationships(records(text))
    forward = graph['projects/pilot.md'][0]
    reverse = graph['people/corin.md'][0]
    assert [item['line'] for item in forward['references']] == [2, 4]
    assert forward['references'] == reverse['references']
    ids = [item['id'] for item in forward['references']]
    assert len(set(ids)) == 2 and all(len(item) == 20 for item in ids)
    assert all(set(item) == {'id', 'line'} for item in forward['references'])
    changed = relationships(records(text.replace('again [2]', 'next week [2]')))
    updated = changed['projects/pilot.md'][0]['references']
    assert updated[0]['id'] == ids[0] and updated[1]['id'] != ids[1]
    assert ids[1] not in {item['id'] for item in updated}


def test_code_examples_are_not_explicit_notebook_references():
    text = '# Pilot\n```md\n[Corin](../people/corin.md)\n```\n`[Corin](../people/corin.md)`\n'
    assert not any(relationships(records(text)).values())


def test_repeated_links_on_one_line_share_one_passage():
    graph = relationships(records('[Corin](../people/corin.md) and [again](../people/corin.md).'))
    assert len(graph['projects/pilot.md'][0]['references']) == 1


def test_reference_routes_never_rebind_through_a_merge():
    result = run_js('''
      const REM = {records: [{path: 'people/current.md'}], aliases: {'people/old.md': 'people/current.md'}};
      const location = {hash: '#r=people%2Fold.md&ref=12345678901234567890'};
    
      console.log(JSON.stringify(route()));
    ''', 'byPath', 'navigationRecord', 'route')
    assert result['record'] == 'people/old.md'
    assert result['reference'] == '12345678901234567890'


def test_reference_selection_reads_original_page_not_translation_or_another_origin():
    graph = relationships(records('# Pilot\n- Ask [Corin](../people/corin.md) [1]. [personal]\n'))
    relation = graph['projects/pilot.md'][0]
    original = '# Pilot\n- Ask [Corin](../people/corin.md) [1]. [personal]\n'
    page = {'path': 'projects/pilot.md', 'original': original, 'text': '# Pilot\n翻译摘要', 'relations': [relation]}
    result = run_js('''
      const page = ''' + json.dumps(page) + ''';
      const found = referencePassage(page, page.relations[0].references[0].id);
      console.log(JSON.stringify({found, stale: referencePassage(page, 'unavailable'),
        foreign: referencePassage({...page, path: 'people/corin.md'}, page.relations[0].references[0].id)}));
    ''', 'referencePassage')
    assert result['found']['text'] == original.splitlines()[1]
    assert result['found']['index'] == 0 and result['found']['link']['path'] == 'people/corin.md'
    assert result['stale'] is None and result['foreign'] is None


def test_backlink_enters_origin_passage_and_outgoing_links_keep_target_navigation():
    graph = relationships(records('[Corin](../people/corin.md) agreed [1].'))
    script = '''
      const REM = {records: [{path: 'projects/pilot.md', category:'projects', title:'Pilot'},
        {path:'people/corin.md', category:'people',title:'Corin'}]};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(child) {this.children.push(child);}});
      const singular = name => name, youify = text => text, inline = text => text, originalMark = () => 'original';
      const incoming = relationCard(INCOMING, 'people/corin.md');
      const outgoing = relationCard(OUTGOING, 'projects/pilot.md');
      console.log(JSON.stringify({incoming, outgoing}));
    '''.replace('INCOMING', json.dumps(graph['people/corin.md'][0])).replace('OUTGOING', json.dumps(graph['projects/pilot.md'][0]))
    result = run_js(script, 'byPath', 'href', 'relationCard')
    key = graph['people/corin.md'][0]['references'][0]['id']
    assert result['incoming']['children'][0]['href'] == '#r=projects%2Fpilot.md&ref=' + key
    assert result['outgoing']['children'][0]['href'] == '#r=people%2Fcorin.md'
    assert result['outgoing']['children'][-1]['href'] == '#r=projects%2Fpilot.md&ref=' + key
    assert 'Corin' not in key


def test_reference_panel_keeps_original_citations_privacy_and_keyboard_target():
    text = '# Pilot\n- Ask [Corin](../people/corin.md) [9]. [personal]\n- Invite [Corin](../people/corin.md) [2].'
    relation = relationships(records(text))['projects/pilot.md'][0]
    page = {'path': 'projects/pilot.md', 'original': text, 'text': '# Translated\nOther words [1].', 'relations': [relation]}
    script = '''
      const page = PAGE, calls = [], attached = [];
      const main = {querySelector: () => null, firstChild: null,
        insertBefore(box) {attached.push(box);}};
      const document = {getElementById: () => main};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(child) {this.children.push(child);},
        focus(options) {this.focusOptions = options;}, scrollIntoView(options) {this.scrollOptions = options;}});
      const originalReferenceInline = (text, r) => {calls.push({text, from:r.path}); return text;};
      showReference(page, page.relations[0].references[0].id);
      showReference(page, page.relations[0].references[1].id);
      showReference(page, 'stale');
      console.log(JSON.stringify({calls, attached}));
    '''.replace('PAGE', json.dumps(page))
    result = run_js(script, 'href', 'referencePassage', 'showReference')
    first, second, stale = result['attached']
    assert result['calls'][0] == {'text': text.splitlines()[1], 'from': page['path']}
    assert result['calls'][1]['text'] == text.splitlines()[2]
    assert first['tabindex'] == '-1' and first['focusOptions'] == {'preventScroll': True}
    assert first['scrollOptions'] == {'block': 'center'}
    assert first['children'][2]['class'] == 'reference-words private'
    assert first['children'][3]['class'] == 'private-hidden-notice'
    assert first['children'][4]['children'][1]['text'] == 'Next reference'
    assert second['children'][3]['children'][1]['text'] == 'Previous reference'
    assert stale['children'][2]['text'] == 'This passage is no longer in this snapshot.'
    assert all('ref=' not in box['children'][-1]['href'] for box in result['attached'])


def test_reference_lines_normalize_windows_endings_and_keep_markdown_examples_out():
    text = '# Pilot\r\n~~~md\r\n[Corin](../people/corin.md)\r\n~~~~\r\n- [contact](../people/corin.md)\r\n'
    relation = relationships(records(text))['projects/pilot.md'][0]
    assert [ref['line'] for ref in relation['references']] == [5]


def test_shared_aliases_ignore_code_examples_and_source_trailer_only_links():
    from connectonion.rem.reader_model import canonical_aliases
    rows = records('# Pilot\n```md\n[old](../people/old.md)\n```\n`[old](../people/old.md)`\n## Sources\n- [old](../people/old.md)')
    aliases = {'people/old.md': {'into': 'people/corin.md'}}
    assert canonical_aliases(rows, aliases) == {}
    assert canonical_aliases(rows, aliases, local=True) == {'people/old.md': 'people/corin.md'}


def test_mutual_links_keep_both_origin_locations_without_overwriting_provenance():
    rows = records('Meet [Corin](../people/corin.md) [1].')
    rows[0]['text'] = 'See [Pilot](../projects/pilot.md) [9].'
    graph = relationships(rows)
    a, b = graph['projects/pilot.md'][0], graph['people/corin.md'][0]
    assert a['via'] == 'projects/pilot.md' and a['sources'] == ['1']
    assert b['via'] == 'people/corin.md' and b['sources'] == ['9']
    assert a['backlinks'] == {'via': 'people/corin.md', 'references': b['references']}
    assert b['backlinks'] == {'via': 'projects/pilot.md', 'references': a['references']}


def test_original_passage_composes_real_inline_chips_and_popup_against_displayed_source_map():
    original = '# Pilot\nOriginal finding [9].\n## Sources\n- [9] outlook:original — 2026-10-01\n'
    translated = '# Pilot\nTranslated finding [9].\n## Sources\n- [9] outlook:other — 2026-10-21\n'
    page = {'path': 'projects/pilot.md', 'category': 'projects', 'original': original, 'text': translated}
    script = '''
      const page = PAGE;
      const REM = {records:[page], source_context:{
        'outlook:original': {source:'outlook', subject:'Original message', time:'2026-10-01', excerpt:'Original evidence'},
        'outlook:other': {source:'outlook', subject:'Different message', time:'2026-10-21', excerpt:'Wrong evidence'}}};
      const UNKNOWN_TEXT = /^Unknown/; const COMMENT = /<!--[\\s\\S]*?-->/g;
      let CITES = {from:page.path,sources:{'9':'outlook:other — 2026-10-21'}};
      const tetherCitations = text => text, uncertainCitations = text => text, quoteSpans = text => text,
        youify = text => text, shortHash = text => text, sourceSender = () => '',
        safeHref = () => null, isNotebookLink = () => false;
      const chip = originalReferenceInline('Original finding [9].', page, 'abcdef12345678901234');
      const after = citationSource(page, '9');
      const captured = [], panel = {parentElement:{hidden:true},
        replaceChildren(){}, appendChild(node){captured.push(node);}, querySelector(){return {};}};
      const el = (tag, attrs={}, children=[]) => ({tag,...attrs,children,focus(){}});
      const evidencePanel = () => panel, evidenceLine = () => ({text:'Original finding',numbers:['9']}),
        supportingSpan = () => null, markedSpan = text => text, closeEvidence = () => {},
        evidenceOriginal = (context,quote) => ({context,quote}), evidenceLayout = () => {},
        scrollEvidenceSpan = () => {}, sourceIdentity = context => context.subject, fmtTime = text => text;
      const document = {body:{classList:{add(){}}}}; let evidenceTrigger = null;
      openEvidence(page, '9', {dataset:{original:'true'}});
      console.log(JSON.stringify({chip, after, captured}));
    '''.replace('PAGE', json.dumps(page))
    result = run_js(script, 'byPath', 'esc', 'listItems', 'rawSection', 'sourceList', 'sourceId',
                    'citationSource', 'sourceChannel', 'citationDay', 'chipLabel', 'citationDate',
                    'citeRun', 'citeChip', 'inline', 'originalCitationPage', 'originalReferenceInline', 'openEvidence')
    from html.parser import HTMLParser

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self.attrs = dict(attrs)

    parser = Links()
    parser.feed(result['chip'])
    assert parser.attrs['data-original'] == 'true'
    assert 'ref=abcdef12345678901234' in parser.attrs['href']
    assert 'Original message' in parser.attrs['title'] and 'Different message' not in parser.attrs['title']
    assert result['after'].startswith('outlook:other')  # Scope restored; normal translated view unchanged.
    original_context = next(item['context'] for item in result['captured'] if 'context' in item)
    assert original_context['excerpt'] == 'Original evidence'


def test_original_passage_popup_collects_whole_reference_line_not_citation_tether():
    result = run_js('''
      let selector = '';
      const chip = {hash:'#r=projects%2Fpilot.md&h=src-9&ref=opaque', dataset:{sources:'9'}};
      const line = {querySelector:()=>null, cloneNode:()=>({querySelectorAll:()=>[],textContent:'Original whole claim'}),
        querySelectorAll:()=>[chip]};
      const trigger = {...chip, parentElement:{textContent:'citation only'},
        closest(query){selector = query; return query.includes('.reference-words') ? line : null;}};
      const evidenceSentence = (_trigger, selected) => selected === line ? 'Original whole claim' : 'wrong';
      console.log(JSON.stringify({result:evidenceLine(trigger), selector}));
    ''', 'evidenceLine')
    assert '.reference-words' in result['selector']
    assert result['result'] == {'text': 'Original whole claim', 'numbers': ['9']}

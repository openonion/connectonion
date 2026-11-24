"""Organisation records with mapped placeholders and sparse mail, using invented data."""
import json
import re

import pytest

from test_rem_org_ui_integration import TEMPLATE, run_js


DOM = r'''
const el = (tag, attrs = {}, children = []) => ({tag, ...attrs,
  children: children.filter(child => child != null),
  append(...nodes) { this.children.push(...nodes); }});
let uiLanguage = 'en';
const orgT = (text, values={}) => text.replace(/\{(\w+)\}/g, (_,key)=>values[key]);
const t = orgT;
const pageName = page => page.title;  // course/team codes: tested in the browser
const singular = category => ({orgs: 'Organisation', projects: 'Project', knowledge: 'Topic'})[category] || category;
const orgProse = text => text || null;
'''

PLACEHOLDERS = ['Unknown — not investigated yet.', '未知 — 尚未调查。',
                'Unknown — 尚未调查', '未知  ——  尚未 调查；［W2］']


def org_js(names, script):
    declarations = '\n'.join(re.search(r'^const ' + name + r' = .*?;$', TEMPLATE.read_text(), re.M)[0]
                             for name in ['UNFILLED_LEAD', 'UNFILLED_LINE'])
    return run_js(['orgSummary', *names], declarations + script)


@pytest.mark.parametrize('summary', PLACEHOLDERS)
def test_mapped_org_opening_starts_with_known_contacts(summary):
    result = org_js(['orgOpening', 'orgPersonLabel', 'addressTitle', 'addressName', 'orgRelation'], DOM + r'''
      const known = () => ({summary: SUMMARY, intro: SUMMARY, kept: [], last: '2026-03-04'});
      const facts = () => ({first: '2025-02-03'}), orgLast = () => '2026-03-04';
      const orgFact = () => '', parseFacts = () => new Map();
      const plainLine = x => x, privatePassages = x => x, firstSentence = x => x;
      const calendarDate = x => x, MECHANICAL = new Set();
      console.log(JSON.stringify(orgOpening({r:{}, events:[], people:[{title:'Fern Vale'}]})));
    '''.replace('SUMMARY', json.dumps(summary)))
    text = ''.join(result['children'])
    assert text.startswith('You know 1 person here.'), text
    assert 'Fern Vale' in text and '2025-02-03' in text and '2026-03-04' in text
    assert summary not in text


@pytest.mark.parametrize('source', ['org', 'person', 'mail', 'index', 'none'])
def test_mapped_org_opening_uses_recorded_first_contact_without_history(source):
    result = org_js(['orgOpening', 'orgPersonLabel', 'addressTitle', 'addressName', 'orgFact', 'facts', 'parseFacts', 'topLevelParts', 'rawSection'], DOM + r'''
      const SOURCE = __SOURCE__, COMMENT = /<!--[\s\S]*?-->/g;
      const FACTS = new Map(), PARSED_FACTS = new Map();
      const org = {path:'orgs/cedar.md', text:'# Cedar Works\n\n## Facts\n- Website: Unknown'};
      const person = {path:'people/fern.md', title:'Fern Vale', text:'# Fern Vale\n\n## Facts\n- Email: fern@cedar.example'};
      if (SOURCE === 'org') org.text += '\n- First contact: 2024-01-01';
      if (SOURCE === 'person') person.text += '\n- First contact: 2024-01-01';
      if (SOURCE === 'mail') person.mail = {first:'2024-01-01'};
      if (SOURCE === 'index') person.index = {first_contact:'2024-01-01'};
      const known = () => ({summary:'', last:''}), section = () => null;
      const historyItems = () => [], listItems = () => [], threads = () => ({items:[],calm:false});
      const plainLine = x => x, plainValue = x => x, orgRelation = () => '', orgLast = () => '';
      const calendarDate = x => x;
      console.log(JSON.stringify(orgOpening({r:org, events:[], people:[person]})));
    '''.replace('__SOURCE__', json.dumps(source)))
    text = ''.join(result['children'])
    assert text.startswith('You know 1 person here.') and 'Fern Vale' in text
    assert ('In touch since 2024-01-01' in text) == (source != 'none'), text
    if source == 'none':
        assert 'In touch since' not in text


@pytest.mark.parametrize('summary', PLACEHOLDERS)
def test_mapped_connection_is_just_its_linked_name(summary):
    result = org_js(['orgConnections'], DOM + r'''
      const known = () => ({summary: SUMMARY}), href = r => '#' + r.path;
      const unit = {path:'orgs/field.md',title:'Field studio',category:'orgs'};
      const byPath = () => unit, orgHidden = () => false;
      console.log(JSON.stringify(orgConnections({r:{path:'orgs/root.md',organisations:[unit.path]}})));
    '''.replace('SUMMARY', json.dumps(summary)))
    # #3397: a connection with no written reason says only how the pages meet, never a placeholder or another page's summary.
    row = result['children'][1]['children']
    assert row[0] == {'tag': 'a', 'href': '#orgs/field.md', 'text': 'Field studio', 'children': []}
    assert row[2]['class'] == 'ov-conn-kind' and row[2]['text'] == 'Organisation · Mentioned on this page'
    assert summary not in str(row)


@pytest.mark.parametrize('summary', PLACEHOLDERS)
def test_org_table_and_fact_labels_skip_placeholder_summaries(summary):
    result = org_js(['orgTableRow', 'orgCoda'], DOM + r'''
      const orgHidden = () => false, orgName = r => r.title, orgActivity = () => null;
      const orgFact = (r,key) => key === 'What they do' ? SUMMARY : '';
      const orgRelation = () => SUMMARY, orgWebsite = () => null, href = () => '#org';
      const plainLine = x => x, orgTableT = x => x;
      const parseFacts = () => new Map([['What they do',[{value:SUMMARY}]]]);
      const row = orgTableRow({r:{title:'Cedar Works'},people:[],last:'',pages:[]});
      console.log(JSON.stringify({summary:row.summary,coda:orgCoda({r:{},people:[]})}));
    '''.replace('SUMMARY', json.dumps(summary)))
    assert result['summary'] == ''
    assert result['coda']['children'][0]['children'] == [], result
    assert 'Website' not in str(result['coda'])


def record_js(script, functions=()):
    """Use the actual page, translation and fact adapters rather than summary stubs."""
    page = TEMPLATE.read_text()
    constants = '\n'.join(re.search(r'^const ' + name + r' = .*?;$', page, re.M)[0]
                          for name in ['UNKNOWN_LINE', 'MECHANICAL', 'PLACEHOLDER', 'STAMP', 'COMMENT'])
    return org_js(['known', 'facts', 'section', 'plainLine', 'pageWords', 'rawSection', 'parseFacts', 'topLevelParts',
                   'swapLanguage', 'orgFact', 'orgRelation', 'firstSentence', 'orgTableRow',
                   'orgOpening', 'orgPersonLabel', 'addressTitle', 'addressName', 'orgConnections', 'orgCoda', 'textCell', 'orgWebsite',
                   'privatePassages', 'unlabelled', 'mendCuts', 'hasPrivacy', *functions],
                  constants + DOM + r'''
      const KNOWN = new Map(), FACTS = new Map(), PARSED_FACTS = new Map(), SESSION_TEXT = new Map();
      const splitTrailers = text => ({body:text}), youify = text => text;
      const historyItems = () => [], listItems = () => [], threads = () => ({items:[],calm:false});
      const plainValue = text => plainLine(text);
      const privateFallback = node => node;
      const inline = text => text, orgHidden = () => false, orgActivity = () => null;
      const orgName = r => r.title, orgLast = () => '', href = r => '#' + r.path;
      const calendarDate = text => text;
    ''' + script)


def browser_script(function):
    """Execute the browser's setup verbatim so Node checks the same records and mutations."""
    import ast

    directory = TEMPLATE.parents[2] / 'tests/e2e/cli'
    if function == 'SETUP':
        tree = ast.parse((directory / 'test_rem_org_table_browser.py').read_text())
        return next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'SETUP' for target in node.targets))
    tree = ast.parse((directory / 'test_rem_org_real_browser.py').read_text())
    test = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function)
    return next(node.args[0].value for node in ast.walk(test) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'evaluate')


@pytest.mark.parametrize('source', ['lead', 'who', 'relationship', 'what', 'to-you', 'model-to-you', 'model-what'])
@pytest.mark.parametrize('stored', [False, True], ids=['page-en', 'cached-zh'])
def test_org_placeholder_browser_fixture_keeps_only_known_website(source, stored):
    result = record_js(r'''
      const REM = {records:[]}, byPath = path => REM.records.find(r => r.path === path);
      const readerStorage = () => {}, closeEvidence = () => {};
      const render = () => { for (const r of REM.records) swapLanguage(r, uiLanguage === 'en' ? '' : uiLanguage); };
      (SETUP)();
      (INJECT)({source:SOURCE,stored:STORED});
      const r = byPath('orgs/cedar.md'), people = r.people.map(byPath);
      console.log(JSON.stringify({summary:orgTableRow({r,people}).summary,coda:orgCoda({r,people})}));
    '''.replace('SETUP', browser_script('SETUP'))
       .replace('INJECT', browser_script('test_org_placeholder_paths_show_dash_in_source_and_cached_translation'))
       .replace('SOURCE', json.dumps(source)).replace('STORED', json.dumps(stored)), ['setInterfaceLanguage'])
    assert result['summary'] == ''
    rows = result['coda']['children'][0]['children']
    assert [row['children'][0]['text'] for row in rows] == ['Website']
    assert rows[0]['children'][1]['children'][0]['href'] == 'https://cedar.example'


@pytest.mark.parametrize('summary', PLACEHOLDERS)
@pytest.mark.parametrize('source', ['lead', 'who', 'relationship', 'what', 'to-you', 'model-to-you', 'model-what'])
@pytest.mark.parametrize('stored', [False, True], ids=['page', 'translation-store'])
def test_org_summary_paths_reject_placeholders_before_rendering(summary, source, stored):
    result = record_js(r'''
      const summary = SUMMARY, source = SOURCE;
      const sections = {who:'Who they are', relationship:'Our relationship'};
      const fields = {what:'What they do', 'to-you':'To you'};
      const text = '# Field team\n\n' + (source === 'lead' ? summary
        : sections[source] ? '## ' + sections[source] + '\n- ' + summary
        : fields[source] ? '## Facts\n- ' + fields[source] + ': ' + summary : '');
      const r = {path:'orgs/field.md',title:'Field team',category:'orgs',written:false,
        text:STORED ? '# Field team\n\nSource-only description.' : text};
      if (source === 'model-to-you') r.to_you = summary;
      if (source === 'model-what') r.facts = {'What they do':[{value:summary}]};
      if (STORED) { r.translations = {zh:text}; swapLanguage(r,'zh'); }
      const row = orgTableRow({r,people:[],pages:[]}), byPath = () => r;
      console.log(JSON.stringify({summary:row.summary,cell:textCell(row.summary),
        opening:orgOpening({r,people:[],events:[]}), coda:orgCoda({r,people:[]}),
        connections:orgConnections({r:{path:'orgs/root.md',organisations:[r.path]}})}));
    '''.replace('SUMMARY', json.dumps(summary)).replace('SOURCE', json.dumps(source))
       .replace('STORED', json.dumps(stored)))
    assert result['summary'] == '', result
    assert result['cell']['text'] == '—'
    assert ''.join(result['opening']['children']) == 'You know 0 people here. '
    assert result['coda']['children'][0]['children'] == []
    row = result['connections']['children'][1]['children']
    assert row[0]['tag'] == 'a' and row[2]['class'] == 'ov-conn-kind' and summary not in str(row)


@pytest.mark.parametrize('summary', ['Unknown — not verified. The team supports field research.',
                                     '未知 — 尚未调查。团队已经提供场地。'])
def test_org_summary_keeps_findings_after_an_unknown(summary):
    assert org_js([], 'console.log(JSON.stringify(orgSummary(' + json.dumps(summary) + ')));') == summary


def test_org_relation_reads_the_translated_to_you_fact_before_the_source_adapter():
    result = record_js(r'''
      const r = {path:'orgs/field.md',title:'Field team',category:'orgs',
        text:'# Field team',to_you:'Your research partner',
        translations:{zh:'# Field team\n\n## Facts\n- To you: 你的研究伙伴'}};
      swapLanguage(r,'zh');
      console.log(JSON.stringify(orgTableRow({r,people:[],pages:[]}).summary));
    ''')
    assert result == '你的研究伙伴'


def test_org_relation_keeps_labelled_passages_when_reading_the_to_you_fact():
    summary = 'Research partner; acquisition discussion [sensitive]; supports field studies'
    result = record_js(r'''
      const r = {path:'orgs/field.md',title:'Field team',category:'orgs',
        text:'# Field team\n\n## Facts\n- To you: ' + SUMMARY, to_you:SUMMARY};
      console.log(JSON.stringify(orgRelation(r)));
    '''.replace('SUMMARY', json.dumps(summary)))
    assert result == summary


def test_org_summary_filters_each_fact_before_joining_supported_values():
    result = record_js(r'''
      const r = {path:'orgs/field.md',title:'Field team',category:'orgs',
        text:'# Field team\n\n## Facts\n- What they do: 未知 — 尚未调查; Supports field research'};
      console.log(JSON.stringify({row:orgTableRow({r,people:[],pages:[]}).summary,coda:orgCoda({r,people:[]})}));
    ''')
    assert result['row'] == 'Supports field research'
    assert '尚未调查' not in str(result['coda'])


@pytest.mark.parametrize('location', ['47 Lantern Avenue, Suite 820, Port Alder, OR 97000, Fictionland（邮件签名）。',
                                     'Port Alder (mail footer)'])
def test_org_location_keeps_free_text_and_qualifiers_on_the_page(location):
    kinds = re.search(r'^const ORG_KINDS = .*?;$', TEMPLATE.read_text(), re.M | re.S)[0]
    result = record_js(kinds + r'''
      const REM = {records:[]}, byPath = path => REM.records.find(r => r.path === path);
      const readerStorage = () => {}, closeEvidence = () => {};
      const render = () => { for (const r of REM.records) swapLanguage(r, uiLanguage === 'en' ? '' : uiLanguage); };
      (SETUP)();
      (INJECT)(LOCATION);
      let orgCurrent;
      const document = {createTextNode: text => ({text})};
      const orgTableT = orgT, categoryHref = () => '#c=orgs', label = () => 'Organisations';
      const orgView = r => ({r,people:r.people.map(byPath),events:[]});
      const orgOver = orgCrumb, translationLine = () => null, orgTree = () => null, orgMilestones = () => null, investigateControl = () => null, recordActs = () => null;
      const nameLang = () => 'en', r = byPath('orgs/cedar.md');
      const row = orgTableRow({r,people:[],pages:[]});
      console.log(JSON.stringify({location:row.location,cell:textCell(row.location),page:orgPage(r)}));
    '''.replace('SETUP', browser_script('SETUP'))
       .replace('INJECT', browser_script('test_long_org_location_is_two_lines_with_full_title_and_page_text'))
       .replace('LOCATION', json.dumps(location)), ['setInterfaceLanguage', 'orgPage', 'orgStage', 'orgCrumb'])
    assert result['location'] == location
    assert result['cell']['title'] == location
    coda = result['page']['children'][-1]
    assert coda['children'][0]['children'][0]['children'][1]['children'] == [location]


def test_org_desktop_location_shares_the_two_line_summary_clamp():
    css = TEMPLATE.read_text().split('@media (min-width: 601px) {', 1)[1].split('}', 1)[0]
    assert '.c-summary' in css and '.c-location' in css
    assert '-webkit-line-clamp: 2' in css


def test_zero_mail_activity_is_blank_and_sorts_last_in_both_directions():
    columns = re.search(r'const ORG_COLUMNS = .*?^\];', TEMPLATE.read_text(), re.M | re.S)[0]
    result = run_js(['peopleOrder'], DOM + r'''
      const orgNameCell = () => null, orgWebsiteCell = () => null;
      const blank = x => x == null || x === '' ? null : x;
      const textCell = value => ({text:value || '—'}), orgTableT = text => text;
      const byTwoWay = () => 0;
    ''' + columns + r'''
      const column = ORG_COLUMNS.find(c => c.key === 'activity');
      const rows = [{r:{title:'Quiet unit'}, rel:{messages_90d:0}},
        {r:{title:'Busy'}, rel:{messages_90d:7}}, {r:{title:'Mapped'}, rel:null},
        {r:{title:'Active'}, rel:{messages_90d:2}}];
      for (const d of rows) d.keys = {activity:column.sort(d)};
      console.log(JSON.stringify({cell:column.cell(rows[0]), key:column.sort(rows[0]),
        orders:[true,false].map(desc => [...rows].sort(peopleOrder(column,desc)).map(d=>d.r.title))}));
    ''')
    assert result['cell'] == {'text': '—'}, result
    assert result['key'] is None
    assert result['orders'] == [['Busy', 'Active', 'Quiet unit', 'Mapped'],
                                ['Active', 'Busy', 'Quiet unit', 'Mapped']]


def test_kind_filters_offer_unclassified_without_inventing_a_kind():
    result = run_js(['orgKindFilters', 'orgDescendants', 'orgFilterRows'], DOM + r'''
      const ORG_KINDS = {}, orgTableT = x => x;
      let orgListMode = 'tree'; const orgFilter = {tab:'all'};
      const rows = [{r:{path:'root'},kind:'',text:'root',children:[
        {r:{path:'unit'},kind:'',text:'unit',children:[]},
        {r:{path:'team'},kind:'team',text:'team',children:[]}]}];
      const filters = orgKindFilters(rows, () => {});
      const unclassified = filters.children.find(button=>button.text==='Unclassified');
      if (unclassified) { filters.querySelectorAll = () => []; unclassified.onclick(); }
      console.log(JSON.stringify({labels:filters.children.map(b=>b.text),
        tab:orgFilter.tab,mode:orgListMode,kind:rows[0].kind,
        matches:orgFilterRows(rows,orgFilter.tab,'').map(d=>[d.r.path,d.children.map(c=>c.r.path)])}));
    ''')
    assert result['labels'] == ['All', 'Unclassified', 'team'], result
    assert result['tab'] == '' and result['mode'] == 'flat' and result['kind'] == ''
    assert result['matches'] == [['root', ['unit']]]

"""Organisation records with mapped placeholders and sparse mail, using invented data."""
import json
import re

import pytest

from test_rem_org_ui_integration import TEMPLATE, run_js


DOM = r'''
const el = (tag, attrs = {}, children = []) => ({tag, ...attrs,
  children: children.filter(child => child != null),
  append(...nodes) { this.children.push(...nodes); }});
const uiLanguage = 'en', orgT = (text, values={}) => text.replace(/\{(\w+)\}/g, (_,key)=>values[key]);
const t = orgT;
const orgProse = text => text || null;
'''

PLACEHOLDERS = ['Unknown — not investigated yet.', '未知 — 尚未调查。']


def org_js(names, script):
    declarations = '\n'.join(re.search(r'^const ' + name + r' = .*?;$', TEMPLATE.read_text(), re.M)[0]
                             for name in ['UNFILLED_LEAD', 'UNFILLED_LINE'])
    return run_js(['orgSummary', *names], declarations + script)


@pytest.mark.parametrize('summary', PLACEHOLDERS)
def test_mapped_org_opening_starts_with_known_contacts(summary):
    result = org_js(['orgOpening', 'orgRelation'], DOM + r'''
      const known = () => ({summary: SUMMARY, intro: SUMMARY, kept: [], last: '2026-03-04'});
      const facts = () => ({first: '2025-02-03'}), orgLast = () => '2026-03-04';
      const orgFact = () => '';
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
    result = org_js(['orgOpening', 'orgFact', 'facts', 'parseFacts', 'topLevelParts', 'rawSection'], DOM + r'''
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
    assert result['children'][1]['children'] == [
        {'tag': 'a', 'href': '#orgs/field.md', 'text': 'Field studio', 'children': []}]


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

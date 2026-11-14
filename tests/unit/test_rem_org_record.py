"""Organisation records never project the owner's task queue (#3036)."""
import json

import pytest

from test_rem_org_ui_integration import run_js


DOM = r'''
const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
  append(...nodes) { this.children.push(...nodes); },
  appendChild(node) { this.children.push(node); },
  get childElementCount() { return this.children.length; }});
const orgT = text => text, t = text => text;
'''


def test_org_list_is_one_contact_order_without_waiting_groups():
    result = run_js(['peopleOrder'], r'''
      const uiLanguage = 'en', byTwoWay = () => 0;
      const rows = [{r: {}, keys:{last:'2026-01-01'}}, {r:{}, keys:{last:'2026-11-01'}}, {r:{},keys:{last:null}}];
      rows.sort(peopleOrder({key:'last'}, true));
      console.log(JSON.stringify(rows.map(d=>d.keys.last)));
    ''')
    assert result == ['2026-11-01', '2026-01-01', None]


def test_org_row_shows_relationship_instead_of_an_overdue_task():
    result = run_js(['orgTableRow'], r'''
      const orgHidden = () => false, orgFact = () => '', orgRelation = () => 'Research partner';
      const orgActivity = () => null, orgWebsite = () => null, orgName = r => r.title;
      console.log(JSON.stringify(orgTableRow({r:{title:'Fernhill'}, people:[], last:'2026-11-01', pages:[]})));
    ''')
    assert result['summary'] == 'Research partner'
    assert 'Overdue' not in str(result) and 'You owe' not in str(result)


def test_org_stage_has_no_today_projection():
    result = run_js(['orgStage'], DOM + r'''
      const orgOver = () => 'breadcrumb', orgName = () => 'Fernhill', nameLang = () => 'en';
      const updatedMarker = () => null, orgSub = () => [], translationLine = () => null;
      const orgOpening = () => 'facts', orgTree = () => 'tree', orgTodayLink = () => 'Today count';
      console.log(JSON.stringify(orgStage({r: {}, people: []})));
    ''')
    assert 'Today count' not in str(result)


def test_org_record_does_not_repeat_the_trees_people_summary():
    result = run_js(['orgPage'], DOM + r'''
      let orgCurrent;
      const orgHidden = () => false, orgView = () => ({}), orgStage = () => 'tree';
      const orgKeyPeople = () => 'duplicate roster', orgMilestones = () => 'history', orgConnections = () => 'connections', orgCoda = () => 'sources';
      console.log(JSON.stringify(orgPage({})));
    ''')
    assert result['children'] == ['tree', 'history', 'connections', 'sources']


def test_org_article_milestones_use_only_the_organisations_dated_story():
    result = run_js(['orgMilestones'], DOM + r'''
      const uiLanguage = 'en', calendarDate = day => 'Date ' + day, orgProse = text => text;
      const orgHistory = (r, people) => { if (people.length) throw Error('activity feed entered article');
        return [{day:'2026-11-14', words:'The studio opened.'}, {day:'2026-01-02', words:'The partnership began.'}]; };
      console.log(JSON.stringify(orgMilestones({r: {}, people: [{title: 'Fern'}]})));
    ''')
    rows = result['children'][1:]
    assert [row['children'][0]['datetime'] for row in rows] == ['2026-01-02', '2026-11-14']
    assert 'Date 2026-11-14' in str(result) and 'Today' not in str(result)
    assert 'The partnership began.' in str(rows[0])


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_org_opening_says_summary_contacts_and_dates_as_sentences(language):
    result = run_js(['orgOpening'], DOM.replace('const orgT = text => text, t = text => text;', '') + r'''
      const uiLanguage = __LANG__, orgT = (key, v) => key.replace('{date}', v.date);
      const known = () => ({summary: 'A teaching university.', last: '2026-10-01'});
      const facts = () => ({first: '2025-01-02'}), orgRelation = () => 'Your research partner.';
      const orgLast = p => p.last, calendarDate = day => day, orgProse = text => text;
      console.log(JSON.stringify(orgOpening({r: {}, people: [{title: 'Fern', last:'2026-11-14'}],
        events: [{day:'2026-01-03'}]})));
    '''.replace('__LANG__', json.dumps(language)))
    text = ''.join(part for part in result['children'] if isinstance(part, str))
    assert 'A teaching university.' in text and 'Your research partner.' in text
    assert '1' in text and 'Fern' in text and '2025-01-02' in text and '2026-11-14' in text
    assert 'Today' not in text


def test_org_article_stage_has_no_state_only_elements():
    result = run_js(['orgStage'], DOM + r'''
      const orgOver = () => 'breadcrumb', orgName = () => 'Fernhill', nameLang = () => 'en';
      const orgOpening = () => 'Opening sentences', orgTree = () => 'tree', translationLine = () => null;
      const updatedMarker = () => ({class: 'updated-label'}), orgSub = () => [], orgFacts = () => 'facts';
      const orgKeyPeople = () => null, orgTodayLink = () => null, orgXray = () => null;
      console.log(JSON.stringify(orgStage({r: {}, people: []})));
    ''')
    assert 'updated-label' not in str(result) and 'ov-time' not in str(result), 'state-only badges/charts remain'
    assert 'Opening sentences' in str(result)


@pytest.mark.parametrize("first_role", ["Tutor", ""])
def test_org_tree_shows_a_multi_unit_person_once_and_keeps_both_roles(first_role):
    from test_rem_org_ui_integration import TREE_DOM, TREE_FUNCTIONS
    result = run_js(TREE_FUNCTIONS, TREE_DOM + r'''
      const p = {path: 'people/fern.md', title: 'Fern', units: [
        {path: 'orgs/course.md', role: 'Tutor'}, {path: 'orgs/team.md', role: 'Product Owner'}]};
      const team = {path: 'orgs/team.md', name: 'Squad', people: [p], units: []};
      const course = {path: 'orgs/course.md', name: 'Course', people: [p], units: [team]};
      const tree = {path: 'orgs/root.md', name: 'Fernhill', people: [], units: [course]};
      const unitPeople = u => [...new Map([...u.people, ...u.units.flatMap(unitPeople)].map(p => [p.path,p])).values()];
      const href = p => '#' + p.path, orgName = r => r.title;
      const byPath = path => ({title: path === team.path ? team.name : course.name});
      const rows = [];
      const visit = item => { if (!item) return; if (item.kind === 'person') rows.push(item);
        for (const child of item.kids || []) visit(child); };
      const node = orgTree({r: {path: tree.path, title: tree.name}, people: [p], tree});
      visit(node.children[1].children[0]); console.log(JSON.stringify(rows));
    '''.replace("role: 'Tutor'", 'role: ' + json.dumps(first_role)))
    assert len(result) == 1
    assert 'Product Owner' in result[0]['meta']
    if first_role:
        assert first_role in result[0]['meta']
    else:
        assert 'Squad' in result[0]['meta']


def test_org_full_memory_date_is_a_calendar_date_without_state_counts():
    result = run_js(['memoryHint'], r'''
      const t = x => x, calendarDay = x => x.slice(0,10), calendarDate = x => 'Date ' + x, fmtDate = () => 'Today';
      console.log(JSON.stringify(memoryHint({category:'orgs',updated:'2026-11-14T12:00:00Z'},true,8,3)));
    ''')
    assert result == 'File updated Date 2026-11-14'


def test_org_connections_are_distinct_public_project_org_and_topic_links():
    result = run_js(['orgConnections'], DOM + r'''
      const uiLanguage = 'en', orgProse = x => x, href = p => '#' + p.path, known = () => ({summary:'Recorded connection.'});
      const rows = [{path:'projects/studio.md',category:'projects',title:'Studio'},
        {path:'orgs/partner.md',category:'orgs',title:'Partner'},
        {path:'knowledge/teaching.md',category:'knowledge',title:'Teaching'},
        {path:'orgs/private.md',category:'orgs',title:'Private',private:true}];
      const byPath = path => rows.find(p => p.path === path), orgHidden = p => !!p.private;
      console.log(JSON.stringify(orgConnections({r:{path:'orgs/root.md',projects:['projects/studio.md'],
        relations: rows.map(p => ({path:p.path})),topics:['knowledge/teaching.md']}})));
    ''')
    links = [row['children'][0]['href'] for row in result['children'][1:]]
    assert links == ['#projects/studio.md', '#knowledge/teaching.md', '#orgs/partner.md']
    assert 'Private' not in str(result)

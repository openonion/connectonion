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
      const orgFacts = () => 'facts', orgTree = () => 'tree', orgTodayLink = () => 'Today count';
      console.log(JSON.stringify(orgStage({r: {}, people: []})));
    ''')
    assert 'Today count' not in str(result)


def test_org_record_does_not_repeat_the_trees_people_summary():
    result = run_js(['orgPage'], DOM + r'''
      let orgCurrent;
      const orgHidden = () => false, orgView = () => ({}), orgStage = () => 'tree';
      const orgKeyPeople = () => 'duplicate roster', orgColumns = () => 'history', orgCoda = () => 'sources';
      console.log(JSON.stringify(orgPage({})));
    ''')
    assert result['children'] == ['tree', 'history', 'sources']


def test_org_contact_timeline_uses_calendar_dates_instead_of_today():
    result = run_js(['orgTime'], r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        append(...nodes) {this.children.push(...nodes);}}), svgEl = el;
      const innerWidth = 1440, REM = {as_of: '2026-11-14'}, DAY_MS = 86400000;
      const calendarDay = d => d, calendarDate = d => 'Date ' + d, fmtDate = () => 'Today';
      const orgScale = () => () => 100, orgT = x => x;
      const box = {clientWidth: 600, replaceChildren(svg) {this.svg = svg;}};
      orgTime({events: [{day: '2026-11-14', words: 'Met', kind: 'them'}]}, box, true);
      console.log(JSON.stringify(box.svg));
    ''')
    assert 'Today' not in str(result)
    assert 'Date 2026-11-14' in str(result)


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

"""Cross-region organisation action contracts in the integrated reader."""
import json
import re
import shutil
import subprocess

import pytest

from connectonion.rem.reader import TEMPLATE


def run_js(names, script):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node runs the reader JavaScript')
    page = TEMPLATE.read_text()
    functions = []
    for name in names:
        match = re.search(r'^function ' + name + r'\(.*', page, re.M)
        assert match, f'reader function {name} is missing'
        function = match[0] if match[0].endswith('}') else re.search(r'function ' + name + r'\(.*?\n\}', page, re.S)[0]
        functions.append(function)
    functions = '\n'.join(functions)
    result = subprocess.run([node], input=functions + '\n' + script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


TREE_FUNCTIONS = ['orgTree', 'orgLoose', 'orgUnitCount', 'orgByLast', 'orgByActivity', 'orgBranchLast']
TREE_DOM = r'''
  const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children, addEventListener() {}});
  const orgTreeItem = d => d;
  const orgT = (key, v = {}) => key.replace(/\{(\w+)\}/g, (m, k) => v[k]);
  const orgFresh = day => !!day, orgUnitRole = (p, path) => (p.units || []).find(e => e.path === path)?.role;
  const orgLast = p => p.last || '', orgRole = () => null, unlabelled = t => t;
'''


def test_same_name_private_org_does_not_join_public_people_or_project_tasks():
    result = run_js(['orgRows'], r'''
      const orgUnitNames = () => [];
      const publicOrg = {path: 'orgs/public.md', title: 'Fernhill', people: ['people/public.md']};
      const privateOrg = {path: 'orgs/private.md', title: 'Fernhill', private: true, people: ['people/private.md']};
      const inCategory = () => [publicOrg, privateOrg], orgName = r => r.title;
      const orgHidden = r => !!r.private, byPath = path => path ? ({path}) : null;
      const orgMembers = r => r.people.map(byPath);
      const orgOwed = () => { throw new Error('The directory must not collect tasks'); };
      const owedFirst = () => 0, known = () => ({last: '2026-11-08'}), orgLast = () => '';
      console.log(JSON.stringify(orgRows().map(row => ({path: row.r.path, tasks: 'owed' in row, people: row.people.map(p => p.path)}))));
    ''')
    assert result == [
        {'path': 'orgs/public.md', 'tasks': False, 'people': ['people/public.md']},
        {'path': 'orgs/private.md', 'tasks': False, 'people': ['people/private.md']},
    ]


def test_org_wording_does_not_overwrite_today_translation():
    page = TEMPLATE.read_text()
    org_labels = re.search(r'const ORG_UI_ZH = .*?^};', page, re.S | re.M)[0]
    result = run_js(['orgT'], org_labels + r'''
      const uiLanguage = 'zh', t = key => ({'Waiting on you': '等你处理'})[key] || key;
      console.log(JSON.stringify([t('Waiting on you'), orgT('Waiting on you')]));
    ''')
    assert result == ['等你处理', '在等你']


def test_explicit_unit_tree_keeps_nested_members_roles_and_unique_rollups():
    result = run_js(['orgMembers', 'orgUnitTree', 'unitPeople', 'unitOwed', *TREE_FUNCTIONS], TREE_DOM + r'''
      const mara = {path: 'people/mara.md', title: 'Mara', units: [{path: 'orgs/team.md', role: 'Product Owner'}]};
      const avery = {path: 'people/avery.md', title: 'Avery'};
      const team = {path: 'orgs/team.md', title: 'Pilot squad', people: [mara.path], children: []};
      const course = {path: 'orgs/course.md', title: 'Pilot course', people: [], children: [team.path]};
      const org = {path: 'orgs/org.md', title: 'Fernhill', people: [mara.path, avery.path], children: [course.path]};
      const rows = [org, course, team, mara, avery], byPath = path => rows.find(row => row.path === path);
      const REM = {owner: ''}, orgHidden = () => false, orgName = r => r.title, orgTeamLabel = p => p.team || '';
      const entry = {row: {key: 'one', units: [team.path]}, t: {}};
      const owedPerson = () => mara, overdue = () => false;
      const href = r => '#' + r.path;
      const people = orgMembers(org), {tree} = orgUnitTree(org, people, [entry]);
      console.log(JSON.stringify({people: people.map(p => p.path), loose: tree.people.map(p => p.path),
        course: tree.units[0].name, team: tree.units[0].units[0].name,
        rolledPeople: unitPeople(tree).map(p => p.path), owed: unitOwed(tree).length,
        card: orgTree({r: org, people, tree})}));
    ''')
    assert result['people'] == ['people/mara.md', 'people/avery.md']
    assert result['loose'] == ['people/avery.md']
    assert result['course'] == 'Pilot course' and result['team'] == 'Pilot squad'
    assert set(result['rolledPeople']) == {'people/mara.md', 'people/avery.md'}
    assert result['owed'] == 1
    text = json.dumps(result['card'])
    assert '#orgs/team.md' in text and '#people/mara.md' in text and 'Product Owner' in text


def test_old_free_text_team_remains_a_group_without_inventing_a_unit_link():
    result = run_js(['orgUnitTree', 'unitPeople'], r'''
      const person = {path: 'people/mara.md', title: 'Mara', team: 'Pilot squad'};
      const org = {path: 'orgs/org.md', title: 'Fernhill', people: [person.path]};
      const byPath = path => path === person.path ? person : org;
      const orgName = r => r.title, owedPerson = () => null, orgTeamLabel = p => p.team || '';
      console.log(JSON.stringify(orgUnitTree(org, [person], []).tree));
    ''')
    assert result['people'] == []
    assert result['units'][0]['name'] == 'Pilot squad'
    assert 'path' not in result['units'][0]
    assert result['units'][0]['people'][0]['path'] == 'people/mara.md'


def test_hidden_unit_members_and_obligations_do_not_roll_into_public_org_ui():
    result = run_js(['orgMembers', 'orgEntries'], r'''
      const person = {path: 'people/private.md'}, privateUnit = {path: 'orgs/private.md', private: true, people: [person.path]};
      const org = {path: 'orgs/public.md', people: [], children: [privateUnit.path], obligations: [
        {record: person.path, units: [privateUnit.path], keys: [], text: 'Private promise'}]};
      const rows = [org, privateUnit, person], byPath = path => rows.find(row => row.path === path);
      const REM = {owner: ''}, orgHidden = r => !!r.private;
      console.log(JSON.stringify({people: orgMembers(org), owed: orgEntries(org)}));
    ''')
    assert result == {'people': [], 'owed': []}


def test_hidden_parent_also_hides_obligations_of_an_unmarked_child():
    result = run_js(['orgHidden', 'orgEntries'], r'''
      const parent = {path: 'orgs/private.md', private: true};
      const child = {path: 'orgs/child.md', parent: parent.path};
      const rows = [parent, child], byPath = path => rows.find(row => row.path === path);
      const revealedOrgs = new Set();
      const root = {obligations: [{units: [child.path], record: 'people/private.md'}]};
      console.log(JSON.stringify({hidden: orgHidden(child), owed: orgEntries(root)}));
    ''')
    assert result == {'hidden': True, 'owed': []}


def test_explicit_parent_and_child_memberships_keep_both_scoped_roles():
    result = run_js(['orgUnitTree', 'unitPeople', 'unitOwed', *TREE_FUNCTIONS], TREE_DOM + r'''
      const parent = {path: 'orgs/course.md', title: 'Course', people: ['people/mara.md'], children: ['orgs/team.md']};
      const child = {path: 'orgs/team.md', title: 'Squad', people: ['people/mara.md'], children: []};
      const mara = {path: 'people/mara.md', title: 'Mara', units: [
        {path: parent.path, role: 'Tutor'}, {path: child.path, role: 'Product Owner'}]};
      const rows = [parent, child, mara], byPath = path => rows.find(row => row.path === path);
      const orgName = r => r.title, orgHidden = () => false, owedPerson = () => null;
      const href = r => '#' + r.path;
      const {tree} = orgUnitTree(parent, [mara], []);
      console.log(JSON.stringify({parentMembers: tree.people.length, total: unitPeople(tree).length, card: orgTree({r: parent, people: [mara], tree})}));
    ''')
    assert result['parentMembers'] == result['total'] == 1
    assert 'Tutor' in json.dumps(result['card']) and 'Product Owner' in json.dumps(result['card'])


def test_parent_unit_page_renders_direct_members_in_their_known_unit():
    result = run_js(['unitPeople', *TREE_FUNCTIONS], TREE_DOM + r'''
      const mara = {path: 'people/mara.md', title: 'Mara', units: [{path: 'orgs/course.md', role: 'Tutor'}]};
      const child = {name: 'Squad', people: [], units: [], owed: []};
      const tree = {people: [mara], units: [child]};
      const orgName = r => r.path, href = r => r.path, byPath = path => ({path});
      const page = orgTree({r: {path: 'orgs/course.md', unit_kind: 'course'}, people: [mara], tree});
      console.log(JSON.stringify(page.children[1].children[0].kids));
    ''')
    assert result[0]['label'] == 'Mara' and result[0]['meta'] == 'Tutor'
    assert result[0]['level'] == 2 and result[0]['kind'] == 'person'
    assert all(row['kind'] != 'loose' for row in result)



@pytest.mark.parametrize('unit_kind,unknown', [('team', False), ('', True)])
def test_known_unit_kind_is_not_presented_as_an_unknown_organisation(unit_kind, unknown):
    result = run_js(['orgQuestions'], r'''
      const orgT = text => text, known = () => ({status: 'Investigated'});
      console.log(JSON.stringify(orgQuestions({unit_kind: ''' + json.dumps(unit_kind) + r''', to_you: 'Your delivery unit'}, [])));
    ''')
    assert ('What kind of organisation this is' in json.dumps(result)) is unknown


# The page's own "last contact" lags when REM has not re-read the organisation; its people wrote later.
ROLLUP = r'''
  const org = {path: 'orgs/fernhill.md', title: 'Fernhill', people: ['people/mara.md', 'people/avery.md']};
  const days = {'orgs/fernhill.md': '2026-10-10', 'people/mara.md': '2026-11-07', 'people/avery.md': '2026-09-02'};
  const byPath = path => path ? ({path, title: path}) : null;
  const known = r => ({last: days[r.path] || ''}), orgLast = p => days[p.path] || '';
  const orgMembers = r => r.people.map(byPath);
'''


def test_an_org_row_takes_its_last_contact_from_the_newest_exchange_of_anyone_there():
    result = run_js(['orgRows'], ROLLUP + r'''
      const orgUnitNames = () => [];
      const inCategory = () => [org], orgName = r => r.title, orgHidden = () => false;
      const orgOwed = () => [], owedFirst = () => 0;
      console.log(JSON.stringify(orgRows().map(row => row.last)));
    ''')
    assert result == ['2026-11-07']


def test_an_org_page_says_last_contact_from_its_people_not_the_page_date():
    result = run_js(['orgFacts'], ROLLUP + r'''
      const orgUnitCount = () => 0, orgT = (key, v = {}) => key.replace(/\{(\w+)\}/g, (m, k) => v[k]), calendarDate = day => day;
      const el = (tag, attrs = {}, children = []) => [attrs.text, ...children.flat()].filter(Boolean).join('');
      const v = {r: org, people: org.people.map(byPath), events: [{day: '2026-03-01'}]};
      console.log(JSON.stringify(orgFacts(v)));
    ''')
    assert 'Last contact 2026-11-07' in result and '2026-10-10' not in result


def test_org_list_folds_only_resolved_units_and_keeps_orphans_findable():
    result = run_js(['orgRows'], r'''
      const orgUnitNames = r => (r.children || []).map(path => byPath(path).title);
      const root = {path: 'orgs/root.md', title: 'Fernhill', children: ['orgs/course.md']};
      const unit = {path: 'orgs/course.md', title: 'Fieldwork', parent: root.path};
      const orphan = {path: 'orgs/orphan.md', title: 'Unplaced squad', parent: 'orgs/missing.md'};
      const rows = [root, unit, orphan], inCategory = () => rows;
      const byPath = path => rows.find(r => r.path === path), orgName = r => r.title;
      const orgHidden = () => false, orgOwed = () => [], orgMembers = () => [];
      const owedFirst = () => 0, known = () => ({last: ''}), orgLast = () => '';
      console.log(JSON.stringify(orgRows().map(o => ({title: o.r.title, units: o.units}))));
    ''')
    assert result == [{'title': 'Fernhill', 'units': ['Fieldwork']}, {'title': 'Unplaced squad', 'units': []}]


def test_org_tree_counts_unique_people_sorts_branches_and_keeps_all_levels():
    result = run_js(['unitPeople', *TREE_FUNCTIONS], TREE_DOM + r'''
      const old = {path: 'people/old.md', title: 'Aster', last: '2026-01-01'};
      const recent = {path: 'people/new.md', title: 'Birch', last: '2026-11-01'};
      const loose = {path: 'people/loose.md', title: 'Cedar'};
      const squad = {name: 'Squad', path: 'orgs/squad.md', people: [recent], units: []};
      const older = {name: 'Older branch', path: 'orgs/older.md', people: [old], units: []};
      const newer = {name: 'Newer branch', path: 'orgs/newer.md', people: [recent], units: [squad]};
      const tree = {people: [loose], units: [older, newer]};
      const r = {path: 'orgs/root.md', title: 'Fernhill'};
      const orgName = r => r.title, href = r => '#' + r.path, byPath = path => ({path});
      console.log(JSON.stringify(orgTree({r, tree, people: [old, recent, loose]})));
    ''')
    root = result['children'][1]['children'][0]
    assert root['level'] == 1 and root['count'] == 3 and root['open'] is True
    newer, older, loose = root['kids']
    assert [newer['label'], older['label']] == ['Newer branch', 'Older branch']
    assert newer['count'] == 1  # parent + child membership is one person in the rollup
    squad = newer['kids'][1]
    assert squad['level'] == 3 and squad['count'] == 1 and squad['kids'] == []
    # Membership counts stay intact; Birch is displayed once in the first branch.
    def person_labels(item):
        return ([item['label']] if item.get('kind') == 'person' else []) + [
            label for child in item.get('kids', []) for label in person_labels(child)]
    assert sorted(person_labels(root)) == ['Aster', 'Birch', 'Cedar']
    assert loose['kind'] == 'loose' and loose['count'] == 1 and loose['open'] is False


def test_org_unit_search_never_exposes_private_branch_names():
    result = run_js(['orgUnitNames'], r'''
      const root = {path: 'orgs/root.md', children: ['orgs/private.md', 'orgs/public.md']};
      const secret = {path: 'orgs/private.md', title: 'Hidden branch', private: true};
      const publicUnit = {path: 'orgs/public.md', title: 'Visible branch', children: [root.path]};
      const rows = [root, secret, publicUnit], byPath = path => rows.find(r => r.path === path);
      const orgHidden = r => !!r.private;
      console.log(JSON.stringify(orgUnitNames(root)));
    ''')
    assert result == ['Visible branch']


def test_org_tree_keyboard_collapses_expands_and_moves_focus_without_navigation():
    result = run_js(['orgTreeKey', 'orgTreeToggle', 'orgTreeFocus'], r'''
      const items = [];
      function item(label, parent = null, open = null) {
        const node = {label, tabIndex: items.length ? -1 : 0, parent, kids: [], open,
          hasAttribute: key => key === 'aria-expanded' && node.open !== null,
          getAttribute: () => node.open,
          setAttribute: (key, value) => { node.open = value; },
          closest: () => node,
          checkVisibility: () => !parent || parent.open === 'true' && parent.checkVisibility(),
          querySelector: selector => selector.includes('.ov-trow') ? null : node.kids[0],
          focus: () => { focused = node; }};
        node.parentElement = {closest: () => parent};
        if (parent) parent.kids.push(node);
        items.push(node);
        return node;
      }
      const root = item('Root', null, 'true'), branch = item('Branch', root, 'true');
      const person = item('Person', branch), other = item('Other', root);
      const tree = {querySelectorAll: selector => selector.includes('tabindex') ? items.filter(n => n.tabIndex === 0) : items};
      let focused = root, prevented = 0;
      const key = value => orgTreeKey(tree, {target: focused, key: value, preventDefault: () => prevented++});
      const steps = [];
      key('ArrowDown'); steps.push(focused.label);
      key('ArrowLeft'); steps.push(branch.open, person.checkVisibility());
      key('ArrowLeft'); steps.push(focused.label);
      key('ArrowDown'); key('ArrowRight'); steps.push(branch.open);
      key('ArrowRight'); steps.push(focused.label);
      key('End'); steps.push(focused.label);
      key('Home'); steps.push(focused.label);
      key(' '); steps.push(root.open, other.checkVisibility());
      console.log(JSON.stringify({steps, stops: items.filter(n => n.tabIndex === 0).length, prevented}));
    ''')
    assert result == {'steps': ['Branch', 'false', False, 'Root', 'true', 'Person', 'Other', 'Root', 'false', False],
                      'stops': 1, 'prevented': 9}

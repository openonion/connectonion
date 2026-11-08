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
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S)[0] for name in names)
    result = subprocess.run([node], input=functions + '\n' + script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('state', ['replied', 'no_reply', 'waiting'])
def test_org_primary_labels_the_action_it_performs(state):
    result = run_js(['orgPrimary'], r'''
      const state = ''' + json.dumps(state) + r''';
      const entry = {r: {}, t: {}};
      const orgT = text => text, owedPerson = () => ({title: 'Mara'}), orgFirstName = () => 'Mara';
      const orgName = () => 'Fernhill', threadDraft = () => state === 'no_reply' ? {status: state} : null;
      let done = false;
      const setDone = () => {done = true;};
      const el = (tag, attrs) => ({...attrs, textContent: attrs.text, matches() {return true;}});
      const primaryAction = () => {
        const node = el('button', {text: state === 'replied' ? 'Mark done' : 'Open the page'});
        if (state === 'replied') node.onclick = setDone;
        return node;
      };
      const owedWords = () => ({title: 'Pilot review'}), threadKind = () => ({mail: true});
      const node = orgPrimary(entry);
      node.onclick?.();
      console.log(JSON.stringify({text: node.textContent, done, className: node.className}));
    ''')
    assert result['className'] == 'ov-primary'
    if state == 'waiting':
        assert result['text'] == 'Reply to {name} · {thing}' and not result['done']
    else:
        assert result['text'] == 'Mark done' and result['done']


def test_same_name_private_org_does_not_join_public_obligations_or_people():
    result = run_js(['orgRows'], r'''
      const publicOrg = {path: 'orgs/public.md', title: 'Fernhill', people: ['people/public.md']};
      const privateOrg = {path: 'orgs/private.md', title: 'Fernhill', private: true, people: ['people/private.md']};
      const inCategory = () => [publicOrg, privateOrg], orgName = r => r.title;
      const orgHidden = r => !!r.private, byPath = path => ({path});
      const orgMembers = r => r.people.map(byPath);
      const orgOwed = r => [{row: {key: r.path}, text: r.private ? 'private promise' : 'public promise'}];
      const owedFirst = () => 0, known = () => ({last: '2026-11-08'});
      console.log(JSON.stringify(orgRows().map(row => ({path: row.r.path, keys: row.owed.map(e => e.row.key), people: row.people.map(p => p.path)}))));
    ''')
    assert result == [
        {'path': 'orgs/public.md', 'keys': ['orgs/public.md'], 'people': ['people/public.md']},
        {'path': 'orgs/private.md', 'keys': ['orgs/private.md'], 'people': ['people/private.md']},
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
    result = run_js(['orgMembers', 'orgUnitTree', 'unitPeople', 'unitOwed', 'orgTeam'], r'''
      const mara = {path: 'people/mara.md', title: 'Mara', units: [{path: 'orgs/team.md', role: 'Product Owner'}]};
      const avery = {path: 'people/avery.md', title: 'Avery'};
      const team = {path: 'orgs/team.md', title: 'Pilot squad', people: [mara.path], children: []};
      const course = {path: 'orgs/course.md', title: 'Pilot course', people: [], children: [team.path]};
      const org = {path: 'orgs/org.md', title: 'Fernhill', people: [mara.path, avery.path], children: [course.path]};
      const rows = [org, course, team, mara, avery], byPath = path => rows.find(row => row.path === path);
      const REM = {owner: ''}, orgHidden = () => false, orgName = r => r.title, orgTeamLabel = p => p.team || '';
      const entry = {row: {key: 'one', units: [team.path]}, t: {}};
      const owedPerson = () => mara, overdue = () => false, unlabelled = text => text;
      const href = r => '#' + r.path, orgFace = () => null, orgRole = () => null;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const people = orgMembers(org), {tree} = orgUnitTree(org, people, [entry]);
      console.log(JSON.stringify({people: people.map(p => p.path), loose: tree.people.map(p => p.path),
        course: tree.units[0].name, team: tree.units[0].units[0].name,
        rolledPeople: unitPeople(tree).map(p => p.path), owed: unitOwed(tree).length,
        card: orgTeam(tree.units[0])}));
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
    result = run_js(['orgUnitTree', 'unitPeople', 'unitOwed', 'orgTeam'], r'''
      const parent = {path: 'orgs/course.md', title: 'Course', people: ['people/mara.md'], children: ['orgs/team.md']};
      const child = {path: 'orgs/team.md', title: 'Squad', people: ['people/mara.md'], children: []};
      const mara = {path: 'people/mara.md', title: 'Mara', units: [
        {path: parent.path, role: 'Tutor'}, {path: child.path, role: 'Product Owner'}]};
      const rows = [parent, child, mara], byPath = path => rows.find(row => row.path === path);
      const orgName = r => r.title, orgHidden = () => false, owedPerson = () => null;
      const href = r => '#' + r.path, orgFace = () => null, orgRole = () => null;
      const overdue = () => false, unlabelled = text => text;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const {tree} = orgUnitTree(parent, [mara], []);
      console.log(JSON.stringify({parentMembers: tree.people.length, total: unitPeople(tree).length, card: orgTeam(tree)}));
    ''')
    assert result['parentMembers'] == result['total'] == 1
    assert 'Tutor' in json.dumps(result['card']) and 'Product Owner' in json.dumps(result['card'])


def test_parent_unit_page_renders_direct_members_in_their_known_unit():
    result = run_js(['orgPeopleSection'], r'''
      const mara = {path: 'people/mara.md'}, child = {name: 'Squad'};
      const tree = {people: [mara], units: [child]}, owing = new Map();
      const orgUnitTree = () => ({tree, owing}), known = () => ({last: ''}), unitOwed = () => [];
      const orgT = text => text, orgTeam = () => null, orgIcon = () => null;
      const orgPerson = (p, owing, unitPath) => ({path: p.path, unitPath});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const page = orgPeopleSection({path: 'orgs/course.md', unit_kind: 'course'}, [mara], []);
      console.log(JSON.stringify(page.children[2].children));
    ''')
    assert result == [{'path': 'people/mara.md', 'unitPath': 'orgs/course.md'}]


@pytest.mark.parametrize('unit_kind,unknown', [('team', False), ('', True)])
def test_known_unit_kind_is_not_presented_as_an_unknown_organisation(unit_kind, unknown):
    result = run_js(['orgRail'], r'''
      const parseFacts = () => new Map(), plainLine = text => text, byPath = () => null;
      const orgT = text => text, known = () => ({status: 'Investigated'}), sourceList = () => [];
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      console.log(JSON.stringify(orgRail({unit_kind: ''' + json.dumps(unit_kind) + r''', to_you: 'Your delivery unit'}, [])));
    ''')
    assert ('What kind of organisation this is' in json.dumps(result)) is unknown

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

"""Organisation row projection stays independent of People and the book page."""
import json
import re
import shutil
import subprocess

import pytest

from connectonion.rem.reader import TEMPLATE


def _project(body):
    names = ['orgVisibleRows', 'orgFilterRows', 'orgDescendants', 'orgListRows']
    source = TEMPLATE.read_text()
    functions = []
    for name in names:
        match = re.search(r'^function ' + name + r'\(.*', source, re.M)
        if match:
            functions.append(match[0] if match[0].endswith('}') else
                             re.search(r'function ' + name + r'\(.*?\n\}', source, re.S)[0])
    setup = """
    let orgListMode = 'tree'; const orgCollapsed = new Set();
    const orgFilter = {tab:'all'};
    const document = {querySelectorAll: () => []};
    const peopleOrder = (col, desc) => (a,b) => (a.keys[col.key] - b.keys[col.key]) * (desc ? -1 : 1);
    const row = (path, rank, children=[]) => ({r:{path},kind:children.length?'university':'team',text:path,children,rank});
    const rows = [row('root', 1, [row('course', 4, [row('squad', 3)])]), row('other', 2)];
    const col = {key:'rank',sort:d=>d.rank}, state = {text:'',desc:true};
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('Node runs the reader JavaScript')
    result = subprocess.run([node], input='\n'.join(functions) + setup + body,
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_org_tree_expands_every_level_by_default_and_collapses_only_named_branch():
    assert _project("""
      const open = orgVisibleRows(rows, orgCollapsed).map(d=>[d.r.path,d.depth,d.expanded]);
      orgCollapsed.add('course');
      const closed = orgVisibleRows(rows, orgCollapsed).map(d=>d.r.path);
      console.log(JSON.stringify({open,closed}));
    """) == {'open': [['root',0,True],['course',1,True],['squad',2,True],['other',0,True]],
              'closed': ['root','course','other']}


def test_org_flat_projection_sorts_all_units_and_kind_filter_excludes_ancestors():
    assert _project("""
      orgListMode = 'flat';
      const sorted = orgListRows(rows,col,state).map(d=>d.r.path);
      orgFilter.tab = 'team';
      const filtered = orgListRows(rows,col,state).map(d=>d.r.path);
      orgFilter.tab = 'all'; orgListMode = 'tree';
      const tree = orgListRows(rows,col,state).map(d=>d.r.path);
      orgCollapsed.add('root'); state.text = 'squad';
      const search = orgListRows(rows,col,state).map(d=>d.r.path);
      state.search.collapsed.add('course');
      const manual = orgListRows(rows,col,state).map(d=>d.r.path);
      state.text = '';
      const restored = orgListRows(rows,col,state).map(d=>d.r.path);
      console.log(JSON.stringify({sorted,filtered,tree,search,manual,restored}));
    """) == {'sorted':['course','squad','other','root'], 'filtered':['squad','other'],
              'tree':['other','root','course','squad'], 'search':['root','course','squad'],
              'manual':['root','course'], 'restored':['other','root']}


def test_org_fixture_summary_rolls_up_distinct_people_and_collapse_writes_only_paths(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_org_tree_notebook import build
    from connectonion.rem.reader import snapshot
    from test_rem_org_ui_integration import run_js

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    data = snapshot(build(tmp_path / 'rem', datetime(2026, 10, 1, 12, tzinfo=timezone.utc)))
    result = run_js(['orgMembers', 'orgTableChildren', 'orgNameCell'], 'const REM = ' + json.dumps(data) + ';\n' + r'''
      const byPath = path => REM.records.find(r=>r.path===path), orgHidden = () => false;
      const orgTableRow = o => o, known = () => ({}), orgLast = () => '', orgUnitNames = () => [];
      const orgName = r => r.title, orgTile = () => ({}), href = r => r.path;
      const orgTableT = (key, values={}) => key.replace(/\{(\w+)\}/g, (_,k)=>values[k]);
      const el = (tag, attrs={}, children=[]) => ({tag,...attrs,children:children.filter(Boolean)});
      const orgCollapsed = new Set(['orgs/fieldwork-studio.md']), saved = [];
      const ORG_SORT = {};
      const readerStorage = (key,value) => saved.push([key,value.split('\n').filter(Boolean)]);
      const r = byPath('orgs/fernhill-university.md');
      const root = {r,pages:[r],people:orgMembers(r),expanded:true};
      root.children = orgTableChildren(root); root.unitCount = root.children.length;
      const cell = orgNameCell(root, () => {});
      const nodes = n => [n,...(n.children||[]).flatMap(nodes)];
      const summary = nodes(cell).find(n=>n.class==='org-unit-summary')?.text;
      require('node:assert/strict').equal(summary, '3 units · 12 people');
      const toggle = nodes(cell).find(n=>n.class==='org-disclosure');
      toggle.onclick(); toggle.onclick();
      console.log(JSON.stringify({summary,saved}));
    ''')
    assert result == {'summary': '3 units · 12 people', 'saved': [
        ['co-rem-org-collapsed', ['orgs/fieldwork-studio.md', 'orgs/fernhill-university.md']],
        ['co-rem-org-collapsed', ['orgs/fieldwork-studio.md']]]}

"""State and hierarchy of the Projects reader; all records are fictional."""
import json
import re

from connectonion.rem.reader import TEMPLATE
from test_rem_reader import _run_reader_js


def _functions(*names):
    page = TEMPLATE.read_text()
    found = [re.search(r'function ' + name + r'\(.*?\n\}', page, re.S) for name in names]
    assert all(found), 'Projects board behavior is missing: ' + ', '.join(names)
    return '\n'.join(match[0] for match in found)


DOM = r'''
const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(x => x != null),
  appendChild(node) { this.children.push(node); }, append(...nodes) {this.children.push(...nodes);} });
'''


def test_projects_default_to_four_state_columns_and_keep_every_record():
    result = _run_reader_js(_functions('pdParams', 'projectBoardState', 'projectStateColumn') + DOM + r'''
      const location = {hash: '#c=projects'}, PD_VIEWS = [['board'], ['list'], ['timeline']], PD_ZOOM = {quarter: []};
      const PD_ASKS = [['state']], PD_STATES = [['active', 'Active'], ['waiting', 'Waiting'], ['quiet', 'Quiet'], ['done', 'Done']];
      const PD_FOLD_AT = 6, pdStateOpen = new Set(PD_STATES.map(([key]) => key));
      const pdT = s => s, projectState = r => r.state, projectLast = r => r.last, projectRank = () => 0;
      const projectStateCard = r => ({path: r.path}), projectsView = () => {};
      const all = Array.from({length: 500}, (_, i) => ({path: 'projects/p-' + i + '.md', state: PD_STATES[i % 4][0], last: '2026-10-01'}));
      console.log(JSON.stringify({params: pdParams(), columns: projectBoardState(all)}));
    ''')
    assert result['params']['view'] == 'board' and result['params']['ask'] == 'state'
    assert [col['data-state'] for col in result['columns']] == ['active', 'waiting', 'quiet', 'done']
    paths = [row['path'] for col in result['columns'] for row in col['children'] if 'path' in row]
    assert len(paths) == len(set(paths)) == 500


def test_waiting_requires_every_confirmed_step_to_belong_to_someone_else():
    result = _run_reader_js(_functions('projectState') + r'''
      const projectTier = r => r.tier;
      const row = (tier, ...kinds) => ({tier, open: kinds.map(kind => ({kind}))});
      const rows = [row('done', 'owed'), row('quiet', 'owed'), row('on_track', 'waiting'), row('on_track', 'agent'),
        row('at_risk', 'waiting', 'owed'), row('on_track', 'waiting', 'unknown'), row('on_track'),
        {tier: 'on_track', open: [{kind: 'waiting'}, {kind: 'owed', project_match: {needs_review: true}}]}];
      console.log(JSON.stringify(rows.map(projectState)));
    ''')
    assert result == ['done', 'quiet', 'waiting', 'waiting', 'active', 'active', 'active', 'waiting']


def test_next_steps_prioritize_overdue_then_owner_and_preserve_long_link_and_privacy():
    result = _run_reader_js(_functions('projectSteps', 'projectStepWhat') + r'''
      const REM = {as_of: '2026-10-01'}, calendarDay = s => s, stripCites = s => s.replace(/\[\d+\]/g, '');
      const threads = r => ({items: r.items}), projectStepOwner = (r, thread) => ({owner: thread.owner});
      const items = [{text: 'agent', owner: 'agent'}, {text: 'waiting', owner: 'them'}, {text: 'owner', owner: 'you'},
        {text: 'late', owner: 'you', due: '2026-09-20'}];
      const long = 'Review [' + 'the release notes '.repeat(20) + '](../notes/release.md) [personal]';
      console.log(JSON.stringify({order: projectSteps({items}).map(s => s.thread.text), long, shown: projectStepWhat(long),
        private: projectStepWhat('Private context [personal] — open: Review the report')}));
    ''')
    assert result['order'] == ['late', 'owner', 'waiting', 'agent']
    assert result['shown'] == result['long']
    assert result['private'] == 'Review the report [personal]'


def test_written_project_lead_puts_steps_and_recent_activity_before_folded_context():
    result = _run_reader_js(_functions('recordFocus') + DOM + r'''
      const REM = {owner: ''}, r = {category: 'projects', path: 'projects/harbour.md'};
      const known = () => ({status: 'Investigated'}), section = () => null, newestStanding = () => '';
      const plainLine = s => s, memoryStatement = () => 'A very long background story', facts = () => ({});
      const privateFallback = x => x, inline = s => s, expansionButton = () => null, sourceList = () => [];
      const threads = () => ({items: [{text: 'Review release', dir: 'mine'}]}), projectSteps = () => [{thread: {text: 'Review release', dir: 'mine'}}];
      const threadRow = (r, thread) => ({step: thread.text});
      const projectStepRow = threadRow, projectRecent = () => ({recent: 'Latest session'});
      const recordFacts = () => ({unfolded: 'facts'}), recordContext = () => ({childNodes: [{unfolded: 'context'}]});
      const activityPanel = () => ({unfolded: 'activity'});
      console.log(JSON.stringify(recordFocus(r)));
    ''')
    text = json.dumps(result)
    assert 'A very long background story' not in text, 'Project background precedes next steps'
    assert 'unfolded' not in text
    assert result['children'][0]['class'] == 'focus-section next-exchanges'
    assert result['children'][1] == {'recent': 'Latest session'}


def test_project_local_graph_stays_inside_full_memory():
    result = _run_reader_js(_functions('graphRailAttach') + r'''
      const r = {category: 'projects', path: 'projects/harbour.md'}, REM = {graph: {nodes: []}};
      const graphModel = () => ({adj: new Map([[r.path, new Set()]]), byId: new Map()});
      const graphLocal = () => ({});
      const el = (tag, attrs, children) => ({classList: {toggle() {}}});
      const placed = [], body = {append: () => placed.push('full memory')};
      const deep = {querySelector: () => body};
      const main = {querySelector: selector => selector.includes('.deep-note') ? deep : null,
        insertBefore: () => placed.push('first screen'), append: () => placed.push('first screen')};
      graphRailAttach(main, r);
      console.log(JSON.stringify(placed));
    ''')
    assert result == ['full memory'], 'Project graph is unfolded on the first screen'

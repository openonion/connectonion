"""Reader regressions from the opt-in suite, exercised without Chrome."""

import re

from test_rem_reader import TEMPLATE, _run_reader_js


def _functions(*names):
    html = TEMPLATE.read_text()
    return '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', html, re.S)[0] for name in names)


def test_a_redraw_keeps_an_explicitly_revealed_session_curtain():
    result = _run_reader_js(_functions('sessionCurtain', 'viewState', 'restoreView') + r'''
      const OPEN_TALKS = new Map();
      const groups = [[{path: 'sessions/sample.md', session_date: '2026-10-15'}]], terms = [];
      let expanded = [], row;
      const el = (tag, attrs, children) => ({tag, ...attrs, children, dataset: {},
        append(...nodes) {this.children = nodes;}, replaceWith(...nodes) {expanded = nodes;},
        querySelector() {return this.children.at(-1);}});
      const sessionButton = (text, action) => ({click: action});
      const sessionRow = group => ({dataset: {}, path: group[0].path});
      const detailsKey = node => node.id;
      const sessionPlace = () => 'Sample', keptFields = () => [], restoreFields = () => {};
      const location = {hash: '#c=sessions'}, scrollY = 12, scrollTo = () => {};
      const document = {querySelectorAll(selector) {
        if (selector === 'details') return [];
        if (selector.includes('data-revealed-session')) return expanded;
        if (selector.includes('session-curtain')) return [row];
        return [];
      }};
      row = sessionCurtain(groups, terms);
      row.querySelector('button').click();
      const state = viewState();
      expanded = []; row = sessionCurtain(groups, terms);
      restoreView(state);
      console.log(JSON.stringify(expanded.map(node => node.path)));
    ''')
    assert result == ['sessions/sample.md']

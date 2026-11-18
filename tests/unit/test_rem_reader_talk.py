"""An open row conversation must survive the live reader's newer-page reload."""

import re

import pytest

from connectonion.rem.reader import TEMPLATE
from tests.unit.test_rem_reader import HAND, _run_reader_js


@pytest.mark.parametrize('reload_at', ['opening', 'working', 'idle'])
def test_row_talk_survives_reload_redraw_and_next_turn(reload_at):
    page = TEMPLATE.read_text()
    names = [*HAND, 'el', 'talkPanel', 'talkTurn', 'viewState', 'keptFields', 'restoreFields',
             'restoreView', 'restoreAfterReload', 'reloadOnto', 'detailsKey']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S)[0] for name in names)
    # Run the real reload initializer a second time, as the next document does.
    initializer = page[page.index('let pendingRestore = (() => {'):page.index('\nfunction restoreView')]
    functions += '\nfunction readReloadState() { return ' + initializer.split(' = ', 1)[1] + '\n}'
    result = _run_reader_js(functions + '\nconst reloadAt = ' + repr(reload_at) + ';\n' + r'''
      class Node {
        constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.value = ''; }
        setAttribute(key, value) { this[key] = value; if (key === 'data-keep') this.dataset.keep = value; }
        appendChild(node) { node.parentElement?.removeChild(node); this.children.push(node); node.parentElement = this; return node; }
        append(...nodes) { nodes.forEach(node => this.appendChild(node)); }
        removeChild(node) { this.children = this.children.filter(child => child !== node); node.parentElement = null; }
        replaceChildren(...nodes) { [...this.children].forEach(node => this.removeChild(node)); this.append(...nodes); }
        get isConnected() { return this === body || !!this.parentElement?.isConnected; }
        querySelectorAll(selector) {
          return this.children.flatMap(node => [
            ...(selector === 'details' && node.tagName === 'DETAILS'
              || selector === 'summary' && node.tagName === 'SUMMARY'
              || selector === '[data-keep]' && node.dataset.keep ? [node] : []),
            ...node.querySelectorAll(selector)]);
        }
        querySelector(selector) { return this.querySelectorAll(selector)[0]; }
        closest() { return null; }
        dispatchEvent() {}
      }
      const body = new Node('body'), editedFields = new WeakSet(), OPEN_TALKS = new Map(), HAND_FAILED = new Map();
      const document = {createElement: tag => new Node(tag), createTextNode: text => Object.assign(new Node('#text'), {textContent: text}),
        querySelectorAll: selector => body.querySelectorAll(selector), activeElement: null};
      const AGENT_NAMES = {codex: 'Codex', claude: 'Claude'}, ACTIVE_TASK = ['queued', 'starting', 'running'];
      const location = {protocol: 'http:', hash: '#view=open', reload() {}}, scrollY = 91, scrollTo = () => {};
      const RELOAD_STATE = 'co-rem-reload', storage = new Map();
      const sessionStorage = {setItem: (key, value) => storage.set(key, value),
        getItem: key => storage.get(key), removeItem: key => storage.delete(key)};
      const key = 'projects/fernhill.md\nFern owes you the Fernhill Labs contract draft.';
      const REM = {live: true, today_queue: [{key, keys: [key]}]}, entry = {key};
      const doneKey = entry => entry.key, agentText = text => el('div', {text}), timers = [], requests = [];
      const setTimeout = callback => timers.push(callback);
      const savedTalk = {id: 'one-talk', agent: 'claude', about: {key}, state: 'working',
        turns: [{role: 'context', text: 'Read the contract item.'}]};
      const fetch = async (url, options) => {
        const request = JSON.parse(options.body); requests.push(request);
        if (request.action === 'say') {
          savedTalk.turns.push({role: 'owner', text: request.text}); savedTalk.state = 'working';
        }
        if (request.action === 'read') {
          savedTalk.turns.push({role: 'agent', text: 'The contract draft is ready.'}); savedTalk.state = 'idle';
        }
        return {ok: true, status: 200, json: async () => structuredClone(savedTalk)};
      };
      const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
      const poll = async () => { timers.splice(0).forEach(callback => callback()); await flush(); };
      const find = (node, predicate) => predicate(node) ? node : node.children.map(child => find(child, predicate)).find(Boolean);
      const panel = row => find(row, node => node.class === 'talk');
      let pendingRestore = null;
      (async () => {
        let row = handOff(entry); body.append(row);
        // The talk's choices sit in the item's second level (Show more, #3072); they open the talk in the row's own slot.
        find(talkMenu(entry, find(row, node => node.class === 'talk-slot')), node => node['data-talk'] === 'claude').onclick();
        if (reloadAt !== 'opening') await flush();
        if (reloadAt === 'idle') await poll();
        const draft = 'Draft the follow-up, short.';
        const originalInput = find(panel(row), node => node.tagName === 'TEXTAREA');
        originalInput.value = draft; editedFields.add(originalInput);
        reloadOnto();
        const kept = JSON.parse(storage.get(RELOAD_STATE));
        // A document reload discards the map; the actual initializer must reopen the saved conversation.
        body.replaceChildren(); OPEN_TALKS.clear();
        pendingRestore = readReloadState();
        row = handOff(entry); body.append(row); restoreAfterReload(); await flush(); await poll();
        const talk = panel(row);
        if (!talk) { console.log(JSON.stringify({kept: kept.talks || null, restored: false})); return; }
        const input = find(talk, node => node.tagName === 'TEXTAREA');
        const restoredDraft = input.value;
        const before = viewState();
        // An ordinary redraw moves the same panel to the new row, including unsent words.
        body.replaceChildren(); row = handOff(entry); body.append(row); restoreView(before);
        const samePanel = panel(row) === talk, typed = input.value;
        await find(talk, node => node.tagName === 'FORM').onsubmit({preventDefault() {}});
        await flush(); await poll();
        console.log(JSON.stringify({kept: kept.talks || null, restored: true, restoredDraft, samePanel, typed,
          context: !!find(talk, node => node.class === 'talk-context'),
          agents: find(talk, node => node.class === 'talk-turns').children.filter(node => node.class === 'talk-turn agent').length,
          owner: find(talk, node => node.class === 'talk-turn owner')?.children[1].textContent,
          enabled: !find(talk, node => node.type === 'submit').disabled,
          say: requests.find(request => request.action === 'say')}));
      })();
    ''')
    key = 'projects/fernhill.md\nFern owes you the Fernhill Labs contract draft.'
    assert result['kept'] == [[key, {'action': 'begin', 'agent': 'claude', 'key': key}]]
    assert result['restored'] and result['samePanel'] and result['context']
    assert result['restoredDraft'] == result['typed'] == result['owner'] == 'Draft the follow-up, short.'
    assert result['agents'] == 2 and result['enabled']
    assert result['say'] == {'action': 'say', 'id': 'one-talk', 'text': result['typed']}

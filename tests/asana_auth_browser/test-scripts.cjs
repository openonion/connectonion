// The page scripts `co auth asana` runs in Asana's developer console, on synthetic pages
// that keep only the structure observed on 2026-11-21 (no page dump, no real token).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');

// The scripts live in asana_auth.py as r"""...""" constants; read them from there so the
// file under test is the one that ships.
const module_ = fs.readFileSync(
  path.resolve(__dirname, '../../connectonion/cli/commands/asana_auth.py'), 'utf8');
const script = (name) => {
  const found = module_.match(new RegExp(name + ' = r"""([\\s\\S]*?)"""'));
  assert.ok(found, name + ' not found in asana_auth.py');
  return found[1];
};
const TOKEN = '2/1220155493282912/1220189395633572:' + 'a'.repeat(32);
const SHAPE = String.raw`\b\d+/\d{6,}/\d{6,}:[0-9a-f]{32}\b`;

function page(html) {
  const dom = new JSDOM(html, {url: 'https://app.asana.com/0/my-apps', runScripts: 'outside-only'});
  const w = dom.window;
  // jsdom lays nothing out; every element counts as on screen, as it does in Chrome here.
  w.Element.prototype.getClientRects = function () { return [{width: 10, height: 10}]; };
  // jsdom has no innerText; Chrome's is the rendered text, which here is the text content.
  Object.defineProperty(w.HTMLElement.prototype, 'innerText', {get() { return this.textContent; }});
  w.fetch = () => { throw Error('No script may call the network'); };
  const run = (name, args = {}) => Promise.resolve(w.eval('(' + script(name) + ')')(args))
    .then((r) => JSON.parse(JSON.stringify(r)));
  return {w, run};
}

const CONSOLE = `
  <a>My apps</a><div role="button">View details</div>
  <div role="button" id="open">Create new token</div>`;
const DIALOG = `
  <div role="dialog"><h2>Create new token</h2>
    <label>Token name <input type="text" placeholder="What will this token be used for?"></label>
    <label><input type="checkbox"> I agree to the Asana API terms</label>
    <div role="button">Cancel</div><div role="button" id="create">Create token</div>
  </div>`;

function consoleWithLateDialog(delay) {
  const p = page(CONSOLE);
  p.w.document.getElementById('open').addEventListener('click', () => {
    // Asana draws the dialog after the click, not during it.
    p.w.setTimeout(() => p.w.document.body.insertAdjacentHTML('beforeend', DIALOG), delay);
  });
  return p;
}

test('the form is opened, waited for, named, and the two clicks are pointed at', async () => {
  const p = consoleWithLateDialog(300);
  const state = await p.run('OPEN_DIALOG_JS', {name: 'co on studio 2026-11-21', hint: 'tick and press Create'});
  assert.deepEqual(state, {tab: false, opened: true, named: true, pointed: true});
  const d = p.w.document.querySelector('[role="dialog"]');
  assert.equal(d.querySelector('input[type="text"]').value, 'co on studio 2026-11-21');
  assert.equal(d.querySelector('[data-co-hint]').textContent, 'tick and press Create');
  assert.match(d.querySelector('#create').style.outline, /solid/);
  assert.match(d.querySelector('input[type="checkbox"]').closest('label').style.outline, /solid/);
  assert.equal(d.querySelector('input[type="checkbox"]').checked, false);   // the terms stay the person's
});

test('a dialog that never comes is reported, not waited for', async () => {
  const p = page(CONSOLE);
  const state = await p.run('OPEN_DIALOG_JS', {name: 'x', hint: 'y', wait: 200});
  assert.deepEqual(state, {tab: false, opened: true, named: false});
});

test('a console without the button opens nothing', async () => {
  const p = page('<a>My apps</a>');
  const state = await p.run('OPEN_DIALOG_JS', {name: 'x', hint: 'y', wait: 200});
  assert.equal(state.opened, false);
  assert.equal(state.named, false);
});

test('the new token is found where Asana shows it, and only a token-shaped string', async () => {
  const shown = page(`<div role="dialog"><input readonly value="${TOKEN}"></div>`);
  assert.deepEqual(await shown.run('FIND_TOKEN_JS', {shape: SHAPE}), {token: TOKEN});
  const inText = page(`<div role="dialog"><p>Copy this token: ${TOKEN}</p></div>`);
  assert.deepEqual(await inText.run('FIND_TOKEN_JS', {shape: SHAPE}), {token: TOKEN});
  const none = page(`<div role="dialog"><p>1220155493282912</p><input value="2/12/34:short"></div>`);
  assert.deepEqual(await none.run('FIND_TOKEN_JS', {shape: SHAPE}), {token: ''});
});

test('the done page is one line and nothing of the console is left', async () => {
  const p = page(`<div role="dialog"><input readonly value="${TOKEN}"></div>`);
  const state = await p.run('DONE_JS', {text: 'Asana authorization complete. You may close this tab.'});
  assert.deepEqual(state, {shown: true});
  assert.equal(p.w.document.body.textContent.trim(), 'Asana authorization complete. You may close this tab.');
  assert.ok(!p.w.document.documentElement.outerHTML.includes(TOKEN));
});

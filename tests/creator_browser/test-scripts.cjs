// Synthetic fixtures retain only the observed semantic structures, not page dumps.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '../../connectonion/useful_skills/co-creator/scripts');
const sources = Object.fromEntries(['extract-tiktok', 'verify-tiktok']
  .map(name => [name, fs.readFileSync(path.join(root, name + '.js'), 'utf8')]));

function page(html, url = 'https://www.tiktok.com/login') {
  const dom = new JSDOM(html, {url, runScripts: 'outside-only'});
  const w = dom.window;
  w.HTMLElement.prototype.getBoundingClientRect = function () {
    const top = this.hasAttribute('data-offscreen') ? 2000 : 100;
    return {x: 20, y: top, top, left: 20, right: 420, bottom: top + 30, width: 400, height: 30};
  };
  w.Element.prototype.click = () => { throw Error('No script may click'); };
  w.fetch = () => { throw Error('No script may call the network'); };
  return {w, run: (name, args = {}) => JSON.parse(JSON.stringify(w.eval('(' + sources[name] + ')')(args)))};
}

test('TikTok login is proven but never reported as ready', () => {
  const p = page('<h2 data-e2e="login-title">Log in to TikTok</h2>', 'https://www.tiktok.com/login?redirect_url=anything');
  const data = p.run('extract-tiktok');
  assert.equal(data.ok, false);
  assert.equal(data.reason, 'login_required');
  assert.equal(p.run('verify-tiktok', {expected_item: data.selected_item}).ok, true);
  assert.equal(p.run('verify-tiktok').ok, false);
  assert.equal(p.run('verify-tiktok', {expected_item: {...data.selected_item, text_hash: 'wrong'}}).ok, false);
  p.w.close();
});

test('a file input on an unobserved upload surface is not permission or readiness', () => {
  const p = page('<input type="file"><button>Post</button>', 'https://www.tiktok.com/tiktokstudio/upload');
  const data = p.run('extract-tiktok');
  assert.equal(data.ok, false);
  assert.equal(data.reason, 'unverified_surface');
  assert.equal(data.submit_supported, false);
  p.w.close();
});

test('verifiers use the same scanner plus a mandatory expected-identity guard', () => {
  for (const [provider, argument] of [['tiktok', 'expected_item']]) {
    const guard = `\n  if (!args || args.${argument} === undefined) return {ok: false, reason: 'expected_identity_required', scanned: []};`;
    assert.equal(sources['verify-' + provider], sources['extract-' + provider].replace('(args) => {', '(args) => {' + guard));
  }
});


test('TikTok verification rejects changed, hidden and absent login headings', () => {
  const p = page('<h2 data-e2e="login-title">Log in to TikTok</h2>');
  const expected = p.run('extract-tiktok').selected_item;
  const heading = p.w.document.querySelector('h2');
  heading.textContent = 'Different';
  assert.equal(p.run('verify-tiktok', {expected_item: expected}).ok, false);
  heading.textContent = 'Log in to TikTok';
  heading.hidden = true;
  assert.equal(p.run('verify-tiktok', {expected_item: expected}).ok, false);
  heading.remove();
  assert.equal(p.run('verify-tiktok', {expected_item: expected}).ok, false);
  p.w.close();
});

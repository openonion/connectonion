"""Two independent browser contexts share notebook decisions; offline changes reconcile."""
import json
import re
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from connectonion.rem import drafts, reader, threads
from connectonion.rem.config import prepare
from connectonion.rem.files import read_json, state_path
from tests.unit.test_rem_live_reader import call
from tests.unit.test_rem_proactive import mail_thread
from tests.unit.test_rem_reader_threads import crowd_the_version_table, thread_key

pytestmark = pytest.mark.skipif(os.environ.get('CO_REM_BROWSER_TEST') != '1', reason='requires Chrome')


def _wait_for_sync(page):
    # Patchright's wait_for_function has no isolated_context argument. Poll
    # through evaluate so this assertion reads the reader's main-world state.
    page.evaluate("""() => new Promise((resolve, reject) => {
      let attempts = 0;
      const check = () => {
        if (!Object.keys(pendingThreads).length) resolve();
        else if (++attempts >= 1500) reject(new Error('Thread decisions did not sync'));
        else setTimeout(check, 20);
      };
      check();
    })""", isolated_context=False)


@pytest.mark.parametrize('width', [1280, 375])
def test_done_skip_undo_and_offline_reconciliation(tmp_path, monkeypatch, width):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.live_host import reader_token
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    root, identity = tmp_path / 'rem', tmp_path / 'identity'
    prepare(root)
    identity.mkdir()
    mail_thread(root)
    row = drafts.queue(root)[0]
    drafts.promote(root, {**row, 'body': 'I will review the pilot today.', 'sources': ['gmail:one']})
    routes = {'rem_root': root, 'identity_dir': identity}
    cookie = 'co_rem=' + reader_token(identity)
    offline = False
    shots = Path('/tmp/frontend-test-screenshots/rem-thread-actions')
    shots.mkdir(parents=True, exist_ok=True)

    def serve(route):
        request = route.request
        if offline and request.url.endswith('/rem/thread'):
            route.abort()
            return
        # Patchright invokes routes inside its event loop; the ASGI helper owns
        # an asyncio.run(), so execute it in a worker with no running loop.
        with ThreadPoolExecutor(max_workers=1) as worker:
            status, headers, body = worker.submit(
                call, routes, request.method, request.url.split(':8123')[-1].split('#')[0],
                cookie=cookie, body=(request.post_data or '').encode()).result()
        route.fulfill(status=status, headers=headers, body=body)

    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        desktop, other = browser.new_context(viewport={'width': width, 'height': 900}), browser.new_context()
        desktop.route('http://127.0.0.1:8123/**', serve)
        other.route('http://127.0.0.1:8123/**', serve)
        page, second = desktop.new_page(), other.new_page()
        page_errors = []
        page.on('pageerror', lambda error: page_errors.append(str(error)))
        url = 'http://127.0.0.1:8123/rem'
        page.goto(url)
        page.locator('.qcard.focal .more-menu > summary').click()  # Skip is behind the letter's 更多 (D-120)
        page.get_by_role('button', name='Skip', exact=True).first.click()
        page.get_by_text('Saved in notebook', exact=True).wait_for()
        assert read_json(state_path(root, 'threads.json'), {})
        page.screenshot(path=str(shots / f'skipped-{width}.png'))
        # The other device reads the decision from Today: a person's page keeps no ledger (D-30).
        second.goto(url + '#view=open')
        second.locator('.done-details summary').click()
        assert 'Skipped' in second.locator('.done-details').inner_text()
        page.locator('#done-notice').get_by_role('button', name='Undo', exact=True).click()
        page.locator('.qcard.focal .more-menu > summary').wait_for()
        page.goto(url + '#view=open')
        page.locator('.task-band .thread').first.get_by_role('button', name='Mark done', exact=True).click()
        page.get_by_text('Saved in notebook', exact=True).wait_for()
        page.wait_for_timeout(5100)
        assert page.locator('#done-notice').count() == 0
        page.screenshot(path=str(shots / f'record-done-{width}.png'))
        second.reload()
        second.locator('.done-details summary').click()
        assert 'Marked done' in second.locator('.done-details').inner_text()
        page.locator('.done-details summary').click()
        page.locator('.done-details').get_by_role('button', name='Undo', exact=True).click()
        _wait_for_sync(page)
        offline = True
        page.get_by_role('button', name='Mark done', exact=True).click()
        page.locator('#thread-save-status').get_by_text('Saved on this device — sync pending', exact=True).wait_for()
        page.screenshot(path=str(shots / f'offline-{width}.png'))
        offline = False
        page.reload()
        page.locator('.done-details summary').click()
        page.locator('.done-details').get_by_role('button', name='Undo', exact=True).wait_for()
        _wait_for_sync(page)
        assert next(iter(threads.listing(root).values()))['state'] == 'done'
        page.locator('.done-details').get_by_role('button', name='Undo', exact=True).click()
        _wait_for_sync(page)
        drafts.discard(root, row['id'])
        mail_thread(root, latest='two')
        page.reload()
        page.get_by_text(re.compile(r'New mail ·')).wait_for()
        page.screenshot(path=str(shots / f'returned-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth', isolated_context=False)
        assert not page_errors
        browser.close()


def _serve(routes, cookie, offline=lambda: False):
    """Route the browser's requests into the Host's ASGI handler; /rem/thread fails while offline()."""
    def serve(route):
        request = route.request
        if offline() and request.url.endswith('/rem/thread'):
            route.abort()
            return
        with ThreadPoolExecutor(max_workers=1) as worker:
            status, headers, body = worker.submit(
                call, routes, request.method, request.url.split(':8123')[-1].split('#')[0],
                cookie=cookie, body=(request.post_data or '').encode()).result()
        route.fulfill(status=status, headers=headers, body=body)
    return serve


def _live_notebook(tmp_path, monkeypatch):
    from connectonion.rem.live_host import reader_token
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    root, identity = tmp_path / 'rem', tmp_path / 'identity'
    prepare(root)
    identity.mkdir()
    mail_thread(root)
    return root, {'rem_root': root, 'identity_dir': identity}, 'co_rem=' + reader_token(identity)


# A loaded machine: the reconcile's read waits until the test calls releaseSync(),
# and every read of /rem/thread is counted in threadReads.
HOLD_SYNC = """(() => { const real = window.fetch; let release;
  const held = new Promise(resolve => { release = resolve; });
  window.threadReads = 0;
  window.releaseSync = () => { sessionStorage.removeItem('hold-sync'); release(); };
  window.fetch = (url, options) => {
    if (url !== '/rem/thread' || options) return real(url, options);
    const read = sessionStorage.getItem('hold-sync') ? held.then(() => real(url, options)) : real(url, options);
    return read.then(response => { window.threadReads++; return response; });
  }; })()"""


@pytest.mark.parametrize('width', [1280, 375])
def test_a_section_opened_before_the_sync_lands_stays_open(tmp_path, monkeypatch, width):
    """The redraw after reconcileThreads keeps what the reader opened (1.9.3 blocker):
    a done saved offline shows at once after reload; a slow GET /rem/thread then
    redrew the page and closed 'Done or skipped', hiding its Undo. The section keeps
    its place when the sync also changes its count (another device marked one done)."""
    from patchright.sync_api import sync_playwright
    from connectonion.rem.files import Notebook
    from connectonion.rem.store import refresh
    root, routes, cookie = _live_notebook(tmp_path, monkeypatch)
    record = Notebook(root).read('people/fern.md')
    Notebook(root).write('people/fern.md', record.replace(
        '- You owe Fern a pilot review. [1]', '- You owe Fern a pilot review. [1]\n- You owe Fern the budget notes. [1]'))
    refresh(root)
    offline = False
    shots = Path('/tmp/frontend-test-screenshots/rem-thread-actions')
    shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        context, other = browser.new_context(viewport={'width': width, 'height': 900}), browser.new_context()
        context.add_init_script(HOLD_SYNC)
        context.route('http://127.0.0.1:8123/**', _serve(routes, cookie, lambda: offline))
        other.route('http://127.0.0.1:8123/**', _serve(routes, cookie))
        page, second = context.new_page(), other.new_page()
        page.goto('http://127.0.0.1:8123/rem#view=open')
        offline = True
        page.locator('.task-band .thread', has_text='pilot review').get_by_role('button', name='Mark done', exact=True).click()
        page.locator('#thread-save-status').get_by_text('Saved on this device — sync pending', exact=True).wait_for()
        offline = False
        page.evaluate("sessionStorage.setItem('hold-sync', '1')", isolated_context=False)
        page.reload()
        page.locator('.done-details summary', has_text='(1)').click()
        # While the read is held, the other device marks the second thread done: the count becomes 2.
        second.goto('http://127.0.0.1:8123/rem#view=open')
        second.locator('.task-band .thread', has_text='budget notes').get_by_role('button', name='Mark done', exact=True).click()
        second.get_by_text('Saved in notebook', exact=True).wait_for()
        page.evaluate('releaseSync()', isolated_context=False)
        # Only the redraw after the sync replaces the pending line and shows both.
        page.locator('.done-details .quiet-line', has_text='Saved in your notebook').wait_for(state='attached')
        page.locator('.done-details summary', has_text='(2)').wait_for(state='attached')
        page.screenshot(path=str(shots / f'kept-open-{width}.png'))
        assert page.locator('.done-details').evaluate('node => node.open', isolated_context=False)
        assert page.locator('.done-details').get_by_role('button', name='Undo', exact=True).first.is_visible()
        assert [row['state'] for row in threads.listing(root).values()] == ['done', 'done']
        browser.close()


@pytest.mark.parametrize('width', [1280, 375])
def test_returning_to_the_window_keeps_a_reply_being_typed(tmp_path, monkeypatch, width):
    """Window focus reconciles thread decisions; its redraw must not wipe an answer typed
    into a reply's slot, nor take the cursor out of it."""
    from patchright.sync_api import sync_playwright
    root, routes, cookie = _live_notebook(tmp_path, monkeypatch)
    row = drafts.queue(root)[0]
    drafts.promote(root, {**row, 'body': 'I will review the pilot on [day].', 'sources': ['gmail:one']})

    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': width, 'height': 900})
        context.add_init_script(HOLD_SYNC)
        context.route('http://127.0.0.1:8123/**', _serve(routes, cookie))
        page = context.new_page()
        page.goto('http://127.0.0.1:8123/rem')
        box = page.locator('.owner-slot input').first
        box.click()
        box.press_sequentially('Friday')
        page.evaluate("""() => new Promise(resolve => {
          const reads = threadReads;
          dispatchEvent(new Event('focus'));
          const check = () => threadReads > reads ? setTimeout(resolve, 300) : setTimeout(check, 20);
          check();
        })""", isolated_context=False)
        assert page.locator('.owner-slot input').first.input_value() == 'Friday'
        browser.close()


def _thread_write(response):
    return response.request.method == 'POST' and response.url.endswith('/rem/thread')


@pytest.mark.parametrize('width', [1280, 375])
def test_done_and_undo_reach_a_notebook_whose_version_table_is_over_64_kb(tmp_path, monkeypatch, width):
    """#2936: every mark carried the whole version table; past the Host's 64 KB it answered 400 and
    the page said "sync pending" for good. A mark names only the mail it cites, at any notebook size."""
    from patchright.sync_api import sync_playwright
    root, routes, cookie = _live_notebook(tmp_path, monkeypatch)
    crowd_the_version_table(root)

    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': width, 'height': 900})
        context.route('http://127.0.0.1:8123/**', _serve(routes, cookie))
        page = context.new_page()
        page.goto('http://127.0.0.1:8123/rem#view=open')
        with page.expect_response(_thread_write) as answered:
            page.locator('.task-band .thread', has_text='pilot review').get_by_role('button', name='Mark done', exact=True).click()
        sent = answered.value.request.post_data
        assert read_json(state_path(root, 'threads.json'), {}).get(thread_key(root), {}).get('state') == 'done'
        assert json.loads(sent)['versions'] == {'mail:gmail:pilot': 'gmail:one'} and len(sent) < 1024
        with page.expect_response(_thread_write):
            page.locator('#done-notice').get_by_role('button', name='Undo', exact=True).click()
        assert thread_key(root) not in read_json(state_path(root, 'threads.json'), {})
        browser.close()


def test_a_done_kept_with_the_whole_table_reaches_the_notebook_on_the_next_load(tmp_path, monkeypatch):
    """A browser that marked Done before the fix holds that mark in its pending list, whole table and all."""
    from patchright.sync_api import sync_playwright
    root, routes, cookie = _live_notebook(tmp_path, monkeypatch)
    crowd_the_version_table(root)

    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        context.route('http://127.0.0.1:8123/**', _serve(routes, cookie))
        page = context.new_page()
        page.goto('http://127.0.0.1:8123/rem#view=open')
        page.locator('.task-band .thread', has_text='pilot review').wait_for()
        _wait_for_sync(page)
        page.evaluate("""key => localStorage.setItem(threadStorageKey(), JSON.stringify({states: {}, pending: {[key]:
          {state: 'done', at: '2026-11-08T01:00:00.000Z', device: 'test', keys: [key], versions: REM.mail_versions}}}))""",
                      thread_key(root), isolated_context=False)
        with page.expect_response(_thread_write) as answered:
            page.reload()
        assert answered.value.status == 200 and len(answered.value.request.post_data) < 1024
        assert read_json(state_path(root, 'threads.json'), {})[thread_key(root)]['state'] == 'done'
        _wait_for_sync(page)
        browser.close()


def test_a_done_met_by_a_busy_notebook_waits_and_is_saved_on_the_next_load(tmp_path, monkeypatch):
    """Another writer holds the notebook for a moment: the Host answers 409, which is not a refusal. The mark waits."""
    from patchright.sync_api import sync_playwright
    from connectonion.rem.files import maintenance_lock
    root, routes, cookie = _live_notebook(tmp_path, monkeypatch)

    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        context.route('http://127.0.0.1:8123/**', _serve(routes, cookie))
        page = context.new_page()
        page.goto('http://127.0.0.1:8123/rem#view=open')
        mark = page.locator('.task-band .thread', has_text='pilot review').get_by_role('button', name='Mark done', exact=True)
        with maintenance_lock(root), page.expect_response(_thread_write) as busy:
            mark.click()
        assert busy.value.status == 409
        page.locator('#done-notice').get_by_text('Saved on this device — sync pending', exact=True).wait_for()
        assert page.get_by_text('Not saved').count() == 0
        assert page.evaluate('Object.keys(pendingThreads).length', isolated_context=False) == 1
        assert read_json(state_path(root, 'threads.json'), {}) == {}
        with page.expect_response(_thread_write) as saved:
            page.reload()
        assert saved.value.status == 200
        assert read_json(state_path(root, 'threads.json'), {})[thread_key(root)]['state'] == 'done'
        _wait_for_sync(page)
        browser.close()


@pytest.mark.parametrize('width', [1280, 375])
def test_a_refused_done_says_not_saved_and_try_again_saves_it(tmp_path, monkeypatch, width):
    """The Host answered 400: nothing is waiting to sync. The thread comes back, and the notice offers another try."""
    from patchright.sync_api import sync_playwright
    root, routes, cookie = _live_notebook(tmp_path, monkeypatch)
    refusing = True
    shots = Path('/tmp/frontend-test-screenshots/rem-thread-actions')
    shots.mkdir(parents=True, exist_ok=True)

    def serve(route):
        if refusing and route.request.method == 'POST' and route.request.url.endswith('/rem/thread'):
            route.fulfill(status=400, headers={'content-type': 'application/json'}, body='{"error": "Invalid JSON"}')
        else:
            _serve(routes, cookie)(route)

    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': width, 'height': 900})
        context.route('http://127.0.0.1:8123/**', serve)
        page = context.new_page()
        page.goto('http://127.0.0.1:8123/rem#view=open')
        mark = page.locator('.task-band .thread', has_text='pilot review').get_by_role('button', name='Mark done', exact=True)
        not_saved = page.locator('#done-notice').get_by_text('Not saved · Try again', exact=True)
        with page.expect_response(_thread_write):
            mark.click()
        not_saved.wait_for()
        page.screenshot(path=str(shots / f'not-saved-{width}.png'))
        assert mark.is_visible()
        assert page.get_by_text('sync pending').count() == 0
        assert page.evaluate('Object.keys(pendingThreads).length', isolated_context=False) == 0
        assert read_json(state_path(root, 'threads.json'), {}) == {}
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth', isolated_context=False)
        page.locator('#done-notice').wait_for(state='detached', timeout=8000)  # it leaves as the Done notice does
        mark.click()
        not_saved.wait_for()
        refusing = False
        page.locator('#done-notice').get_by_role('button', name='Try again', exact=True).click()
        page.get_by_text('Saved in notebook', exact=True).wait_for()
        assert read_json(state_path(root, 'threads.json'), {})[thread_key(root)]['state'] == 'done'
        browser.close()

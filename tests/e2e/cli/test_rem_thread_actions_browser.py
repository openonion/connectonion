"""Two independent browser contexts share notebook decisions; offline changes reconcile."""
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
        page.get_by_role('button', name='Skip', exact=True).first.click()
        page.get_by_text('Saved in notebook', exact=True).wait_for()
        assert read_json(state_path(root, 'threads.json'), {})
        page.screenshot(path=str(shots / f'skipped-{width}.png'))
        second.goto(url + '#r=people%2Ffern.md')
        second.get_by_role('button', name='Undo', exact=True).wait_for()
        assert 'Skipped' in second.locator('.owe').inner_text()
        page.locator('#done-notice').get_by_role('button', name='Undo', exact=True).click()
        page.get_by_role('button', name='Skip', exact=True).first.wait_for()
        page.goto(url + '#r=people%2Ffern.md')
        page.get_by_role('button', name='Mark done', exact=True).click()
        page.get_by_text('Saved in notebook', exact=True).wait_for()
        page.wait_for_timeout(5100)
        assert page.locator('#done-notice').count() == 0
        page.screenshot(path=str(shots / f'record-done-{width}.png'))
        second.reload()
        assert 'Marked done' in second.locator('.owe').inner_text()
        page.get_by_role('button', name='Undo', exact=True).click()
        _wait_for_sync(page)
        offline = True
        page.get_by_role('button', name='Mark done', exact=True).click()
        page.get_by_text('Saved on this device — sync pending', exact=True).wait_for()
        page.screenshot(path=str(shots / f'offline-{width}.png'))
        offline = False
        page.reload()
        page.get_by_role('button', name='Undo', exact=True).wait_for()
        _wait_for_sync(page)
        assert next(iter(threads.listing(root).values()))['state'] == 'done'
        page.get_by_role('button', name='Undo', exact=True).click()
        _wait_for_sync(page)
        drafts.discard(root, row['id'])
        mail_thread(root, latest='two')
        page.reload()
        page.get_by_text(re.compile(r'New mail ·')).wait_for()
        page.screenshot(path=str(shots / f'returned-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth', isolated_context=False)
        assert not page_errors
        browser.close()

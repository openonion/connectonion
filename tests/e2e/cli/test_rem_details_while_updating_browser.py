"""Deferred pages load their details while a newer render builds (1.9.6rc2).

The "Updating…" banner was appended to /rem/data.json too, so every page that
waits for the details (Org, Projects, All records, Skills) failed with
"Unexpected non-whitespace character after JSON".
"""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from connectonion.rem import reader
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from tests.unit.test_rem_live_reader import call

pytestmark = pytest.mark.skipif(os.environ.get('CO_REM_BROWSER_TEST') != '1', reason='requires Chrome')


def test_org_and_projects_render_while_the_banner_shows(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.live_host import reader_token
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    root, identity = tmp_path / 'rem', tmp_path / 'identity'
    prepare(root)
    identity.mkdir()
    book = Notebook(root)
    book.write('orgs/harbour-labs.md', '# Harbour Labs\n\nA fictional lab.\n')
    book.write('projects/tide-gauge.md', '# Tide Gauge\n\nA fictional project.\n')
    routes = {'rem_root': root, 'identity_dir': identity}
    cookie = 'co_rem=' + reader_token(identity)
    call(routes, 'GET', '/rem', cookie=cookie)
    reader.refresh(root)
    # The banner's condition, forced: the key moved and a rebuild is running.
    real_version = reader.reader_version
    monkeypatch.setattr(reader, 'reader_version', lambda root: [*real_version(root), 'moved'])
    monkeypatch.setattr(reader, '_rebuild_stale', lambda *a, **k: True)

    def serve(route):
        request = route.request
        with ThreadPoolExecutor(max_workers=1) as worker:
            status, headers, body = worker.submit(
                call, routes, request.method, request.url.split(':8123')[-1].split('#')[0],
                cookie=cookie, body=(request.post_data or '').encode()).result()
        route.fulfill(status=status, headers=headers, body=body)

    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        context.route('http://127.0.0.1:8123/**', serve)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for hash_, name in (('#c=orgs', 'Harbour Labs'), ('#c=projects', 'Tide Gauge')):
            page.goto('http://127.0.0.1:8123/rem' + hash_)
            page.locator('#rem-updating').wait_for()                    # the banner is on the page
            page.locator('#main').get_by_text(name).first.wait_for()    # and the details loaded
            assert 'Could not load notebook' not in page.locator('#main').inner_text()
        browser.close()
    assert errors == []

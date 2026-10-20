"""The reader's design contract that holds without a browser.

Both themes must define every colour token: a token missing from dark falls
back to the light value and paints a light patch on a dark page. The page is
opened from file:// with a person's private notes in it, so it never names a
remote host. The People table's mail columns come from one adapter (#2064).
"""

import json
import re

import pytest
from datetime import datetime, timezone

from connectonion.rem.reader import TEMPLATE, mail_facts, snapshot


def _blocks(css: str) -> dict:
    light = re.search(r":root \{(.*?)\n  \}", css, re.S).group(1)
    media = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\}', css, re.S).group(1)
    forced = re.search(r':root\[data-theme="dark"\] \{(.*?)\}', css, re.S).group(1)
    tokens = lambda block: set(re.findall(r"(--[\w-]+):", block))  # noqa: E731
    return {"light": tokens(light), "dark-auto": tokens(media), "dark-forced": tokens(forced)}


def test_both_themes_define_every_colour_token():
    blocks = _blocks(TEMPLATE.read_text(encoding="utf-8"))
    faces = {"--display", "--text", "--ui", "--code", "--mono"}
    colours = blocks["light"] - faces
    assert len(colours) >= 20
    assert blocks["dark-auto"] == colours
    assert blocks["dark-forced"] == colours


def test_the_template_names_no_remote_host_and_loads_no_font():
    page = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"https?://(?!www\.)[a-z0-9.-]+\.[a-z]{2,}", page)
    assert "@font-face" not in page and "@import" not in page and "<link" not in page


def test_mail_facts_sum_a_person_seen_under_two_addresses(tmp_path):
    state = tmp_path / ".state"
    state.mkdir()
    (state / "map.json").write_text(json.dumps({"people": [
        {"address": "a@x.example", "record": "people/a.md", "mails": 5, "sent": 2, "received": 3, "first": "2026-08-02", "last": "2026-09-01"},
        {"address": "a@y.example", "record": "people/a.md", "mails": 4, "sent": 1, "received": 3, "first": "2026-07-09", "last": "2026-09-20"},
        {"record": "people/owner.md"}]}))
    assert mail_facts(tmp_path) == {"people/a.md": {"mails": 9, "sent": 3, "received": 6, "first": "2026-07-09", "last": "2026-09-20"}}


def test_the_sheet_reads_the_index_when_there_is_one_and_the_page_before(tmp_path, monkeypatch):
    """#2067: the index's People rows come first; without an index the snapshot has none."""
    import sys
    import types
    from connectonion.rem.reader import index_rows
    monkeypatch.setitem(sys.modules, "connectonion.rem.store", None)  # a co rem without the store
    assert index_rows(tmp_path) == {}
    fake = types.ModuleType("connectonion.rem.store")
    fake.people_table = lambda root, **kw: [{"record": "people/a.md", "phone": "+64 21 000", "emails": ["a@x.example"]}] \
        if kw.get("include_unlisted") else []
    monkeypatch.setitem(sys.modules, "connectonion.rem.store", fake)
    import connectonion.rem as rem
    monkeypatch.setattr(rem, "store", fake, raising=False)
    assert index_rows(tmp_path) == {"people/a.md": {"record": "people/a.md", "phone": "+64 21 000", "emails": ["a@x.example"]}}
    fake.people_table = lambda root, **kw: []  # the index file does not exist yet
    assert index_rows(tmp_path) == {}


def test_the_fixture_notebook_snapshot_carries_what_the_views_draw(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
    from rem_reader_notebook import build
    data = snapshot(build(tmp_path / "rem", datetime.now(timezone.utc)))
    mara = next(r for r in data["records"] if r["path"] == "people/mara-ostrowski.md")
    assert mara["mail"]["mails"] == 59 and mara["written"]
    assert any("people/mara-ostrowski.md" in run.get("changed", []) for run in data["logs"])


def test_the_template_has_activity_and_no_run_logs_category():
    """notes/ and logs/ are read under one Activity view; the browser checks live in
    tests/e2e/cli/test_rem_reader_design_browser.py (CO_REM_BROWSER_TEST=1)."""
    page = TEMPLATE.read_text(encoding="utf-8")
    assert "Run logs" not in page
    assert 'const ACTIVITY = new Set(["notes", "logs"])' in page
    assert 'view === "activity"' in page and 'href: "#view=activity"' in page


@pytest.mark.parametrize('zh', [False, True])
def test_fixture_cached_chinese_pages_preserve_reader_contract(tmp_path, monkeypatch, zh):
    import sys
    from pathlib import Path
    from connectonion.rem import translate
    from connectonion.rem.files import Notebook
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    root = build(tmp_path / 'rem', datetime(2026, 10, 20, 12, tzinfo=timezone.utc), zh=zh)
    data = snapshot(root)
    assert data['your_languages'] == (['zh', 'en'] if zh else ['en'])
    paths = ['people/mara-ostrowski.md', 'people/ines-halvorsen.md', 'people/avery-lin.md',
             'orgs/fernhill-labs.md', 'projects/harbour.md']
    for path in paths:
        translated = translate.cached(root, path, 'zh')
        if not zh:
            assert translated is None
            continue
        original = Notebook(root).read(path)
        assert translate.checked(original, translated) == translated
        assert original.partition('\n## Sources')[2] == translated.partition('\n## Sources')[2]
        assert '试点' in translated or path == 'people/ines-halvorsen.md'
        record = next(r for r in data['records'] if r['path'] == path)
        assert record['translations']['zh'] == translated


def test_readme_capture_uses_seven_offline_viewports_without_launching_a_browser(tmp_path, monkeypatch):
    import importlib.util
    import sys
    import types
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('capture_rem_reader', Path(__file__).resolve().parents[2] / 'scripts' / 'capture_rem_reader.py')
    capture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture)
    calls = []

    class Page:
        def route(self, pattern, callback):
            assert pattern == 'http*://**/*'
            callback(types.SimpleNamespace(abort=lambda: calls.append('blocked')))

        def goto(self, url):
            calls.append(url)

        def locator(self, selector):
            return types.SimpleNamespace(wait_for=lambda: None)

        def screenshot(self, **options):
            calls.append(options)

        def close(self):
            pass

    class Browser:
        def new_page(self, **options):
            calls.append(options)
            return Page()

        def close(self):
            pass

    class Playwright:
        def __enter__(self):
            return types.SimpleNamespace(chromium=types.SimpleNamespace(launch=lambda **kw: Browser()))

        def __exit__(self, *args):
            pass

    monkeypatch.setitem(sys.modules, 'playwright.sync_api', types.SimpleNamespace(sync_playwright=Playwright))
    monkeypatch.setattr(capture, 'render', lambda root: '<html>invented fixture</html>')
    shots = capture.capture_readme(tmp_path)
    assert [shot.name for shot in shots] == ['reader-desktop.png', 'reader-phone.png',
        'tour-en-person-dark-desktop.png', 'tour-en-open-phone-dark.png', 'tour-zh-home-desktop.png',
        'tour-zh-person-phone.png', 'tour-en-people-desktop.png']
    viewports = [call for call in calls if isinstance(call, dict) and 'viewport' in call]
    assert len(viewports) == 7 and calls.count('blocked') == 7
    for options in viewports:
        phone = options['viewport']['width'] == 390
        assert options['viewport'] == {'width': 390, 'height': 844} if phone else options['viewport'] == {'width': 1440, 'height': 1000}
        assert options['device_scale_factor'] == (2 if phone else 1)
    assert all(not call['full_page'] for call in calls if isinstance(call, dict) and 'path' in call)
    assert [options['locale'] for options in viewports] == ['en-GB'] * 4 + ['zh-CN'] * 2 + ['en-GB']

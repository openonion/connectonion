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
    css = TEMPLATE.read_text(encoding="utf-8")
    blocks = _blocks(css)
    light = re.search(r":root \{(.*?)\n  \}", css, re.S).group(1)
    # Every token whose light value is a colour; sizes, grid and motion do not change with the theme.
    colours = set(re.findall(r"(--[\w-]+): (?:#[\da-f]{6}|rgba\([^)]*\));", light))
    assert colours == {"--paper", "--raised", "--ink", "--grey", "--rule", "--well", "--green", "--on-green", "--red", "--pencil", "--scrim"}
    # N3 (D-123): the one green and its label are the same in both themes; every other colour has its dark value.
    # The shadows are drawn in colour too (a dark hairline on paper, a light one at night), so they change with it.
    shadows = {"--e1", "--e2", "--e3", "--e-fuse"}
    assert blocks["dark-auto"] == colours - {"--green", "--on-green"} | shadows
    assert blocks["dark-forced"] == blocks["dark-auto"]


def test_the_template_names_no_remote_host_and_loads_no_font():
    page = TEMPLATE.read_text(encoding="utf-8")
    # Explicit navigation to the original mail is allowed; remote assets are not.
    assert set(re.findall(r"https?://(?!www\.)[a-z0-9.-]+\.[a-z]{2,}", page)) == {
        'https://mail.google.com', 'https://outlook.live.com'}
    assert not re.search(r'(?:src\s*=\s*["\']|fetch\(["\'])https?://', page)
    assert "@font-face" not in page and "@import" not in page
    # The one <link> is the tab icon, a data: drawing; a stylesheet or a font would be a fetch.
    assert page.count("<link") == 1 and re.findall(r'<link\b[^>]*?\bhref="([^",]*)', page) == ["data:image/svg+xml"]


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


@pytest.mark.parametrize('theme', ['light', 'dark-auto', 'dark-forced'])
def test_muted_text_and_focus_tokens_meet_contrast_on_reader_surfaces(theme):
    css = TEMPLATE.read_text()
    patterns = {
        'light': r':root \{(.*?)\n  \}',
        'dark-auto': r':root:not\(\[data-theme="light"\]\) \{(.*?)\}',
        'dark-forced': r':root\[data-theme="dark"\] \{(.*?)\}',
    }
    block = re.search(patterns[theme], css, re.S).group(1)
    light = dict(re.findall(r'(--[\w-]+): (#[\da-f]{6})', re.search(patterns['light'], css, re.S).group(1)))
    colors = {**light, **dict(re.findall(r'(--[\w-]+): (#[\da-f]{6})', block))}  # green is the same in both themes

    def luminance(hex_color):
        rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))

    # N3: the paper, a raised card and a well inside it; the hairline still backs older tabs.
    for surface in ['--paper', '--raised', '--well', '--rule']:
        for token, minimum in [('--grey', 4.5), ('--ink', 3)]:
            a, b = sorted([luminance(colors[token]), luminance(colors[surface])])
            assert (b + .05) / (a + .05) >= minimum, (theme, token, surface)

    assert colors['--green'] == '#22d27a'
    for surface in ['--raised', '--well']:
        a, b = sorted([luminance(colors['--red']), luminance(colors[surface])])
        assert (b + .05) / (a + .05) >= 4.5, (theme, '--red', surface)
    # Red is text (overdue, danger), so it must read on the paper it sits on in both themes; in N3 a card is
    # --raised and its hover row --well (checked above), and --rule is only a hairline.
    for surface, foreground in [('--green', '--on-green'), ('--paper', '--ink'), ('--rule', '--ink'), ('--paper', '--red')]:
        a, b = sorted([luminance(colors[foreground]), luminance(colors[surface])])
        assert (b + .05) / (a + .05) >= 4.5, (theme, foreground, surface)
    # Pencil is REM's inference drawn as a dashed mark; at under 4.5:1 it never colours text.
    assert not re.search(r'(?<![\w-])color:\s*var\(--pencil\)', css)
    button = re.search(r'\.btn-act \{([^}]+)\}', css).group(1)
    assert 'background: var(--green)' in button and 'color: var(--on-green)' in button
    # Hover must change something: N3's primary lifts (D-123); the older views' keys still turn over.
    lift = _rule(css, '.btn-act:hover')
    assert lift and 'translateY' in lift
    for selector in ['.projects-view .btn-act:hover, .sessions-view.r4 .btn-act:hover', '.gx-open:hover']:
        hover = _rule(css, selector)
        assert hover and 'background: var(--on-green)' in hover and 'color: var(--green)' in hover, selector
    a, b = sorted([luminance(colors['--green']), luminance(colors['--on-green'])])
    assert (b + .05) / (a + .05) >= 4.5, (theme, 'hovered primary label')


def _rule(css, selector):
    """The body of the rule whose selector list is exactly `selector` (first match)."""
    match = re.search(r'(?:^|[}\n])\s*' + re.escape(selector) + r'\s*\{([^}]*)\}', css)
    return match.group(1) if match else None


def test_overdue_is_red_and_waiting_and_changed_keep_a_mark_of_their_own():
    """Collapsing amber and indigo onto ink left overdue, waiting and changed looking like nothing."""
    css = TEMPLATE.read_text(encoding="utf-8")
    for selector in ['.overdue, .thread .when.overdue', '.next-exchanges .when.overdue', '.r4 .chip.late',
                     '.ov-chip.late', '.qhead .qage.late']:
        assert 'color: var(--red)' in (_rule(css, selector) or ''), selector
    # An overdue chip is red on paper with a red edge, never a grey box.
    late = _rule(css, '.r4 .chip.late')
    assert 'var(--rule)' not in late and 'outline: var(--hair) solid var(--red)' in late
    waiting, open_ = _rule(css, '  .nav .n'), _rule(css, 'nav a .n.open')
    assert waiting and waiting.strip() != (open_ or '').strip()
    changed, dt = _rule(css, '.person-insight dt.changed'), _rule(css, '.person-insight dt')
    assert changed and 'color' not in changed and changed.strip() != dt.strip()
    assert _rule(css, '.person-insight dt.at-stake') is None

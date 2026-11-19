"""Fixes from the hourly auto-scan (#3165): search that reads in groups (#3169), a skill page that prints only
what is known, and a Changes page in the reader's words. Invented fixtures only."""

import os

import pytest

from tests.e2e.cli.test_rem_record_pages_browser import reader  # noqa: F401  (the shared reader fixture)

SHOTS = os.environ.get("REM_PR_SHOTS")
KINDS = ["people", "orgs", "projects", "knowledge", "skills", "decisions", "sessions"]


def _shot(page, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, name))


def _many_hits(page):
    """220 invented pages that all mention 'quill', 30-odd of each kind, with ISO dates and raw ids in their text."""
    page.evaluate("""() => {
      const kinds = ['people', 'orgs', 'projects', 'knowledge', 'skills', 'decisions', 'sessions'];
      for (let i = 0; i < 220; i++) {
        const c = kinds[i % kinds.length], slug = 'quill-' + c + '-' + i;
        const text = '# Quill ' + c + ' ' + i + '\\n\\n## Who they are\\n- 2026-10-0' + (1 + i % 9) + 'T10:00:00Z: met about the quill pilot in codex:01a1a594-aaaa-bbbb-cccc-dddddddddddd:200924-7da282f4 and 7152b30ab162a51eeae8672cea167403.\\n';
        REM.records.push({ path: c + '/' + slug + '.md', title: 'Quill ' + c + ' ' + i, category: c, written: true, text,
          ...(c === 'sessions' ? { session_title: 'Quill session ' + i, session_messages: [] } : {}) });
      }
      KNOWN.clear(); FACTS.clear();
    }""", isolated_context=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_search_reads_in_groups_of_five_with_counts_chips_and_show_all(reader, width):  # noqa: F811
    open_page, _ = reader
    page = open_page("", width=width)
    _many_hits(page)
    page.evaluate("location.hash = '#q=quill'", isolated_context=False)
    page.locator(".search-group[data-kind]").first.wait_for()
    groups = page.locator(".search-group[data-kind]")
    assert groups.count() >= 5
    for i in range(groups.count()):
        group = groups.nth(i)
        shown = group.locator(".hits > li:visible").count()
        total = int(group.locator("h2 .n").inner_text())
        assert shown == min(5, total), (shown, total)
        if total > 5:
            assert group.get_by_role("button", name=f"显示全部 {total} 个").is_visible()
    # The page shows groups of five, not one long list.
    assert page.locator(".search-group[data-kind] .hits > li:visible").count() <= 5 * groups.count()
    # Kind chips filter the groups.
    chips = page.locator(".search-kinds button")
    assert chips.count() >= 5
    page.locator(".search-kinds button", has_text="人物").click()
    assert page.locator(".search-group[data-kind]:visible").count() == 1
    page.locator(".search-kinds button", has_text="全部").click()
    # Show all opens one group in place.
    first = groups.first
    total = int(first.locator("h2 .n").inner_text())
    first.get_by_role("button", name=f"显示全部 {total} 个").click()
    assert first.locator(".hits > li:visible").count() == total
    # A snippet is one line: local dates, no raw ids.
    text = page.locator("#main").inner_text()
    assert "2026-10-0" not in text and "T10:00:00Z" not in text
    assert "codex:01a1a594" not in text and "7152b30ab162a51eeae8672cea167403" not in text
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    _shot(page, f"auto-search-{width}.png")


def test_a_skill_page_prints_only_what_is_known(reader):  # noqa: F811
    open_page, _ = reader
    page = open_page("", width=1440)
    page.evaluate("""() => {
      REM.records.push({ path: 'skills/catalog/quill-brief.md', title: 'quill-brief', category: 'skills', written: true,
        text: '# quill-brief\\n\\n## What it does\\nQuill weekly brief (user)\\n\\n## When to use\\n未知 — 尚未调查\\n\\n'
          + '## Inputs\\n未知 — 尚未调查\\n\\n## Outputs\\n未知 — 尚未调查\\n\\n## Current status\\n未知 — 尚未核实\\n\\n## Where it lives\\n/Users/someone/.claude/skills/quill-brief/SKILL.md\\n\\n## Sources\\n' });
      KNOWN.clear(); FACTS.clear();
    }""", isolated_context=False)
    page.evaluate("location.hash = '#r=skills%2Fcatalog%2Fquill-brief.md'", isolated_context=False)
    main = page.locator("#main")
    main.locator("h1").first.wait_for()
    text = main.inner_text()
    assert text.count("未知 — 尚未") == 0 and text.count("not investigated yet") <= 1  # never one placeholder per section
    assert "Quill weekly brief" in main.locator("h1").first.inner_text()
    assert "0 个来源" not in text and "0 sources" not in text
    assert "/Users/someone" not in text and "SKILL.md" in text
    assert page.locator("#main [title*='/Users/someone/.claude/skills/quill-brief/SKILL.md']").count() >= 1
    _shot(page, "auto-skill-1440.png")


def test_changes_speak_in_the_readers_words_and_about_the_notebook(reader):  # noqa: F811
    open_page, _ = reader
    page = open_page("view=changes", width=1440)
    page.evaluate("""() => { REM.logs = []; REM.brief_logs = []; render(); }""", isolated_context=False)
    text = page.locator("#main").inner_text()
    assert "已核实" not in text and "verified" not in text.lower()
    assert "昨夜没有页面内容改变" in text
    _shot(page, "auto-changes-empty-1440.png")


def test_a_change_shows_dates_in_the_readers_form(reader):  # noqa: F811
    open_page, _ = reader
    page = open_page("view=changes", width=1440)
    page.evaluate("""() => {
      const r = REM.records.find(r => r.category === 'people');
      REM.first_run_at = '2026-09-01T00:00:00Z';
      REM.logs = [{ phase: 'investigate', started_at: '2026-10-01T02:00:00Z', finished_at: '2026-10-01T03:00:00Z', changed: [],
        claim_changes: [{ record: r.path, kind: 'revised', field: 'Last contact', before: 'Met on 2026-09-02T10:00:00Z', after: 'Met again on 2026-09-30T08:00:00Z', sources: ['1'] }] }];
      render();
    }""", isolated_context=False)
    text = page.locator("#main").inner_text()
    assert page.locator(".claim-card").count() == 1
    assert "T10:00:00Z" not in text and "2026-09-30" not in text

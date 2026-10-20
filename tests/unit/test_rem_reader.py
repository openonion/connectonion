"""The HTML reader is disposable presentation over the notebook, never a second store."""

import json
import os
import re
import shutil
import subprocess

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import TEMPLATE, contact_candidates, open_reader, reader_path, render, write_reader

HOSTILE = "# Alice\n\nSaid: <script>alert(1)</script> and </script><img src=x onerror=alert(2)>\n"


def _run_reader_js(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed; it runs the reader's JavaScript")
    privacy = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0)
                        for name in ["privatePassages", "unlabelled", "hasPrivacy"])
    script = privacy + "\n" + script
    # stdin, not -e: Linux caps one argument at 128 KB and the template is larger.
    script = "const UI = {en: {}}; let uiLanguage = 'en';\n" + re.search(r"function t\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + re.search(r"function uiLocale\(.*?\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + script
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_this_week_project_rows_strip_the_now_label():
    page = TEMPLATE.read_text(encoding="utf-8")
    parsing = page[page.index("const UNKNOWN_LINE ="):page.index("function mappedContact(")]
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["splitTrailers", "plainLine", "displayLine", "summaryLine"])
    week = page[page.index("  // This week: what"):page.index('  const processing = el("details"')]
    script = "\n".join([
        parsing, functions,
        'const youify = text => text;',
        'const el = (tag, attrs, children = []) => ({tag, ...attrs, children});',
        'const shortDate = day => day, moon = () => null, href = r => r.path;',
        'const singular = () => "project", sectionHead = text => ({text});',
        'let r; const weekChanges = () => [{r, day: "2026-10-16"}];',
        'const rows = [], main = {appendChild: node => rows.push(node)};',
        'const updatedMarker = () => null;',
        'for (const [i, line] of ["Now: waiting on review", "**Now:** waiting on review"].entries()) {',
        'r = {path: `projects/pilot-${i}.md`, title: "Pilot", category: "projects",',
        'text: "# Pilot\\n\\n## Insight\\n- " + line};',
        week, '}', 'console.log(JSON.stringify(rows));',
    ])
    rows = _run_reader_js(script)
    for details in rows:
        week_list = details["children"][1]
        summary = next(child["text"] for child in week_list["children"][0]["children"][2]["children"]
                       if child and child.get("class") == "s")
        assert summary == "waiting on review"


def test_statement_capitalisation_preserves_code_and_paths():
    page = TEMPLATE.read_text(encoding="utf-8")
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["capFirst", "memoryStatement", "newestStanding", "plainLine", "listItems"])
    cases = [
        ("origin/main is ahead", "origin/main is ahead"),
        ("`co rem` runs nightly", "`co rem` runs nightly"),
        ("src/app.py fails", "src/app.py fails"),
        ("waiting on review", "Waiting on review"),
        ("iOS builds pass", "iOS builds pass"),
        ("camelCase stays", "camelCase stays"),
        *[(word + " is pending", word + " is pending")
          for word in [r"src\app", "app.py", "task_id", "a`b", "user@example.com", "ref:main", "issue#2", "v2"]],
        ("équipe ready", "Équipe ready"),
        ("", ""),
    ]
    script = "\n".join([
        functions, 'const REM = {owner: "people/owner.md"}, youify = text => text;',
        'const known = r => ({summary: ""});',
        'const section = (r, name) => name === "where it stands" && r.statement ? {text: "- 2026-10-16 — " + r.statement} : null;',
        'const cases = ' + json.dumps(cases) + ';',
        'console.log(JSON.stringify(cases.map(([text]) => [capFirst(text),',
        'memoryStatement({path: "projects/pilot.md", category: "projects", statement: text})])));',
    ])
    for (text, expected), (capitalised, lead) in zip(cases, _run_reader_js(script)):
        assert capitalised == expected, text
        assert lead == expected.replace("`", "").replace("#", ""), text


def test_snapshot_uses_stated_org_names_without_changing_notebook(tmp_path):
    from connectonion.rem.reader import snapshot

    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    pages = {
        "orgs/brightlane-example-1.md": "# brightlane.example\n\nBrightlane's legal identity is recorded.\n",
        "orgs/connectonion-com-2.md": "# connectonion.com\n\nAn agent framework.\n",
        "orgs/harbourpost-example-3.md": "# harbourpost.example\n\nNo name stated.\n\n## Sources\n- HarbourPost archived mail\n",
        "orgs/stonefield-example-4.md": "# stonefield.example\n\nStone Field manages properties.\n",
        "orgs/named.md": "# An existing title\n\nConnectOnion operates here.\n",
        "projects/domain.md": "# brightlane.example\n\nBrightlane operates here.\n",
        "people/alice.md": "# Alice\n\n## Facts\n- Company: [ConnectOnion](../orgs/connectonion-com-2.md) [3]\n",
        "people/bob.md": "# Bob\n\n- Company: [An older name](../orgs/brightlane-example-1.md) [1]\n",
    }
    for path, text in pages.items():
        notebook.write(path, text)
    before = {p.relative_to(tmp_path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in tmp_path.rglob("*") if p.is_file()}

    records = {r["path"]: r for r in snapshot(tmp_path)["records"]}
    for path, name, domain in [("orgs/brightlane-example-1.md", "Brightlane", "brightlane.example"),
                               ("orgs/connectonion-com-2.md", "ConnectOnion", "connectonion.com"),
                               ("orgs/stonefield-example-4.md", "Stone Field", "stonefield.example")]:
        assert records[path]["title"] == name
        assert records[path]["domain"] == domain
        assert records[path]["text"] == pages[path]
    assert records["orgs/harbourpost-example-3.md"]["title"] == "harbourpost.example"
    assert "domain" not in records["orgs/harbourpost-example-3.md"]
    assert records["orgs/named.md"]["title"] == "An existing title"
    assert "domain" not in records["orgs/named.md"]
    assert records["projects/domain.md"]["title"] == "brightlane.example"
    assert "domain" not in records["projects/domain.md"]
    assert before == {p.relative_to(tmp_path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("domain, text, expected", [
    ("stonefield.example", "Stone Field manages properties.", "Stone Field"),
    ("connectonion.com", "Connectonion began. ConnectOnion grew. ConnectOnion ships.", "ConnectOnion"),
    ("brightlane.example", "Brightlane’s legal identity.", "Brightlane"),
    ("onetwothreefourfive.com", "One Two Three Four Five operates here.", ""),
    ("stonefield.example", "Stone and Field are separate words.", ""),
    ("brightlane.example", "brightlane is lowercase.", ""),
    ("brightlane.example", "No name.\n\n## Sources\nBrightlane is only a source.\n\n## History\nNothing new.", ""),
])
def test_org_prose_name_matches_capitalised_runs_and_most_frequent_spelling(domain, text, expected):
    from connectonion.rem.reader import _org_name

    assert _org_name(domain, f"# {domain}\n\n{text}\n") == expected


def test_org_company_name_uses_the_most_common_linked_company_fact():
    from connectonion.rem.reader import _org_company_name

    values = ["Older name", "connectonion.com", "connectonion.com", "ConnectOnion", "ConnectOnion"]
    records = [{"path": f"people/{i}.md", "category": "people",
                "text": f"# Person {i}\n\n- Company: [{value}](../orgs/co.md) [3]\n"}
               for i, value in enumerate(values)]
    assert _org_company_name("orgs/co.md", records) == "ConnectOnion"
    assert _org_company_name("orgs/other.md", records) == ""


@pytest.mark.parametrize("protocol", ["file:", "about:"])
def test_copy_path_and_reopen_command_keep_the_notebook_root(tmp_path, protocol):
    root = tmp_path / "owner's notebook"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice\n")
    page = render(root)
    data = json.loads(re.search(r"const REM = (.*);", page).group(1))
    record = next(r for r in data["records"] if r["path"] == "people/alice.md")
    # Execute the generated handlers with only the clipboard and footer DOM stubbed.
    command = re.search(r"function remCommand\(args\).*", page).group(0)
    copy = re.search(r"pathBtn.onclick = .*", page).group(0)
    footer = next(line for line in page.splitlines() if "settings.appendChild" in line and "re-renders" in line)
    script = "\n".join([
        "const REM = " + json.dumps(data) + "; const r = " + json.dumps(record) + ";",
        "const location = {protocol: " + json.dumps(protocol) + "};",
        "const result = {}, pathBtn = {};",
        "const copyToClipboard = path => result.path = path;",
        "const el = (tag, attrs) => attrs.text;",
        "const settings = {appendChild: text => result.footer = text};",
        command, copy, footer, "pathBtn.onclick(); console.log(JSON.stringify(result));",
    ])
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed; it runs the reader's JavaScript")
    privacy = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0)
                        for name in ["privatePassages", "unlabelled", "hasPrivacy"])
    script = privacy + "\n" + script
    # stdin, not -e: Linux caps one argument at 128 KB and the template is larger.
    script = "const UI = {en: {}}; let uiLanguage = 'en';\n" + re.search(r"function t\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + re.search(r"function uiLocale\(.*?\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + script
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    quoted_root = "'" + str(root).replace("'", "'\\''") + "'"
    assert json.loads(result.stdout) == {
        "path": str(root / record["path"]),
        "footer": "Reload for latest" if protocol == "about:" else f"co rem --root {quoted_root} open re-renders",
    }


def test_render_embeds_records_and_neutralizes_markup(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).write("people/alice.md", HOSTILE)
    Notebook(tmp_path).write("decisions/markdown.md", "# Markdown over a database\n\nSee [Alice](../people/alice.md).")
    page = render(tmp_path)
    assert "people/alice.md" in page and "decisions/markdown.md" in page
    # Note text reaches the page only as JSON data; no raw tag from a note may appear as markup.
    assert "<script>alert(1)" not in page
    assert "<img src=x" not in page
    assert page.count("</script>") == page.count("<script")
    assert "as_of" in page


def test_render_does_not_export_uncited_session_window_text(tmp_path):
    from connectonion.rem.files import state_path, write_json

    prepare(tmp_path)
    Notebook(tmp_path).write("people/alice.md", "# Alice\n\nA short, cited page.\n")
    cache = state_path(tmp_path, "session-windows/example.json")
    write_json(cache, {"items": [{"source": "codex:example:123", "text": "private uncited session marker"}]})

    assert "private uncited session marker" not in render(tmp_path)


def test_snapshot_shows_dead_running_run_as_interrupted(tmp_path, monkeypatch):
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.reader import snapshot
    from connectonion.rem.service import run_logs, running_marker

    prepare(tmp_path)
    write_json(state_path(tmp_path, "runs/run_dead.json"), {
        "started_at": "2026-10-16T00:00:00+00:00", "outcome": "running", **running_marker()})
    monkeypatch.setattr("connectonion.rem.service._alive", lambda pid: False)

    assert snapshot(tmp_path)["logs"][0]["outcome"] == "interrupted"
    assert run_logs(tmp_path)[0]["outcome"] == "running"


def test_reader_lists_unreviewed_mail_contacts_without_making_empty_pages(tmp_path):
    from connectonion.rem.files import state_path, write_json
    prepare(tmp_path)
    write_json(state_path(tmp_path, "map.json"), {
        "all_history": True, "people": [],
        "without_page": [{"address": "leah@example.org", "name": "Leah Bell", "mails": 1,
                          "sent": 1, "received": 0, "last": "1998-06-01", "subject": "private subject"}],
        "errors": [{"source": "outlook", "stage": "metadata-window", "error": "ReadTimeout"}]})
    rows, coverage = contact_candidates(tmp_path)
    assert rows == [{"name": "Leah Bell", "email": "leah@example.org", "last": "1998-06-01",
                     "mails": 1, "sent": 1, "received": 0}]
    assert coverage["incomplete"] and coverage["scope"] == "all available history since 1970"
    assert "private subject" not in render(tmp_path)
    assert Notebook(tmp_path).list("people") == []


def test_render_is_self_contained_with_no_remote_assets(tmp_path):
    page = render(tmp_path)
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', page)
    assert "<link" not in page  # styles are inline; a stylesheet would be a fetch
    assert "@import" not in page


def test_render_before_start_shows_not_started_and_creates_nothing(tmp_path):
    root = tmp_path / "rem"
    page = render(root)
    assert "Not started" in page
    assert not root.exists()


def test_write_reader_lands_outside_the_notebook_and_leaves_notes_untouched(tmp_path):
    prepare(tmp_path)
    note = tmp_path / "notes" / "idea.md"
    Notebook(tmp_path).write("notes/idea.md", "# Idea\n")
    before = sorted((p.relative_to(tmp_path).as_posix(), p.stat().st_mtime_ns)
                    for p in tmp_path.rglob("*") if p.is_file())
    page = write_reader(tmp_path)
    assert page.is_file()
    assert tmp_path not in page.parents  # rendered output is not inside the collected tree
    if os.name != "nt":
        assert oct(page.stat().st_mode & 0o777) == "0o600"
    after = sorted((p.relative_to(tmp_path).as_posix(), p.stat().st_mtime_ns)
                   for p in tmp_path.rglob("*") if p.is_file())
    assert before == after
    assert note.read_text() == "# Idea\n"
    assert Notebook(tmp_path).list() == ["notes/idea.md"]  # the page is not a record


def test_write_reader_refuses_to_follow_a_planted_symlink(tmp_path, monkeypatch):
    """The page name is predictable, so a symlink planted there must not become a write elsewhere."""
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    try:
        os.symlink(victim, reader_path(tmp_path / "rem"))
    except OSError as error:
        if os.name == "nt" and getattr(error, "winerror", None) == 1314:
            pytest.skip("symlinks require Windows Developer Mode or elevation")
        raise
    with pytest.raises(OSError):
        write_reader(tmp_path / "rem")
    assert victim.read_text() == "keep"


def test_write_reader_replaces_its_snapshot_without_posix_only_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    root = tmp_path / "rem"
    first = write_reader(root)
    first.write_text("old snapshot")
    second = write_reader(root)
    assert second == first
    assert "old snapshot" not in second.read_text()
    assert list(tmp_path.glob("co-rem-*.html")) == [second]


def test_open_reader_launches_the_file_uri_only_when_asked(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    page = open_reader(tmp_path, launch=False)
    assert opened == []
    page = open_reader(tmp_path, launch=True)
    assert opened == [page.as_uri()]
    assert opened[0].startswith("file://")


def test_summary_values_hide_only_empty_placeholders():
    page = TEMPLATE.read_text(encoding="utf-8")
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["plainLine", "knownValue"])
    unfilled = next(line for line in page.splitlines() if line.startswith("const UNFILLED_LINE ="))
    cases = [None, "", "  ", "Unknown", "unknown", "Unknown.", "—", "Unknown — not verified.",
             "Unknown — not verified. The latest session confirms a changed owner.", "Avery Lin", 0]
    result = _run_reader_js("\n".join([functions, unfilled, "const youify = text => text;",
                                     "console.log(JSON.stringify(" + json.dumps(cases) + ".map(knownValue))); "]))
    assert result == [False] * 8 + [True] * 3


def test_empty_between_you_has_no_section_but_real_threads_remain():
    page = TEMPLATE.read_text(encoding="utf-8")
    function = re.search(r"function betweenYou\(.*?\n\}", page, re.S).group(0)
    result = _run_reader_js("\n".join([
        function, 'const threads = r => r;',
        'const el = (tag, attrs, children) => ({tag, ...attrs, children});',
        'const ledgerColumn = (r, items, dir) => ({dir, count: items.length});',
        'console.log(JSON.stringify([betweenYou({items: [], calm: "Nothing open as of 2026-10-20"}),',
        'betweenYou({items: [{dir: "mine"}], calm: ""})]));',
    ]))
    assert result[0] is None
    assert result[1]["children"][1]["children"] == [{"dir": "mine", "count": 1}, {"dir": "theirs", "count": 0}]


def test_source_focus_candidates_exclude_unreachable_controls():
    page = TEMPLATE.read_text(encoding="utf-8")
    function = re.search(r"function evidenceControls\(.*?\n\}", page, re.S).group(0)
    result = _run_reader_js("\n".join([
        function,
        'const getComputedStyle = node => ({visibility: node.visibility || "visible"});',
        'const cases = [{id: "close"}, {id: "disabled", disabled: true}, {id: "negative", tab: -1},',
        '{id: "aria-hidden", hidden: true}, {id: "hidden-ancestor", hidden: true},',
        '{id: "no-layout", rects: []}, {id: "invisible", visibility: "hidden"}, {id: "last"}];',
        'const controls = cases.map(c => ({...c, tabIndex: c.tab ?? 0, matches: () => !!c.disabled,',
        'closest: () => c.hidden ? {} : null, getClientRects: () => c.rects || [{}]}));',
        'console.log(JSON.stringify(evidenceControls({querySelectorAll: () => controls}).map(c => c.id)));',
    ]))
    assert result == ["close", "last"]


def test_reader_template_javascript_compiles():
    script = TEMPLATE.read_text(encoding="utf-8").split("<script>", 1)[1].split("</script>", 1)[0]
    assert _run_reader_js("new Function(" + json.dumps(script) + "); console.log(true);") is True


def test_project_thread_direction_requires_an_explicit_debtor():
    page = TEMPLATE.read_text(encoding="utf-8")
    functions = page[page.index('let OWING = null;'):page.index('const DIRECTION_LABEL =')]
    cases = {
        '2026-10-13: You asked to revisit a title.': 'plain',
        '2026-10-13: Requested confirmation of the plan.': 'plain',
        'Avery promised to send a draft.': 'mine',
        'The user owes Mara an answer.': 'mine',
        'Mara owes you feedback.': 'theirs',
        'Waiting on Fernhill for a test inbox; promised 2026-09-12.': 'theirs',
        'Promised a draft; owner is unclear.': 'plain',
    }
    script = '\n'.join([
        'const REM = {owner: "people/avery.md"};',
        'const byPath = () => ({title: "Avery Lin"});', functions,
        'console.log(JSON.stringify(' + json.dumps(list(cases)) + '.map(projectDirection)));',
    ])
    assert _run_reader_js(script) == list(cases.values())


def test_activity_disclosure_filters_and_refreshes_private_rows():
    page = TEMPLATE.read_text(encoding="utf-8")
    activity = page[page.index('function activityDisclosure('):page.index('\nfunction record(')]
    script = r'''
      let hidePrivate = false;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        dataset: {type: attrs['data-type']},
        classList: {contains: name => (attrs.class || '').split(' ').includes(name), toggle() {}},
        appendChild(child) { this.children.push(child); },
        append(...nodes) { this.children.push(...nodes); },
        setAttribute(key, value) { this[key] = value; },
        querySelectorAll() { return this.children; }
      });
      const document = {documentElement: {classList: {contains: () => hidePrivate}}};
      const section = () => ({text: ''});
      const historyItems = () => Array.from({length: 9}, (_, i) => ({day: '2026-09-0' + (9-i), text: String(i)}));
      const historyRowContent = text => el('p', {class: Number(text) < 2 ? 'privacy-only' : ''});
      const activityType = text => Number(text) < 7 ? 'Decision' : 'Conversation';
      const threadDate = day => day;
      const privateHistoryNotice = () => el('p', {class: 'private-history-notice'});
    ''' + activity + r'''
      const panel = activityPanel({path: 'orgs/example.md'});
      const filters = panel.children.find(n => n.class === 'activity-filters');
      const list = panel.children.find(n => n.class === 'activity-list');
      const more = panel.children.find(n => n.class === 'btn-action activity-more');
      const shown = () => list.children.filter(n => !n.hidden).length;
      const states = [[shown(), more.textContent, more.hidden]];
      more.onclick(); states.push([shown(), more.textContent, more.hidden]);
      hidePrivate = true; list.refreshActivity();
      states.push([shown(), more.textContent, more.hidden]);
      more.onclick(); states.push([shown(), more.textContent, more.hidden]);
      filters.children.find(b => b.text === 'Conversation 2').onclick();
      states.push([shown(), more.textContent, more.hidden]);
      console.log(JSON.stringify({states, noticeNext: panel.children[panel.children.indexOf(list)+1].class}));
    '''
    assert _run_reader_js(script) == {
        'states': [[5, 'Show all 9', False], [9, 'Show less', False],
                   [7, 'Show less', False], [5, 'Show all 7', False], [2, 'Show all 2', True]],
        'noticeNext': 'private-history-notice',
    }


def test_unquoted_inline_html_never_parses_a_dom():
    page = TEMPLATE.read_text(encoding="utf-8")
    function = re.search(r"function quoteSpans\(.*?\n\}", page, re.S).group(0)
    inputs = ["plain prose", "<em>formatted prose</em>", "", "a &amp; b",
              '<a href="#r=sessions%2Fexample.md">Session</a>',
              '<span class="private" data-level="personal">Labelled prose</span>',
              '<code title="a long identifier">identifier</code>']
    # No document exists in Node: even attempting to build a DOM fails this test.
    assert _run_reader_js(function + "\nconsole.log(JSON.stringify(" + json.dumps(inputs)
                          + ".map(quoteSpans)));") == inputs


def test_thread_priority_uses_only_explicit_deadlines_and_blocking_words():
    page = TEMPLATE.read_text(encoding="utf-8")
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["blockerTag", "threadAge", "dueLabel", "threadDate", "age", "daysSince"])
    cases = [
        {"text": "Please review the draft.", "since": "2026-10-17"},
        {"text": "This blocks the launch.", "since": "2026-10-17"},
        {"text": "The launch is blocked.", "since": "2026-10-17"},
        {"text": "Blocking the export.", "since": "2026-10-17"},
        {"text": "Review before we can launch.", "since": "2026-10-17"},
        {"text": "Review before lunch.", "since": "2026-10-17", "due": "2026-10-23"},
        {"text": "Unblocked already.", "since": "2026-09-01", "due": "2026-09-10"},
    ]
    result = _run_reader_js("\n".join([
        functions, 'const REM = {as_of: "2026-10-20"}, DAY_MS = 86400000;',
        'const calendarDay = text => text.slice(0, 10);',
        'const el = (tag, attrs) => attrs;',
        'console.log(JSON.stringify(' + json.dumps(cases)
        + '.map(t => ({age: threadAge(t), tag: blockerTag(t)}))));',
    ]))
    assert [row["age"] for row in result] == ["3 days"] * 5 + ["due 23 Oct", "overdue · 10 Sep"]
    assert [bool(row["tag"]) for row in result] == [False, True, True, True, True, False, False]


@pytest.mark.parametrize('languages', [['zh', 'en'], ['en', 'zh']])
def test_interface_language_prefers_supported_non_english_and_leaves_record_prose_alone(tmp_path, monkeypatch, languages):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr('connectonion.rem.languages.owner_languages', lambda root: {'languages': languages})
    page = render(build(tmp_path / 'rem', datetime(2026, 10, 1, tzinfo=timezone.utc)), local=True)
    data = json.loads(re.search(r'const REM = (.*);', page).group(1))
    interface = page[page.index('let uiLanguage ='):page.index('function setInterfaceLanguage(')]
    script = '\n'.join([
        '(function() {', 'const REM = ' + json.dumps(data) + ';', interface,
        'const original = REM.records.find(r => r.path === "people/mara-ostrowski.md").text;',
        'const labels = [t("People"), t("Between you")];',
        'uiLanguage = "en"; labels.push(t("People"));',
        'REM.your_languages = ["en", "zh"];',
        'console.log(JSON.stringify({labels, original}));', '})();',
    ])
    result = _run_reader_js(script)
    assert result['labels'] == ['人物', '我们之间', 'People']
    assert result['original'] == next(r['text'] for r in data['records'] if r['path'] == 'people/mara-ostrowski.md')


@pytest.mark.parametrize('storage', [
    "Object.defineProperty(globalThis, 'localStorage', {get() { throw Error('blocked'); }});",
    "globalThis.localStorage = {getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); }};",
    "delete globalThis.localStorage;",
])
def test_reader_preferences_survive_unavailable_or_throwing_storage(storage):
    function = re.search(r'function readerStorage\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js('\n'.join([
        function, storage,
        '(async () => { console.log(JSON.stringify([await readerStorage("co-rem-ui-language"),',
        'await readerStorage("co-rem-ui-language", "zh")])); })();',
    ]))
    assert result == [None, None]


def test_display_commands_use_short_form_only_for_the_default_notebook(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem.reader import snapshot
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    root = build(tmp_path / '.co' / 'rem', datetime(2026, 10, 1, tzinfo=timezone.utc))
    data = snapshot(root)
    assert data['default_root'] is True
    function = re.search(r'function remCommand\(args\).*', TEMPLATE.read_text()).group(0)
    result = _run_reader_js('\n'.join([
        'const REM = ' + json.dumps(data) + ';', function,
        'const commands = [remCommand("sources"), remCommand("import sessions")];',
        'REM.default_root = false; REM.root = "/tmp/avery\'s notebook";',
        'commands.push(remCommand("import sessions")); console.log(JSON.stringify(commands));',
    ]))
    assert result[:2] == ['co rem sources', 'co rem import sessions']
    assert result[2] == "co rem --root '/tmp/avery'\\''s notebook' import sessions"


def test_dynamic_reader_chrome_translates_without_changing_english():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['age', 'dueLabel', 'threadDate', 'citationDate', 'chipLabel'])
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "en";', interface, functions,
        'const REM = {as_of: "2026-10-20"}, calendarDay = day => day;',
        'const daysSince = day => Number(day), citationSource = () => "", sourceId = () => "";',
        'const sourceChannel = () => "";',
        'const labels = () => [age("10"), age("1"), age("0"), citationDate({}, "99"),',
        'dueLabel({due: "2026-10-19"}), dueLabel({due: "2026-10-21"}),',
        't("Read {n} items", {n: 240}), t("Rewrote {n} pages", {n: 7}),',
        't("{n} runs", {n: 10}), t("{n} written of {m}", {n: 3, m: 6, unit: " 人"})];',
        'const en = labels(); uiLanguage = "zh"; const zh = labels();',
        'console.log(JSON.stringify({en, zh})); })();',
    ]))
    assert result['en'] == ['10 days', '1 day', 'today', 'source 99', 'overdue · 19 Oct', 'due 21 Oct',
                            'Read 240 items', 'Rewrote 7 pages', '10 runs', '3 written of 6']
    assert result['zh'] == ['10 天', '1 天', '今天', '来源 99', '已逾期 · 10月19日', '到期 10月21日',
                            '阅读了 240 项', '改写了 7 页', '10 次运行', '已撰写 3 / 6 人']


@pytest.mark.parametrize('source', ['unbroken' * 80 + ':fixture', 'gmail:fixture', ''],
                         ids=['long-source', 'undated-mail', 'missing'])
def test_undated_quiet_citation_uses_number_instead_of_source_label(source):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['citationDay', 'citationDate'])
    result = _run_reader_js('\n'.join([
        functions, 'const REM = {source_context: {}};',
        'const citationSource = () => ' + json.dumps(source) + ', sourceId = text => text;',
        'const chipLabel = () => ' + json.dumps(source) + ';',
        'const labels = [citationDate({}, "99")];',
        'REM.source_context[' + json.dumps(source) + '] = {time: "2026-10-20"};',
        'labels.push(citationDate({}, "99")); console.log(JSON.stringify(labels));',
    ]))
    assert result == ['source 99', '20 Oct']


def test_reader_browser_evaluate_strings_compile():
    import ast
    scripts = []
    for path in sorted((TEMPLATE.parents[2] / 'tests/e2e/cli').glob('test_rem*reader*browser.py')):
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'evaluate' and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                scripts.append({'file': path.name, 'line': node.lineno, 'source': node.args[0].value})
    assert scripts
    script = '\n'.join([
        'const vm = require("node:vm"), scripts = ' + json.dumps(scripts) + ';',
        'for (const script of scripts) new vm.Script(script.source, {filename: script.file + ":" + script.line});',
        'console.log(JSON.stringify(scripts.length));',
    ])
    assert _run_reader_js(script) == len(scripts)


@pytest.mark.parametrize('languages,browser,expected', [
    (['en', 'zh'], 'en-AU', 'zh'), (['ja', 'en', 'zh'], 'en-AU', 'zh'),
    (['en'], 'zh-CN', 'zh'), ([], 'zh-TW', 'zh'),
    (['ja', 'en'], 'ja-JP', 'en'), ([], 'en-AU', 'en'),
])
def test_reader_interface_language_default(languages, browser, expected):
    page = TEMPLATE.read_text()
    default = page[page.index('let uiLanguage ='):page.index('let morePeopleColumns =')]
    result = _run_reader_js('\n'.join([
        '(() => { const REM = {your_languages: ' + json.dumps(languages) + '};',
        'const navigator = {language: ' + json.dumps(browser) + '};', default,
        'console.log(JSON.stringify(uiLanguage)); })();',
    ]))
    assert result == expected


def test_changed_field_matches_raw_facts_before_display_formatting():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['changedValue', 'factText', 'plainLine'])
    script = '\n'.join([
        '(() => {', functions, 'const youify = value => value;',
        'const r = {path: "people/avery-lin.md"};',
        'let items; const parseFacts = () => new Map([["First contact", items]]);',
        'let memoryPass = {claims: [{record: r.path, field: "first contact",',
        'before: "2026-09-01", after: "2026-10-01"}]};',
        'const check = () => { const classes = [];',
        'const node = {textContent: "1 Oct 2026", classList: {add: value => classes.push(value)}};',
        'changedValue(node, r, "First contact"); return {classes, title: node.title}; };',
        'items = [{value: "2026-10-01", qualifier: ""}]; const date = check();',
        'items = [{value: "2026-10-02", qualifier: ""}]; const superseded = check();',
        'items = [{value: "https://example.com", qualifier: "work"}, {value: "https://example.com/pilot", qualifier: ""}];',
        'memoryPass.claims[0].after = "https://example.com (work); https://example.com/pilot";',
        'const multiple = check(); memoryPass.claims = []; const older = check();',
        'console.log(JSON.stringify({date, superseded, multiple, older})); })();',
    ])
    result = _run_reader_js(script)
    assert result['date'] == {'classes': ['changed-value'], 'title': 'Changed last night: 2026-09-01 → 2026-10-01'}
    assert result['multiple']['classes'] == ['changed-value']
    assert result['superseded'] == result['older'] == {'classes': []}


def test_update_markers_follow_latest_pass_in_the_invented_notebook(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem.reader import snapshot
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    data = snapshot(build(tmp_path / 'rem', datetime(2026, 10, 1, 12, tzinfo=timezone.utc)))
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['lastPass', 'runTime', 'sameClaim', 'updatedMarker'])
    result = _run_reader_js('\n'.join([
        '(() => { const REM = ' + json.dumps(data) + ';', functions,
        'const HOUR = 3600e3, FAILED = /^(failed|abandoned|error|refused|timeout)/i;',
        re.search(r'^const STAMP = .*$', page, re.M).group(0),
        'const byPath = path => REM.records.find(r => r.path === path);',
        'const listedRecords = () => REM.records, byActivity = () => 0, sourceName = value => value;',
        'const el = (tag, attrs, children) => ({...attrs, children});',
        'const memoryPass = lastPass();',
        'console.log(JSON.stringify({changed: memoryPass.changed.map(r => r.path).sort(),',
        'mara: updatedMarker(byPath("people/mara-ostrowski.md")),',
        'eyebrow: updatedMarker(byPath("people/mara-ostrowski.md"), true),',
        'tomas: updatedMarker(byPath("people/tomas-reyes.md"))})); })();',
    ]))
    assert result['changed'] == ['orgs/fernhill-labs.md', 'people/avery-lin.md',
                                 'people/mara-ostrowski.md', 'projects/harbour.md']
    assert result['mara'] == {'class': 'fresh-label', 'text': 'last night',
                              'title': "Updated in last night's pass"}
    assert result['eyebrow']['children'][0]['text'] == '●'
    assert result['eyebrow']['children'][1] == 'updated last night'
    assert result['tomas'] is None


def test_record_freshness_labels_translate_without_changing_english():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    labels = ['last activity', 'file updated', 'last mapped session', 'last name match',
              'archived messages', 'last night', "Updated in last night's pass"]
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "en";', interface,
        'const labels = ' + json.dumps(labels) + ';',
        'const en = labels.map(label => t(label)); uiLanguage = "zh";',
        'console.log(JSON.stringify({en, zh: labels.map(label => t(label))})); })();',
    ]))
    assert result['en'] == labels
    assert result['zh'] == ['最近动态', '文件更新于', '最近映射的会话', '最近名称匹配',
                            '条存档消息', '昨夜', '昨夜整理时更新']


def test_audited_chrome_uses_category_nouns_and_keeps_english_labels():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['categoryCount', 'usageCaption', 'refusalReason', 'sourceLabel', 'threadDate'])
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "zh";', interface, functions,
        'const REM = {source_context: {"claude-code:12345678-1234-1234-1234-123456789abc:1": {time: "2026-09-03T12:00:00Z"}}};',
        'const fmtDate = () => "10月10日";',
        'const categories = ["people", "orgs", "projects", "skills", "decisions", "principles"];',
        'const zh = categories.map(c => categoryCount(c, {written: 3, mapped: 6}, 6));',
        'const emptyCounts = categories.map(c => categoryCount(c, null, 3));',
        'const labels = [t("Waiting on you"), t("Current context"), t("daily-update"),',
        'usageCaption({count: 2, last: "2026-10-10"}),',
        'refusalReason("Changed page has no numbered evidence references"),',
        'refusalReason("Missing or duplicate citation: 22"),',
        'sourceLabel("claude-code:12345678-1234-1234-1234-123456789abc:1"), sourceLabel("claude-code:" + "a".repeat(50))];',
        'uiLanguage = "en";',
        'const en = categories.map(c => categoryCount(c, {written: 3, mapped: 6}, 6));',
        'console.log(JSON.stringify({zh, emptyCounts, labels, en, englishReason: refusalReason("Missing or duplicate citation: 22")})); })();',
    ]))
    units = ['人', '个组织', '个项目', '项', '项', '条']
    assert result['zh'] == [f'已撰写 3 / 6 {unit}' for unit in units]
    assert result['emptyCounts'] == [f'3 {unit}' for unit in units]
    assert result['en'] == ['3 written of 6'] * 6
    assert result['labels'] == ['等你处理', '当前背景', '每日更新', '2 次技能名称匹配 · 最近 10月10日 · 版本未验证',
                                '改动的页面缺少编号来源引用', '缺失或重复的引用：22', 'Claude Code 会话 · 9月3日', 'claude-code:aaaaaaaa…']
    assert result['englishReason'] == 'Missing or duplicate citation: 22'


def test_activity_translates_known_refusals_before_joining_separate_errors():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['refusalReason', 'unwritten'])
    errors = ['Missing section: Facts', 'Cited local file needs a file: source ID and SHA-256: 22',
              'Fact without a citation: Role; cite the message it came from, or write Unknown',
              'Page cites only the page itself and the coverage note; nothing about the subject was read']
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "zh";', interface, functions,
        'const run = {refusals: [{record: "people/avery-lin.md", errors: ' + json.dumps(errors) + '}]};',
        'const zh = unwritten(run)[0].why; uiLanguage = "en";',
        'console.log(JSON.stringify({zh, en: unwritten(run)[0].why})); })();',
    ]))
    assert result['en'] == '; '.join(errors)
    assert result['zh'] == ('缺少章节：Facts；引用本地文件须有 file: 来源 ID 与 SHA-256：22；'
                            '事实缺少引用：Role；请引用原消息，或填写 Unknown；'
                            '页面仅引用自身与覆盖记录，未阅读主题相关材料')


@pytest.mark.parametrize('source,dated,expected', [
    ('outlook:123456789abc:Returned client agreement.pdf', True,
     'outlook:123456789abc:Returned client agreement.pdf'),
    ('outlook:' + 'a' * 40 + ':Returned client agreement.pdf', False,
     'outlook:' + 'a' * 40 + ':Returned client agreement.pdf'),
    ('gmail:123456789abc', True, 'gmail:123456789abc'),
    ('claude-code:human-readable-session-name:1', True, 'claude-code:human-readable-session-name:1'),
    ('codex:12345678-1234-1234-1234-123456789abc:2', True, 'Codex session · 3 Sep'),
    ('claude-code:12345678-1234-1234-1234-123456789abc:2', True, 'Claude Code session · 3 Sep'),
    ('codex:12345678-1234-1234-1234-123456789abc:2', False, 'codex:12345678…:2'),
    ('file:' + 'b' * 32, True, 'file:bbbbbbbb…'),
    ('gmail:' + 'c' * 31, False, 'gmail:' + 'c' * 31),
])
def test_source_labels_only_shorten_opaque_segments(source, dated, expected):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['sourceLabel', 'threadDate'])
    context = {source: {'time': '2026-09-03T12:00:00Z'}} if dated else {}
    result = _run_reader_js('\n'.join([
        functions, 'const REM = {source_context: ' + json.dumps(context) + '};',
        'console.log(JSON.stringify(sourceLabel(' + json.dumps(source) + ')));',
    ]))
    assert result == expected


def test_reader_near_duplicate_obligations_keep_direction_dates_and_sources():
    page = TEMPLATE.read_text()
    functions = page[page.index('function obligationWords('):page.index('function threadCounterpart(')]
    raw = re.search(r'function rawSection\(.*?\n\}', page, re.S).group(0)
    script = r'''
      const REM = {source_context: {}}, COMMENT = /<!--[\s\S]*?-->/g, DAY_MS = 86400000;
    ''' + raw + functions + r'''
      const entry = (name, text, source = 'gmail:letter', day = '2026-09-30', dir = 'mine') => ({
        r: {path: 'people/' + name + '.md', text: '# ' + name + '\n\n## Sources\n- [1] ' + source},
        t: {text, since: day, dir}
      });
      const a = entry('mara', 'You owe a Letter of Support draft with contribution questions [1].');
      const b = entry('tomas', 'Please send a support letter draft with contribution questions [1].', 'gmail:other', '2026-10-01');
      const c = entry('ines', 'A completely reworded request [1].');
      const groups = threadGroups([a, b, c]);
      const bridge = threadGroups([a, {...a, t: {...a.t, since: '2026-10-06'}},
        {...a, t: {...a.t, since: '2026-10-12'}}]);
      REM.source_context = {'gmail:one': {source: 'gmail', thread: 'fixture-thread'},
        'gmail:two': {source: 'gmail', thread: 'fixture-thread'}};
      const evidence = item => obligationEvidence(item);
      console.log(JSON.stringify({
        grouped: groups.map(group => group.map(entry => entry.r.path)),
        bridge: bridge.map(group => group.length),
        sharedThread: sameObligation(evidence(entry('mara', 'Travel itinerary [1].', 'gmail:one')),
          evidence(entry('ines', 'Please check invoices [1].', 'gmail:two'))),
        opposite: sameObligation(evidence(a), evidence({...b, t: {...b.t, dir: 'theirs'}})),
        older: sameObligation(evidence(a), evidence({...b, t: {...b.t, since: '2026-10-08'}})),
        quoteOnly: sameObligation(evidence(entry('mara', 'Invoice audit “send the details” [1].')),
          evidence(entry('tomas', 'Travel itinerary “send the details” [1].', 'gmail:travel'))),
        unresolved: sameObligation(evidence(entry('mara', 'First request [9].')),
          evidence(entry('tomas', 'Unrelated invoice [9].')))
      }));
    '''
    result = _run_reader_js(script)
    assert result == {'grouped': [['people/mara.md', 'people/tomas.md'], ['people/ines.md']],
                      'bridge': [2, 1], 'sharedThread': False,
                      'opposite': False, 'older': False, 'quoteOnly': False, 'unresolved': False}


def test_reader_language_swap_reuses_parsing_and_restores_original():
    page = TEMPLATE.read_text()
    swap = re.search(r'function swapLanguage\(.*?\n\}', page, re.S).group(0)
    parsing = page[page.index('const UNKNOWN_LINE ='):page.index('function mappedContact(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['splitTrailers', 'plainLine'])
    script = parsing + functions + swap + r'''
      const FACTS = new Map(), SESSION_TEXT = new Map(), youify = text => text;
      const r = {path: 'people/avery-lin.md', category: 'people', title: 'Avery Lin',
        text: '# Avery Lin\n\nAn original lead [1].',
        translations: {zh: '# Avery Lin\n\n中文摘要 [1].'}};
      const summaries = [known(r).summary];
      swapLanguage(r, 'zh'); summaries.push(known(r).summary);
      swapLanguage(r, ''); summaries.push(known(r).summary);
      swapLanguage(r, 'ja'); summaries.push(known(r).summary);
      console.log(JSON.stringify(summaries));
    '''
    assert _run_reader_js(script) == ['An original lead.', '中文摘要.', 'An original lead.', 'An original lead.']


def test_reader_skills_group_and_search_reveals_rare_matches():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['skillGroups', 'skillUsage'])
    script = r'''
      const el = (tag, attrs = {}, children = []) => ({tag, value: "", ...attrs, children,
        appendChild(child) { this.children.push(child); },
        append(...nodes) { this.children.push(...nodes); },
        set textContent(value) { this.children = []; }
      });
      const label = () => 'Skills', row = r => ({text: r.title});
      const daysSince = day => (new Date('2026-10-01') - new Date(day)) / 86400000;
    ''' + functions + r'''
      const names = ['weekly-brief', 'invoice-check', 'lark-mail', 'lark-doc', 'lark-calendar', 'talk-outline'];
      const items = names.map((title, i) => ({title, path: 'skills/catalog/' + title + '.md',
        text: 'Invoked 3 times in the last 180 days; last on ' + (i < 2 ? '2026-09-30' : i < 5 ? '2026-08-15' : '2026-01-01')}));
      const box = skillGroups(items), find = box.children[0], content = box.children[1];
      const groups = content.children.map(n => n.tag === 'details' ? [n.children[0].text, !!n.open] :
        [n.children[0].children[0], n.children[1].children.map(row => row.text)]);
      find.value = 'talk-outline'; find.oninput();
      const searched = content.children[0];
      console.log(JSON.stringify({groups, searched: [searched.children[0].text, searched.open,
        searched.children[1].children.map(row => row.text)]}));
    '''
    assert _run_reader_js(script) == {
        'groups': [['Used in the last 30 days', ['weekly-brief', 'invoice-check']],
                   ['lark', ['lark-calendar', 'lark-doc', 'lark-mail']], ['Rarely used (1)', False]],
        'searched': ['Rarely used (1)', True, ['talk-outline']]}


def test_reader_translated_relationship_takes_precedence_over_index_prose():
    page = TEMPLATE.read_text()
    parsing = page[page.index('const UNKNOWN_LINE ='):page.index('// ---------- the sheet:')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['splitTrailers', 'swapLanguage'])
    script = parsing + functions + r'''
      const REM = {}, SESSION_TEXT = new Map(), youify = text => text;
      const r = {path: 'people/avery-lin.md', title: 'Avery Lin', category: 'people',
        index: {how_known: 'Original indexed relationship'},
        text: '# Avery Lin\n\n## Our relationship\n- An original relationship [1].',
        translations: {zh: '# Avery Lin\n\n## Our relationship\n- 中文相识经过 [1].'}};
      const values = [facts(r).how];
      swapLanguage(r, 'zh'); values.push(facts(r).how);
      swapLanguage(r, ''); values.push(facts(r).how);
      console.log(JSON.stringify(values));
    '''
    assert _run_reader_js(script) == ['Original indexed relationship', '中文相识经过.', 'Original indexed relationship']


@pytest.mark.parametrize('separator', ['；', ';', '：', ':', '—'])
def test_reader_waiting_summary_trims_chinese_separators(separator):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['morningWords', 'plainLine', 'capFirst', 'threadWords'])
    result = _run_reader_js(functions + r'''
      const inCategory = () => [], youify = text => text;
      const r = {title: 'Avery Lin'}, separator = ''' + json.dumps(separator) + r''';
      uiLanguage = 'zh';
      const chinese = morningWords('请签署试点协议' + separator + ' ，、；：— 后续安排明天讨论 [4]', r);
      uiLanguage = 'en';
      console.log(JSON.stringify([chinese,
        morningWords('Review the draft: keep this clause — and this one; discuss tomorrow [4]', r)]));
    ''')
    assert result == [{'words': '请签署试点协议', 'context': '后续安排明天讨论 [4]'},
                      {'words': 'Review the draft: keep this clause — and this one', 'context': 'discuss tomorrow [4]'}]


def test_reader_parsed_facts_cache_follows_language_override_and_text_changes():
    page = TEMPLATE.read_text()
    parsing = page[page.index('const UNKNOWN_LINE ='):page.index('// ---------- the sheet:')]
    result = _run_reader_js(parsing + r'''
      const r = {path: 'people/avery.md', text: '# Avery\n\n## Facts\n- Role: Professor [1]\n- Company: Example Lab [1]\n',
        translations: {zh: '# Avery\n\n## Facts\n- Role: 理学院教授 [1]\n- Company: 示例实验室（历史任职） [1]\n'}};
      uiLanguage = 'zh';
      const chinese = parseFacts(r), reused = parseFacts(r) === chinese;
      uiLanguage = 'en';
      const english = parseFacts(r);
      uiLanguage = 'zh';
      const restored = parseFacts(r) === chinese;
      r.readLanguage = '';
      const override = parseFacts(r) === english;
      delete r.readLanguage;
      r.translations.zh = r.translations.zh.replace('理学院教授', '副教授');
      console.log(JSON.stringify({role: chinese.get('Role'), company: chinese.get('Company'),
        english: english.get('Role')[0].value, reused, restored, override,
        updated: parseFacts(r).get('Role')[0].value}));
    ''')
    assert result == {'role': [{'value': '理学院教授', 'qualifier': '', 'citations': ['1']}],
                      'company': [{'value': '示例实验室', 'qualifier': '历史任职', 'citations': ['1']}],
                      'english': 'Professor', 'reused': True, 'restored': True, 'override': True, 'updated': '副教授'}



def test_reader_history_accepts_chinese_colon_and_preserves_citations():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['listItems', 'historyItems'])
    result = _run_reader_js(functions + r'''
      console.log(JSON.stringify(historyItems('- 2026-10-15：Theo Park 发来合同 [3].\n- 2026-10-14: 已确认 [2].')));
    ''')
    assert result == [{'day': '2026-10-15', 'end': '', 'text': 'Theo Park 发来合同 [3].'},
                      {'day': '2026-10-14', 'end': '', 'text': '已确认 [2].'}]


def test_reader_merged_threads_exclude_empty_prose_and_the_rows_own_person():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['threadEntries', 'threadGroups', 'obligationEvidence', 'obligationWords',
                                       'sameObligation', 'plainLine', 'threadWords', 'rawSection'])
    result = _run_reader_js(functions + r'''
      const REM = {owner: 'people/aaron.md'}, COMMENT = /<!--[\s\S]*?-->/g, DAY_MS = 86400000;
      const youify = text => text;
      const records = [
        {path: REM.owner, title: 'Avery Lin', category: 'people'},
        {path: 'people/mara.md', title: 'Mara Ostrowski', category: 'people'},
        {path: 'people/mara-alias.md', title: 'Mara Ostrowski', category: 'people'},
        {path: 'people/mia-chen.md', title: 'Mia Chen', category: 'people'}
      ];
      const inCategory = () => records, listedRecords = () => records;
      const threads = r => ({items: r.items});
      for (const r of records) {
        r.text = '# ' + r.title + '\n\n## Sources\n- [1] gmail:shared';
        r.items = [{text: 'You owe Mara Ostrowski a signed agreement [1].', dir: 'mine', since: '2026-10-15'}];
      }
      records[0].items = [{text: ' ', originalText: 'You owe Mara Ostrowski a signed agreement [1].', dir: 'mine', since: '2026-10-16'},
        {text: 'You owe Mia Chen [1]', dir: 'mine', since: '2026-10-15'},
        {text: '[1].', dir: 'mine', since: '2026-10-16'}];
      records[1].items.push({...records[1].items[0]});
      const merged = threadEntries();
      console.log(JSON.stringify(merged.map(({r, t, also}) => ({person: r.title, text: t.text,
        also: also.map(person => person.title)}))));
    ''')
    assert result == [{'person': 'Mara Ostrowski', 'text': 'You owe Mara Ostrowski a signed agreement [1].',
                       'also': ['Mia Chen']}]


def test_reader_recent_skills_are_capped_and_overflow_keeps_family_groups():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['skillGroups', 'skillUsage'])
    result = _run_reader_js(r'''
      const el = (tag, attrs = {}, children = []) => ({tag, value: '', ...attrs, children,
        appendChild(child) { this.children.push(child); }, append(...nodes) { this.children.push(...nodes); },
        set textContent(value) { this.children = []; }
      });
      const label = () => 'Skills', row = r => ({text: r.title});
      const daysSince = day => (new Date('2026-10-20') - new Date(day)) / 86400000;
    ''' + functions + r'''
      const items = Array.from({length: 16}, (_, i) => ({title: (i < 3 ? 'misc' : 'lark-') + i,
        path: 'skills/catalog/skill-' + i + '.md',
        text: 'Invoked 3 times in the last 180 days; last on 2026-10-' + String(i+1).padStart(2, '0')}));
      const content = skillGroups(items).children[1];
      console.log(JSON.stringify(content.children.map(group => [group.children[0].children[0],
        group.children[1].children.map(row => row.text)])));
    ''')
    assert result == [['Used in the last 30 days', ['lark-15', 'lark-14', 'lark-13', 'lark-12', 'lark-11',
                                                  'lark-10', 'lark-9', 'lark-8', 'lark-7', 'lark-6']],
                      ['lark', ['lark-3', 'lark-4', 'lark-5']], ['Other', ['misc0', 'misc1', 'misc2']]]


@pytest.mark.parametrize('marker', ['Now:', 'Now：', '现在：'])
def test_reader_insight_labels_tolerate_chinese_punctuation(marker):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['memoryStatement', 'newestStanding', 'plainLine', 'listItems', 'capFirst'])
    result = _run_reader_js(functions + r'''
      const REM = {}, youify = text => text;
      const section = (r, name) => name === 'insight' ? {text: '- ' + r.marker + ' 已完成交付 [1].'} : null;
      const known = () => ({summary: ''});
      console.log(JSON.stringify(memoryStatement({path: 'people/arthur.md', category: 'people',
        marker: ''' + json.dumps(marker) + r'''})));
    ''')
    assert result == '已完成交付.'


@pytest.mark.parametrize('separator', [': ', '：', '： ', ' — '])
def test_reader_project_standing_tolerates_date_colon_without_space(separator):
    page = TEMPLATE.read_text()
    function = re.search(r'function newestStanding\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js(function + r'''
      const REM = {}, section = () => ({text: ''' + json.dumps('- 2026-10-15' + separator + '已经交付 [1].') + r'''});
      console.log(JSON.stringify(newestStanding({path: 'projects/launch.md', category: 'projects'})));
    ''')
    assert result == '已经交付 [1].'


@pytest.mark.parametrize('text,expected', [
    ('Earlier finding! Dr. Mara gives examples, e.g. support letters',
     'Dr. Mara gives examples, e.g. support letters'),
    ('Earlier question? You owe Mara a draft: “I will send it. Please wait!” (2026-10-14)',
     'You owe Mara a draft: “I will send it. Please wait!” (2026-10-14)'),
    ('Earlier finding; A separate supported clause', 'A separate supported clause'),
    ('Version 3.5 uses example.test: keep this, and that.',
     'Version 3.5 uses example.test: keep this, and that.'),
    ('前文。需要草稿：保留说明，及细节', '需要草稿：保留说明，及细节'),
    ('前文！「请等待。稍后答复！」（日期）需要草稿', '「请等待。稍后答复！」（日期）需要草稿'),
    ('前文？需要草稿', '需要草稿'),
    ('前文；需要草稿', '需要草稿'),
])
def test_reader_evidence_boundaries_preserve_english_and_add_cjk(text, expected):
    function = re.search(r'function sentenceEnds\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + '\nconst text = ' + json.dumps(text) + r''';
      console.log(JSON.stringify(text.slice(sentenceEnds(text).at(-1)).trim()));
    ''')
    assert result == expected


@pytest.mark.parametrize('text,expected', [
    ('Mara gives examples, e.g.support letters. Send the draft: include details, please. Third sentence.',
     'Mara gives examples, e.g.support letters. Send the draft: include details, please. Third sentence.'),
    ('Version 3.5 uses example.test. Next sentence. Third sentence.',
     'Version 3.5 uses example.test. Next sentence. Third sentence.'),
    ('前文。需要草稿：保留说明，及细节！第三句。', '前文。 需要草稿：保留说明，及细节！'),
    ('公开介绍。秘密信息[personal]。公开结尾。', '公开介绍。 秘密信息[personal]。公开结尾。'),
])
def test_reader_person_lead_keeps_english_punctuation_and_private_passages(text, expected):
    function = re.search(r'function personLead\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const section = () => null, listItems = () => [], known = () => ({intro: ''' + json.dumps(text) + r'''});
      const el = (tag, attrs) => attrs.html, privateFallback = node => node, inline = text => text;
      console.log(JSON.stringify(personLead({path: 'people/mara.md'})));
    ''')
    assert result == expected


@pytest.mark.parametrize('punctuation', ['.', '!', '?', ';', ':', ',', '。', '！', '？', '；', '：', '，'])
@pytest.mark.parametrize('brackets,space', [('[]', ' '), ('[]', ''), ('［］', ' '), ('［］', '')])
def test_reader_privacy_passages_keep_chinese_tags_with_their_words(punctuation, brackets, space):
    label = brackets[0] + 'personal' + brackets[1]
    secret = '私密日期' + space + label + ' [13]' + punctuation
    text = '公开介绍。' + secret + '用户还需进行秘密后续联系' + space + label + '。公开结尾。'
    result = _run_reader_js('const text = ' + json.dumps(text) + r''';
      const passages = [];
      const publicText = privatePassages(text, (passage, level) => { passages.push([passage, level]); return ''; });
      console.log(JSON.stringify({passages, publicText, labelled: hasPrivacy(text)}));
    ''')
    assert result['publicText'] == '公开介绍。公开结尾。'
    assert len(result['passages']) == 2
    assert all(level == 'personal' for passage, level in result['passages'])
    assert result['labelled']


def test_reader_privacy_plain_summaries_preserve_public_words_links_and_inline_code():
    page = TEMPLATE.read_text()
    plain = re.search(r'function plainLine\(.*?\n\}', page, re.S).group(0)
    text = ('公开介绍。秘密文件 `case.txt` 和 [同事](people/secret.name.md)[sensitive] [1]。'
            '秘密日期。 [personal] [13]用户秘密后续联系[personal]。公开结尾。')
    result = _run_reader_js(plain + '\nconst youify = text => text;\nconst text = ' + json.dumps(text) + r''';
      console.log(JSON.stringify({plain: plainLine(text), original: plainLine(text, true),
        stripped: unlabelled(text)}));
    ''')
    assert result['plain'] == result['stripped'] == '公开介绍。公开结尾。'
    assert '[personal]' in result['original'] and '秘密文件' in result['original']


@pytest.mark.parametrize('secret', [
    '秘密的报价是3.5万元[personal]。',
    '“秘密一。秘密二”[personal]。',
    '「秘密一！秘密二？」［sensitive］。',
    '"秘密一。秘密二"[personal]。',
    '秘密网址https://secret.example/path[personal]。',
    '秘密地址secret@example.test[sensitive]。',
    '秘密资料 [同事](people/secret.name.md) 和 `case.txt`[personal]。',
])
def test_reader_privacy_does_not_split_quotes_decimals_or_addresses(secret):
    text = '公开介绍。' + secret + '公开结尾。'
    result = _run_reader_js('const text = ' + json.dumps(text) + r''';
      const passages = [];
      const publicText = privatePassages(text, passage => { passages.push(passage); return ''; });
      console.log(JSON.stringify({publicText, passages}));
    ''')
    assert result['publicText'] == '公开介绍。公开结尾。'
    assert result['passages'] == [secret]


def test_reader_session_search_removes_labelled_passages_before_indexing_and_truncating():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['sessionText', 'sessionExcerpt'])
    result = _run_reader_js(functions + r'''
      const SESSION_TEXT = new Map();
      const r = {path: 'sessions/fixture.md', title: 'Public session',
        session_summary: '公开摘要。秘密摘要[personal]。',
        text: '## What you typed\n公开问题。秘密问题［personal］。\n## Final reply\n秘密答复[sensitive]。公开答复。'};
      console.log(JSON.stringify({text: sessionText(r), excerpt: sessionExcerpt(r, ['秘密'])}));
    ''')
    assert '秘密' not in json.dumps(result, ensure_ascii=False)
    assert result['text']['you'] == '公开问题。'
    assert result['text']['agent'] == '公开答复。'


@pytest.mark.parametrize('secret', [
    '"秘密引语。秘密后半句"[personal]。',
    '“秘密引语！秘密后半句”［sensitive］。',
    '秘密的报价是3.5万元[personal]。',
    '秘密地址secret@example.test[sensitive]。',
    '秘密条件 & 更多条件[personal]。',
])
def test_reader_inline_privacy_wraps_the_full_passage_after_html_escaping(secret):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['esc', 'inline'])
    html = _run_reader_js(functions + r'''
      const youify = text => text, quoteSpans = text => text,
        uncertainCitations = text => text, tetherCitations = text => text;
      console.log(JSON.stringify(inline('公开介绍。' + ''' + json.dumps(secret) + r''' + '公开结尾。', 'fixture.md')));
    ''')
    assert html.count('class="private"') == 1
    assert html.startswith('公开介绍。<span class="private"')
    assert html.endswith('</span>公开结尾。')
    assert not re.search(r'[\[［](personal|sensitive)[\]］]', html)
    from xml.etree.ElementTree import fromstring
    root = fromstring('<p>' + html + '</p>')
    assert len(root) == 1 and root[0].get('class') == 'private'
    assert root.text + root[0].tail == '公开介绍。公开结尾。'


def test_reader_classifies_a_full_session_reply_before_truncating_its_preview():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['sessionFinalReply', 'sessionQuote'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children, appendChild() {}});
      const sessionUnquote = text => text, sessionSection = r => r;
      const sessionButton = () => ({});
      const full = '秘密'.repeat(700) + '［personal］。';
      const result = sessionFinalReply(full);
      console.log(JSON.stringify(result.children[1]));
    ''')
    assert result['class'] == 'session-quote private'
    assert len(result['textContent']) == 601
    assert result['sessionFullText'].endswith('［personal］。')


def test_written_thread_dates_and_evidence_backed_request_groups():
    page = TEMPLATE.read_text()
    names = ['writtenDatePattern', 'writtenDates', 'threads', 'listItems', 'isCalm', 'direction', 'projectDirection', 'owing', 'rawSection',
             'threadEntries', 'obligationWords', 'obligationEvidence', 'sameObligation', 'threadGroups']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + r'''
      const REM = {as_of: '2026-10-20T12:00:00Z', owner: 'people/avery-lin.md'}, DAY_MS = 86400000;
      const COMMENT = /<!--[\s\S]*?-->/g, calendarDay = value => value.slice(0, 10), daysSince = () => 0;
      let OWING = null;
      const byPath = () => ({title: 'Avery Lin'}), plainLine = text => text, threadWords = text => text;
      let records = [];
      const listedRecords = () => records;
      const entry = (path, text, n = 4, source = 'outlook:aa11bb22cc33') => ({
        path, title: path.startsWith('people') ? 'Theo Park' : 'Northgate University',
        category: path.split('/')[0], text: '# Page\n\n## Open threads\n- ' + text + '\n\n## Sources\n- [' + n + '] ' + source
      });
      records = [entry('people/theo-park.md', 'T3 capstone agreement: Theo asks the user to fill in the collaborator details, sign the execution section and reply all by 2026-10-23 [15][16].', 15),
        entry('orgs/northgate-university.md', 'Northgate asked the user to complete and sign the capstone agreement by 23 October 2026. [32][33]', 32)];
      const a = threadEntries().map(({t, also}) => ({due: t.due, copies: also.length}));
      records = [entry('people/theo-park.md', 'Theo — send the meeting link the user requested on 2026-09-03 [4].'),
        entry('orgs/northgate-university.md', 'The user asked Theo to send a Meet link on Sep 3 [4].'),
        entry('projects/harbour.md', 'The user requested a meeting link on Sept 3; whether it was sent is unknown [4].')];
      const b = threadEntries().map(({t, also}) => ({since: t.since, copies: also.length}));
      records = [entry('orgs/northgate-university.md', 'Mia Chen requested written approval to upload client code to LLMs for planning; no approval is supplied. [43]', 43),
        entry('people/mia-chen.md', 'The team, through Mia Chen, said on 2026-10-17 that written approval is required before uploading client code to LLMs; the user owes the team a decision [2].', 2)];
      const c = threadEntries().map(({r, t, also}) => ({path: r.path, dir: t.dir, copies: also.length}));
      records = [entry('people/theo-park.md', 'Theo Park — sign the agreement by 23 Oct [4].'),
        entry('orgs/northgate-university.md', 'Theo Park — send the invoice for September by 23 Oct [4].')];
      REM.records = [...records, {title: 'Theo Park', category: 'people'}];
      const negative = threadEntries().length;
      records = [entry('people/theo-park.md', 'Theo Park promised on 2026-08-31 to send the first work-package draft covering milestones, staffing, dependencies, delivery, scope and costs [4].'),
        entry('orgs/northgate-university.md', 'Northgate University promised a standalone Work Package draft on 2026-08-31 detailing research objectives, methods, resources, evaluation and acceptance [4].')];
      REM.records = records;
      const evidence = records.map(r => obligationEvidence({r, t: threads(r).items[0]}));
      const overlap = [...evidence[0].words].filter(word => evidence[1].words.has(word)).length;
      const coefficient = overlap / Math.min(...evidence.map(item => item.words.size));
      const workPackage = threadEntries().map(({t, also}) => ({since: t.since, copies: also.length}));
      const undated = sameObligation({...evidence[0], day: ''}, {...evidence[1], day: ''});
      const crossDirection = sameObligation({...evidence[0], dir: 'plain'}, {...evidence[1], dir: 'mine'});
      records = [entry('people/theo-park.md', 'You owe Theo Park a Harbour sprint budget forecast covering staffing allocations [4].'),
        entry('orgs/northgate-university.md', 'You owe Theo Park a Harbour sprint security checklist covering access permissions [4].')];
      REM.records = records;
      const undatedRequests = threadEntries().length;
      const byPerson = ['You owe a reply requested by Theo Park on Sep 3; due October 23, 2026 [4].',
        'You owe a reply requested by Theo Park, due October 23, 2026 [4].'].map(text => threads(entry('people/theo-park.md', text)).items[0].due);
      const dates = writtenDates('23 October 2026; October 23, 2026; 23 Oct; Sep 3; Sept 3; March 3');
      const due = threads(entry('people/theo-park.md', 'The user owes a review, since Sep 3, due October 23, 2026 [4].')).items[0];
      REM.as_of = '2026-01-10T12:00:00Z';
      console.log(JSON.stringify({a, b, c, negative, workPackage, coefficient, undated, crossDirection, undatedRequests,
        byPerson, dates, due: [due.since, due.due], rollover: writtenDates('Dec 20')}));
    ''')
    assert result == {
        'a': [{'due': '2026-10-23', 'copies': 1}],
        'b': [{'since': '2026-09-03', 'copies': 2}],
        'c': [{'path': 'people/mia-chen.md', 'dir': 'mine', 'copies': 1}], 'negative': 2,
        'workPackage': [{'since': '2026-08-31', 'copies': 1}], 'coefficient': 1 / 3,
        'undated': False, 'crossDirection': False, 'undatedRequests': 2,
        'dates': ['2026-10-23', '2026-10-23', '2026-10-23', '2026-09-03', '2026-09-03', '2026-03-03'],
        'due': ['2026-09-03', '2026-10-23'], 'byPerson': ['2026-10-23', '2026-10-23'], 'rollover': ['2025-12-20']}


@pytest.mark.parametrize('blocked', [False, True])
def test_done_threads_filter_today_and_counts_without_changing_record_threads(blocked):
    page = TEMPLATE.read_text()
    names = ['doneKey', 'doneStorageKey', 'isDone', 'setDone', 'shortHash', 'readerStorage', 'todayEntries', 'threadCounts']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + 'const blocked = ' + json.dumps(blocked) + ';' + r'''
      const REM = {root: '/fixture/notebook', as_of: '2026-10-20T12:00:00Z'}, DAY_MS = 86400000;
      let doneThreads = new Set(), saved = {}, rendered = 0;
      const localStorage = {setItem: (key, value) => { if (blocked) throw new Error('Storage blocked'); saved[key] = value; }};
      const render = () => rendered++, doneNotice = () => {}, window = {scrollY: 0, scrollTo() {}};
      const document = {getElementById: () => null}, calendarDay = value => value.slice(0, 10);
      const make = (text, dir, due = '', since = '') => ({r: {path: 'people/theo-park.md'}, t: {text, dir, due, since}});
      const entries = [make('You owe the signed agreement', 'mine', '2026-10-18'),
        make('You owe the draft', 'mine', '2026-10-20'), make('They owe a link', 'theirs', '', '2026-10-20'),
        make('Old thread', 'mine', '', '2026-10-19'), make('Future thread', 'mine', '2026-10-23'),
        {...make('Quiet thread', 'theirs', '2026-09-01'), t: {text: 'Quiet thread', dir: 'theirs', due: '2026-09-01', quiet: true}}];
      const threadEntries = () => entries;
      (async () => {
        const before = todayEntries(entries).length;
        setDone(entries[0], true);
        await Promise.resolve(); await Promise.resolve();
        const marked = {today: todayEntries(entries).length, counts: threadCounts(), saved: Object.values(saved).map(JSON.parse),
          sameTranslation: doneKey({...entries[0], t: {...entries[0].t, originalText: entries[0].t.text, text: '已翻译'}}) === doneKey(entries[0])};
        setDone(entries[0], false);
        await Promise.resolve(); await Promise.resolve();
        console.log(JSON.stringify({before, marked, after: todayEntries(entries).length, open: threadCounts().mine,
          stored: Object.values(saved).map(JSON.parse), rendered, records: entries.length}));
      })();
    ''')
    assert result['before'] == result['after'] == 4
    assert result['marked']['today'] == 3
    assert result['marked']['counts'] == {'mine': 3, 'theirs': 1, 'other': 0, 'quiet': 1, 'open': 4}
    assert result['marked']['saved'] == [] if blocked else len(result['marked']['saved'][0]) == 1
    assert result['marked']['sameTranslation']
    assert result['open'] == 4 and result['stored'] == ([] if blocked else [[]])
    assert result['rendered'] == 2 and result['records'] == 6


def test_thread_prompt_keeps_citations_root_and_public_text_only_in_both_languages():
    page = TEMPLATE.read_text()
    names = ['threadPrompt', 'sourceList', 'sourceId', 'listItems', 'rawSection', 'plainLine', 'obligationWords', 'obligationEvidence']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    command = re.search(r'function remCommand\(args\).*', page).group(0)
    interface = page[page.index('const UI ='):page.index('function t(')]
    result = _run_reader_js(functions + command + interface.replace('const UI =', 'const TRANSLATED_UI =') + r'''
      UI.zh = TRANSLATED_UI.zh;
      const REM = {root: '/fixture/notebook', default_root: false}, DIRECTION_LABEL = {mine: 'You owe'};
      const COMMENT = /<!--[\s\S]*?-->/g, UNKNOWN_TEXT = /^Unknown$/, youify = text => text;
      const r = {path: 'people/mara-ostrowski.md', title: 'Mara Ostrowski', text: '# Mara Ostrowski\n\n## Sources\n'
        + '- [4] outlook:e4a2c1907bd3 — addendum; observed 2026-10-11.\n'
        + '- [5] outlook:unused — unused; observed 2026-10-10.\n'
        + '- [6] Hidden source [personal]\n'};
      const entry = {r, t: {text: 'Sign the capstone agreement [4]. Secret payment [personal] [5]. Public ending. [6]',
        dir: 'mine', since: '2026-10-11', due: '2026-10-23'}, also: [{path: 'orgs/fernhill-labs.md'}]};
      const en = threadPrompt(entry);
      uiLanguage = 'zh'; entry.t.text = '请签署协议 [4]。秘密付款[personal] [5]。公开结尾。 [6]';
      console.log(JSON.stringify({en, zh: threadPrompt(entry)}));
    ''')
    en, zh = result['en'], result['zh']
    assert 'Sign the capstone agreement [4]' in en
    assert 'Page: people/mara-ostrowski.md (Mara Ostrowski)' in en
    assert "co rem --root '/fixture/notebook' show people/mara-ostrowski.md" in en
    assert 'Also on: orgs/fernhill-labs.md' in en
    assert '- [4] outlook:e4a2c1907bd3 — 2026-10-11' in en
    assert 'Cited sources:' in en and 'do not send, sign, pay or contact anyone without my approval' in en
    assert '请帮我处理' in zh and '请签署协议 [4]' in zh and '引用来源：' in zh and '未经我批准' in zh
    for prompt in (en, zh):
        assert 'Secret' not in prompt and '秘密' not in prompt
        assert 'outlook:unused' not in prompt and 'Hidden source' not in prompt
        assert "co rem --root '/fixture/notebook' search" in prompt


def test_brief_header_counts_due_soon_including_overdue_and_translates_find():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    function = re.search(r'function briefHeader\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js('(() => { let uiLanguage = "en";\n' + interface + function + r'''
      const REM = {as_of: '2026-10-20'}, calendarDay = day => day, lastPass = () => null;
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children});
      const entries = [{t: {since: '2026-10-20'}}, {t: {due: '2026-10-18'}},
        {t: {due: '2026-10-20'}}, {t: {due: '2026-10-23'}}];
      const header = briefHeader({mine: 4}, entries), noDeadline = briefHeader({mine: 1}, entries.slice(0, 1));
      const quiet = briefHeader({mine: 0}, []);
      uiLanguage = 'zh';
      const zh = briefHeader({mine: 4}, entries);
      console.log(JSON.stringify({header, noDeadline, quiet, zh, find: t('Find')}));
    })();''')
    assert result['header']['children'][0]['text'] == 'Tuesday, 20 October'
    assert result['header']['children'][1]['text'] == '3 due soon · 4 waiting on you'
    assert result['noDeadline']['children'][1]['text'] == '1 waiting on you'
    assert result['quiet']['children'][1]['text'] == 'A quiet morning'
    assert result['zh']['children'][1]['text'] == '3 项即将到期 · 4 件等你处理'
    assert result['find'] == '查找'


def test_today_includes_three_day_boundary_and_preserves_shared_page_context():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['todayEntries', 'todayThread', 'morningWords'])
    result = _run_reader_js(functions + r'''
      const REM = {as_of: '2026-10-30'}, DAY_MS = 86400000, calendarDay = day => day;
      const r = {path: 'people/theo-park.md', title: 'Theo Park'}, also = [{path: 'orgs/northgate-university.md'}];
      const make = (text, due = '', since = '', extra = {}) => ({r, also, t: {text, due, since, dir: 'mine', ...extra}});
      const entries = [make('overdue', '2026-10-29'), make('today', '2026-10-30'),
        make('three days', '2026-11-02'), make('four days', '2026-11-03'),
        make('new', '', '2026-10-30', {dir: 'theirs'}), make('old', '', '2026-10-29'),
        make('done', '2026-10-30'), make('quiet', '2026-10-01', '', {quiet: true}),
        make('undirected', '2026-10-30', '', {dir: 'plain'})];
      const isDone = entry => entry.t.text === 'done';
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children}), href = page => page.path;
      const capFirst = text => text, threadWords = text => text, plainLine = text => text;
      const privateFallback = node => node, inline = text => text, threadActions = () => null;
      const dueLabel = thread => 'due ' + thread.due, alsoOn = pages => ({also: pages});
      const quoted = make('You owe Theo a Letter of Support draft; “Please include the contribution details.” [4].', '2026-11-02');
      console.log(JSON.stringify({selected: todayEntries(entries).map(entry => entry.t.text),
        row: todayThread(entries[2]), quoted: todayThread(quoted)}));
    ''')
    assert result['selected'] == ['overdue', 'today', 'three days', 'new']
    assert result['row']['children'][3]['children'][0]['text'] == 'due 2026-11-02'
    assert result['row']['children'][4]['also'] == [{'path': 'orgs/northgate-university.md'}]
    assert result['quoted']['children'][1]['text'] == '“Please include the contribution details.”'
    assert 'Letter of Support draft' in result['quoted']['children'][2]['html']
    assert '[4]' in result['quoted']['children'][2]['html']


def test_claim_values_use_only_current_cached_facts_for_chinese_after():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['parseFacts', 'rawSection', 'factText', 'plainLine',
                                       'originalMark', 'claimValue', 'overnightChange', 'changeCard'])
    result = _run_reader_js(functions + r'''
      UI.zh = {Original: '原文', 'No Chinese translation yet; showing original': '尚无中文译文，显示原文', role: '职位'};
      const PARSED_FACTS = new Map(), COMMENT = /<!--[\s\S]*?-->/g, youify = text => text;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const r = {path: 'people/mara-ostrowski.md', title: 'Mara Ostrowski', readLanguage: '',
        text: '# Mara Ostrowski\n\n## Facts\n- Role: **Head of Partnerships** (work); Pilot lead [2]\n',
        translations: {zh: '# Mara Ostrowski\n\n## Facts\n- Role: 合作负责人（工作）; 试点负责人 [2]\n'}};
      const byPath = () => r, href = r => '#r=' + r.path;
      const claim = {record: r.path, field: 'role', before: 'Partnerships lead',
        after: 'Head of Partnerships (work); Pilot lead', sources: ['2']};
      uiLanguage = 'zh';
      const translated = overnightChange(claim), card = changeCard(claim);
      const stale = claimValue({...claim, after: 'Old role'}, r, true);
      const absent = claimValue(claim, {...r, translations: {}}, true);
      const missingField = claimValue(claim, {...r, translations: {zh: '## Facts\n- Email: mara@fernhill.example'}}, true);
      uiLanguage = 'en';
      const english = overnightChange(claim);
      console.log(JSON.stringify({translated, card, stale, absent, missingField, english}));
    ''')
    before, _, after = result['translated']['children'][2]['children']
    # The 原文 mark sits beside the struck value, not inside the strike-through.
    assert before['children'][0] == {'tag': 'del', 'text': 'Partnerships lead', 'children': []}
    assert before['children'][1] == {'tag': 'span', 'class': 'lang-status', 'text': '原文',
                                      'title': '尚无中文译文，显示原文', 'children': []}
    assert after['children'] == [{'tag': 'span', 'text': '合作负责人 (工作); 试点负责人', 'children': []}, None]
    assert result['translated']['children'][1]['text'] == ' · 职位'
    assert result['card']['children'][2]['children'][1] == before
    assert result['card']['children'][3]['children'][1] == after
    for key in ['stale', 'absent', 'missingField']:
        assert result[key]['children'][1]['text'] == '原文'
    assert result['stale']['children'][0]['text'] == 'Old role'
    assert result['absent']['children'][0]['text'] == 'Head of Partnerships (work); Pilot lead'
    en_before, _, en_after = result['english']['children'][2]['children']
    assert en_before['children'] == [{'tag': 'del', 'text': 'Partnerships lead', 'children': []}, None]
    assert en_after['children'] == [{'tag': 'span', 'text': 'Head of Partnerships (work); Pilot lead', 'children': []}, None]
    assert '原文' not in json.dumps(result['english'], ensure_ascii=False)


def test_unknown_is_localised_only_on_display_paths():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['esc', 'inline', 'plainLine', 'displayLine', 'parseFacts', 'rawSection'])
    result = _run_reader_js(functions + r'''
      UI.zh = {Unknown: '未知'};
      const PARSED_FACTS = new Map(), COMMENT = /<!--[\s\S]*?-->/g;
      const youify = text => text, quoteSpans = text => text,
        uncertainCitations = text => text, tetherCitations = text => text, shortHash = text => text;
      const text = '审阅结果：Unknown。是否已回复仍为 Unknown。';
      const r = {path: 'people/mara-ostrowski.md', text: '## Facts\n- Phone: Unknown\n'};
      uiLanguage = 'zh';
      const zh = {inline: inline(text), plain: displayLine(text), parsed: parseFacts(r).get('Phone'),
        raw: plainLine(text), code: inline('`Unknown`')};
      uiLanguage = 'en';
      console.log(JSON.stringify({zh, en: [inline(text), displayLine(text)], text, markdown: r.text}));
    ''')
    original = '审阅结果：Unknown。是否已回复仍为 Unknown。'
    assert result['zh'] == {'inline': '审阅结果：未知。是否已回复仍为 未知。',
                            'plain': '审阅结果：未知。是否已回复仍为 未知。',
                            'parsed': [], 'raw': original, 'code': '<code>Unknown</code>'}
    assert result['en'] == [original, original] and result['text'] == original
    assert result['markdown'] == '## Facts\n- Phone: Unknown\n'


def test_summary_line_strips_only_leading_insight_labels():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['plainLine', 'displayLine', 'summaryLine'])
    result = _run_reader_js(functions + r'''
      const youify = text => text;
      const labels = ['Now:', '**Now:**', '**Pattern**:', 'At stake:', 'Changed:', '现在：', '规律：', '关键所在：', '变化：'];
      console.log(JSON.stringify({stripped: labels.map(label => summaryLine('- ' + label + ' waiting on review [2]')),
        kept: summaryLine('Discuss the Pattern: now'), raw: plainLine('Now: waiting on review')}));
    ''')
    assert result['stripped'] == ['waiting on review'] * 9
    assert result['kept'] == 'Discuss the Pattern: now'
    assert result['raw'] == 'Now: waiting on review'


def test_role_summary_shows_first_and_count_with_full_title():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['roleSummary', 'plainLine'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children});
      const youify = text => text, inline = text => text, privateFallback = node => node;
      const roles = 'Head of Partnerships; Pilot lead; Research liaison';
      console.log(JSON.stringify([roleSummary(roles, ''), roleSummary('Pilot lead', ''),
        roleSummary('Public role; Secret role [sensitive]', '')]));
    ''')
    assert result[0]['title'] == 'Head of Partnerships; Pilot lead; Research liaison'
    assert result[0]['children'][0]['html'] == 'Head of Partnerships'
    assert result[0]['children'][1]['text'] == ' +2'
    assert result[0]['children'][1]['class'] == 'role-more'
    assert result[1]['children'][1] is None
    assert result[2]['title'] == ''  # No private words in a tooltip.
    assert '[sensitive]' in result[2]['children'][0]['html']


def test_category_lede_joins_counts_after_translated_punctuation():
    page = TEMPLATE.read_text()
    function = re.search(r'function ledeSeparator\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js(function + r'''
      const lines = ['这是谁？上次聊到哪了？', '已完成。', '怎么做！', 'Who is this?', 'Written.', 'Ready!', '人物'];
      uiLanguage = 'zh'; const zh = lines.map(text => text + ledeSeparator(text) + '已撰写 84 / 84 人');
      uiLanguage = 'en'; const en = ['Who is this?', 'People'].map(text => text + ledeSeparator(text) + '84 written');
      console.log(JSON.stringify({zh, en}));
    ''')
    assert result['zh'][0] == '这是谁？上次聊到哪了？ 已撰写 84 / 84 人'
    assert all(' · ' not in line for line in result['zh'][:-1])
    assert result['zh'][-1] == '人物 · 已撰写 84 / 84 人'
    assert result['en'] == ['Who is this? 84 written', 'People. 84 written']


def test_all_builtin_facts_and_sheet_labels_have_chinese_entries():
    page = TEMPLATE.read_text()
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    labels = re.search(r'const FACT_LABELS = (\{.*?\n\});', page, re.S).group(1)
    columns = re.search(r'const COLUMNS = (\{.*?\n\});', page, re.S).group(1)
    # Column rendering closures are defined but never called here.
    result = _run_reader_js('UI.zh = ' + ui + '; const FACT_LABELS = ' + labels + '; const COLUMNS = ' + columns + r''';
      const labels = [...new Set([...Object.values(FACT_LABELS).flat(),
        ...Object.values(COLUMNS).flat().map(column => column.label), 'Facts', '— not found'])];
      uiLanguage = 'zh';
      console.log(JSON.stringify(labels.filter(label => /[A-Za-z]/.test(t(label)))));
    ''')
    assert result == []


def test_changed_role_keeps_full_list_tooltip_inside_change_tooltip():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['contactLine', 'roleSummary', 'changedValue', 'factText', 'plainLine'])
    result = _run_reader_js(functions + r'''
      const role = '合作负责人; 试点负责人; 研究联络人', original = 'Head of Partnerships; Pilot lead; Research liaison';
      const r = {path: 'people/mara-ostrowski.md'};
      const facts = () => ({role}), mappedContact = () => false;
      const youify = text => text, inline = text => text, privateFallback = node => node;
      const parseFacts = () => new Map([['Role', original.split('; ').map(value => ({value, qualifier: ''}))]]);
      const memoryPass = {claims: [{record: r.path, field: 'role', before: 'Partnerships lead', after: original}]};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        childNodes: children, classList: {add() {}},
        appendChild(node) { this.children.push(node); }, append(text) { this.children.push(text); }});
      console.log(JSON.stringify(contactLine(r)));
    ''')
    changed = result['children'][0]['children'][0]
    compact_role = changed['children'][0]
    assert changed['title'].startswith('Changed last night:')
    assert compact_role['title'] == '合作负责人; 试点负责人; 研究联络人'
    assert compact_role['children'][0]['html'] == '合作负责人'
    assert compact_role['children'][1]['text'] == ' +2'
